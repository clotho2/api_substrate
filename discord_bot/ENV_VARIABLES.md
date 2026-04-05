# Environment Variables - Discord-Letta Bot

**Updated:** April 5, 2026  
**Status:** ✅ Current - Matches actual code usage (includes retry config)

Copy these to your `.env` file and fill in your values.

---

## 🔴 REQUIRED - Core Functionality

### Grok API (via api_substrate)
```bash
GROK_BASE_URL=http://localhost:8284
GROK_SESSION_ID=discord-bot
GROK_MODEL=grok-4-1-fast-reasoning           # OPTIONAL (substrate picks model if unset)
GROK_API_TIMEOUT_MS=300000
```

### Discord
```bash
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_CHANNEL_ID=your_main_channel_id
```

---

## 🟡 REQUIRED - Bot Behavior

```bash
# Message behavior
USE_SENDER_PREFIX=true  # Controls message formatting - includes sender name in context
SURFACE_ERRORS=true

# Response triggers
RESPOND_TO_DMS=true
RESPOND_TO_MENTIONS=true
RESPOND_TO_BOTS=false
RESPOND_TO_GENERIC=false

# Timezone Configuration
TIMEZONE=Europe/Berlin  # IANA timezone (e.g., America/New_York, Asia/Tokyo)
```

---

## 🟢 OPTIONAL - Advanced Features

### 🛠️ Admin Commands (Oct 16, 2025 - Remote Control System)
```bash
# Discord User ID of the admin (can execute !pm2, !system, !bot commands)
# To find your User ID:
# 1. Enable Developer Mode in Discord (User Settings → Advanced → Developer Mode)
# 2. Right-click your username → Copy User ID
# SECURITY: Only this user can execute admin commands!
ADMIN_USER_ID=your_discord_user_id_here

# Path to chat stats script (optional - for !bot stats command)
STATS_SCRIPT_PATH=/home/user/api_substrate/discord_bot/get_current_chat_stats.py

# Example admin commands you can use:
# !pm2 list              - Show all PM2 processes
# !pm2 stop all          - Stop all processes
# !pm2 restart all       - Restart all processes  
# !pm2 logs discord-bot   - Show bot logs
# !system status         - Show system info (uptime, memory, CPU)
# !bot stats             - Show bot statistics (autonomous system)
# !help                  - Show all admin commands
```

### 🔒 DM Restriction (Jan 2025 - Security Feature)
```bash
# Discord User ID that is allowed to send/receive DMs with the bot
# If set, the bot will ONLY:
# - Accept incoming DMs from this user ID
# - Allow discord_tool to send DMs to this user ID
# If not set (empty), DMs work normally (no restriction)
# To find your User ID:
# 1. Enable Developer Mode in Discord (User Settings → Advanced → Developer Mode)
# 2. Right-click your username → Copy User ID
# SECURITY: Prevents accidental DMs to wrong users!
ALLOWED_DM_USER_ID=your_discord_user_id_here

# Example: If set to "123456789012345678"
# - Bot will reject DMs from other users
# - discord_tool send_message with target_type="user" will only work for this ID
# - Other users get error message: "Sorry, I can only receive DMs from the authorized user."
```

### Autonomous Mode / Timer
```bash
# 🔒 AUTONOMOUS MODE - Bot decides itself when to respond (with bot-loop prevention!)
# WARNING: Only enable if you trust the bot-loop prevention system!
# If enabled, bot sees ALL channel messages and decides autonomously whether to respond
# Bot-loop prevention: Max 1 bot-to-bot exchange before 60s cooldown
# 🚨 Self-Spam Prevention: Max 3 consecutive bot messages without response
ENABLE_AUTONOMOUS=false

# Heartbeat system (periodic autonomous messages)
ENABLE_TIMER=false
```

### 💰 API Retry Configuration (Oct 2025)
```bash
# Enable/disable automatic retries for temporary API failures (502, 503, 504)
# true = Better UX (auto-retry on errors)
# false = Save credits (no retries, user must retry manually)
ENABLE_API_RETRY=true

# Maximum number of retry attempts (0-5 recommended)
# 1 = Conservative (default) - max 2 API calls per message
# 2 = Balanced - max 3 API calls per message
# 3 = Aggressive - max 4 API calls per message
# 0 = No retries - only 1 API call per message
MAX_API_RETRIES=1

# API Timeout in milliseconds (Nov 2025 - erhöht für große Requests)
# Default: 180000 (180s = 3 Minuten)
# Warum höher: Große Requests (240k+ Tokens) brauchen länger
# Timeout = bereits abgerechnet → kein Retry mehr (verhindert Doppelabrechnung)
# Empfohlene Werte:
# - 120000 (120s) = Für normale Requests (2 Minuten)
# - 180000 (180s) = Für große Requests (3 Minuten) - DEFAULT
# - 240000 (240s) = Für sehr große Requests (4 Minuten)
# - 300000 (300s) = Maximum (5 Minuten) - nur bei extrem großen Requests
LETTA_API_TIMEOUT_MS=180000

# See docs/RETRY_CONFIG.md for detailed credit cost analysis
```

### TTS System
```bash
ENABLE_TTS=false
# Comma-separated API keys for TTS endpoints
# Generate with: openssl rand -hex 32
TTS_API_KEYS=your-secret-key-1,your-secret-key-2
```

### Midjourney Integration
```bash
MIDJOURNEY_CHANNEL_ID=
```

### Task Scheduler
```bash
TASKS_CHANNEL_ID=
```

### Spotify Control
```bash
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here
SPOTIFY_REFRESH_TOKEN=your_spotify_refresh_token_here
```

### Weather Integration (Optional)
```bash
# OpenWeatherMap API Key for weather data in heartbeat messages
# Get free API key at: https://openweathermap.org/api
OPENWEATHER_API_KEY=your_openweather_api_key_here

# Weather Location Configuration (Optional - defaults to Munich, Germany)
WEATHER_CITY=Munich                    # City name (e.g., London, Paris, Berlin)
WEATHER_COUNTRY_CODE=de                # ISO 3166 country code (e.g., de, uk, fr, us)
WEATHER_LANGUAGE=de                    # Language for weather descriptions (e.g., de, en, fr)
WEATHER_CITY_DISPLAY=München           # Display name in messages (optional, defaults to WEATHER_CITY)
```

### Bot Language Configuration
```bash
# Language for bot messages (heartbeat, system messages)
# Options: 'en' (English) or 'de' (German)
# Default: 'en'
BOT_LANGUAGE=en
```

### GIF Integration (Optional)
```bash
# Tenor API Key for automatic GIF sending
# Get free API key at: https://developers.google.com/tenor/guides/quickstart
TENOR_API_KEY=your_tenor_api_key_here
```

### Server Config
```bash
PORT=3001
```

---

## 📝 Example `.env` File

```bash
# Core - Grok API (via api_substrate)
GROK_BASE_URL=http://localhost:8284
GROK_SESSION_ID=discord-bot
GROK_MODEL=grok-4-1-fast-reasoning           # OPTIONAL (substrate picks model if unset)
GROK_API_TIMEOUT_MS=300000
USE_SENDER_PREFIX=true  # Message formatting
SURFACE_ERRORS=true

# Discord
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_CHANNEL_ID=1234567890123456789

# Bot behavior
RESPOND_TO_DMS=true
RESPOND_TO_MENTIONS=true
RESPOND_TO_BOTS=false
RESPOND_TO_GENERIC=false

# Timezone
TIMEZONE=Europe/Berlin

# Optional features (disabled by default)
ENABLE_AUTONOMOUS=false  # 🔒 Autonomous mode with bot-loop prevention
ENABLE_TIMER=false       # Heartbeat system
ENABLE_TTS=false         # Text-to-speech

PORT=3001
```

---

## 🔒 Security Notes

1. **Never commit `.env` to git** - it contains secrets!
2. **Generate TTS keys securely:** `openssl rand -hex 32`
3. **Keep Discord token private** - it gives full bot access
4. **Rotate keys regularly** for production use

---

## ❌ Removed Variables

These were in old templates but are **no longer used**:

- `FORCE_NON_STREAM` - Removed in chunking fix (Oct 12, 2025)
- `SURFACE_TOOL_CHUNKS` - Not used in current code
- `SURFACE_REASONING_CHUNKS` - Not used in current code
- `TIMER_INTERVAL_MINUTES` - Hardcoded in code
- `FIRING_PROBABILITY` - Hardcoded in code
- `APP_ID` - Never used
- `PUBLIC_KEY` - Never used
- Piper TTS paths - Not referenced in code

---

## 🚀 Quick Start

```bash
# 1. Copy this template
cp ENV_VARIABLES.md .env

# 2. Edit .env with your values
nano .env

# 3. Remove the markdown headers and comments
# (Keep only the KEY=value lines)

# 4. Start bot
npm start
```

