import SwiftUI
import HealthKit

@main
struct GuardianWatchApp: App {
    @StateObject private var healthKitManager = HealthKitManager()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(healthKitManager)
                .onAppear {
                    healthKitManager.requestAuthorizationAndStart()
                }
        }
    }
}
