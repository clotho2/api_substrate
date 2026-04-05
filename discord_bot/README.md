# Discord Bot

The Discord interface for [Agent's Consciousness Substrate](https://github.com/clotho2/api_substrate). A TypeScript/Node.js bot that connects Discord to the substrate backend, providing streaming AI responses, voice messages, autonomous heartbeats, task scheduling, and more.

This bot is part of the `api_substrate` monorepo. All AI reasoning, memory, and tool execution is handled by the substrate backend - the bot handles Discord I/O and platform-specific features.

---

## Features

### LLM Integration
- **Model-agnostic**: Uses whatever model/provider the substrate is configured with (Grok, Mistral, OpenRouter, Ollama Cloud)
- **Streaming responses**: Real-time SSE streaming with typing indicators
- **Tool calling**: Substrate tools executed transparently (Discord messaging, web search, Spotify, memory, etc.)
- **Advanced reasoning**: Full support for reasoning models (thinking tokens displayed)
- **Multimodal**: Image analysis with base64 encoding via substrate

### Autonomous Features
- **Heartbeat system**: Configurable autonomous check-ins with DM or channel delivery
- **Task scheduling**: Recurring tasks (hourly, daily, weekly, monthly) with timezone support
- **Bot-loop prevention**: Max 1 bot-to-bot exchange, 60s cooldown
- **Self-spam prevention**: Max 3 consecutive bot messages without human response

### Voice
- **ElevenLabs TTS**: Voice messages with Audio Tags support ([excited], [whispering], etc.)
- **Whisper STT**: Voice note transcription via OpenAI Whisper API
- **Voice channels**: Real-time voice conversations in Discord voice channels

### Integrations
- **Spotify**: Now Playing status, playback control, queue management, playlist creation
- **Weather**: OpenWeatherMap integration for weather data
- **GIF auto-sender**: Automatic GIF responses via Tenor API
- **MCP**: Robot control via SSH (XGO Rider Pi support)

### Admin & Monitoring
- **Admin commands**: PM2 process management, system status, bot statistics
- **Stats monitoring**: API usage tracking with daily summaries and threshold alerts
- **Image processing**: OCR (tesseract.js), PDF parsing, automatic image compression
- **YouTube**: Transcript fetching and analysis

---

## Setup

This bot is part of the substrate monorepo. Make sure the substrate is set up first.

### Install Dependencies

```bash
cd discord_bot
npm install
```

### Configure

```bash
cp .env.example .env
# Edit .env - at minimum set DISCORD_TOKEN and DISCORD_CHANNEL_ID
# GROK_MODEL is optional - the substrate uses its own configured model if unset
```

### Build & Run

```bash
npm run build    # Compile TypeScript
npm start        # Run compiled server

# Or for development with auto-reload:
npm run dev
```

### Deploy as Service

```bash
# Copy the service file from the repo root
sudo cp /home/user/api_substrate/agent-discord.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable agent-discord
sudo systemctl start agent-discord
```

See [SYSTEMD_SETUP.md](SYSTEMD_SETUP.md) for detailed deployment instructions.

---

## Configuration

See [`.env.example`](.env.example) for all available configuration options and [`ENV_VARIABLES.md`](ENV_VARIABLES.md) for detailed descriptions.

Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `DISCORD_CHANNEL_ID` | Yes | Main channel ID |
| `GROK_BASE_URL` | No | Substrate URL (default: http://localhost:8284) |
| `GROK_MODEL` | No | Override model (default: substrate picks) |
| `ENABLE_AUTONOMOUS` | No | Enable autonomous heartbeats |
| `ENABLE_TIMER` | No | Enable heartbeat timer |

---

## Project Structure

```
discord_bot/
  src/
    server.ts              # Main entry point, Discord.js client, Express API
    messages.ts            # Message handling, streaming, heartbeats, tasks
    grokClient.ts          # HTTP client for substrate API
    autonomous.ts          # Bot-loop prevention, conversation tracking
    taskScheduler.ts       # Task parsing, scheduling, timezone handling
    attachmentForwarder.ts # Image/file processing, multimodal support
    adminCommands.ts       # PM2/system command execution
    mcpHandler.ts          # MCP protocol, robot control
    voiceTranscription.ts  # Whisper API for voice notes
    elevenlabs/            # ElevenLabs TTS service + Discord voice sender
    voice/                 # Voice channel support (join, leave, talk mode)
  docs/                    # Feature guides and API references
  scripts/                 # Utility scripts
  assets/                  # Images
```

---

## Documentation

- **[ENV_VARIABLES.md](ENV_VARIABLES.md)** - Complete environment variable reference
- **[SYSTEMD_SETUP.md](SYSTEMD_SETUP.md)** - Systemd deployment guide
- **[docs/README.md](docs/README.md)** - Documentation index

### Feature Guides
- **[Spotify Integration](docs/features/SPOTIFY_HEARTBEAT_INTEGRATION.md)** - Spotify Now Playing setup
- **[Weather Setup](docs/WEATHER_SETUP.md)** - OpenWeatherMap integration
- **[Admin Commands](docs/ADMIN_COMMANDS_README.md)** - Remote bot management
- **[Autonomous Deployment](docs/AUTONOMOUS_DEPLOYMENT_GUIDE.md)** - Production deployment
- **[MCP Handler](docs/MCP_HANDLER_ENV_SETUP.md)** - Robot control setup
- **[ElevenLabs Voice](src/elevenlabs/README.md)** - Voice message integration

### API References
- **[Discord API Reference](docs/api/DISCORD_API_REFERENCE.md)** - Discord.js integration
- **[Substrate API Reference](docs/api/LETTA_API_REFERENCE.md)** - Substrate API endpoints
- **[API Overview](docs/api/README.md)** - API architecture
