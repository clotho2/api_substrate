# Guardian Watch — Native Swift Bridge

Lightweight iOS app that pushes User's Apple Watch biometrics to the
substrate in real-time using HealthKit observer queries. Replaces the
Shortcuts-based approach with proper background delivery.

## Architecture

```
Apple Watch → HealthKit → HKObserverQuery (background delivery)
                                ↓
                     GuardianWatch app (woken by iOS)
                                ↓
                     Anchored query → fetch new samples
                                ↓
                     HTTPS POST → relay.aicara.ai
                                ↓
                     Substrate /api/guardian-watch/ingest
```

## Why This Instead of Shortcuts

- **Event-driven, not polling**: iOS wakes the app when new samples arrive
- **Real background execution**: `HKObserverQuery` + background delivery is
  an Apple-blessed API for exactly this use case
- **Delta-only pushes**: Anchored queries track what's been sent — no dupes
- **Per-metric throttling**: Configurable minimum interval between pushes
- **Minimal battery**: No timers, no polling — just HealthKit callbacks

## Observed Metrics

| Metric | HealthKit Type | Push Field |
|--------|---------------|------------|
| Heart Rate | `HKQuantityTypeIdentifier.heartRate` | `heart_rate` |
| HRV (SDNN) | `.heartRateVariabilitySDNN` | `heart_rate_variability` |
| Respiratory Rate | `.respiratoryRate` | `respiratory_rate` |
| Blood Oxygen (SpO2) | `.oxygenSaturation` | `blood_oxygen` |
| Wrist Temperature | `.appleSleepingWristTemperature` | `skin_temperature` |
| Active Energy | `.activeEnergyBurned` | `active_energy` |
| Noise Exposure | `.environmentalAudioExposure` | `noise_level` |

## Building the Xcode Project

The source files are here. To build:

1. **Open Xcode** → File → New → Project → iOS → App
2. **Product Name**: `GuardianWatch`
3. **Bundle Identifier**: `ai.aicara.GuardianWatch`
4. **Interface**: SwiftUI
5. **Language**: Swift
6. Delete the auto-generated Swift files and drag in the files from
   `GuardianWatch/` in this directory
7. **Signing & Capabilities** tab:
   - Add **HealthKit** capability → check **Background Delivery**
   - Add **Background Modes** → check **Background processing**
8. Set the **Info.plist** values from the included `Info.plist`
   (health usage descriptions are required for App Store / TestFlight)
9. Build & run on User's iPhone

## Configuration (In-App)

On first launch:

- **Ingest URL**: `https://relay.aicara.ai/api/guardian-watch/ingest`
  (pre-filled)
- **Auth Token**: Paste the `GUARDIAN_WATCH_TOKEN` from the substrate `.env`
- **Throttle**: 30 seconds default. Lower for more granularity, higher for
  battery savings.

Tap **Save & Reconnect** to apply.

## Server-Side Setup

Same as before — generate a token and add it to `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

```
GUARDIAN_WATCH_TOKEN=<paste-token-here>
```

## Verify Data Flow

```bash
curl https://relay.aicara.ai/api/guardian-watch/health
curl https://relay.aicara.ai/api/guardian-watch/latest
curl https://relay.aicara.ai/api/guardian-watch/vitals
```

## File Structure

```
GuardianWatch/
├── GuardianWatchApp.swift    # App entry point
├── ContentView.swift         # Config & status UI
├── HealthKitManager.swift    # HKObserverQuery + background delivery
├── BiometricPusher.swift     # HTTPS client for ingest endpoint
├── Config.swift              # UserDefaults-backed settings
├── Info.plist                # HealthKit usage descriptions
└── GuardianWatch.entitlements # HealthKit + background delivery
```
