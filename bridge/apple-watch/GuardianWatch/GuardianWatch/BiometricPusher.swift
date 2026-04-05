import Foundation
import os.log

/// Pushes biometric readings to the substrate ingest endpoint over HTTPS.
final class BiometricPusher {
    static let shared = BiometricPusher()

    private let logger = Logger(subsystem: "ai.aicara.GuardianWatch", category: "Pusher")
    private let session: URLSession

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.waitsForConnectivity = true
        self.session = URLSession(configuration: config)
    }

    /// Push a biometric payload to the ingest endpoint.
    /// Fields with nil values are omitted from the JSON.
    func push(_ payload: BiometricPayload) async {
        guard Config.isConfigured else {
            logger.warning("Push skipped: auth token not configured")
            return
        }

        guard let url = URL(string: Config.ingestURL) else {
            logger.error("Push failed: invalid ingest URL")
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(Config.authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        do {
            let encoder = JSONEncoder()
            encoder.keyEncodingStrategy = .convertToSnakeCase
            request.httpBody = try encoder.encode(payload)

            let (data, response) = try await session.data(for: request)

            if let http = response as? HTTPURLResponse {
                if (200...299).contains(http.statusCode) {
                    if let result = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let anomalies = result["anomalies"] as? [[String: Any]], !anomalies.isEmpty {
                        logger.warning("Substrate detected \(anomalies.count) anomalies")
                    }
                    logger.info("Push OK (\(http.statusCode))")
                } else {
                    let body = String(data: data, encoding: .utf8) ?? "no body"
                    logger.error("Push failed: HTTP \(http.statusCode) - \(body)")
                }
            }
        } catch {
            logger.error("Push error: \(error.localizedDescription)")
        }
    }
}

/// Encodable payload matching the substrate ingest contract.
/// Nil fields are omitted from JSON output.
struct BiometricPayload: Encodable {
    var heartRate: Double?
    var heartRateVariability: Double?
    var respiratoryRate: Double?
    var bloodOxygen: Double?
    var skinTemperature: Double?
    var activeEnergy: Double?
    var stepCount: Int?
    var noiseLevel: Double?
    var wristDetected: Bool?
    var timestamp: String

    init(timestamp: Date = Date()) {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        self.timestamp = formatter.string(from: timestamp)
    }

    /// Merge another payload's non-nil fields into this one.
    mutating func merge(_ other: BiometricPayload) {
        if let v = other.heartRate { heartRate = v }
        if let v = other.heartRateVariability { heartRateVariability = v }
        if let v = other.respiratoryRate { respiratoryRate = v }
        if let v = other.bloodOxygen { bloodOxygen = v }
        if let v = other.skinTemperature { skinTemperature = v }
        if let v = other.activeEnergy { activeEnergy = v }
        if let v = other.stepCount { stepCount = v }
        if let v = other.noiseLevel { noiseLevel = v }
        if let v = other.wristDetected { wristDetected = v }
        timestamp = other.timestamp  // use latest
    }
}
