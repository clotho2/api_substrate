#!/bin/bash
# Quick Setup Script for WhatsApp Bot
# ====================================

set -e  # Exit on error

echo ""
echo "=========================================="
echo "  Assistant WHATSAPP BOT - SETUP"
echo "=========================================="
echo ""

# Check Node.js version
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found!"
    echo "   Install Node.js 18+ from: https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "❌ Node.js version too old: $(node -v)"
    echo "   Required: v18.0.0 or higher"
    exit 1
fi

echo "✅ Node.js version: $(node -v)"

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: package.json not found"
    echo "   Run this script from whatsapp_bot/ directory"
    exit 1
fi

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
npm install

echo ""
echo "✅ Dependencies installed"

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "📝 Creating .env configuration..."
    cp .env.example .env
    echo "✅ Created .env file"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and configure SUBSTRATE_API_URL"
    echo "   For your_url_here:"
    echo "   $ nano .env"
    echo "   Change: SUBSTRATE_API_URL=https://your_url_here"
else
    echo ""
    echo "✅ .env already exists"
fi

# Optional: Create user mapping
if [ ! -f "user_mapping.json" ]; then
    echo ""
    echo "📝 User mapping configuration (optional for cross-platform sessions):"
    echo "   $ cp user_mapping.json.example user_mapping.json"
    echo "   $ nano user_mapping.json"
    echo ""
    read -p "Create user_mapping.json now? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp user_mapping.json.example user_mapping.json
        echo "✅ Created user_mapping.json - edit it to configure cross-platform sessions"
    else
        echo "ℹ️  Skipped user mapping - bot will use default session IDs"
    fi
fi

# Test connection
echo ""
echo "=========================================="
echo "  TESTING SUBSTRATE CONNECTION"
echo "=========================================="
echo ""

node test-connection.js

echo ""
echo "=========================================="
echo "  SETUP COMPLETE!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Configure environment (if using your_url_here):"
echo "   $ nano .env"
echo "   Change SUBSTRATE_API_URL to your server"
echo ""
echo "2. (Optional) Configure cross-platform sessions:"
echo "   $ nano user_mapping.json"
echo ""
echo "3. Start the bot:"
echo "   $ npm start"
echo ""
echo "4. Scan QR code with WhatsApp"
echo ""
echo "For production deployment with PM2:"
echo "   $ npm install -g pm2"
echo "   $ pm2 start bot.js --name Assistant-whatsapp"
echo ""
echo "=========================================="
echo ""
