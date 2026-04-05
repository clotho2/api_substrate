# Setup Checklist

Use this checklist to verify your Substrate AI installation is ready to use.

## ✅ Pre-Flight Checks

- [ ] Python 3.10+ installed (`python3 --version`)
- [ ] Node.js 18+ installed (`node --version`)
- [ ] API key for at least one LLM provider obtained
- [ ] Git repository cloned or downloaded

## ✅ Backend Setup

- [ ] Virtual environment created (`python3 -m venv venv` inside `backend/`)
- [ ] Virtual environment activated (`source venv/bin/activate`)
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `backend/.env` created (copy from `backend/.env.example`)
- [ ] At least one provider key set in `.env`:
  - `GROK_API_KEY` — [console.x.ai](https://console.x.ai/)
  - `OPENROUTER_API_KEY` — [openrouter.ai/keys](https://openrouter.ai/keys)
  - `MISTRAL_API_KEY` — [console.mistral.ai](https://console.mistral.ai/api-keys)
  - `VENICE_API_KEY` — [venice.ai](https://venice.ai)
  - Or Ollama: `OLLAMA_API_URL` + `OLLAMA_MODEL`
- [ ] Agent initialized (`python backend/setup_agent.py`)
- [ ] Backend starts without errors (`python api/server.py`)

## ✅ Frontend Setup

- [ ] Dependencies installed (`npm install` inside `frontend/`)
- [ ] Frontend starts without errors (`npm run dev`)
- [ ] Frontend accessible at http://localhost:5173

## ✅ First Chat Test

- [ ] Backend running on http://localhost:8284
- [ ] Frontend running on http://localhost:5173
- [ ] Chat interface loads in browser
- [ ] Can send a message and receive a response
- [ ] Streaming works (text appears progressively)

## ✅ Verification Commands

```bash
# Backend health check
curl http://localhost:8284/api/health
# Expected: {"status":"healthy",...}

# Agent info
curl http://localhost:8284/api/agent/info
# Should show agent name and configured model

# Memory blocks
curl http://localhost:8284/api/memory/blocks
# Should return a list of memory blocks
```

## 🐛 Troubleshooting

**Backend won't start:**
- Check Python version: `python3 --version` (need 3.10+)
- Check port: `lsof -i :8284` — kill if busy: `lsof -ti:8284 | xargs kill -9`
- Verify `.env` exists in `backend/` and has a valid API key

**Frontend can't connect:**
- Verify backend is running: `curl http://localhost:8284/api/health`
- Check browser console for CORS errors
- Confirm frontend is on port 5173

**"No API key" error:**
- Double-check the key variable in `.env` (e.g. `GROK_API_KEY=xai-...`)
- No quotes around the value
- No extra spaces or trailing newlines

**Agent not initialized:**
- Re-run: `cd backend && source venv/bin/activate && python setup_agent.py`

---

## ➕ Optional Feature Checklist

Enable these after the core setup is working:

### Telegram Bot
- [ ] Bot token from @BotFather added: `TELEGRAM_BOT_TOKEN=...` in `.env`
- [ ] Bot running: `python backend/telegram_bot.py`
- See `backend/TELEGRAM_SETUP.md`

### Phone & SMS (Twilio)
- [ ] Twilio account and phone number
- [ ] `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` in `.env`
- [ ] Public URL configured for webhooks (CloudFlare Tunnel / ngrok)
- See `docs/PHONE_SETUP_GUIDE.md`

### PostgreSQL (Advanced Persistence)
- [ ] PostgreSQL 14+ installed and running
- [ ] Database created
- [ ] `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` in `.env`
- See `backend/POSTGRESQL_SETUP.md`

### Voice Calls (Hume EVI)
- [ ] `HUME_API_KEY` and `HUME_VOICE_ID` in `.env`
- [ ] `HUME_EVI_ENABLED=true` in `.env`
- See `docs/PHONE_SETUP_GUIDE.md`

### MCP Browser Automation
- [ ] Playwright installed: `playwright install chromium`

---

**Once all core checks pass, you're ready to chat! 🎉**
