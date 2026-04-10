import Foundation

/// Persistent configuration backed by UserDefaults.
struct Config {
    private static let defaults = UserDefaults.standard

    static var ingestURL: String {
        get { defaults.string(forKey: "ingest_url") ?? "https://http://your_url.com/api/guardian-watch/ingest" }
        set { defaults.set(newValue, forKey: "ingest_url") }
    }

    static var authToken: String {
        get { defaults.string(forKey: "auth_token") ?? "" }
        set { defaults.set(newValue, forKey: "auth_token") }
    }

    /// Minimum seconds between pushes for the same metric type.
    /// Prevents battery drain from rapid HealthKit updates.
    static var throttleInterval: TimeInterval {
        get { defaults.double(forKey: "throttle_interval").nonZero ?? 30.0 }
        set { defaults.set(newValue, forKey: "throttle_interval") }
    }

    static var isConfigured: Bool {
        !authToken.isEmpty
    }
}

private extension Double {
    var nonZero: Double? { self == 0 ? nil : self }
}
