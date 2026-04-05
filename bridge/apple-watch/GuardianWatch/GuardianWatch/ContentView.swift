import SwiftUI

struct ContentView: View {
    @EnvironmentObject var healthKit: HealthKitManager
    @State private var endpointURL = Config.ingestURL
    @State private var authToken = Config.authToken
    @State private var throttle = String(format: "%.0f", Config.throttleInterval)

    var body: some View {
        NavigationView {
            Form {
                // Status
                Section("Status") {
                    HStack {
                        Circle()
                            .fill(healthKit.isRunning ? .green : .red)
                            .frame(width: 10, height: 10)
                        Text(healthKit.statusMessage)
                            .foregroundColor(.secondary)
                    }

                    if healthKit.isRunning {
                        LabeledContent("Pushes sent", value: "\(healthKit.pushCount)")

                        if let last = healthKit.lastPushTime {
                            LabeledContent("Last push") {
                                Text(last, style: .relative)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                }

                // Connection
                Section("Substrate Connection") {
                    TextField("Ingest URL", text: $endpointURL)
                        .textContentType(.URL)
                        .keyboardType(.URL)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                        .onSubmit { Config.ingestURL = endpointURL }

                    SecureField("Auth Token", text: $authToken)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                        .onSubmit { Config.authToken = authToken }
                }

                // Tuning
                Section("Tuning") {
                    HStack {
                        Text("Throttle (sec)")
                        Spacer()
                        TextField("30", text: $throttle)
                            .keyboardType(.numberPad)
                            .frame(width: 60)
                            .multilineTextAlignment(.trailing)
                            .onSubmit {
                                if let val = Double(throttle), val >= 5 {
                                    Config.throttleInterval = val
                                }
                            }
                    }
                    Text("Minimum seconds between pushes for the same metric. Lower = more data, more battery.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                // Save
                Section {
                    Button("Save & Reconnect") {
                        Config.ingestURL = endpointURL
                        Config.authToken = authToken
                        if let val = Double(throttle), val >= 5 {
                            Config.throttleInterval = val
                        }
                        healthKit.requestAuthorizationAndStart()
                    }
                    .frame(maxWidth: .infinity)
                }

                // Info
                Section("About") {
                    Text("Guardian Watch pushes User's Apple Watch biometrics to Agent's substrate via HealthKit observer queries. The app runs in the background — no need to keep it open.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .navigationTitle("Guardian Watch")
        }
    }
}
