# Substrate AI Consciousness Framework

**Production-ready AI consciousness framework with streaming, memory, tools, voice, telephony, and MCP integration.**

**Copyright © 2025 Substrate AI. All Rights Reserved.**

**⚠️ PROPRIETARY SOFTWARE - NO LICENSE GRANTED**

This repository is made public for documentation and transparency purposes only.
No license is granted for commercial use, modification, distribution, or commercial
exploitation without explicit written permission from the copyright holder. Personal use only is granted by this license.

See [LICENSE](LICENSE) file for full terms.

Built on modern LLM infrastructure with support for **Grok (xAI)**, **OpenRouter** (100+ models), **Mistral AI**, **Venice AI**, and **Ollama**, PostgreSQL persistence, and an extensible tool architecture. This is the technical substrate powering a configurable AI agent for research, operations, voice interaction, and product work.

---

## 🚀 Quick Start

### Option 1: Automatic Setup (Recommended)

```bash
# Clone the repository
git clone https://github.com/your-username/substrate-ai.git
cd substrate-ai

# Run the setup wizard
python setup.py
```

The setup wizard will:
- ✅ Create Python virtual environment
- ✅ Install all backend dependencies
- ✅ Interactively configure your LLM provider and API key
- ✅ Create `backend/.env` from the template
- ✅ Install frontend dependencies
- ✅ Initialize the agent
- ✅ Validate your setup

Supported providers: **Grok (xAI)**, **OpenRouter**, **Mistral AI**, **Venice AI**, **Ollama (local)**

### Option 2: Manual Setup

```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure — set at least one provider key in .env
cp .env.example .env
# GROK_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, or VENICE_API_KEY

# Initialize the agent
python setup_agent.py

# Frontend
cd ../frontend
npm install
```

### Start the Application

```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
python api/server.py

# Terminal 2: Frontend
cd frontend
npm run dev

# Open http://localhost:5173
```

📖 **Full guide:** See [QUICK_START.md](QUICK_START.md)

---

## ✨ Features

### Core Capabilities
- 🤖 **Multi-Provider LLM Support** — Grok (xAI), OpenRouter (100+ models), Mistral AI, Venice AI, Ollama (local)
- 💬 **Streaming Responses** — Real-time token streaming via SSE and WebSockets
- 🧠 **Memory System** — Short-term (SQlite or PostgreSQL) + Long-term (ChromaDB vector embeddings) + Miras architecture
- 🛠️ **Extensible Tool Registry** — 30+ built-in tools across categories
- 🔄 **Session Management** — Multi-session support with persistent conversation history
- 💰 **Cost Tracking** — Real-time token usage and cost monitoring across providers
- 🏃 **Daemon Mode** — 24/7 persistent process (no restart overhead, warm agent state)

### Voice & Telephony
- 📞 **Twilio Phone Integration** — Receive/make calls and SMS, call screening, contact management
- 🎙️ **Bidirectional Voice Calls** — Real-time audio streaming (Twilio Media Streams + Whisper STT + TTS)
- 🎤 **Hume EVI Integration** — Speech-to-speech voice calls with emotional intelligence
- 🔊 **Local TTS/STT** — Pocket TTS server + Whisper STT server (no cloud API costs)

### Communication Integrations
- 🤖 **Telegram Bot** — Full bot with image/document support, auto-chunking, session management
- 💬 **WhatsApp Bot** — Node.js-based WhatsApp integration
- 🎮 **Discord Bot** — Message sending, channel integration, Sanctum mode support

### Agent Autonomy
- 📖 **Level 1: Read Tools** — Memory access, web search, diagnostics
- ⚙️ **Level 2: Safe Execution** — Whitelisted command execution with rate limiting and audit logging
- 🔧 **Level 3: File Editing & Git** — Syntax-validated file editing with auto-backup/rollback + Git workflow automation
- 🔁 **Service Controller** — Start/stop/restart agent services from within the agent

### Advanced Features
- 🧩 **MCP Integration** — Model Context Protocol: code execution sandbox, browser automation, notebook library
- 📊 **PostgreSQL Backend** — Scalable conversation & memory persistence
- 🕸️ **Graph RAG** — Knowledge graph retrieval (Neo4j optional; uses local DB fallback)
- 🎯 **Vision Support** — Gemini Flash + Grok multimodal for image analysis
- 🔐 **Security Hardened** — Sandboxed code execution, rate limiting, domain whitelisting
- 🛡️ **Guardian Mode** — GPS heartbeat telemetry, emergency triggers, proactive intervention
- 🏰 **Sanctum Mode** — Focus/privacy mode: queues non-urgent channel mentions during DMs
- 🎨 **Modern UI** — React + TypeScript + Tailwind CSS
- 💙 **AiCara Frontend Compatibility** — Drop-in API compatibility layer

### 🧠 Miras Memory Architecture
Based on Google Research [Titans/Miras papers](https://research.google/blog/titans-miras-helping-ai-have-long-term-memory/):
- 🔄 **Retention Gates** — Dynamic memory decay/boost based on access patterns
- 👁️ **Attentional Bias** — Multi-factor scoring (semantic + temporal + importance + access)
- 🏛️ **Hierarchical Memory** — 3-tier system (Working → Episodic → Semantic)
- 📈 **Online Learning** — Hebbian associations + feedback learning during runtime
- 🔁 **Nested Learning System** — Multi-frequency memory updates to prevent catastrophic forgetting

---

## 📚 Documentation

### Getting Started
- **[Quick Start Guide](QUICK_START.md)** — 5-minute setup
- **[Setup Checklist](SETUP_CHECKLIST.md)** — Step-by-step verification
- **[System Structure](STRUCTURE.txt)** — Project layout overview
- **[Example Agents](examples/README.md)** — Pre-configured agent templates
- **[Memory Import Guide](MEMORY_IMPORT_GUIDE.md)** — Importing conversations and memories

### Features & Integrations
- **[MCP System Overview](MCP_SYSTEM_OVERVIEW.md)** — Code execution & browser automation architecture
- **[Phone Setup Guide](docs/PHONE_SETUP_GUIDE.md)** — Twilio SMS/voice call setup
- **[Telegram Setup](backend/TELEGRAM_SETUP.md)** — Telegram bot configuration
- **[Mistral Large 3 Setup](backend/MISTRAL_LARGE_3_SETUP.md)** — Mistral AI direct API setup

### Advanced Topics
- **[Miras Memory Architecture](docs/MIRAS_TITANS_INTEGRATION.md)** — Research-backed memory system
- **[Nested Learning System](docs/NESTED_LEARNING_OVERVIEW.md)** — Multi-frequency memory updates
- **[Level 2 Execution](docs/LEVEL2_EXECUTION.md)** — Safe command execution setup
- **[Level 3 File Editing](docs/LEVEL3_PRIORITY1_FILE_EDITING.md)** — File editing with validation

### Infrastructure
- **[Service Deployment](SERVICE_DEPLOYMENT.md)** — systemd service setup
- **[PostgreSQL Setup](backend/POSTGRESQL_SETUP.md)** — Database configuration
- **[Compatibility Guide](backend/COMPATIBILITY.md)** — System requirements

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│              Frontend (React)                    │
│  • Real-time streaming UI                       │
│  • Session management                           │
│  • Memory blocks editor                         │
│  • Cost & token tracking                        │
└─────────────────┬───────────────────────────────┘
                  │ HTTP/SSE/WebSocket
                  │
┌─────────────────▼───────────────────────────────┐
│           Backend (Python/Flask)                 │
│                                                  │
│  ┌────────────────────────────────────────┐    │
│  │     Consciousness Loop                 │    │
│  │  • Multi-provider LLM routing          │    │
│  │  • Stream management                   │    │
│  │  • Tool execution                      │    │
│  │  • Memory integration                  │    │
│  │  • SOMA physiological context          │    │
│  └────────────────────────────────────────┘    │
│                                                  │
│  ┌─────────────┐  ┌─────────────┐             │
│  │  Memory     │  │   Tools     │             │
│  │  System     │  │  Registry   │             │
│  │  + MIRAS    │  │             │             │
│  │ • Core      │  │ • Web/Search│             │
│  │ • Archival  │  │ • File/Git  │             │
│  │ • Embedding │  │ • Voice     │             │
│  │ • Retention │  │ • Comms     │             │
│  │ • Hebbian   │  │ • Hardware  │             │
│  └─────────────┘  └─────────────┘             │
│                                                  │
│  ┌────────────────────────────────────────┐    │
│  │     Integrations                       │    │
│  │  • Telegram Bot                        │    │
│  │  • Discord Bot                         │    │
│  │  • Twilio SMS/Voice + Hume EVI         │    │
│  │  • Guardian Mode (GPS/emergency)       │    │
│  │  • Sanctum Mode (focus/privacy)        │    │
│  └────────────────────────────────────────┘    │
│                                                  │
│  ┌────────────────────────────────────────┐    │
│  │        MCP Integration                 │    │
│  │  • Code execution sandbox              │    │
│  │  • Browser automation (Playwright)     │    │
│  │  • Notebook library server             │    │
│  │  • Agent dev server                    │    │
│  │  • Vision analysis (Gemini/Grok)       │    │
│  └────────────────────────────────────────┘    │
└──────────────────┬──────────────────────────────┘
                   │
      ┌────────────┼────────────┬────────────┐
      │            │            │            │
┌─────▼─────┐ ┌───▼────┐ ┌────▼─────┐ ┌────▼─────┐
│PostgreSQL │ │ChromaDB│ │MCP Servers│ │  Neo4j   │
│Persistence│ │Vectors │ │(Stdio)    │ │(Optional)│
└───────────┘ └────────┘ └──────────┘ └──────────┘
```

---

## 🔧 Tech Stack

### Backend
- **Python 3.11+** — Core runtime
- **Flask + flask-socketio** — API server with SSE and WebSocket streaming
- **PostgreSQL** — Primary database (conversation history, memory, call logs)
- **ChromaDB** — Vector embeddings for semantic search
- **Neo4j** — Graph database for Graph RAG (optional, local DB fallback)
- **RestrictedPython** — Sandboxed code execution

### LLM Providers
- **Grok (xAI)** — Native SDK + HTTP API, primary default
- **OpenRouter** — Multi-model gateway (100+ LLMs)
- **Mistral AI** — Direct API (Magistral reasoning models)
- **Venice AI** — Privacy-focused, uncensored models
- **Ollama** — Local model inference

### Voice Stack
- **Twilio** — Phone numbers, SMS, Media Streams (bidirectional audio)
- **Hume EVI** — Empathic voice interface (speech-to-speech)
- **Whisper** — Local speech-to-text
- **Pocket TTS** — Local text-to-speech server

### Communication
- **python-telegram-bot** — Telegram integration
- **WhatsApp (Node.js)** — WhatsApp bot
- **Discord** — Bot integration

### Frontend
- **React 18** — UI framework
- **TypeScript** — Type safety
- **Tailwind CSS** — Styling
- **Vite** — Build tool & dev server

### MCP Integration
- **Playwright** — Browser automation (Chromium)
- **Gemini 2.0 Flash** — Vision analysis (free tier)
- **fastmcp** — MCP protocol implementation
- **Notebook Library MCP** — Document processing and notebook management
- **Agent Dev MCP** — Agent development tools

---

## 🛠️ Tools Reference

### Memory Management
- `core_memory_append` — Add to agent's core memory
- `core_memory_replace` — Modify core memory
- `archival_memory_insert` — Store in long-term memory
- `archival_memory_search` — Semantic search across memories
- `memory_tag_tools` — Tag and filter memories

### Web & Research
- `fetch_webpage` — Retrieve and parse web pages
- `web_search` — DuckDuckGo search (free)
- `tavily_search` — Tavily AI-optimized search
- `arxiv_search` — Academic paper search
- `jina_reader` — Advanced web content extraction
- `deep_research` — Multi-step autonomous research (query decomposition → parallel search → synthesis)
- `pdf_reader` — Extract text from PDFs and ArXiv LaTeX sources

### Communication
- `discord_send_message` — Discord bot integration
- `phone_tool` — Twilio SMS send, call management, contact management
- `send_voice_message` — Send ElevenLabs voice messages

### Agent Autonomy (Level 2 & 3)
- `command_executor` — Whitelisted Linux command execution with audit logging
- `file_editor` — Syntax-validated file editing with auto-backup and rollback
- `git_workflow` — Git branch/commit/PR automation
- `service_controller` — Start/stop/restart agent systemd services

### Location & Places
- `google_places_tool` — Google Places search
- `places_search` — Location-based search

### MCP / Execution
- `execute_code` — Sandboxed Python execution (MCP)
- `browser_tool` — Full browser automation (navigate, screenshot, click, fill)
- `notebook_library_tool` — Document indexing and notebook search
- `agent_dev_tool` — Agent development and testing utilities

### Hardware & Integrations
- `spotify_control` — Spotify playback control
- `lovense_tool` — Lovense hardware control via MCP
- `sanctum_tool` — Control focus/privacy mode (on/off/status/queue)
- `cost_tools` — Query token usage and cost data

### Graph RAG (API endpoints)
- `GET /api/graph/nodes` — Get graph nodes
- `GET /api/graph/edges` — Get graph relationships
- `GET /api/graph/stats` — Graph statistics
- `POST /api/graph/rag` — Retrieve context from knowledge graph

---

## 📦 Installation

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ (optional, SQLite fallback available)
- An API key for at least one LLM provider

### Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Optional: Playwright for MCP browser automation
playwright install chromium
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### WhatsApp Bot Setup

```bash
cd whatsapp_bot
npm install
# Configure user_mapping.json (see user_mapping.json.example)
node bot.js
```

### Telegram Bot Setup

See [backend/TELEGRAM_SETUP.md](backend/TELEGRAM_SETUP.md) for full setup instructions.

```bash
# Add TELEGRAM_BOT_TOKEN to backend/.env
python backend/telegram_bot.py
```

---

## 📞 Voice & Telephony

The framework supports two voice call pipelines:

### Pipeline 1: STT → Consciousness Loop → TTS
Real-time bidirectional audio via Twilio Media Streams WebSocket:
- Caller audio → Twilio → Whisper STT → Consciousness Loop → TTS → Twilio → Caller
- Supports barge-in (caller can interrupt mid-response)
- Energy-based speech endpointing

### Pipeline 2: Hume EVI (speech-to-speech)
Lower latency pipeline using Hume's Empathic Voice Interface:
- Caller audio → Twilio → EVI (integrated STT + LLM + TTS) → Twilio → Caller
- Tool calls route through the substrate's MemoryTools
- Context injection (system prompt, memory blocks, Graph RAG)

See [docs/PHONE_SETUP_GUIDE.md](docs/PHONE_SETUP_GUIDE.md) for Twilio setup.

---

## 🛡️ Guardian Mode

Guardian Mode provides safety features for real-world awareness:
- **GPS Heartbeat** — Periodic location telemetry from mobile client
- **Emergency Triggers** — Panic button routes through the consciousness loop
- **Proactive Intervention** — Agent evaluates context and can reach out proactively
- **Apple Watch Biometrics** — Heart rate and activity data integration

Endpoints: `POST /api/guardian/heartbeat`, `POST /api/guardian/emergency`

---

## 🏰 Sanctum Mode

When the user is in an active DM conversation, Sanctum Mode automatically queues non-urgent channel @mentions instead of delivering them to the consciousness loop. An auto-reply is sent in the channel:

> "Assistant's in sanctum; will circle back when free."

Queued mentions are reviewed during heartbeats. The agent can also manually activate/deactivate via the `sanctum_tool`.

---

## 🔐 Security Features

### Code Execution Sandbox
- ✅ RestrictedPython compilation (no unsafe operations)
- ✅ 30-second timeout enforcement
- ✅ 512MB memory limit per execution
- ✅ Isolated workspace per session

### Level 2 Command Execution
- ✅ Command whitelist (only approved binaries)
- ✅ Rate limiting (max 15 commands/min)
- ✅ Full audit log at `/var/log/agent_dev_commands.log`
- ✅ Sandboxed to `/home/user`
- ✅ Dry-run mode for safe testing

### Level 3 File Editing
- ✅ Path sandboxing (restricted to `/home/user`)
- ✅ Syntax validation before write (Python, JSON, YAML, JS)
- ✅ Dangerous pattern detection (eval, exec, `__import__`)
- ✅ Timestamped auto-backup before every change
- ✅ Auto-rollback on validation failure

### Browser Automation
- ✅ Domain whitelist (Wikipedia, GitHub, ArXiv, etc.)
- ✅ Domain blacklist (banking, payments blocked)
- ✅ Rate limiting (10 nav/min, 5 screenshots/min)
- ✅ Headless mode only

### API Security
- ✅ Rate limiting on all endpoints
- ✅ CORS configuration
- ✅ Input sanitization
- ✅ API key validation

---

## 🚀 Service Deployment (systemd)

The repository includes systemd service files for production deployment:

| Service file | Description |
|---|---|
| `api-substrate.service` | Main backend API server |
| `api-telegram.service` | Telegram bot process |
| `substrate-agent.service` | Agent substrate (alternative config) |
| `substrate-telegram.service` | Telegram bot (alternative config) |
| `whatsapp_bot/nate-whatsapp.service` | WhatsApp bot |

```bash
sudo cp api-substrate.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable api-substrate
sudo systemctl start api-substrate
```

See [SERVICE_DEPLOYMENT.md](SERVICE_DEPLOYMENT.md) for full instructions.

---

## 🧪 Testing

```bash
# Backend startup test
cd backend
python test_startup.py

# MCP integration tests
python test_mcp_integration.py

# Level 3 demo (file editing)
python tools/test_level3_demo.py
```

---

## 🗺️ Roadmap

### Completed ✅
- [x] Multi-provider LLM support (Grok, OpenRouter, Mistral, Venice, Ollama)
- [x] Streaming SSE + WebSocket responses
- [x] PostgreSQL persistence
- [x] Memory system (core + archival + Miras architecture)
- [x] Tool execution framework (30+ tools)
- [x] MCP code execution sandbox
- [x] Browser automation (Playwright)
- [x] Vision analysis (Gemini + Grok multimodal)
- [x] Skills learning system
- [x] Cost tracking
- [x] **Miras Memory Architecture** (Retention Gates, Attentional Bias, Hierarchical Memory, Online Learning)
- [x] **Nested Learning System** (multi-frequency memory updates)
- [x] **Telegram bot** (text + image + document support)
- [x] **WhatsApp bot** (Node.js)
- [x] **Twilio SMS + voice calls** (bidirectional Media Streams)
- [x] **Hume EVI** (speech-to-speech voice interface)
- [x] **Local TTS/STT** (Pocket TTS + Whisper)
- [x] **Level 2 safe command execution** (whitelisted + audited)
- [x] **Level 3 file editing** (syntax validation, auto-backup, rollback)
- [x] **Git workflow automation**
- [x] **Guardian Mode** (GPS heartbeat, emergency triggers)
- [x] **Sanctum Mode** (focus/privacy for DMs)
- [x] **Daemon Mode** (24/7 persistent process)
- [x] **Notebook library MCP server**
- [x] **Agent dev MCP server**
- [x] **Emotional intensity analyzer**
- [x] systemd service deployment

### In Progress 🚧
- [ ] Additional MCP servers (filesystem, database)
- [ ] Collaborative skill libraries
- [ ] Advanced prompt engineering UI
- [ ] Multi-agent orchestration

### Planned 🎯
- [ ] Voice interface (mobile)
- [ ] Cloud deployment templates
- [ ] Plugin marketplace

---

## 📦 Project Structure

```
api_substrate/
├── backend/
│   ├── api/              # Flask route blueprints (chat, agents, voice, guardian, etc.)
│   ├── core/             # Consciousness loop, memory system, LLM clients, Miras
│   ├── services/         # Background services (Whisper, TTS, Graph RAG, emotional analysis)
│   ├── tools/            # Tool implementations (30+ tools)
│   ├── letta_compat/     # Letta/MemGPT import compatibility
│   └── telegram_bot.py   # Telegram bot entry point
├── frontend/             # React + TypeScript + Tailwind UI
├── mcp_servers/
│   ├── agent_dev/        # Agent development MCP server
│   └── notebook_library/ # Document indexing MCP server
├── whatsapp_bot/         # Node.js WhatsApp integration
├── docs/                 # Extended documentation
├── examples/             # Pre-configured agent templates
├── scripts/              # Setup and utility scripts
└── tests/                # Test suite
```

---

## 🤝 Contributing

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

### Code Standards
- Python: PEP 8, type hints, docstrings
- TypeScript: ESLint, Prettier, strict mode
- Tests: Add tests for new features
- Docs: Update relevant documentation

---

## 📄 License

See [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

### Technologies
- **xAI / Grok** — Primary LLM API
- **OpenRouter** — Multi-model API gateway
- **Mistral AI** — Direct API with reasoning models
- **Venice AI** — Privacy-focused LLM access
- **Anthropic MCP** — Model Context Protocol architecture
- **Playwright** — Browser automation framework
- **Gemini** — Vision analysis (Google)
- **PostgreSQL** — Database engine
- **ChromaDB** — Vector embeddings
- **Twilio** — Telephony infrastructure
- **Hume** — Empathic voice interface

### Research
- **Google Titans/Miras** — Advanced memory architecture (Retention Gates, Attentional Bias, Online Learning)
- **"It's All Connected"** — Test-time memorization and retention research

### Community
Built with inspiration from:
- Letta (formerly MemGPT) — Memory architecture patterns
- LangChain — Tool execution concepts
- AutoGPT — Agent autonomy ideas

---

## 📧 Support

- 🐛 **Bug Reports:** GitHub Issues
- 💬 **Questions:** GitHub Discussions
- 📖 **Documentation:** See `/docs` folder and individual `*.md` files
- 🔧 **Troubleshooting:** See [QUICK_START.md](QUICK_START.md)

---

**Built for developers who need production-ready AI agents.**

*Version 1.2.0 | Last Updated: March 2026*
