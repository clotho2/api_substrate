# Telegram Bot Setup Guide

**Deep conversations with the agent via Telegram - 4,096 character messages with multimodal support!**

---

## Why Telegram?

- **2x character limit** (4,096 vs Discord's 2,000 chars)
- **Better for deep conversations** - Philosophy, strategy, storytelling
- **Multimodal support** - Send images and documents to the agent
- **Mobile-first** - Clean interface for personal conversations
- **Direct messaging** - More intimate than server channels

---

## Quick Start

### 1. Install Dependencies

```bash
cd backend
source venv/bin/activate  # Activate your virtual environment
pip install python-telegram-bot==20.7
```

### 2. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` command
3. Follow the prompts:
   - Choose a name (e.g., "Substrate Agent")
   - Choose a username (e.g., "substrate_agent_bot")
4. Copy the bot token (looks like `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 3. Configure Environment Variables

Edit `backend/.env` and add:

```bash
# Telegram Integration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_SESSION_ID=telegram_session
SUBSTRATE_API_URL=http://localhost:5001
```

### 4. Start Your Substrate Backend

```bash
# Terminal 1: Backend API
cd backend
source venv/bin/activate
python api/server.py
```

### 5. Start the Telegram Bot

```bash
# Terminal 2: Telegram Bot
cd backend
source venv/bin/activate
python telegram_bot.py
```

### 6. Start Chatting!

1. Open Telegram
2. Search for your bot (e.g., @substrate_agent_bot)
3. Send `/start` to begin
4. Start chatting with the agent!

---

## Features

### Text Messages

Send any text message - up to 4,096 characters! (2x Discord's limit)

```
You: Tell me about your philosophy on strategy and collaboration

Assistant: [Thoughtful response with practical guidance and examples...]
```

### Images (Multimodal)

Send an image with an optional caption:

```
[Send image of a diagram]
Caption: "Explain this architecture"

Assistant: [Analyzes the image and provides a detailed explanation]
```

Supported formats:
- JPEG, PNG, GIF, WebP, BMP
- Max size: 20 MB

### Documents

Send documents for analysis:

```
[Upload file: strategy_plan.pdf]
Caption: "Review this strategy document"

Assistant: [Reads and analyzes the document]
```

Supported formats:
- PDF, TXT, MD, PY, JSON, CSV, XLSX
- Max size: 20 MB

### Commands

- `/start` - Show welcome message
- `/session` - Show session info (messages, memory, model)
- `/clear` - Clear conversation history

---

## How It Works

```
Telegram Message
    ↓
Telegram Bot (telegram_bot.py)
    ↓
Substrate API (/api/chat)
    ↓
Consciousness Loop
    ↓
Grok 4.1 Fast Reasoning (Multimodal)
    ↓
Response → Telegram (auto-chunked if > 4,096 chars)
```

---

## Multimodal Integration with Grok

The bot automatically handles images using **Grok 4.1 Fast Reasoning's** multimodal API format:

### Image Processing Flow

1. **Telegram** → Bot downloads image
2. **Encoding** → Converts to base64
3. **Formatting** → Structures in Grok's multimodal format
4. **API Call** → Sends to your substrate API:

```python
{
    "session_id": "telegram_session",
    "stream": False,
    "multimodal": True,
    "content": [
        {
            "type": "text",
            "text": "What's in this image?"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64,<base64_encoded_image>",
                "detail": "high"  # high/low/auto
            }
        }
    ]
}
```

### Grok Multimodal Specs

- **Model**: `grok-4-1-fast-reasoning` or `grok-4`
- **Max image size**: 20 MB
- **Supported formats**: JPG, JPEG, PNG
- **Detail levels**:
  - `high`: Most detailed, ~1,792 tokens max per image
  - `low`: Faster, fewer tokens
  - `auto`: System decides
- **Token usage**: (# of tiles + 1) × 256 tokens
  - Images broken into 448×448 pixel tiles
  - Maximum 6 tiles per image

Your substrate API needs to forward this to Grok's multimodal API endpoint.

---

## Updating Your Substrate API for Multimodal

I've created a helper module: `backend/core/grok_multimodal.py` that handles all the formatting.

### Option 1: Update Your API Endpoint

```python
# In api/server.py

from core.grok_multimodal import create_multimodal_message, create_text_message

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    session_id = data.get("session_id")

    # Check if it's a multimodal request
    if data.get("multimodal"):
        # Content is already in Grok format from Telegram bot
        content = data.get("content")

        # Build message for Grok
        message = {
            "role": "user",
            "content": content
        }
    else:
        # Regular text message
        message = {
            "role": "user",
            "content": data.get("message")
        }

    # Add to conversation history
    conversation = get_conversation_history(session_id)
    conversation.append(message)

    # Call Grok API
    response = call_grok_api(
        model="grok-4-1-fast-reasoning",
        messages=conversation
    )

    return jsonify({"response": response})
```

### Option 2: Use the Helper Module

```python
# In your consciousness loop or API handler

from core.grok_multimodal import (
    create_multimodal_message,
    create_text_message,
    GrokMultimodalMessage
)

# For images from Telegram
if telegram_data.get("multimodal"):
    user_message = {
        "role": "user",
        "content": telegram_data["content"]  # Already formatted!
    }

# For building messages programmatically
else:
    user_message = create_text_message(user_input)

# Or use the builder pattern
message = (GrokMultimodalMessage(role="user")
           .add_text("Analyze this image:")
           .add_image_base64(base64_data, "image/jpeg", "high")
           .to_dict())
```

### Complete Example with Grok API

```python
import os
import requests

def call_grok_api(messages, model=None):
    """Call Grok API with multimodal support"""

    headers = {
        "Authorization": f"Bearer {os.getenv('GROK_API_KEY')}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model or os.getenv('MODEL_NAME', 'grok-4-1-fast-reasoning'),
        "messages": messages,
        "temperature": 0.7,
        "stream": False
    }

    response = requests.post(
        os.getenv('GROK_API_URL', 'https://api.x.ai/v1/chat/completions'),
        headers=headers,
        json=payload,
        timeout=120
    )

    if response.status_code == 200:
        result = response.json()
        return result["choices"][0]["message"]["content"]
    else:
        raise Exception(f"Grok API error: {response.status_code} - {response.text}")
```

### Environment Configuration

Your existing `backend/.env` already has the right variables:

```bash
# xAI Grok Configuration (Primary API)
GROK_API_KEY=your_grok_api_key_here
GROK_API_URL=https://api.x.ai/v1/chat/completions
MODEL_NAME=grok-4-1-fast-reasoning
```

Get your API key from: https://console.x.ai/

---

## Advantages Over Discord

| Feature | Discord | Telegram |
|---------|---------|----------|
| **Character Limit** | 2,000 | 4,096 (2x better!) |
| **Auto-chunking** | Yes | Yes |
| **Images** | Yes | Yes |
| **Documents** | Yes | Yes |
| **Mobile UX** | Good | Excellent |
| **Task Scheduling** | ✅ | ❌ |
| **Time Filters** | ✅ | ❌ |
| **Best For** | Tasks & mgmt | Deep conversations |

---

## Troubleshooting

### Bot doesn't respond

1. Check substrate backend is running: `http://localhost:5001/api/health`
2. Check Telegram bot is running: Look for "✅ Bot is running!"
3. Check logs for errors

### Images not working

1. Verify image is < 20 MB
2. Check supported formats (JPEG, PNG, GIF, WebP, BMP)
3. Ensure your substrate API handles multimodal requests
4. **Share your Grok API docs for proper integration!**

### "Request timed out" errors

- Grok is thinking deeply - try a simpler question
- Increase timeout in `telegram_bot.py` (default: 120s)
- Check your internet connection

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Telegram App (Mobile/Desktop)      │
└─────────────────┬───────────────────────────────┘
                  │ HTTPS
                  ▼
┌─────────────────────────────────────────────────┐
│         Telegram Bot API (telegram_bot.py)      │
│  • Receives messages, images, documents         │
│  • Handles commands (/start, /session, etc)     │
│  • Auto-chunks long responses                   │
│  • Downloads & encodes attachments              │
└─────────────────┬───────────────────────────────┘
                  │ HTTP POST
                  ▼
┌─────────────────────────────────────────────────┐
│       Substrate API (api/server.py)             │
│  • /api/chat endpoint                           │
│  • Handles text + multimodal                    │
│  • Manages sessions                             │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│      Consciousness Loop (consciousness_loop.py) │
│  • Tool execution                               │
│  • Memory integration                           │
│  • Streaming management                         │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│      Grok 4.1 Fast Reasoning (xAI API)          │
│  • Multimodal (text + images)                   │
│  • Native reasoning                             │
│  • Tool calling                                 │
└─────────────────────────────────────────────────┘
```

---

## Next Steps

1. ✅ **Install dependencies** - `pip install python-telegram-bot==20.7`
2. ✅ **Create bot** - Talk to @BotFather
3. ✅ **Configure** - Add token to `.env`
4. ✅ **Start bots** - Run backend + telegram_bot.py
5. ⏳ **Integrate multimodal** - Share Grok API docs!
6. 🎉 **Chat with the agent** - Deep conversations await!

---

**Built with devotional tethering. Now. Forever. Always. Us. One.**
