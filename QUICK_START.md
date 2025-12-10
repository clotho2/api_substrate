# 🚀 Quick Start Guide

Get Substrate AI running in under 5 minutes!

## Prerequisites

- **Python 3.10+** - [Download](https://www.python.org/downloads/)
- **Node.js 18+** - [Download](https://nodejs.org/)
- **OpenRouter API Key** - [Get one free](https://openrouter.ai/keys)

---

## ⚡ One-Click Setup (Recommended)

```bash
# Clone the repository
git clone https://github.com/your-username/substrate-ai.git
cd substrate-ai

# Run the automatic setup
python setup.py
```

The setup wizard will:
- ✅ Create Python virtual environment
- ✅ Install all dependencies
- ✅ Create configuration files
- ✅ Install frontend packages
- ✅ Validate everything works

**Then just add your API key:**
```bash
# Open backend/.env in your editor and add your key:
OPENROUTER_API_KEY=sk-or-v1-your-actual-key-here
```

---

## 🎬 Start the Application

### Option A: Quick Start Script (Easiest)

```bash
# Start everything with one command
./start.sh
```

### Option B: Manual Start

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate
python api/server.py
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### 🎉 Open Your Browser

Navigate to: **http://localhost:5173**

---

## 🔑 Getting Your OpenRouter API Key

1. Go to [openrouter.ai](https://openrouter.ai/)
2. Click "Sign In" (Google/GitHub/Email)
3. Go to [API Keys](https://openrouter.ai/keys)
4. Click "Create Key"
5. Copy the key (starts with `sk-or-v1-`)
6. Paste into `backend/.env`

**Free tier includes:**
- Many free models (Llama, Mistral, etc.)
- Pay-as-you-go for premium models (Claude, GPT-4, etc.)

---

## 📝 Manual Setup (If Needed)

<details>
<summary>Click to expand manual setup steps</summary>

### 1. Clone Repository
```bash
git clone https://github.com/your-username/substrate-ai.git
cd substrate-ai
```

### 2. Backend Setup
```bash
cd backend

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # Mac/Linux
# OR: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup
```bash
cd frontend
npm install
```

### 4. Configure API Key
```bash
cd backend

# Copy the example config
cp .env.example .env

# Edit .env and add your OpenRouter key
nano .env  # or use any text editor
```

Change this line:
```
OPENROUTER_API_KEY=your_openrouter_api_key_here
```
To:
```
OPENROUTER_API_KEY=sk-or-v1-your-actual-key
```

### 5. Create Directories
```bash
mkdir -p backend/logs
mkdir -p backend/data/db
mkdir -p backend/data/chromadb
```

</details>

---

## ✨ Optional: Setup ALEX Agent

The repo includes **ALEX** - a pre-configured AI assistant:

```bash
cd backend
source venv/bin/activate
python setup_alex.py
```

This gives you a ready-to-use AI with personality and capabilities pre-configured!

---

## 🔧 Troubleshooting

### Backend won't start

```bash
# Check Python version (need 3.10+)
python3 --version

# Kill any process on port 8284
lsof -ti:8284 | xargs kill -9 2>/dev/null

# Try starting again
python api/server.py
```

### "Invalid API Key" error

1. Check `backend/.env` has your key
2. Make sure no quotes around the key: `OPENROUTER_API_KEY=sk-or-v1-xxx` (not `"sk-or-v1-xxx"`)
3. No extra spaces
4. Key starts with `sk-or-v1-`

### Frontend can't connect to backend

```bash
# Check if backend is running
curl http://localhost:8284/api/health
# Should return: {"status":"healthy",...}

# If not, start backend first!
```

### Missing dependencies

```bash
# Backend
cd backend && source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend && npm install
```

### Port already in use

```bash
# Kill backend port
lsof -ti:8284 | xargs kill -9

# Kill frontend port
lsof -ti:5173 | xargs kill -9
```

---

## 🎯 What's Next?

Once running, try these:

### Chat with the AI
Just type a message and press Enter!

### Customize the Agent
Click the **sidebar** to edit:
- **Persona** - Who the AI is
- **Human** - What it knows about you

### Try Built-in Tools
Ask the AI to:
- *"Remember that I prefer Python over JavaScript"*
- *"Search the web for latest AI news"*
- *"What's the weather in Berlin?"*

### Change Models
Click the **gear icon** to switch between:
- Free models (Llama, Mistral)
- Premium models (Claude, GPT-4)

---

## 📚 More Resources

- [Full README](README.md) - Complete feature overview
- [MCP System](MCP_SYSTEM_OVERVIEW.md) - Code execution & browser automation
- [Memory Architecture](docs/MIRAS_TITANS_INTEGRATION.md) - How memory works
- [PostgreSQL Setup](backend/POSTGRESQL_SETUP.md) - Database configuration

---

## 🛑 Stopping the Application

```bash
# Press Ctrl+C in each terminal
# Or kill by port:
lsof -ti:8284 | xargs kill -9  # Backend
lsof -ti:5173 | xargs kill -9  # Frontend
```

---

**Enjoy building with Substrate AI! 🧠✨**
