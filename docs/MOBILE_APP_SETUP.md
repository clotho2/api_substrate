# Mobile App Setup, Testing & Deployment

AiCara Chat mobile app — Expo SDK 55 / React Native 0.83

The backend is already deployed at `http://your_url.com` via Cloudflare tunnel. The mobile app connects to it out of the box — no backend setup needed on your local machine.

## Prerequisites

- **Node.js** 18+ (20 LTS recommended)
- **npm** 9+ (comes with Node.js)
- **Expo Go** app on your phone ([iOS](https://apps.apple.com/app/expo-go/id982107779) / [Android](https://play.google.com/store/apps/details?id=host.exp.exponent)) — for testing only

---

## 1. Install Dependencies

```bash
cd mobile
npm install
```

---

## 2. Test with Expo Go

Expo Go lets you run the app on your phone without building a native binary. Good for quick iteration.

```bash
cd mobile
npx expo start --tunnel
```

Use `--tunnel` so the dev server is reachable from your phone on any network (not just local Wi-Fi). It will prompt to install `@expo/ngrok` on first use — say yes.

Scan the QR code:
- **iOS**: Open Camera app, point at the QR code, tap the Expo Go banner
- **Android**: Open Expo Go app, tap "Scan QR code"

The app will load and connect to `(http://your_url.com)` automatically.

> **Note:** Expo Go is for testing during development. You need a computer running `npx expo start` for it to work. For a standalone app on your phone, see Deployment below.

### What to test

- [ ] App loads, shows welcome message
- [ ] Text messages send and stream back
- [ ] Voice mode toggle works (mic icon in header)
- [ ] Voice recording captures speech and transcribes
- [ ] TTS plays Nate's responses aloud
- [ ] Conversation mode: auto-listens after Nate speaks
- [ ] Barge-in: "Interrupt Nate" stops speech
- [ ] Location appears in settings modal
- [ ] Settings: speaker mode, voice speed, volume boost work
- [ ] Markdown renders (bold, italic, links)

### Voice modes

1. **WebSocket mode** (primary) — Real-time pipeline via `/mobile/voice-stream`. Green "Real-time voice" label appears in voice mode. Requires `DEEPGRAM_API_KEY` and `CARTESIA_API_KEY` on the server.

2. **REST fallback** — Uses `/stt` and `/tts` endpoints. Activates automatically if WebSocket is unavailable.

### TypeScript check

```bash
npx tsc --noEmit
```

### Unit tests

```bash
npm test                    # Watch mode
npx jest --ci --forceExit   # Single run
```

---

## 3. Deployment

### Install EAS CLI

EAS (Expo Application Services) builds native iOS/Android binaries in the cloud — no Xcode or Android Studio needed on your machine.

```bash
npm install -g eas-cli
eas login
```

Create an account at [expo.dev](https://expo.dev) if you don't have one.

### Create eas.json

Create this file at `mobile/eas.json`:

```json
{
  "cli": {
    "version": ">= 3.0.0"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "ios": {
        "simulator": false
      }
    },
    "preview": {
      "distribution": "internal",
      "ios": {
        "simulator": false
      }
    },
    "production": {}
  },
  "submit": {
    "production": {}
  }
}
```

### Choose your deployment path

#### Path A: Internal Distribution (Best for you + friends beta testing)

This installs the app directly on registered devices. No App Store review. No Apple Developer license needed for testers — only **you** need one. Friends just tap a link to install.

```bash
cd mobile

# Register your device (and friends' devices)
eas device:create
# This generates a URL — send it to each tester. They open it on their
# iPhone, install the provisioning profile, and their device UDID is
# registered automatically.

# Build for iOS (internal distribution)
eas build --profile preview --platform ios

# Build for Android (generates an APK anyone can install)
eas build --profile preview --platform android
```

After the build completes (~10-15 min), EAS gives you an install URL. Send it to testers — they tap it on their phone and the app installs directly.

**For iOS:** Each tester's device must be registered via `eas device:create` first (Apple's ad-hoc provisioning requirement — max 100 devices per year on your Apple Developer account). After adding new devices, rebuild.

**For Android:** The APK installs on any Android phone. No device registration needed. Testers just need to allow "Install from unknown sources" when prompted.

#### Path B: TestFlight (Best for wider iOS beta testing)

TestFlight supports up to 10,000 testers without device registration. Testers install the free TestFlight app from the App Store, then you invite them via email.

```bash
cd mobile

# Build production binary
eas build --profile production --platform ios

# Submit to TestFlight
eas submit --platform ios
```

You'll be prompted to link your Apple Developer account. After submission, the build appears in [App Store Connect](https://appstoreconnect.apple.com/) under TestFlight. Add testers by email — they get an invite to install via the TestFlight app.

First submission requires Apple review (~24-48h). Subsequent builds usually go through in a few hours.

#### Path C: App Store / Play Store (Public release)

```bash
# Build production binaries
eas build --profile production --platform ios
eas build --profile production --platform android

# Submit to stores
eas submit --platform ios
eas submit --platform android
```

- **iOS**: Requires Apple Developer account ($99/year) — you have this
- **Android**: Requires Google Play Developer account ($25 one-time)

### OTA Updates (After any build is deployed)

Once the app is installed on phones (via any path above), push JavaScript-only updates instantly without rebuilding:

```bash
eas update --branch preview --message "Improve voice latency"
```

Users get the update next time they open the app. No rebuild, no store review. Only works for JS/TS changes — native dependency changes require a new build.

---

## 4. Customizing for Friends' AIs

If friends want to clone the app and point it at their own substrate server, they just need to change the backend URL before building:

**Option A:** Edit `app/config/substrate.ts` directly — change the default URL:
```typescript
export const SUBSTRATE_URL = getEnvVar(
  'EXPO_PUBLIC_SUBSTRATE_URL',
  'https://their-server.com'  // Change this
);
```

**Option B:** Create `mobile/.env` (not committed to git):
```bash
EXPO_PUBLIC_SUBSTRATE_URL=https://their-server.com
EXPO_PUBLIC_USER_ID=their_username
EXPO_PUBLIC_SESSION_ID=their_session
```

Then build with EAS as described above. Each person gets their own app binary pointing at their own server.

---

## Backend Voice Configuration (Server Side)

The mobile app connects to whatever is running at `http://your_url.com`. Voice features need these API keys in the server's `.env`:

### Minimum (REST voice)

Works with whatever STT/TTS providers are already configured (Whisper, ElevenLabs, etc.).

### Full Real-Time Voice (WebSocket pipeline)

Add to the backend `.env` on the Hetzner server:

```bash
DEEPGRAM_API_KEY=your_key_here      # Streaming STT
CARTESIA_API_KEY=your_key_here      # Low-latency streaming TTS
CARTESIA_VOICE_ID=                  # Optional, has a default male voice
```

Install the dependency and restart:

```bash
cd backend
pip install websockets>=12.0
# Then restart the substrate server
```

Confirm it's working — look for this in the server logs:
```
📱 Mobile Voice WebSocket enabled at /mobile/voice-stream
```

### Cost Reference

| Service | Cost | Notes |
|---------|------|-------|
| Deepgram Nova-3 | $0.0043/min | ~$0.26/hour of voice use |
| Cartesia Sonic | $0.042/1K chars | ~$0.50/hour of TTS |

---

## Project Structure

```
mobile/
  app/
    index.tsx              # Main chat screen
    modal.tsx              # Settings modal
    _layout.tsx            # Navigation layout
    config/
      substrate.ts         # Backend URL and endpoint config
      brand.ts             # App branding/colors
    lib/
      voiceEngine.ts       # Voice engine (WebSocket + REST fallback)
      voiceCallHandler.ts  # Incoming voice call handler
      substrateEngine.ts   # Chat API client (SSE streaming)
    components/
      AudioWaveformIcon.tsx # Animated voice waveform
  assets/                  # Icons, splash screen
  constants/               # Theme colors
  types/                   # TypeScript type definitions
  app.json                 # Expo config (permissions, plugins)
  eas.json                 # EAS Build config (create this)
  package.json             # Dependencies
  tsconfig.json            # TypeScript config
```

---

## Troubleshooting

### "Network request failed" on voice/chat

- Verify the server is running: `curl http://your_url.com/health`
- Check Cloudflare tunnel status if the server is up but app can't connect

### Voice mode not working

- Grant microphone permission when prompted on first use
- Check backend logs for STT/TTS errors
- WebSocket voice needs `DEEPGRAM_API_KEY` + `CARTESIA_API_KEY` on the server

### Expo Go: "Unable to resolve module"

```bash
npx expo install --fix    # Fix version mismatches
npx expo start --clear    # Clear bundler cache and restart
```

### Full reset

```bash
rm -rf node_modules .expo
npm install
npx expo start --tunnel --clear
```

### EAS build fails

```bash
eas build --profile preview --platform ios --clear-cache
```

Check build logs at [expo.dev/accounts/[you]/builds](https://expo.dev).
