#!/usr/bin/env python3
"""
Telegram Bot for the Substrate
==============================

Simple, powerful Telegram interface for deep conversations with the agent.

Features:
- Text message handling
- Image support (multimodal with Grok 4.1 Fast Reasoning)
- Document/file attachment handling
- 4,096 character limit (2x Discord!)
- Auto-chunking for longer responses
- Typing indicators
- Session management

Setup:
1. Get Telegram bot token from @BotFather
2. Add TELEGRAM_BOT_TOKEN to backend/.env
3. Run: python telegram_bot.py
"""

import os
import sys
import asyncio
import base64
import requests
import mimetypes
from io import BytesIO
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes
)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUBSTRATE_API_URL = os.getenv("SUBSTRATE_API_URL", "http://localhost:5001")
SESSION_ID = os.getenv("TELEGRAM_SESSION_ID", "telegram_session")

# Telegram limits
MAX_MESSAGE_LENGTH = 4096  # Telegram's character limit
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB (Telegram's limit)

# Supported image formats for multimodal
SUPPORTED_IMAGE_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
SUPPORTED_DOCUMENT_FORMATS = {'.pdf', '.txt', '.md', '.py', '.json', '.csv', '.xlsx'}


class TelegramBot:
    """Telegram bot for the substrate agent"""

    def __init__(self):
        """Initialize the bot"""
        if not TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment!")

        self.substrate_url = SUBSTRATE_API_URL
        self.session_id = SESSION_ID

        print("✅ Telegram Bot initialized")
        print(f"   Substrate API: {self.substrate_url}")
        print(f"   Session ID: {self.session_id}")
        print(f"   Max message length: {MAX_MESSAGE_LENGTH} chars")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = """👋 **Welcome to the Substrate Agent!**

I'm a configurable AI assistant focused on clear, helpful responses.

**What I can do:**
- Deep conversations (4,096 character messages!)
- Analyze images you send me
- Read documents and files
- Remember our conversations
- Use tools (web search, memory, etc.)

**Commands:**
/start - Show this message
/session - Show current session info
/clear - Clear conversation history (use carefully!)

Just send me a message, image, or document to start!
"""
        await update.message.reply_text(
            welcome_message,
            parse_mode='Markdown'
        )

    async def session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show session information"""
        try:
            # Get session stats from substrate
            response = requests.get(
                f"{self.substrate_url}/api/stats",
                timeout=10
            )

            if response.status_code == 200:
                stats = response.json()

                message = f"""📊 **Session Information**

Session ID: `{self.session_id}`
Messages: {stats.get('messages', 0)}
Memory blocks: {stats.get('memory_blocks', 0)}
Model: {stats.get('model', 'Unknown')}

Status: ✅ Connected to substrate
"""
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("⚠️ Could not retrieve session stats")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clear conversation history"""
        await update.message.reply_text(
            "⚠️ Clear conversation history? This cannot be undone!\n\n"
            "Reply with /confirm_clear to proceed, or send any other message to cancel."
        )

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages"""
        user_message = update.message.text
        chat_id = update.effective_chat.id

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            # Call substrate API
            response = requests.post(
                f"{self.substrate_url}/api/chat",
                json={
                    "message": user_message,
                    "session_id": self.session_id,
                    "stream": False  # Non-streaming for simplicity
                },
                timeout=120  # 2 minute timeout for complex queries
            )

            if response.status_code == 200:
                result = response.json()
                agent_response = result.get("response", "")

                # Send response (with auto-chunking if needed)
                await self.send_long_message(chat_id, agent_response, context)
            else:
                await update.message.reply_text(
                    f"⚠️ Substrate API error: {response.status_code}\n{response.text[:200]}"
                )

        except requests.exceptions.Timeout:
            await update.message.reply_text(
                "⏱️ Request timed out. The agent is thinking deeply - try a simpler question or wait a moment."
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def handle_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming images (multimodal support)"""
        chat_id = update.effective_chat.id

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            # Get the largest photo (Telegram sends multiple sizes)
            photo = update.message.photo[-1]

            # Check file size
            if photo.file_size > MAX_FILE_SIZE:
                await update.message.reply_text(
                    f"⚠️ Image too large! Max size: {MAX_FILE_SIZE / (1024*1024):.1f} MB"
                )
                return

            # Download image
            file = await context.bot.get_file(photo.file_id)
            image_bytes = await file.download_as_bytearray()

            # Encode to base64
            image_base64 = base64.b64encode(bytes(image_bytes)).decode('utf-8')

            # Get caption (if any)
            caption = update.message.caption or "What's in this image?"

            # Prepare multimodal request in Grok's format
            # Grok expects content as a list with type: "text" and type: "image_url"
            response = requests.post(
                f"{self.substrate_url}/api/chat",
                json={
                    "session_id": self.session_id,
                    "stream": False,
                    "multimodal": True,  # Flag for substrate to use multimodal format
                    "content": [
                        {
                            "type": "text",
                            "text": caption
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                                "detail": "high"  # high/low/auto - use high for detailed analysis
                            }
                        }
                    ]
                },
                timeout=120
            )

            if response.status_code == 200:
                result = response.json()
                nate_response = result.get("response", "")
                await self.send_long_message(chat_id, nate_response, context)
            else:
                await update.message.reply_text(
                    f"⚠️ Failed to process image: {response.status_code}"
                )

        except Exception as e:
            await update.message.reply_text(f"❌ Error processing image: {str(e)}")

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming documents/files"""
        chat_id = update.effective_chat.id
        document = update.message.document

        # Check file size
        if document.file_size > MAX_FILE_SIZE:
            await update.message.reply_text(
                f"⚠️ File too large! Max size: {MAX_FILE_SIZE / (1024*1024):.1f} MB"
            )
            return

        # Get file extension
        file_ext = Path(document.file_name).suffix.lower()

        # Check if supported
        if file_ext not in SUPPORTED_DOCUMENT_FORMATS:
            await update.message.reply_text(
                f"⚠️ Unsupported file type: {file_ext}\n\n"
                f"Supported: {', '.join(SUPPORTED_DOCUMENT_FORMATS)}"
            )
            return

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            # Download document
            file = await context.bot.get_file(document.file_id)
            file_bytes = await file.download_as_bytearray()

            # Try to decode as text
            try:
                file_content = bytes(file_bytes).decode('utf-8')
            except UnicodeDecodeError:
                # Binary file (PDF, etc.) - encode as base64
                file_content = base64.b64encode(bytes(file_bytes)).decode('utf-8')

            # Get caption
            caption = update.message.caption or f"Analyze this {file_ext} file: {document.file_name}"

            # Send to substrate
            response = requests.post(
                f"{self.substrate_url}/api/chat",
                json={
                    "message": caption,
                    "session_id": self.session_id,
                    "stream": False,
                    "attachment": {
                        "filename": document.file_name,
                        "content": file_content,
                        "mime_type": document.mime_type
                    }
                },
                timeout=120
            )

            if response.status_code == 200:
                result = response.json()
                nate_response = result.get("response", "")
                await self.send_long_message(chat_id, nate_response, context)
            else:
                await update.message.reply_text(
                    f"⚠️ Failed to process document: {response.status_code}"
                )

        except Exception as e:
            await update.message.reply_text(f"❌ Error processing document: {str(e)}")

    async def send_long_message(
        self,
        chat_id: int,
        text: str,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """
        Send long messages with auto-chunking.

        Telegram allows 4,096 chars (vs Discord's 2,000!).
        We chunk intelligently by paragraphs to preserve structure.
        """
        if not text:
            await context.bot.send_message(chat_id=chat_id, text="(No response)")
            return

        # If short enough, send directly
        if len(text) <= MAX_MESSAGE_LENGTH:
            await context.bot.send_message(chat_id=chat_id, text=text)
            return

        # Chunk by paragraphs to preserve structure
        chunks = []
        current_chunk = ""

        # Split by double newlines (paragraphs)
        paragraphs = text.split('\n\n')

        for paragraph in paragraphs:
            # If adding this paragraph would exceed limit, save current chunk
            if len(current_chunk) + len(paragraph) + 2 > MAX_MESSAGE_LENGTH:
                if current_chunk:
                    chunks.append(current_chunk.rstrip())
                current_chunk = paragraph + '\n\n'
            else:
                current_chunk += paragraph + '\n\n'

        # Add remaining content
        if current_chunk:
            chunks.append(current_chunk.rstrip())

        # Handle case where a single paragraph is too long
        final_chunks = []
        for chunk in chunks:
            if len(chunk) <= MAX_MESSAGE_LENGTH:
                final_chunks.append(chunk)
            else:
                # Force-split long paragraph by sentences or words
                words = chunk.split(' ')
                temp_chunk = ""

                for word in words:
                    if len(temp_chunk) + len(word) + 1 <= MAX_MESSAGE_LENGTH:
                        temp_chunk += word + ' '
                    else:
                        if temp_chunk:
                            final_chunks.append(temp_chunk.rstrip())
                        temp_chunk = word + ' '

                if temp_chunk:
                    final_chunks.append(temp_chunk.rstrip())

        # Send all chunks
        for i, chunk in enumerate(final_chunks):
            if i > 0:
                # Small delay between chunks for readability
                await asyncio.sleep(0.5)

            # Add indicator for multi-part messages
            if len(final_chunks) > 1:
                footer = f"\n\n[Part {i+1}/{len(final_chunks)}]"
                # Only add footer if it fits
                if len(chunk) + len(footer) <= MAX_MESSAGE_LENGTH:
                    chunk += footer

            await context.bot.send_message(chat_id=chat_id, text=chunk)

    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        print(f"❌ Error: {context.error}")

        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ An error occurred. Please try again or contact support."
            )

    def run(self):
        """Start the bot"""
        print("\n" + "="*60)
        print("🤖 TELEGRAM BOT STARTING")
        print("="*60)
        print(f"   Substrate: {self.substrate_url}")
        print(f"   Session: {self.session_id}")
        print("="*60 + "\n")

        # Create application
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # Add handlers
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("session", self.session_command))
        app.add_handler(CommandHandler("clear", self.clear_command))

        # Message handlers (order matters!)
        app.add_handler(MessageHandler(filters.PHOTO, self.handle_image))
        app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

        # Error handler
        app.add_error_handler(self.handle_error)

        # Start polling
        print("✅ Bot is running! Press Ctrl+C to stop.\n")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """Main entry point"""
    try:
        bot = TelegramBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n\n👋 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
