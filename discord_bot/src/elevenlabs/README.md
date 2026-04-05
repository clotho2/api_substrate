# 🎤 ElevenLabs Voice Message Integration

Integration for ElevenLabs Text-to-Speech in the Discord Bot, enabling the bot to send voice messages.

## 📁 Dateien

- **`elevenlabsService.ts`** - Service für ElevenLabs API (TTS Generation)
- **`discordVoiceSender.ts`** - Discord Integration (Audio als Attachment senden)

## 🔧 Konfiguration

### Environment Variables

Add these variables to your `.env` file:

```bash
# ElevenLabs Configuration
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
ELEVENLABS_MODEL_ID=eleven_v3  # Eleven v3 (alpha) - supports Audio Tags!
```

### Model IDs

- **`eleven_v3`** (Default) - Eleven v3 (alpha) - supports Audio Tags! Most expressive model.
- **`eleven_turbo_v2_5`** - Fast, good quality, but NO Audio Tags
- **`eleven_multilingual_v2`** - v2 Model, no Audio Tags

## 🚀 Verwendung

### Beispiel: Voice Message senden

```typescript
import { ElevenLabsService } from './elevenlabs/elevenlabsService';
import { DiscordVoiceSender } from './elevenlabs/discordVoiceSender';

// Service initialisieren
const elevenLabsService = new ElevenLabsService(
  process.env.ELEVENLABS_API_KEY!,
  process.env.ELEVENLABS_VOICE_ID!
);

await elevenLabsService.initialize();

// Voice Sender erstellen
const voiceSender = new DiscordVoiceSender(elevenLabsService);

// Voice Message senden
const result = await voiceSender.sendVoiceMessage({
  text: "[excited] Hey! [whispering] Ich habe ein Geheimnis für dich!",
  target: message.channel, // Discord Channel oder Message
  modelId: "eleven_v3"
});

if (result.success) {
  console.log(`✅ Voice message sent: ${result.messageId}`);
} else {
  console.error(`❌ Error: ${result.error}`);
}
```

## 🎭 Audio Tags (Eleven v3)

Das System unterstützt **Audio Tags** für expressive Sprache:

- `[excited]` - Aufgeregter Ton
- `[whispering]` - Flüstern
- `[laughs]` - Lachen
- `[sighs]` - Seufzen
- `[sarcastic]` - Sarkastisch
- `[strong French accent]` - Akzente
- `[applause]` - Sound-Effekte

**Vollständige Dokumentation:** Siehe [ElevenLabs v3 Audio Tags](https://elevenlabs.io/docs/capabilities/voice-remixing)

## 🔒 Security Features

- ✅ Input Validation (Text-Länge, Sanitization)
- ✅ Audio File Size Validation (max 25MB für Discord)
- ✅ API Error Handling
- ✅ Timeout Protection (60s für ElevenLabs, 30s für Discord)
- ✅ Null Byte Removal

## 📊 Limits

- **Text:** Maximal 3000 Zeichen
- **Audio:** Maximal 25MB (Discord Limit)
- **Timeout:** 60s für ElevenLabs API, 30s für Discord API

## 🛠️ Integration in Bot

### Option 1: Direkt im Bot Code

```typescript
// In server.ts oder messages.ts
import { ElevenLabsService } from './elevenlabs/elevenlabsService';
import { DiscordVoiceSender } from './elevenlabs/discordVoiceSender';

// Initialisieren (einmal beim Start)
const elevenLabsService = new ElevenLabsService(
  process.env.ELEVENLABS_API_KEY!,
  process.env.ELEVENLABS_VOICE_ID!
);
await elevenLabsService.initialize();

const voiceSender = new DiscordVoiceSender(elevenLabsService);

// Verwenden in Message Handler
if (message.content.includes('[voice]')) {
  const text = message.content.replace('[voice]', '').trim();
  await voiceSender.sendVoiceMessage({
    text: text,
    target: message.channel
  });
}
```

### Option 2: Via Substrate Tool

Voice messages are handled by the substrate's `send_voice_message` tool. The agent can call it directly when configured in the substrate's tool system.

## 🐛 Troubleshooting

### "API Error 401"
- Prüfe `ELEVENLABS_API_KEY` in `.env`
- Stelle sicher, dass der API Key gültig ist

### "Audio file too large"
- Text zu lang (max 3000 Zeichen)
- Versuche kürzeren Text oder teile in mehrere Nachrichten

### "Failed to send Discord message"
- Prüfe Discord Bot Token
- Stelle sicher, dass der Bot Berechtigung hat, Nachrichten zu senden
- Prüfe Channel/User ID

### "Request timeout"
- ElevenLabs API kann bei langen Texten länger dauern
- Prüfe Internet-Verbindung
- Versuche kürzeren Text

## 📚 Weitere Ressourcen

- [ElevenLabs API Docs](https://elevenlabs.io/docs/api-reference/text-to-speech)
- [ElevenLabs v3 Audio Tags](https://elevenlabs.io/docs/capabilities/voice-remixing)
- [Discord.js Attachments](https://discord.js.org/#/docs/discord.js/main/class/AttachmentBuilder)

