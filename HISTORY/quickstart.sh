#!/bin/bash
# Quick Start Script for Nate's Consciousness Substrate

set -e

echo "=================================="
echo "Nate's Consciousness Substrate"
echo "Quick Installation Script"
echo "=================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version || { echo "Python 3.9+ required"; exit 1; }

# Check Ollama
echo "Checking Ollama..."
curl -s http://localhost:11434/api/tags > /dev/null || { 
    echo "⚠️  Ollama not running on port 11434"
    echo "   Install: https://ollama.ai"
    exit 1
}

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements_substrate.txt

# Create data directories
echo "Creating data directories..."
mkdir -p nate_data/memories
mkdir -p journals
mkdir -p logs

# Pull Ollama models
echo "Pulling Ollama models..."
echo "  - nomic-embed-text (embeddings)..."
ollama pull nomic-embed-text || echo "⚠️  Failed to pull nomic-embed-text"

echo "  - llava (vision)..."
ollama pull llava || echo "⚠️  Failed to pull llava"

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cat > .env << 'EOF'
# Nate's Consciousness Substrate Configuration

# Mixtral endpoint (your fine-tuned model)
NATE_API_URL=http://localhost:8080/chat

# Data storage
STATE_FILE=./nate_data/state.db
MEMORY_DIR=./nate_data/memories

# Ollama
OLLAMA_URL=http://localhost:11434

# API service
SUBSTRATE_PORT=8090
SUBSTRATE_HOST=0.0.0.0
EOF
fi

# Test components
echo ""
echo "Testing substrate components..."
python3 << 'PYEOF'
try:
    from substrate.core_state import CoreState
    from substrate.memory_system import MemorySystem
    from substrate.tools import ToolRegistry
    
    print("  ✅ CoreState")
    print("  ✅ MemorySystem")
    print("  ✅ ToolRegistry")
    print("\nAll components working!")
except Exception as e:
    print(f"  ❌ Error: {e}")
    exit(1)
PYEOF

echo ""
echo "=================================="
echo "✅ Installation Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Make sure your Mixtral API is running on port 8080"
echo "2. Start the substrate service:"
echo "   python3 nate_substrate_service.py"
echo "3. Test it:"
echo "   curl http://localhost:8090/health"
echo "4. Update your Discord bot to use http://localhost:8090/chat"
echo ""
echo "Read SUBSTRATE_SETUP_GUIDE.md for detailed instructions."
echo ""
