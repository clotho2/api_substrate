# Substrate Service Deployment Guide

This guide covers deploying the agent substrate as a systemd service.

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
sudo mkdir -p /opt/substrate/agent
sudo cp -r . /opt/substrate/agent/

# 2. Create .env file with your API key
sudo cp .env.example /opt/substrate/agent/.env
sudo nano /opt/substrate/agent/.env
# Add your actual GROK_API_KEY

# 3. Install the service file
sudo cp substrate.service.env /etc/systemd/system/substrate-agent.service

# 4. Install Python dependencies
cd /opt/substrate/agent/backend
sudo pip3 install -r requirements.txt
sudo pip3 install requests python-dotenv

# 5. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable substrate-agent
sudo systemctl start substrate-agent
```

### Option 2: Using inline environment variables

This option puts environment variables directly in the service file.

```bash
# 1. Deploy the substrate
sudo mkdir -p /opt/substrate/agent
sudo cp -r . /opt/substrate/agent/

# 2. Edit the service file with your API key
sudo cp substrate.service /etc/systemd/system/
sudo nano /etc/systemd/system/substrate-agent.service
# Replace "your-xai-api-key-here" with your actual key

# 3. Install Python dependencies
cd /opt/substrate/agent/backend
sudo pip3 install -r requirements.txt
sudo pip3 install requests python-dotenv

# 4. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable substrate-agent
sudo systemctl start substrate-agent
```

## 📊 Service Management

### Check Status
```bash
sudo systemctl status substrate-agent
```

### View Logs
```bash
# Real-time logs
sudo journalctl -u substrate-agent -f

# Last 100 lines
sudo journalctl -u substrate-agent -n 100

# Logs since boot
sudo journalctl -u substrate-agent -b
```

### Restart Service
```bash
sudo systemctl restart substrate-agent
```

### Stop Service
```bash
sudo systemctl stop substrate-agent
```

### Disable Service
```bash
sudo systemctl disable substrate-agent
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GROK_API_KEY` | Your xAI API key | (required) |
| `GROK_API_URL` | Grok API endpoint | `https://api.x.ai/v1/chat/completions` |
| `MODEL_NAME` | Grok model to use | `grok-4-1-fast-reasoning` |
| `DB_PATH` | SQLite database path | `substrate.db` |
| `PORT` | Service port | `8091` |
| `N_CTX` | Context window size | `131072` |
| `DEFAULT_MAX_TOKENS` | Max response tokens | `4096` |
| `DEFAULT_TEMPERATURE` | Sampling temperature | `0.7` |

### Updating Configuration

**If using .env file:**
```bash
sudo nano /opt/substrate/agent/.env
sudo systemctl restart substrate-agent
```

**If using inline variables:**
```bash
sudo nano /etc/systemd/system/substrate-agent.service
sudo systemctl daemon-reload
sudo systemctl restart substrate-agent
```

## 🛡️ Security Considerations

1. **API Key Protection**
   - Use `.env` file method (Option 1) for production
   - Set proper file permissions: `sudo chmod 600 /opt/substrate/agent/.env`
   - Never commit `.env` to version control

2. **Service User**
   - Consider running as dedicated user instead of root
   - Create service user: `sudo useradd -r -s /bin/false substrate-agent`
   - Update service file: `User=substrate-agent`
   - Set permissions: `sudo chown -R substrate-agent:substrate-agent /opt/substrate/agent`

3. **Network Security**
   - Firewall rules for port 8091 if needed
   - Consider reverse proxy (nginx) for TLS

## 🐛 Troubleshooting

### Service won't start

```bash
# Check for errors
sudo journalctl -u substrate-agent -n 50

# Verify Python dependencies
cd /opt/substrate/agent/backend
python3 -c "import requests; import dotenv; print('Dependencies OK')"

# Test manually
cd /opt/substrate/agent
python3 backend/agent_runner.py
```

### API Key Errors

```bash
# Verify API key is set
sudo grep GROK_API_KEY /opt/substrate/agent/.env

# Test API key manually
cd /opt/substrate/agent
python3 -c "from config import GROK_API_KEY; print('Key loaded:', GROK_API_KEY[:10]+'...')"
```

### Permission Errors

```bash
# Check file ownership
ls -la /opt/substrate/agent/

# Fix if needed
sudo chown -R root:root /opt/substrate/agent/
sudo chmod 755 /opt/substrate/agent/
```

## 📝 Migration from Mixtral

If migrating from the old Mixtral-based service:

```bash
# 1. Stop old service
sudo systemctl stop substrate-agent

# 2. Backup old database
sudo cp /opt/substrate/agent/substrate.db /opt/substrate/agent/substrate.db.backup

# 3. Deploy new code
sudo cp -r . /opt/substrate/agent/

# 4. Update configuration
sudo cp .env.example /opt/substrate/agent/.env
sudo nano /opt/substrate/agent/.env
# Add GROK_API_KEY, remove MIXTRAL_URL

# 5. Update service file
sudo cp substrate.service.env /etc/systemd/system/substrate-agent.service

# 6. Restart
sudo systemctl daemon-reload
sudo systemctl start substrate-agent
```

## ✅ Verification

After deployment, verify the service is working:

```bash
# 1. Check service status
sudo systemctl status substrate-agent

# 2. Check logs for startup messages
sudo journalctl -u substrate-agent -n 20

# 3. Test API endpoint (if applicable)
curl http://localhost:8091/health  # If you have a health endpoint

# 4. Check database
ls -lh /opt/substrate/agent/substrate.db
```

## 📱 Telegram Bot Deployment (Optional)

The Telegram bot provides a multimodal interface to the agent with a 4,096 character limit (2x Discord).

### Prerequisites

- The substrate service must be running first
- Telegram bot token from @BotFather
- python-telegram-bot library installed

### Option 1: Using .env file (RECOMMENDED)

```bash
# 1. Get Telegram bot token
# Talk to @BotFather on Telegram, send /newbot

# 2. Add to .env file
sudo nano /opt/substrate/agent/.env
# Add these lines:
# TELEGRAM_BOT_TOKEN=your_bot_token_here
# TELEGRAM_SESSION_ID=telegram_session
# SUBSTRATE_API_URL=http://localhost:8284

# 3. Install python-telegram-bot
sudo pip3 install python-telegram-bot==20.7

# 4. Install the service file
sudo cp substrate-telegram.service.env /etc/systemd/system/substrate-telegram.service

# 5. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable substrate-telegram
sudo systemctl start substrate-telegram
```

### Option 2: Using inline environment variables

```bash
# 1. Edit the service file with your tokens
sudo cp substrate-telegram.service /etc/systemd/system/
sudo nano /etc/systemd/system/substrate-telegram.service
# Replace "your-telegram-bot-token-here" with your actual token

# 2. Install python-telegram-bot
sudo pip3 install python-telegram-bot==20.7

# 3. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable substrate-telegram
sudo systemctl start substrate-telegram
```

### Telegram Bot Management

```bash
# Check status
sudo systemctl status substrate-telegram

# View logs
sudo journalctl -u substrate-telegram -f

# Restart bot
sudo systemctl restart substrate-telegram

# Stop bot
sudo systemctl stop substrate-telegram
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
sudo systemctl status substrate-agent

# Verify API endpoint
curl http://localhost:8284/api/chat

# Test bot token
python3 -c "import os; print('Token loaded' if os.getenv('TELEGRAM_BOT_TOKEN') else 'No token')"

# Check logs for errors
sudo journalctl -u substrate-telegram -n 50
```

## 📚 Additional Resources

- **Configuration:** See `config.py` for all available settings
- **Environment Template:** See `.env.example` for variable reference
- **Setup Script:** Run `python backend/setup_agent.py` to initialize core memory
- **Testing:** Run `python backend/agent_runner.py` to test the agent
- **Telegram Setup:** See `backend/TELEGRAM_SETUP.md` for detailed bot configuration

---

**The agent is now running as a systemd service. ⚡**
