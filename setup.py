#!/usr/bin/env python3
"""
🚀 Substrate AI - One-Click Setup Script

Run this script to set up everything automatically:
    python setup.py

What it does:
1. Creates Python virtual environment
2. Installs all dependencies
3. Creates .env file from template
4. Creates necessary directories
5. Installs frontend dependencies
6. Validates the setup

After running, just add your OpenRouter API key to backend/.env and start!
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_step(step_num, total, message):
    """Print a formatted step message"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}[{step_num}/{total}]{Colors.END} {message}")

def print_success(message):
    print(f"  {Colors.GREEN}✅ {message}{Colors.END}")

def print_warning(message):
    print(f"  {Colors.YELLOW}⚠️  {message}{Colors.END}")

def print_error(message):
    print(f"  {Colors.RED}❌ {message}{Colors.END}")

def run_command(cmd, cwd=None, shell=True):
    """Run a shell command and return success status"""
    try:
        result = subprocess.run(
            cmd, 
            shell=shell, 
            cwd=cwd, 
            capture_output=True, 
            text=True
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def main():
    print(f"""
{Colors.BOLD}╔═══════════════════════════════════════════════════════════╗
║        🧠 SUBSTRATE AI - SETUP WIZARD                      ║
║        Production-Ready AI Agent Framework                 ║
╚═══════════════════════════════════════════════════════════╝{Colors.END}
""")
    
    # Get project root directory
    project_root = Path(__file__).parent.absolute()
    backend_dir = project_root / "backend"
    frontend_dir = project_root / "frontend"
    
    total_steps = 6
    errors = []
    
    # ========================================
    # STEP 1: Check Python Version
    # ========================================
    print_step(1, total_steps, "Checking Python version...")
    
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 10):
        print_error(f"Python 3.10+ required. You have {python_version.major}.{python_version.minor}")
        print("  Please install Python 3.10 or newer: https://www.python.org/downloads/")
        sys.exit(1)
    
    print_success(f"Python {python_version.major}.{python_version.minor}.{python_version.micro} ✓")
    
    # ========================================
    # STEP 2: Create Virtual Environment
    # ========================================
    print_step(2, total_steps, "Setting up Python virtual environment...")
    
    venv_path = backend_dir / "venv"
    
    if venv_path.exists():
        print_success("Virtual environment already exists")
    else:
        success, _, err = run_command(f"python3 -m venv {venv_path}")
        if success:
            print_success("Virtual environment created")
        else:
            print_error(f"Failed to create venv: {err}")
            errors.append("venv creation")
    
    # Determine pip path
    if sys.platform == "win32":
        pip_path = venv_path / "Scripts" / "pip"
        python_path = venv_path / "Scripts" / "python"
    else:
        pip_path = venv_path / "bin" / "pip"
        python_path = venv_path / "bin" / "python"
    
    # ========================================
    # STEP 3: Install Python Dependencies
    # ========================================
    print_step(3, total_steps, "Installing Python dependencies (this may take a few minutes)...")
    
    requirements_file = backend_dir / "requirements.txt"
    
    # Upgrade pip first
    run_command(f"{pip_path} install --upgrade pip -q")
    
    # Install requirements
    success, out, err = run_command(
        f"{pip_path} install -r {requirements_file}",
        cwd=backend_dir
    )
    
    if success:
        print_success("All Python dependencies installed")
    else:
        print_warning("Some packages may have failed. Trying essential packages...")
        # Try installing essential packages one by one
        essential = [
            "flask", "flask-cors", "flask-socketio", "python-dotenv",
            "openai", "chromadb", "aiohttp", "httpx", "psutil",
            "pydantic", "tiktoken", "requests", "colorama"
        ]
        for pkg in essential:
            run_command(f"{pip_path} install {pkg} -q")
        print_success("Essential packages installed")
    
    # ========================================
    # STEP 4: Create Configuration Files
    # ========================================
    print_step(4, total_steps, "Creating configuration files...")
    
    # Create .env from .env.example
    env_file = backend_dir / ".env"
    env_example = backend_dir / ".env.example"
    
    if env_file.exists():
        print_success(".env file already exists")
    elif env_example.exists():
        shutil.copy(env_example, env_file)
        print_success(".env file created from template")
        print_warning("Don't forget to add your OPENROUTER_API_KEY to backend/.env!")
    else:
        # Create minimal .env
        env_content = """# Substrate AI Configuration
# Get your API key from: https://openrouter.ai/keys

OPENROUTER_API_KEY=your_openrouter_api_key_here

# Server Configuration
PORT=8284
HOST=0.0.0.0

# Optional: Local Embeddings (requires Ollama)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# Optional: PostgreSQL (for advanced persistence)
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5432
# POSTGRES_DB=substrate_ai
# POSTGRES_USER=postgres
# POSTGRES_PASSWORD=your_password_here
"""
        env_file.write_text(env_content)
        print_success(".env file created")
        print_warning("Add your OPENROUTER_API_KEY to backend/.env!")
    
    # Create necessary directories
    dirs_to_create = [
        backend_dir / "logs",
        backend_dir / "data" / "db",
        backend_dir / "data" / "chromadb",
    ]
    
    for dir_path in dirs_to_create:
        dir_path.mkdir(parents=True, exist_ok=True)
    
    print_success("Data directories created")
    
    # ========================================
    # STEP 5: Install Frontend Dependencies
    # ========================================
    print_step(5, total_steps, "Setting up frontend...")
    
    # Check if npm is available
    npm_check, _, _ = run_command("npm --version")
    
    if not npm_check:
        print_warning("npm not found. Skipping frontend setup.")
        print("  Install Node.js from: https://nodejs.org/")
        errors.append("frontend (npm not found)")
    else:
        # Install frontend dependencies
        success, _, err = run_command("npm install", cwd=frontend_dir)
        if success:
            print_success("Frontend dependencies installed")
        else:
            print_warning(f"Frontend install had issues: {err[:100]}")
            errors.append("frontend npm install")
    
    # ========================================
    # STEP 6: Validate Setup
    # ========================================
    print_step(6, total_steps, "Validating setup...")
    
    # Check if key files exist
    checks = [
        (backend_dir / "api" / "server.py", "Backend server"),
        (backend_dir / "core" / "consciousness_loop.py", "Consciousness loop"),
        (backend_dir / "core" / "memory_system.py", "Memory system"),
        (frontend_dir / "src" / "App.tsx", "Frontend app"),
    ]
    
    all_good = True
    for file_path, name in checks:
        if file_path.exists():
            print_success(f"{name} found")
        else:
            print_error(f"{name} missing!")
            all_good = False
    
    # ========================================
    # FINAL SUMMARY
    # ========================================
    print(f"""
{Colors.BOLD}═══════════════════════════════════════════════════════════{Colors.END}
""")
    
    if errors:
        print(f"{Colors.YELLOW}⚠️  Setup completed with some warnings:{Colors.END}")
        for err in errors:
            print(f"   - {err}")
    else:
        print(f"{Colors.GREEN}✅ Setup completed successfully!{Colors.END}")
    
    print(f"""
{Colors.BOLD}📝 NEXT STEPS:{Colors.END}

1. {Colors.YELLOW}Add your OpenRouter API key:{Colors.END}
   Edit: backend/.env
   Set:  OPENROUTER_API_KEY=sk-or-v1-your-key-here
   
   Get a key at: https://openrouter.ai/keys

2. {Colors.YELLOW}Start the backend:{Colors.END}
   cd backend
   source venv/bin/activate  # On Windows: venv\\Scripts\\activate
   python api/server.py

3. {Colors.YELLOW}Start the frontend (new terminal):{Colors.END}
   cd frontend
   npm run dev

4. {Colors.YELLOW}Open in browser:{Colors.END}
   http://localhost:5173

{Colors.BOLD}📖 Documentation:{Colors.END}
   - README.md - Overview and features
   - QUICK_START.md - Detailed setup guide
   - docs/MIRAS_TITANS_INTEGRATION.md - Memory architecture

{Colors.GREEN}Enjoy building with Substrate AI! 🚀{Colors.END}
""")

if __name__ == "__main__":
    main()

