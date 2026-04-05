#!/usr/bin/env python3
"""
🚀 Substrate AI - Setup Wizard

Run this script to set up everything automatically:
    python setup.py

What it does:
1. Checks Python version
2. Creates Python virtual environment
3. Installs all dependencies
4. Walks you through API key configuration
5. Creates .env file
6. Installs frontend dependencies
7. Initializes the agent
8. Validates the setup
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


# ──────────────────────────────────────────────────────────
# Terminal helpers
# ──────────────────────────────────────────────────────────

class Colors:
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    BLUE   = '\033[94m'
    CYAN   = '\033[96m'
    BOLD   = '\033[1m'
    END    = '\033[0m'

def step(n, total, msg):
    print(f"\n{Colors.BLUE}{Colors.BOLD}[{n}/{total}]{Colors.END} {msg}")

def ok(msg):   print(f"  {Colors.GREEN}✅ {msg}{Colors.END}")
def warn(msg): print(f"  {Colors.YELLOW}⚠️  {msg}{Colors.END}")
def err(msg):  print(f"  {Colors.RED}❌ {msg}{Colors.END}")
def info(msg): print(f"  {Colors.CYAN}ℹ️  {msg}{Colors.END}")

def ask(prompt, default=""):
    """Prompt the user for input, showing the default in brackets."""
    display = f" [{default}]" if default else ""
    try:
        value = input(f"  {Colors.BOLD}{prompt}{display}: {Colors.END}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return value if value else default

def ask_yn(prompt, default=True):
    hint = "Y/n" if default else "y/N"
    try:
        value = input(f"  {Colors.BOLD}{prompt} ({hint}): {Colors.END}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if value in ("y", "yes"):
        return True
    if value in ("n", "no"):
        return False
    return default

def run(cmd, cwd=None):
    """Run a shell command and return (success, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        return r.returncode == 0, r.stdout, r.stderr
    except Exception as e:
        return False, "", str(e)


# ──────────────────────────────────────────────────────────
# Provider definitions
# ──────────────────────────────────────────────────────────

PROVIDERS = {
    "1": {
        "name": "Grok (xAI)",
        "env_key": "GROK_API_KEY",
        "model_key": "MODEL_NAME",
        "default_model": "grok-4-1-fast-reasoning",
        "key_hint": "starts with 'xai-'",
        "signup_url": "https://console.x.ai/",
        "notes": "Recommended. Fast reasoning, 131K context, free tier available.",
    },
    "2": {
        "name": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "model_key": "DEFAULT_LLM_MODEL",
        "default_model": "openrouter/auto",
        "key_hint": "starts with 'sk-or-v1-'",
        "signup_url": "https://openrouter.ai/keys",
        "notes": "Access to 100+ models (Claude, GPT-4, Llama, Mistral, etc.). Free tier available.",
    },
    "3": {
        "name": "Mistral AI",
        "env_key": "MISTRAL_API_KEY",
        "model_key": "MISTRAL_MODEL",
        "default_model": "magistral-medium-2509",
        "key_hint": "from console.mistral.ai",
        "signup_url": "https://console.mistral.ai/api-keys",
        "notes": "Direct Mistral API. Includes Magistral reasoning models.",
    },
    "4": {
        "name": "Venice AI",
        "env_key": "VENICE_API_KEY",
        "model_key": "DEFAULT_LLM_MODEL",
        "default_model": "venice/llama-3.3-70b",
        "key_hint": "from venice.ai",
        "signup_url": "https://venice.ai",
        "notes": "Privacy-focused, no conversation logging, uncensored models.",
    },
    "5": {
        "name": "Ollama (local)",
        "env_key": None,
        "model_key": "OLLAMA_MODEL",
        "default_model": "llama3.2",
        "key_hint": None,
        "signup_url": "https://ollama.ai/",
        "notes": "Run models locally. Requires Ollama installed on this machine.",
    },
}


def choose_provider():
    """Interactive provider selection. Returns the provider dict."""
    print(f"""
{Colors.BOLD}Choose your LLM provider:{Colors.END}

  1) Grok (xAI)     — Fast reasoning, 131K context  {Colors.GREEN}[recommended]{Colors.END}
  2) OpenRouter      — 100+ models via one API
  3) Mistral AI      — Direct Mistral + reasoning models
  4) Venice AI       — Privacy-focused, no logging
  5) Ollama (local)  — Run models on your machine
""")
    choice = ask("Enter number", "1")
    provider = PROVIDERS.get(choice, PROVIDERS["1"])
    print(f"\n  {Colors.GREEN}Selected: {provider['name']}{Colors.END}")
    info(provider["notes"])
    return provider


def configure_provider(provider, env_path: Path) -> dict:
    """
    Walk the user through entering their API key and model.
    Returns a dict of env var additions to write.
    """
    additions = {}

    # API key (Ollama local doesn't need one)
    if provider["env_key"]:
        print(f"\n  Get your key at: {Colors.CYAN}{provider['signup_url']}{Colors.END}")
        key = ask(f"Paste your {provider['name']} API key ({provider['key_hint']})", "")
        if key:
            additions[provider["env_key"]] = key
        else:
            warn(f"No key entered. Add {provider['env_key']} to backend/.env before starting.")
    else:
        info("Ollama runs locally — no API key needed.")
        additions["OLLAMA_API_URL"] = ask("Ollama base URL", "http://localhost:11434")

    # Model selection
    model = ask("Model name", provider["default_model"])
    additions[provider["model_key"]] = model

    return additions


# ──────────────────────────────────────────────────────────
# .env writer
# ──────────────────────────────────────────────────────────

def update_env_file(env_path: Path, updates: dict):
    """
    Write or update key=value pairs in an .env file.
    Existing keys are updated in-place; new keys are appended.
    """
    lines = []
    updated_keys = set()

    if env_path.exists():
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                lines.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
            else:
                lines.append(line)

    # Append keys not already present
    for key, value in updates.items():
        if key not in updated_keys:
            lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n")


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────

def main():
    print(f"""
{Colors.BOLD}╔═══════════════════════════════════════════════════════════╗
║        🧠 SUBSTRATE AI — SETUP WIZARD                     ║
║        Production-Ready AI Agent Framework                ║
╚═══════════════════════════════════════════════════════════╝{Colors.END}
""")

    project_root = Path(__file__).parent.absolute()
    backend_dir  = project_root / "backend"
    frontend_dir = project_root / "frontend"

    TOTAL = 7
    errors = []

    # ────────────────────────────────────
    # STEP 1: Python version
    # ────────────────────────────────────
    step(1, TOTAL, "Checking Python version...")

    pv = sys.version_info
    if pv.major < 3 or (pv.major == 3 and pv.minor < 10):
        err(f"Python 3.10+ required. You have {pv.major}.{pv.minor}")
        print("  Install Python 3.10+: https://www.python.org/downloads/")
        sys.exit(1)
    ok(f"Python {pv.major}.{pv.minor}.{pv.micro}")

    # ────────────────────────────────────
    # STEP 2: Virtual environment
    # ────────────────────────────────────
    step(2, TOTAL, "Setting up Python virtual environment...")

    venv_path = backend_dir / "venv"

    if venv_path.exists():
        ok("Virtual environment already exists")
    else:
        success, _, e = run(f"python3 -m venv {venv_path}")
        if success:
            ok("Virtual environment created")
        else:
            err(f"Failed to create venv: {e}")
            errors.append("venv creation")

    if sys.platform == "win32":
        pip_path    = venv_path / "Scripts" / "pip"
        python_path = venv_path / "Scripts" / "python"
    else:
        pip_path    = venv_path / "bin" / "pip"
        python_path = venv_path / "bin" / "python"

    # ────────────────────────────────────
    # STEP 3: Python dependencies
    # ────────────────────────────────────
    step(3, TOTAL, "Installing Python dependencies (this may take a few minutes)...")

    requirements_file = backend_dir / "requirements.txt"

    run(f"{pip_path} install --upgrade pip -q")

    success, _, e = run(f"{pip_path} install -r {requirements_file}", cwd=backend_dir)

    if success:
        ok("All Python dependencies installed")
    else:
        warn("Some packages may have failed. Installing essentials individually...")
        for pkg in [
            "flask", "flask-cors", "flask-socketio", "python-dotenv",
            "openai", "chromadb", "aiohttp", "httpx", "psutil",
            "pydantic", "tiktoken", "requests", "colorama",
        ]:
            run(f"{pip_path} install {pkg} -q")
        ok("Essential packages installed")
        errors.append("some optional packages may be missing — re-run 'pip install -r requirements.txt' to retry")

    # ────────────────────────────────────
    # STEP 4: Configuration
    # ────────────────────────────────────
    step(4, TOTAL, "Configuring environment...")

    env_file    = backend_dir / ".env"
    env_example = backend_dir / ".env.example"

    if not env_file.exists():
        if env_example.exists():
            shutil.copy(env_example, env_file)
            ok(".env created from template")
        else:
            env_file.write_text("# Substrate AI Configuration\n")
            ok(".env file created")
    else:
        ok(".env file already exists")

    # Interactive provider configuration
    if ask_yn("\nConfigure your LLM provider now?", default=True):
        provider = choose_provider()
        additions = configure_provider(provider, env_file)
        update_env_file(env_file, additions)
        ok(f"{provider['name']} written to backend/.env")
    else:
        warn("Skipped provider config — edit backend/.env before starting the server.")

    # Create necessary data directories
    for d in [
        backend_dir / "logs",
        backend_dir / "data" / "db",
        backend_dir / "data" / "chromadb",
    ]:
        d.mkdir(parents=True, exist_ok=True)
    ok("Data directories created")

    # ────────────────────────────────────
    # STEP 5: Frontend
    # ────────────────────────────────────
    step(5, TOTAL, "Setting up frontend...")

    npm_ok, _, _ = run("npm --version")

    if not npm_ok:
        warn("npm not found — skipping frontend setup.")
        info("Install Node.js 18+ from https://nodejs.org/ then run 'npm install' in frontend/")
        errors.append("frontend (npm not found)")
    else:
        success, _, e = run("npm install", cwd=frontend_dir)
        if success:
            ok("Frontend dependencies installed")
        else:
            warn(f"Frontend install had issues: {e[:120]}")
            errors.append("frontend npm install")

    # ────────────────────────────────────
    # STEP 6: Initialize agent
    # ────────────────────────────────────
    step(6, TOTAL, "Initializing agent...")

    setup_agent_script = backend_dir / "setup_agent.py"

    if setup_agent_script.exists():
        success, out, e = run(f"{python_path} setup_agent.py", cwd=backend_dir)
        if success:
            ok("Agent initialized")
        else:
            warn(f"Agent init had issues (you can fix this later): {e[:120]}")
            errors.append("agent initialization — run 'python backend/setup_agent.py' manually")
    else:
        warn("setup_agent.py not found — skipping agent init.")

    # ────────────────────────────────────
    # STEP 7: Validate
    # ────────────────────────────────────
    step(7, TOTAL, "Validating setup...")

    checks = [
        (backend_dir / "api" / "server.py",              "Backend server"),
        (backend_dir / "core" / "consciousness_loop.py", "Consciousness loop"),
        (backend_dir / "core" / "memory_system.py",      "Memory system"),
        (frontend_dir / "src" / "App.tsx",                "Frontend app"),
        (backend_dir / ".env",                            "Configuration file"),
    ]

    for path, name in checks:
        if path.exists():
            ok(name)
        else:
            err(f"{name} missing: {path}")

    # ────────────────────────────────────
    # Summary
    # ────────────────────────────────────
    print(f"\n{Colors.BOLD}{'═'*60}{Colors.END}\n")

    if errors:
        print(f"{Colors.YELLOW}⚠️  Setup completed with warnings:{Colors.END}")
        for e in errors:
            print(f"   • {e}")
    else:
        print(f"{Colors.GREEN}✅ Setup complete!{Colors.END}")

    print(f"""
{Colors.BOLD}📝 NEXT STEPS:{Colors.END}

1. {Colors.YELLOW}Confirm your API key in backend/.env{Colors.END}
   Make sure the key for your chosen provider is present and correct.

2. {Colors.YELLOW}Start the backend:{Colors.END}
   cd backend
   source venv/bin/activate  {Colors.CYAN}# Windows: venv\\Scripts\\activate{Colors.END}
   python api/server.py

3. {Colors.YELLOW}Start the frontend (new terminal):{Colors.END}
   cd frontend
   npm run dev

4. {Colors.YELLOW}Open in browser:{Colors.END}
   http://localhost:5173

{Colors.BOLD}⚡ Or launch everything at once:{Colors.END}
   ./start.sh

{Colors.BOLD}📖 Optional integrations (configure in backend/.env):{Colors.END}
   Telegram bot  → backend/TELEGRAM_SETUP.md
   Phone & SMS   → docs/PHONE_SETUP_GUIDE.md
   PostgreSQL    → backend/POSTGRESQL_SETUP.md
   Voice calls   → docs/PHONE_SETUP_GUIDE.md

{Colors.GREEN}Enjoy building with Substrate AI! 🚀{Colors.END}
""")


if __name__ == "__main__":
    main()
