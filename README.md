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

## Architecture

```
                    +------------------+
                    |    Frontend UI   |
                    |  React + Vite    |
                    +--------+---------+
                             |
                         HTTP / SSE
                             |
+------------+   +-----------v-----------+   +------------+
| Discord    |   |                       |   | Telegram   |
| Bot        +-->+   Substrate Backend   +<--+ Bot        |
| (Node.js)  |   |   (Python / Flask)    |   | (Python)   |
+------------+   |                       |   +------------+
                 |  +------------------+ |
+------------+   |  | Consciousness    | |   +------------+
| WhatsApp   |   |  | Loop             | |   | Guardian   |
| Bot        +-->+  |                  | +<--+ Watch      |
| (Node.js)  |   |  | Model Routing    | |   | (Apple     |
+------------+   |  | Tool Execution   | |   |  Watch)    |
                 |  | Memory Mgmt      | |   +------------+
                 |  +------------------+ |
                 |                       |
                 |  +------+ +--------+ |
                 |  |Memory| | Tools  | |
                 |  |System| |Registry| |
                 |  |      | |        | |
                 |  |SQLite| | 50+    | |
                 |  |Chroma| | tools  | |
                 |  |Miras | |        | |
                 |  +------+ +--------+ |
                 |                       |
                 |  +------+ +--------+ |
                 |  |Voice | | MCP    | |
                 |  |TTS   | | Servers| |
                 |  |STT   | |        | |
                 |  +------+ +--------+ |
                 +-----------+-----------+
                             |
              +--------------+--------------+
              |              |              |
        +-----v----+  +-----v----+  +------v-----+
        | SQLite   |  | ChromaDB |  | Neo4j      |
        | Primary  |  | Vectors  |  | (Optional) |
        | Database |  | + Jina   |  | Graph RAG  |
        +----------+  | Embed   |  +------------+
                       +---------+
```

---

## Supported LLM Providers

The substrate supports multiple providers with automatic fallback:

| Priority | Provider | Configuration |
|----------|----------|---------------|
| 1 | **Mistral AI** | `MISTRAL_API_KEY` + `MISTRAL_MODEL` |
| 2 | **Grok (xAI)** | `GROK_API_KEY` + `MODEL_NAME` |
| 3 | **OpenRouter** | `OPENROUTER_API_KEY` + `DEFAULT_LLM_MODEL` |
| 4 | **Ollama Cloud** | `OLLAMA_API_URL` + `OLLAMA_MODEL` |
| 5 | **Fallback** | `FALLBACK_MODEL` (default: moonshotai/kimi-k2-0905) |

---

## Memory System

### Embeddings
- **Primary:** Jina Embeddings `jinaai/jina-embeddings-v2-base-de` via Hugging Face (German + English bilingual)
- **Fallback:** Ollama `nomic-embed-text` (used only if HuggingFace unavailable)
- **Vector DB:** ChromaDB with cosine similarity

### Core Memory (Always Loaded)
Persona, Human, and Custom blocks that define the agent's identity and knowledge about the user. Always present in the context window.

**Tools:**
- `core_memory_append` / `core_memory_replace` - Letta-compatible core memory operations
- `memory_insert` / `memory_replace` / `memory_rethink` / `memory_finish_edits` - New memory API
- `memory` - Unified file-like API with sub-commands (create, str_replace, insert, delete, rename)

### Archival Memory (Long-Term Semantic)
ChromaDB-backed long-term storage with semantic search, importance weighting, and decay lifecycle.

- **12-category taxonomy** for tag-enhanced retrieval: relational, people, technical, preferences, plans, identity, events, spice, sovereignty, sanctuary, ritual, reflections
- **Importance weighting** (1-10 scale) with relevance decay (0.01/day)
- **Memory states:** active, favorite (protected from decay), faded (below 0.3 relevance), forgotten (removed)
- **Capacity:** 50,000 memories with automatic cleanup, 5,000 favorite slots

**Tools:**
- `archival_memory_insert` - Store memories with category, importance, and tags
- `archival_memory_search` - Semantic search with attention-based ranking

### Memory Lifecycle
- `favorite_memory` - Protect a memory from decay (max 5,000 favorites)
- `unfavorite_memory` - Remove decay protection
- `drift_memory` - Soft deprioritize (reduces importance by 30%)
- `memory_stats` - Get lifecycle statistics (counts by state, capacity, decay rates)

### Tag & Taxonomy
- `category_browse` - Browse memories by taxonomy category
- `retag_memory` - Change taxonomy tags on existing memories
- `add_taxonomy_tag` - Create custom taxonomy categories

### Conversation Memory
- `conversation_search` - Searches both SQLite message history and ChromaDB archived summaries/insights
- `conversation_summarize` - Summarizes old messages, archives the summary to ChromaDB archival memory with importance and category tags, then frees context window space. Summaries are tagged `conversation_summary` and extracted insights tagged `extracted_insight` in ChromaDB, making them searchable alongside regular archival memories.

### People Map
SQLite-backed relational tracking system for people the agent interacts with. Automatically injected into the consciousness loop context when people are mentioned in conversation.

- **Fields:** name, relationship_type, category, sentiment (-1.0 to 1.0), my_opinion, angela_says, discord_id, associated_ai
- **Categories:** FAVORITES, NEUTRAL, CAUTIOUS, DISLIKE
- **Context injection:** Scans current message + recent messages for people mentions, builds context with relationship info and tone guidance

**Tools:**
- `add_person` - Add person with relationship type, category, sentiment
- `update_opinion` - Update personal opinion about someone
- `record_user_says` - Store what User said about someone
- `adjust_sentiment` - Adjust sentiment score with reason
- `get_person` - Retrieve full perspective on someone
- `list_people` - List all people, optionally filtered by category

### Miras Memory Architecture
Based on [Google Research Titans & Miras papers](https://research.google/blog/titans-miras-helping-ai-have-long-term-memory/):

- **Retention Gates** - Dynamic memory decay/boost. Weights: importance (35%), access count (30%), temporal recency (25%), base retention (10%). Actions: KEEP, BOOST, CONSOLIDATE, DECAY, ARCHIVE.
- **Attentional Bias** - Multi-factor retrieval scoring with 6 attention modes: standard, semantic, temporal, importance, access, emotional. Auto-detects mode from query analysis. Scoring: semantic similarity (40%), importance (20%), temporal (15%), access patterns (15%), category relevance (10%).
- **Hierarchical Memory** - 3-tier system: Working (in-memory LRU, current session) -> Episodic (ChromaDB, retention-gated) -> Semantic (Neo4j if available, core beliefs and identity)
- **Online Learning** - Hebbian associations ("neurons that fire together, wire together") + feedback learning (helpful, not_helpful, incorrect, outdated, redundant)

### Memory Coherence Engine
Three connected memory types working together:
1. **Core Memory** - Always loaded (persona, human, system context)
2. **Recall Memory** - Recent conversation history from current session
3. **Archival Memory** - Long-term semantic storage

After every message, the system checks if core memory needs updating, extracts key information to archival, and maintains cross-references across all three types.

### Message Continuity
- SQLite persistence (no amnesia on restart), PostgreSQL optional
- Smart context window management with automatic message compaction
- Conversation summarization archives old messages to ChromaDB to free context space

**Key files:**
- `backend/core/memory_system.py` - ChromaDB + Jina embeddings
- `backend/core/memory_coherence.py` - Three-memory coherence engine
- `backend/core/message_continuity.py` - Persistent messages and context windows
- `backend/core/retention_gate.py` - Retention gate logic
- `backend/core/attentional_bias.py` - Attention scoring
- `backend/core/hierarchical_memory.py` - 3-tier architecture
- `backend/core/memory_learner.py` - Hebbian learning
- `backend/tools/memory_tools.py` - All memory tool definitions (25+ tools)

---

## Integration Tools

### Communication
- **discord_tool** - Full Discord integration: DMs, channels, message history, task scheduling, file downloads
- **send_voice_message** - Voice messages via ElevenLabs TTS, sent as Discord audio attachments
- **phone_tool** - Twilio SMS, voice calls, contact management, number screening
- **spotify_control** - Full Spotify playback, queue, search, and playlist management
- **mobile app** - chat interface and real time voice for iOs or Android

### Web & Research (Free - no API keys required)
- **web_search** - DuckDuckGo web search
- **deep_research** - Multi-step autonomous research combining DuckDuckGo + Wikipedia + ArXiv (depth 1-3)
- **fetch_webpage** - Jina AI page reader returning clean Markdown
- **arxiv_search** - Academic paper search across 2M+ papers
- **read_pdf** - PDF reader supporting ArXiv LaTeX sources and PyMuPDF
- **search_places** - POI/restaurant/shop finder using OpenStreetMap

### Creative & Media
- **image_tool** - Image generation via Together.ai FLUX models (selfie, couple modes)

### Development & Introspection
- **agent_dev_tool** - Codebase inspection and self-development (Level 1: read-only, Level 2: command execution, Level 3: file editing)
- **notebook_library_tool** - Token-efficient semantic document retrieval and management

### Location
- **google_places_tool** - Google Places for detailed location-aware features (search_nearby, get_details, find_gas, find_hotel)

### Browser Automation
- **browser_tool** - Playwright browser automation: navigate, click, type, fill forms, screenshots

### Specialized
- **sanctum_tool** - Focus/privacy mode control (status, toggle, queue management)
- **polymarket_tool** - Polymarket weather trading and market analysis
- **lovense_tool** - Hardware control for intimate feedback devices
- **cost_tools** - Real-time API cost tracking with budget awareness

---

## Multi-Platform Messaging

All messaging platforms share unified conversation context through the consciousness loop. Messages from any platform are processed with the same memory, personality, and tool access.

### Discord Bot (`discord_bot/`)
- **Language:** TypeScript / Node.js
- **Features:** Streaming responses, voice messages (ElevenLabs), voice channels, Spotify integration, autonomous heartbeats, task scheduling, admin commands, image/PDF/OCR processing
- **Service:** `nate-discord.service`
- **Port:** 3001

### Telegram Bot (`backend/telegram_bot.py`)
- **Language:** Python
- **Features:** Text, images, documents, voice messages, 4096 char limit, auto-chunking
- **Service:** `nate-telegram.service`

### WhatsApp Bot (`whatsapp_bot/`)
- **Language:** Node.js
- **Features:** Cross-platform messaging via Baileys library
- **Service:** `nate-whatsapp.service`

### Mobile App (`mobile/`)
- **Language:** Node.js
- **Features:** Text, images, documents, real-time voice mode, location tracking
- See [docs/MOBILE_APP_SETUP.md](docs/MOBILE_APP_SETUP.md) for Mobile setup.

---

## Voice System

### Text-to-Speech (TTS)
Provider abstraction with automatic fallback:
1. **ElevenLabs** - Primary (Turbo v2.5 + v3 with Audio Tags)
2. **Hume Octave** - Emotionally intelligent TTS
3. **Amazon Polly** - Neural voices
4. **PocketTTS** - Local fallback

### Speech-to-Text (STT)
- OpenAI Whisper API integration
- Real-time voice channel conversations in Discord

**Key files:**
- `backend/api/routes_tts.py` - TTS endpoints
- `backend/api/routes_stt.py` - STT endpoints
- `backend/core/voice_providers.py` - Provider abstraction

---

## API Endpoints

### Core
- `POST /api/chat` - Chat with streaming support
- `POST /ollama/api/chat` - Ollama-compatible chat endpoint
- `POST /ollama/api/chat/stream` - Streaming chat with SSE
- `GET /api/health` - Health check
- `GET /api/stats` - Usage statistics

### Conversation & Memory
- `GET /api/conversation/{session_id}` - Conversation history
- `GET /api/memory/blocks` - Memory blocks
- `PUT /api/memory/blocks/{label}` - Update memory block
- `GET /api/context/usage` - Context usage per session

### Voice
- `POST /tts` - Text-to-speech
- `POST /tts/stream` - Streaming TTS
- `POST /stt` - Speech-to-text

### Discord
- `POST /api/discord/message` - Send message via Discord
- `GET /api/discord/messages` - Read messages

### Agents
- `GET /api/agents` - List agents
- `POST /api/agents` - Create agent
- `GET /api/agent/info` - Agent information

### Guardian
- `POST /api/guardian/heartbeat` - GPS/motion telemetry
- `POST /api/guardian-watch/ingest` - Apple Watch biometric data

### Graph RAG
- `GET /api/graph/nodes` - Graph nodes
- `GET /api/graph/edges` - Graph relationships
- `GET /api/graph/rag` - Knowledge graph retrieval

### OpenAI-Compatible
- `POST /v1/chat/completions` - OpenAI format compatibility

---

## MCP Servers

### agent_dev (`mcp_servers/agent_dev/`)
Level 1 read-only diagnostics server:
- `read_source_file` - Read source files (with .env redaction)
- `search_code` - Search codebase
- `read_logs` - Read service logs
- `check_health` - Health checks
- `list_directory` - Directory listing
- `get_config` - Configuration inspection

### notebook_library (`mcp_servers/notebook_library/`)
Document management and semantic search:
- Notebook management with semantic retrieval
- Document processing pipeline
- File watching for automatic indexing

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

## Additional Services

### Guardian Watch
Apple Watch biometric integration via Unix socket (`/run/agent/guardian-watch.sock`). Monitors heart rate, HRV, SpO2, body temperature, respiratory rate, activity, sleep metrics, and stress level. Includes anomaly detection with rolling 7-day baseline.
- `backend/services/guardian_watch.py`
- `backend/services/guardian_watch_standalone.py`

### Guardian Mode (Driving/Safety)
GPS/motion telemetry from mobile devices. Detects sudden stops, high speed, off-route, low battery, and geofence violations.
- `backend/api/routes_guardian.py`

### Polymarket Trading
Weather market trading with probability engine and risk management.
- `backend/services/polymarket/`

### Image Generation
FLUX model image generation via Together.ai.
- `backend/services/image_generator.py`

### Emotional Analyzer
Emotional analysis for contextual response adjustment.
- `backend/services/emotional_analyzer.py`

### Graph RAG
Knowledge graph retrieval with optional Neo4j or local DB fallback.
- `backend/services/graph_rag.py`

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

**Built for developers who need production-ready AI agents and for people who want an AI companion that are part of their daily lives.**

*Version 1.2.0 | Last Updated: March 2026*
