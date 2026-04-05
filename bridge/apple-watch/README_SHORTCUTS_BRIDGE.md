# Apple Watch → Substrate Bridge via iOS Shortcuts

Minimal, battery-friendly bridge that reads User's Apple Watch biometric
data via HealthKit and POSTs it to the Guardian Watch service on the substrate.

## Architecture

```
Apple Watch → HealthKit → iOS Shortcuts (timed automation)
                                ↓
                        "Get Health Samples"
                                ↓
                        "Get Contents of URL" (POST)
                                ↓
                    Substrate /api/guardian-watch/ingest
```

## Setup

### 1. Generate Auth Token (on substrate server)

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Add the output to your `.env` file:
```
GUARDIAN_WATCH_TOKEN=<paste-token-here>
```

Restart the substrate service so it picks up the token.

### 2. Create the Shortcut

Open the **Shortcuts** app on the iPhone. Create a new shortcut named
**"Guardian Watch Push"**.

Add these actions in order:

---

#### Action 1: Find Health Samples

- **Type**: Heart Rate
- **Starting Date**: is **today**
- **Sort by**: Start Date, **Latest First**
- **Limit**: Get **1** Health Sample

> **Note**: iOS Shortcuts date filters only go down to days, not minutes.
> "Today" + "Latest First" + "Limit 1" grabs the most recent reading,
> which is what we want. The substrate marks data stale if it's >2 min old.

Save the result to a variable: `HeartRate`

#### Action 2: Find Health Samples

- **Type**: Heart Rate Variability
- **Starting Date**: is **today**
- **Sort by**: Start Date, **Latest First**
- **Limit**: Get **1** Health Sample

Save to: `HRV`

#### Action 3: Find Health Samples

- **Type**: Respiratory Rate
- **Starting Date**: is **today**
- **Sort by**: Start Date, **Latest First**
- **Limit**: Get **1** Health Sample

Save to: `RespRate`

#### Action 4: Find Health Samples

- **Type**: Blood Oxygen Saturation
- **Starting Date**: is **today**
- **Sort by**: Start Date, **Latest First**
- **Limit**: Get **1** Health Sample

Save to: `SpO2`

#### Action 5: If (HeartRate has any value)

Only POST if we actually have fresh data. Wrap the remaining actions
in this `If` block.

#### Action 6: Dictionary

Create a dictionary with:

| Key | Value |
|-----|-------|
| `heart_rate` | `HeartRate` (value) |
| `heart_rate_variability` | `HRV` (value) |
| `respiratory_rate` | `RespRate` (value) |
| `blood_oxygen` | `SpO2` (value) |
| `timestamp` | Current Date (ISO 8601) |

#### Action 7: Get Contents of URL

- **URL**: `https://<your-substrate-domain>:8284/api/guardian-watch/ingest`
- **Method**: POST
- **Headers**:
  - `Authorization`: `Bearer <your-token>`
  - `Content-Type`: `application/json`
- **Request Body**: JSON — use the Dictionary from Action 6

#### Action 8: End If

---

### 3. Create the Automation

Go to the **Automations** tab in Shortcuts.

**Create a Personal Automation:**

- **Trigger**: Time of Day → **Repeat** → Every **1 minute**
  - (iOS 17+: You can set this. On older iOS, minimum is 1 hour —
    use the "Run Shortcut every X minutes" workaround via Focus modes)
- **Action**: Run Shortcut → **Guardian Watch Push**
- **Turn OFF** "Ask Before Running"
- **Turn ON** "Notify When Run" (optional, disable after testing)

> **Battery note**: Polling every 1 minute is aggressive. For production,
> every 2-5 minutes is the sweet spot. Heart rate doesn't change that fast
> in normal conditions, and the substrate-side anomaly detection will catch
> spikes regardless of polling frequency.

### 4. Verify It Works

On the substrate server:

```bash
# Check health
curl https://<your-domain>:8284/api/guardian-watch/health

# Check if data is flowing
curl https://<your-domain>:8284/api/guardian-watch/latest

# Watch the feed live
watch -n5 'curl -s https://<your-domain>:8284/api/guardian-watch/vitals | python3 -m json.tool'
```

## Frequency Recommendations

| Scenario | Interval | Battery Impact |
|----------|----------|----------------|
| Testing | 30 sec | High — use briefly |
| Active Guardian Mode | 1 min | Moderate |
| Daily monitoring | 5 min | Low |
| Passive/sleep | 15 min | Negligible |

The Shortcut can check a "Guardian Mode Active" flag (a text file in
iCloud or a toggle in the Shortcuts app) to dynamically adjust behavior.

## Limitations of the Shortcuts Approach

1. **No true push**: Shortcuts polls on a timer. It cannot react to
   HealthKit changes in real-time like `HKObserverQuery` can.
2. **Background execution**: iOS may delay or skip automation runs
   when the phone is locked. This is unreliable for critical monitoring.
3. **No delta filtering client-side**: The substrate handles anomaly
   detection. Every poll sends whatever HealthKit has, even if unchanged.

**When to upgrade to Swift app**: If you need <30 second latency on
critical events (SpO2 drops, sudden HR spikes), real background execution,
or want to reduce cellular data by filtering client-side — build the
minimal `HKObserverQuery` Swift background app. The substrate ingest
endpoint is identical either way.

## Security Notes

- Token is sent via HTTPS only — never over HTTP
- `GUARDIAN_WATCH_TOKEN` uses constant-time comparison (hmac.compare_digest)
- Token can be rotated by updating `.env` and the Shortcut simultaneously
- If token is blank/unset on server, auth is disabled (dev mode only)
