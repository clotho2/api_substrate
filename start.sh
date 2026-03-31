#!/bin/bash
# ==============================================
# 🚀 Substrate AI - Quick Start Script
# ==============================================
# Usage: ./start.sh [backend|frontend|both]
# ==============================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           🧠 SUBSTRATE AI - LAUNCHER                      ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"

# Function to check if port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to kill process on port
kill_port() {
    if check_port $1; then
        echo -e "${YELLOW}⚠️  Port $1 in use. Freeing it...${NC}"
        lsof -ti:$1 | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

# Function to start backend
start_backend() {
    echo -e "\n${GREEN}🔧 Starting Backend...${NC}"
    
    # Check for .env file
    if [ ! -f "$BACKEND_DIR/.env" ]; then
        echo -e "${YELLOW}⚠️  No .env file found. Creating from template...${NC}"
        if [ -f "$BACKEND_DIR/.env.example" ]; then
            cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
        fi
        echo -e "${YELLOW}   Run 'python setup.py' to configure your API key, or edit backend/.env directly.${NC}"
        exit 1
    fi

    # Check that at least one provider API key is configured
    has_key=false
    for key_name in GROK_API_KEY OPENROUTER_API_KEY MISTRAL_API_KEY VENICE_API_KEY; do
        value=$(grep -E "^${key_name}=" "$BACKEND_DIR/.env" 2>/dev/null | cut -d= -f2-)
        if [ -n "$value" ] && ! echo "$value" | grep -qiE "your_.*_api_key_here|^$"; then
            has_key=true
            break
        fi
    done
    # Ollama cloud: needs both OLLAMA_API_URL and OLLAMA_MODEL
    ollama_url=$(grep -E "^OLLAMA_API_URL=" "$BACKEND_DIR/.env" 2>/dev/null | cut -d= -f2-)
    ollama_model=$(grep -E "^OLLAMA_MODEL=" "$BACKEND_DIR/.env" 2>/dev/null | cut -d= -f2-)
    if [ -n "$ollama_url" ] && [ -n "$ollama_model" ]; then
        has_key=true
    fi

    if [ "$has_key" = false ]; then
        echo -e "${RED}❌ No API key found in backend/.env${NC}"
        echo -e "${YELLOW}   Set one of: GROK_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, or VENICE_API_KEY${NC}"
        echo -e "${YELLOW}   Or run: python setup.py  to configure interactively${NC}"
        exit 1
    fi
    
    # Kill existing process on port 8284
    kill_port 8284
    
    # Activate venv and start
    cd "$BACKEND_DIR"
    
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}⚠️  No venv found. Running setup first...${NC}"
        cd "$PROJECT_ROOT"
        python3 setup.py
        cd "$BACKEND_DIR"
    fi
    
    source venv/bin/activate
    
    echo -e "${GREEN}✅ Backend starting on http://localhost:8284${NC}"
    python api/server.py
}

# Function to start frontend
start_frontend() {
    echo -e "\n${GREEN}🎨 Starting Frontend...${NC}"
    
    # Kill existing process on port 5173
    kill_port 5173
    
    cd "$FRONTEND_DIR"
    
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}⚠️  No node_modules. Installing...${NC}"
        npm install
    fi
    
    echo -e "${GREEN}✅ Frontend starting on http://localhost:5173${NC}"
    npm run dev
}

# Function to start both
start_both() {
    echo -e "${BLUE}Starting both backend and frontend...${NC}"
    
    # Start backend in background
    start_backend &
    BACKEND_PID=$!
    
    # Wait for backend to be ready
    echo -e "${YELLOW}Waiting for backend to start...${NC}"
    sleep 5
    
    # Start frontend in foreground
    start_frontend
    
    # Cleanup on exit
    trap "kill $BACKEND_PID 2>/dev/null" EXIT
}

# Main logic
case "${1:-both}" in
    backend)
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    both)
        start_both
        ;;
    *)
        echo "Usage: ./start.sh [backend|frontend|both]"
        exit 1
        ;;
esac

