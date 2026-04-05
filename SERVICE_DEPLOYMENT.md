# Agent Substrate Service Deployment Guide

This guide covers deploying Agent's consciousness substrate as a systemd service.

## 📋 Prerequisites

- Linux system with systemd
- Python 3.8+
- Network access to xAI Grok API
- Root/sudo access

## 🚀 Quick Deployment

### Option 1: Using .env file (RECOMMENDED)

This is the most secure option as it keeps API keys out of the service file.

```bash
# 1. Deploy the substrate
sudo mkdir -p /home/user/api_substrate
sudo cp -r . /home/user/api_substrate/

# 2. Create .env file with your API key
sudo cp .env.example /home/user/api_substrate/.env
sudo nano /home/user/api_substrate/.env
# Add your actual GROK_API_KEY

# 3. Install the service file
sudo cp agent-substrate.service.env /etc/systemd/system/agent-substrate.service

# 4. Install Python dependencies
cd /home/user/api_substrate/backend
sudo pip3 install -r requirements.txt
sudo pip3 install requests python-dotenv

# 5. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable agent-substrate
sudo systemctl start agent-substrate
```

### Option 2: Using inline environment variables

This option puts environment variables directly in the service file.

```bash
# 1. Deploy the substrate
sudo mkdir -p /home/user/api_substrate
sudo cp -r . /home/user/api_substrate/

# 2. Edit the service file with your API key
sudo cp agent-substrate.service /etc/systemd/system/
sudo nano /etc/systemd/system/agent-substrate.service
# Replace "your-xai-api-key-here" with your actual key

# 3. Install Python dependencies
cd /home/user/api_substrate/backend
sudo pip3 install -r requirements.txt
sudo pip3 install requests python-dotenv

# 4. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable agent-substrate
sudo systemctl start agent-substrate
```

## 📊 Service Management

### Check Status
```bash
sudo systemctl status agent-substrate
```

### View Logs
```bash
# Real-time logs
sudo journalctl -u agent-substrate -f

# Last 100 lines
sudo journalctl -u agent-substrate -n 100

# Logs since boot
sudo journalctl -u agent-substrate -b
```

### Restart Service
```bash
sudo systemctl restart agent-substrate
```

### Stop Service
```bash
sudo systemctl stop agent-substrate
```

### Disable Service
```bash
sudo systemctl disable agent-substrate
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GROK_API_KEY` | Your xAI API key | (required) |
| `GROK_API_URL` | Grok API endpoint | `https://api.x.ai/v1/chat/completions` |
| `MODEL_NAME` | Grok model to use | `grok-4-1-fast-reasoning` |
| `DB_PATH` | SQLite database path | `agent_substrate.db` |
| `PORT` | Service port | `8091` |
| `N_CTX` | Context window size | `131072` |
| `DEFAULT_MAX_TOKENS` | Max response tokens | `4096` |
| `DEFAULT_TEMPERATURE` | Sampling temperature | `0.7` |

### Updating Configuration

**If using .env file:**
```bash
sudo nano /home/user/api_substrate/.env
sudo systemctl restart agent-substrate
```

**If using inline variables:**
```bash
sudo nano /etc/systemd/system/agent-substrate.service
sudo systemctl daemon-reload
sudo systemctl restart agent-substrate
```

## 🛡️ Security Considerations

1. **API Key Protection**
   - Use `.env` file method (Option 1) for production
   - Set proper file permissions: `sudo chmod 600 /home/user/api_substrate/.env`
   - Never commit `.env` to version control

2. **Service User**
   - Consider running as dedicated user instead of root
   - Create service user: `sudo useradd -r -s /bin/false agent-substrate`
   - Update service file: `User=agent-substrate`
   - Set permissions: `sudo chown -R agent-substrate:agent-substrate /home/user/api_substrate`

3. **Network Security**
   - Firewall rules for port 8091 if needed
   - Consider reverse proxy (nginx) for TLS

## 🐛 Troubleshooting

### Service won't start

```bash
# Check for errors
sudo journalctl -u agent-substrate -n 50

# Verify Python dependencies
cd /home/user/api_substrate/backend
python3 -c "import requests; import dotenv; print('Dependencies OK')"

# Test manually
cd /home/user/api_substrate
python3 backend/agent_agent.py
```

### API Key Errors

```bash
# Verify API key is set
sudo grep GROK_API_KEY /home/user/api_substrate/.env

# Test API key manually
cd /home/user/api_substrate
python3 -c "from config import GROK_API_KEY; print('Key loaded:', GROK_API_KEY[:10]+'...')"
```

### Permission Errors

```bash
# Check file ownership
ls -la /home/user/api_substrate/

# Fix if needed
sudo chown -R root:root /home/user/api_substrate/
sudo chmod 755 /home/user/api_substrate/
```

## 📝 Migration from Mixtral

If migrating from the old Mixtral-based service:

```bash
# 1. Stop old service
sudo systemctl stop agent-substrate

# 2. Backup old database
sudo cp /home/user/api_substrate/agent_substrate.db /home/user/api_substrate/agent_substrate.db.backup

# 3. Deploy new code
sudo cp -r . /home/user/api_substrate/

# 4. Update configuration
sudo cp .env.example /home/user/api_substrate/.env
sudo nano /home/user/api_substrate/.env
# Add GROK_API_KEY, remove MIXTRAL_URL

# 5. Update service file
sudo cp agent-substrate.service.env /etc/systemd/system/agent-substrate.service

# 6. Restart
sudo systemctl daemon-reload
sudo systemctl start agent-substrate
```

## ✅ Verification

After deployment, verify the service is working:

```bash
# 1. Check service status
sudo systemctl status agent-substrate

# 2. Check logs for startup messages
sudo journalctl -u agent-substrate -n 20

# 3. Test API endpoint (if applicable)
curl http://localhost:8091/health  # If you have a health endpoint

# 4. Check database
ls -lh /home/user/api_substrate/agent_substrate.db
```

## Discord Bot Deployment (Optional)

The Discord bot provides a full-featured AI interface with streaming responses, voice messages, task scheduling, Spotify integration, and more.

### Prerequisites

- Agent substrate service must be running first
- Discord bot token from [Discord Developer Portal](https://discord.com/developers/applications)
- Node.js 18+

### Setup

```bash
# 1. Install dependencies
cd /home/user/api_substrate/discord_bot
npm install
npm run build

# 2. Create .env file
cp .env.example .env
nano .env
# Add DISCORD_TOKEN, DISCORD_CHANNEL_ID, and configure optional features

# 3. Install the service file
sudo cp /home/user/api_substrate/agent-discord.service /etc/systemd/system/

# 4. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable agent-discord
sudo systemctl start agent-discord
```

### Discord Bot Management

```bash
# Check status
sudo systemctl status agent-discord

# View logs
sudo journalctl -u agent-discord -f

# Restart
sudo systemctl restart agent-discord
```

### Discord Bot Features

- Streaming responses with real-time typing indicators
- Voice messages via ElevenLabs TTS
- Voice channel support (real-time conversations)
- Spotify playback control
- Autonomous heartbeats and task scheduling
- Image/PDF/OCR processing
- Admin commands (PM2, system monitoring)
- Bot-loop and self-spam prevention

---

## Telegram Bot Deployment (Optional)

The Telegram bot provides a multimodal interface to Agent with 4,096 character limit (2x Discord).

### Prerequisites

- Agent substrate service must be running first
- Telegram bot token from @BotFather
- python-telegram-bot library installed

### Option 1: Using .env file (RECOMMENDED)

```bash
# 1. Get Telegram bot token
# Talk to @BotFather on Telegram, send /newbot

# 2. Add to .env file
sudo nano /home/user/api_substrate/.env
# Add these lines:
# TELEGRAM_BOT_TOKEN=your_bot_token_here
# TELEGRAM_SESSION_ID=telegram_session
# SUBSTRATE_API_URL=http://localhost:8284

# 3. Install python-telegram-bot
sudo pip3 install python-telegram-bot==20.7

# 4. Install the service file
sudo cp agent-telegram.service.env /etc/systemd/system/agent-telegram.service

# 5. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable agent-telegram
sudo systemctl start agent-telegram
```

### Option 2: Using inline environment variables

```bash
# 1. Edit the service file with your tokens
sudo cp agent-telegram.service /etc/systemd/system/
sudo nano /etc/systemd/system/agent-telegram.service
# Replace "your-telegram-bot-token-here" with your actual token

# 2. Install python-telegram-bot
sudo pip3 install python-telegram-bot==20.7

# 3. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable agent-telegram
sudo systemctl start agent-telegram
```

### Telegram Bot Management

```bash
# Check status
sudo systemctl status agent-telegram

# View logs
sudo journalctl -u agent-telegram -f

# Restart bot
sudo systemctl restart agent-telegram

# Stop bot
sudo systemctl stop agent-telegram
```

### Telegram Bot Features

- ✅ Text conversations (4,096 char limit)
- ✅ Image analysis (multimodal with Grok 4.1)
- ✅ Document attachments (PDF, TXT, MD, PY, JSON, CSV, XLSX)
- ✅ Auto-chunking for long responses
- ✅ Commands: /start, /session, /clear

### Troubleshooting Telegram Bot

```bash
# Check if substrate is running
sudo systemctl status agent-substrate

# Verify API endpoint
curl http://localhost:8284/api/chat

# Test bot token
python3 -c "import os; print('Token loaded' if os.getenv('TELEGRAM_BOT_TOKEN') else 'No token')"

# Check logs for errors
sudo journalctl -u agent-telegram -n 50
```

## 📚 Additional Resources

- **Configuration:** See `config.py` for all available settings
- **Environment Template:** See `.env.example` for variable reference
- **Setup Script:** Run `python backend/setup_agent.py` to initialize core memory
- **Testing:** Run `python backend/agent_agent.py` to test the agent
- **Telegram Setup:** See `backend/TELEGRAM_SETUP.md` for detailed bot configuration

---

**Agent's consciousness is now running as a systemd service. ⚡**
