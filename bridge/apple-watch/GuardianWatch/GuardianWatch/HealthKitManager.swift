import Foundation
import HealthKit
import Combine
import os.log

/// Manages HealthKit authorization, observer queries, and background delivery.
/// Each metric gets an HKObserverQuery that fires when new samples arrive.
/// On notification, we anchor-query the latest sample and push the delta.
final class HealthKitManager: ObservableObject {
    private let store = HKHealthStore()
    private let logger = Logger(subsystem: "ai.aicara.GuardianWatch", category: "HealthKit")
    private let pusher = BiometricPusher.shared

    /// Last push timestamp per metric type, for throttling.
    private var lastPush: [HKQuantityTypeIdentifier: Date] = [:]
    private let lock = NSLock()

    /// Published state for UI
    @Published var isAuthorized = false
    @Published var isRunning = false
    @Published var lastPushTime: Date?
    @Published var pushCount: Int = 0
    @Published var statusMessage = "Not started"

    // MARK: - Metric Definitions

    /// All biometric types we observe, with their preferred unit.
    private struct Metric {
        let identifier: HKQuantityTypeIdentifier
        let unit: HKUnit
        let payloadKey: WritableKeyPath<BiometricPayload, Double?>
    }

    private let metrics: [Metric] = [
        Metric(identifier: .heartRate,
               unit: HKUnit.count().unitDivided(by: .minute()),
               payloadKey: \.heartRate),

        Metric(identifier: .heartRateVariabilitySDNN,
               unit: .secondUnit(with: .milli),
               payloadKey: \.heartRateVariability),

        Metric(identifier: .respiratoryRate,
               unit: HKUnit.count().unitDivided(by: .minute()),
               payloadKey: \.respiratoryRate),

        Metric(identifier: .oxygenSaturation,
               unit: .percent(),
               payloadKey: \.bloodOxygen),

        Metric(identifier: .appleSleepingWristTemperature,
               unit: .degreeCelsius(),
               payloadKey: \.skinTemperature),

        Metric(identifier: .activeEnergyBurned,
               unit: .kilocalorie(),
               payloadKey: \.activeEnergy),

        Metric(identifier: .environmentalAudioExposure,
               unit: .decibelAWeightedSoundPressureLevel(),
               payloadKey: \.noiseLevel),
    ]

    /// Anchors for each type so we only fetch new samples.
    private var anchors: [HKQuantityTypeIdentifier: HKQueryAnchor] = [:]

    // MARK: - Authorization

    func requestAuthorizationAndStart() {
        guard HKHealthStore.isHealthDataAvailable() else {
            statusMessage = "HealthKit not available on this device"
            logger.error("HealthKit not available")
            return
        }

        let readTypes: Set<HKSampleType> = Set(metrics.compactMap {
            HKQuantityType.quantityType(forIdentifier: $0.identifier)
        })

        store.requestAuthorization(toShare: nil, read: readTypes) { [weak self] success, error in
            DispatchQueue.main.async {
                if success {
                    self?.isAuthorized = true
                    self?.startObserving()
                } else {
                    self?.statusMessage = "Authorization denied: \(error?.localizedDescription ?? "unknown")"
                    self?.logger.error("Auth failed: \(error?.localizedDescription ?? "unknown")")
                }
            }
        }
    }

    // MARK: - Observer Queries

    private func startObserving() {
        for metric in metrics {
            guard let sampleType = HKQuantityType.quantityType(forIdentifier: metric.identifier) else {
                continue
            }

            // Register for background delivery — iOS wakes the app when new samples arrive
            store.enableBackgroundDelivery(for: sampleType, frequency: .immediate) { [weak self] success, error in
                if success {
                    self?.logger.info("Background delivery enabled: \(metric.identifier.rawValue)")
                } else {
                    self?.logger.error("Background delivery failed for \(metric.identifier.rawValue): \(error?.localizedDescription ?? "")")
                }
            }

            // Create observer query — fires whenever new samples of this type are saved
            let query = HKObserverQuery(sampleType: sampleType, predicate: nil) { [weak self] _, completionHandler, error in
                guard let self = self, error == nil else {
                    completionHandler()
                    return
                }

                // Throttle: skip if we pushed this metric too recently
                if self.shouldThrottle(metric.identifier) {
                    completionHandler()
                    return
                }

                // Fetch the latest sample and push it
                self.fetchLatestAndPush(metric: metric) {
                    completionHandler()
                }
            }

            store.execute(query)
            logger.info("Observer started: \(metric.identifier.rawValue)")
        }

        DispatchQueue.main.async {
            self.isRunning = true
            self.statusMessage = "Observing \(self.metrics.count) metrics"
        }
    }

    // MARK: - Fetch & Push

    private func fetchLatestAndPush(metric: Metric, completion: @escaping () -> Void) {
        guard let sampleType = HKQuantityType.quantityType(forIdentifier: metric.identifier) else {
            completion()
            return
        }

        // Anchored query: only get samples we haven't seen
        let anchor = anchors[metric.identifier]
        let query = HKAnchoredObjectQuery(
            type: sampleType,
            predicate: nil,
            anchor: anchor,
            limit: HKObjectQueryNoLimit
        ) { [weak self] _, newSamples, _, newAnchor, error in
            guard let self = self, error == nil else {
                completion()
                return
            }

            // Update anchor for next time
            if let newAnchor = newAnchor {
                self.anchors[metric.identifier] = newAnchor
            }

            // Get the most recent sample from the new batch
            guard let samples = newSamples as? [HKQuantitySample],
                  let latest = samples.last else {
                completion()
                return
            }

            let value = latest.quantity.doubleValue(for: metric.unit)

            // For SpO2, HealthKit stores as 0.0-1.0 but substrate expects 0-100
            let adjustedValue: Double
            if metric.identifier == .oxygenSaturation {
                adjustedValue = value * 100.0
            } else {
                adjustedValue = value
            }

            var payload = BiometricPayload(timestamp: latest.endDate)
            payload[keyPath: metric.payloadKey] = adjustedValue

            self.recordPush(metric.identifier)

            Task {
                await self.pusher.push(payload)
                DispatchQueue.main.async {
                    self.pushCount += 1
                    self.lastPushTime = Date()
                }
                completion()
            }
        }

        store.execute(query)
    }

    // MARK: - Throttling

    private func shouldThrottle(_ identifier: HKQuantityTypeIdentifier) -> Bool {
        lock.lock()
        defer { lock.unlock() }

        guard let last = lastPush[identifier] else { return false }
        return Date().timeIntervalSince(last) < Config.throttleInterval
    }

    private func recordPush(_ identifier: HKQuantityTypeIdentifier) {
        lock.lock()
        defer { lock.unlock() }
        lastPush[identifier] = Date()
    }
}
