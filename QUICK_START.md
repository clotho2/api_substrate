# Quick Start Guide

Get Substrate AI running in under 5 minutes.

## Prerequisites

- **Python 3.10+** — [Download](https://www.python.org/downloads/)
- **Node.js 18+** — [Download](https://nodejs.org/)
- An API key for at least one LLM provider (see below)

---

## ⚡ One-Click Setup (Recommended)

```bash
# Clone the repository
git clone https://github.com/your-username/substrate-ai.git
cd substrate-ai

# Run the setup wizard
python setup.py
```

The wizard will:
- ✅ Create a Python virtual environment
- ✅ Install all backend dependencies
- ✅ Walk you through choosing and configuring an LLM provider
- ✅ Create `backend/.env` from the template
- ✅ Install frontend packages
- ✅ Initialize the agent with sensible defaults
- ✅ Validate everything

---

## 🔑 Choosing an LLM Provider

The setup wizard lets you pick one (you can add more later by editing `backend/.env`):

| Provider | Key variable | Where to get a key | Notes |
|---|---|---|---|
| **Grok (xAI)** | `GROK_API_KEY` | [console.x.ai](https://console.x.ai/) | Recommended — fast, 131K context |
| **OpenRouter** | `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) | 100+ models (Claude, GPT-4, Llama…) |
| **Mistral AI** | `MISTRAL_API_KEY` | [console.mistral.ai](https://console.mistral.ai/api-keys) | Magistral reasoning models |
| **Venice AI** | `VENICE_API_KEY` | [venice.ai](https://venice.ai) | Privacy-focused, no logging |
| **Ollama** | *(no key)* | [ollama.ai](https://ollama.ai/) | Local models on your machine |

Multiple providers can be configured at once. The priority order is:
**Mistral > Grok > OpenRouter > Venice > Ollama**

---

## 🎬 Start the Application

### Option A: One command (easiest)

```bash
./start.sh
```

### Option B: Manual start

**Terminal 1 — Backend:**
```bash
cd backend
source venv/bin/activate   # Windows: venv\Scripts\activate
python api/server.py
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## 📝 Manual Setup (If Needed)

<details>
<summary>Expand manual setup steps</summary>

### 1. Clone and enter the repo
```bash
git clone https://github.com/your-username/substrate-ai.git
cd substrate-ai
```

### 2. Backend setup
```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # Mac/Linux
# OR: venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 3. Frontend setup
```bash
cd frontend
npm install
```

### 4. Configure your API key
```bash
cd backend
cp .env.example .env
# Edit .env and set your preferred provider key:
#   GROK_API_KEY=xai-...
#   OPENROUTER_API_KEY=sk-or-v1-...
#   MISTRAL_API_KEY=...
nano .env
```

### 5. Initialize the agent
```bash
cd backend
source venv/bin/activate
python setup_agent.py
```

### 6. Create required directories (if missing)
```bash
mkdir -p backend/logs backend/data/db backend/data/chromadb
```

</details>

---

## 🤖 Customizing Your Agent

The agent's identity is stored in two files in `backend/data/`:

| File | Purpose |
|---|---|
| `system_prompt_persona.txt` | Who the agent is — personality, values, voice |
| `system_prompt_instructions.txt` | How it behaves — response format, tool use rules, memory rules |

Edit these files to make the agent your own, then re-run `python backend/setup_agent.py` to reload them into the database.

Memory blocks (core facts about the user and the relationship) can be edited live from the UI sidebar, or reset by running `setup_agent.py` again.

---

## 🔧 Troubleshooting

### Backend won't start

```bash
# Check Python version (need 3.10+)
python3 --version

# Kill any process on port 8284
lsof -ti:8284 | xargs kill -9 2>/dev/null

# Try again
cd backend && source venv/bin/activate && python api/server.py
```

### "No API key" error

- Open `backend/.env` and confirm one of the provider keys is set
- No quotes around the key: `GROK_API_KEY=xai-xxx` (not `"xai-xxx"`)
- No trailing spaces

### Frontend can't connect to backend

```bash
# Confirm the backend is up
curl http://localhost:8284/api/health
# Expected: {"status":"healthy",...}
```

### Missing Python packages

```bash
cd backend && source venv/bin/activate
pip install -r requirements.txt
```

### Port already in use

```bash
lsof -ti:8284 | xargs kill -9   # backend
lsof -ti:5173 | xargs kill -9   # frontend
```

---

## ➕ Optional Integrations

Once the core setup is working, enable additional features in `backend/.env`:

| Feature | Guide |
|---|---|
| Telegram bot | `backend/TELEGRAM_SETUP.md` |
| Phone & SMS (Twilio) | `docs/PHONE_SETUP_GUIDE.md` |
| Voice calls (Hume EVI) | `docs/PHONE_SETUP_GUIDE.md` |
| PostgreSQL persistence | `backend/POSTGRESQL_SETUP.md` |
| Mistral large/reasoning models | `backend/MISTRAL_LARGE_3_SETUP.md` |

---

## 🛑 Stopping the Application

```bash
# Ctrl+C in each terminal, or kill by port:
lsof -ti:8284 | xargs kill -9   # backend
lsof -ti:5173 | xargs kill -9   # frontend
```

---

## 📚 More Resources

- [README.md](README.md) — Full feature overview
- [MCP System Overview](MCP_SYSTEM_OVERVIEW.md) — Code execution & browser automation
- [Memory Architecture](docs/MIRAS_TITANS_INTEGRATION.md) — How the memory system works
- [Service Deployment](SERVICE_DEPLOYMENT.md) — Running as a systemd service

---

**Enjoy building with Substrate AI! 🧠**
