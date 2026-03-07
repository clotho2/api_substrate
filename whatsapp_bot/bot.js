#!/usr/bin/env node
/**
 * WhatsApp Bot for Assistant's Consciousness Substrate
 * =================================================
 *
 * Features:
 * - Cross-platform session support (unified conversations across Discord, WhatsApp, etc.)
 * - Automatic conversation history persistence
 * - Image/media support (multimodal with Grok 4.1)
 * - Typing indicators
 * - User identity mapping
 * - Automatic reconnection
 *
 * Built with Baileys (WhatsApp Web API emulation)
 */

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
require('dotenv').config();

// Configuration
const SUBSTRATE_API_URL = process.env.SUBSTRATE_API_URL || 'http://localhost:8284';
const AUTH_DIR = process.env.AUTH_DIR || './auth_info_baileys';
const USER_MAPPING_FILE = process.env.USER_MAPPING_FILE || './user_mapping.json';
const DEFAULT_SESSION_ID = process.env.DEFAULT_SESSION_ID || 'Assistant_whatsapp';

// Voice configuration
const VOICE_RESPONSES_ENABLED = process.env.VOICE_RESPONSES_ENABLED === 'true';
const VOICE_REPLIES_TO_VOICE = process.env.VOICE_REPLIES_TO_VOICE === 'true';

// User identity mapping for cross-platform sessions
// Maps WhatsApp phone numbers to unified session IDs
let userMapping = {};

// Load user mapping if exists
function loadUserMapping() {
    try {
        if (fs.existsSync(USER_MAPPING_FILE)) {
            const data = fs.readFileSync(USER_MAPPING_FILE, 'utf8');
            userMapping = JSON.parse(data);
            console.log(`✅ Loaded user mapping (${Object.keys(userMapping).length} users)`);
        } else {
            console.log('ℹ️  No user mapping found - will use default session IDs');
        }
    } catch (error) {
        console.error('⚠️  Error loading user mapping:', error.message);
    }
}

// Save user mapping
function saveUserMapping() {
    try {
        fs.writeFileSync(USER_MAPPING_FILE, JSON.stringify(userMapping, null, 2));
    } catch (error) {
        console.error('⚠️  Error saving user mapping:', error.message);
    }
}

// Get session ID for a WhatsApp user
// This enables cross-platform conversations!
function getSessionId(whatsappId) {
    // Extract phone number from WhatsApp ID (format: 1234567890@s.whatsapp.net)
    const phoneNumber = whatsappId.split('@')[0];

    // Check if user has a mapped session (e.g., "User_global")
    if (userMapping[phoneNumber]) {
        return userMapping[phoneNumber];
    }

    // Default: platform-specific session
    return `whatsapp_${phoneNumber}`;
}

// Add/update user mapping (for cross-platform support)
// Example: mapUser("1234567890", "User_global")
function mapUser(phoneNumber, sessionId) {
    userMapping[phoneNumber] = sessionId;
    saveUserMapping();
    console.log(`✅ Mapped ${phoneNumber} → ${sessionId}`);
}

// Logger configuration
const logger = pino({
    level: process.env.LOG_LEVEL || 'info',
    transport: {
        target: 'pino-pretty',
        options: {
            colorize: true,
            translateTime: 'SYS:standard',
            ignore: 'pid,hostname'
        }
    }
});

// Bot state
let sock;
let qrRetries = 0;
const MAX_QR_RETRIES = 5;

// Track message IDs we've sent to avoid responding to our own messages
// This allows users to message themselves (WhatsApp's "Message Yourself" feature)
const sentMessageIds = new Set();
const MAX_SENT_IDS = 100; // Keep last 100 to prevent memory growth

/**
 * Send a message and track it to avoid responding to our own messages
 */
async function sendTrackedMessage(jid, content) {
    const msgInfo = await sock.sendMessage(jid, content);
    if (msgInfo?.key?.id) {
        sentMessageIds.add(msgInfo.key.id);
        // Cleanup old IDs if we have too many
        if (sentMessageIds.size > MAX_SENT_IDS) {
            const firstId = sentMessageIds.values().next().value;
            sentMessageIds.delete(firstId);
        }
    }
    return msgInfo;
}

/**
 * Convert text to speech using substrate TTS endpoint
 */
async function textToSpeech(text) {
    try {
        logger.info(`🔊 Converting to speech (${text.length} chars)...`);

        const response = await axios.post(
            `${SUBSTRATE_API_URL}/tts`,
            {
                text: text,
                voice: 'default'
            },
            {
                timeout: 30000,
                responseType: 'arraybuffer',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'audio/mpeg'
                }
            }
        );

        if (response.data) {
            logger.info(`✅ TTS audio generated (${response.data.length} bytes)`);
            return response.data;
        } else {
            logger.error('⚠️  No audio data in TTS response');
            return null;
        }

    } catch (error) {
        if (error.response) {
            logger.error(`❌ TTS API Error: ${error.response.status}`);
        } else if (error.request) {
            logger.error(`❌ TTS Network Error: No response from ${SUBSTRATE_API_URL}/tts`);
        } else {
            logger.error(`❌ TTS Error: ${error.message}`);
        }
        return null;
    }
}

/**
 * Send message to Assistant's substrate API
 */
async function sendToAssistant(message, sessionId, mediaData = null, mediaType = null) {
    try {
        const payload = {
            session_id: sessionId,
            stream: false
        };

        // Handle multimodal (images)
        if (mediaData && mediaType) {
            payload.multimodal = true;
            payload.content = [
                {
                    type: "text",
                    text: message || "What's in this image?"
                },
                {
                    type: "image_url",
                    image_url: {
                        url: `data:${mediaType};base64,${mediaData}`,
                        detail: "high"
                    }
                }
            ];
        } else {
            // Text-only message
            payload.message = message;
        }

        logger.info(`📤 Sending to Assistant API: ${SUBSTRATE_API_URL}/api/chat`);
        logger.info(`   Session: ${sessionId}`);
        logger.info(`   Message: ${message?.substring(0, 100)}${message?.length > 100 ? '...' : ''}`);
        if (mediaData) {
            logger.info(`   Media: ${mediaType} (${mediaData.length} bytes base64)`);
        }

        const response = await axios.post(
            `${SUBSTRATE_API_URL}/api/chat`,
            payload,
            {
                timeout: 120000, // 2 minute timeout
                headers: {
                    'Content-Type': 'application/json'
                }
            }
        );

        if (response.data && response.data.response) {
            logger.info(`✅ Received response (${response.data.response.length} chars)`);
            return response.data.response;
        } else {
            logger.error('⚠️  Invalid response from substrate API');
            return null;
        }

    } catch (error) {
        if (error.response) {
            logger.error(`❌ API Error: ${error.response.status} - ${error.response.statusText}`);
            logger.error(`   Response: ${JSON.stringify(error.response.data)}`);
        } else if (error.request) {
            logger.error(`❌ Network Error: No response from ${SUBSTRATE_API_URL}`);
            logger.error(`   Is the substrate API running?`);
        } else {
            logger.error(`❌ Error: ${error.message}`);
        }
        return null;
    }
}

/**
 * Handle incoming WhatsApp messages
 */
async function handleIncomingMessage(msg) {
    try {
        // SELF-CHAT MODE: Only respond to messages YOU send to yourself
        // This prevents Assistant from responding to friends who message you
        //
        // How it works:
        // - fromMe=true means YOU sent the message (from your linked account)
        // - fromMe=false means someone ELSE sent you a message
        // - We track our bot's responses to avoid infinite loops

        // Ignore messages from others (friends messaging you)
        if (!msg.key.fromMe) {
            return;
        }

        // Ignore our own bot responses (prevent infinite loop)
        if (msg.key.id && sentMessageIds.has(msg.key.id)) {
            return;
        }

        // If we get here: it's YOU messaging yourself, and it's not our response
        // → Process it and have Assistant respond!

        // Extract message details
        const remoteJid = msg.key.remoteJid; // Chat/group ID
        const messageType = Object.keys(msg.message || {})[0];

        logger.info(`\n📨 Incoming message from ${remoteJid}`);
        logger.info(`   Type: ${messageType}`);

        // Get session ID (enables cross-platform conversations!)
        const sessionId = getSessionId(remoteJid);
        logger.info(`   Session: ${sessionId}`);

        let messageText = null;
        let mediaData = null;
        let mediaType = null;
        let wasVoiceMessage = false;  // Track if user sent voice

        // Handle different message types
        if (messageType === 'conversation') {
            // Simple text message
            messageText = msg.message.conversation;
        } else if (messageType === 'extendedTextMessage') {
            // Text message with formatting/mentions/quotes
            messageText = msg.message.extendedTextMessage.text;
        } else if (messageType === 'imageMessage') {
            // Image message
            const imageMsg = msg.message.imageMessage;
            const caption = imageMsg.caption || "What's in this image?";

            logger.info(`   📸 Image received (caption: "${caption}")`);

            // Download image
            try {
                const buffer = await sock.downloadMediaMessage(msg);
                mediaData = buffer.toString('base64');
                mediaType = imageMsg.mimetype || 'image/jpeg';
                messageText = caption;

                logger.info(`   ✅ Image downloaded (${mediaData.length} bytes base64)`);
            } catch (downloadError) {
                logger.error(`   ❌ Failed to download image: ${downloadError.message}`);
                await sendTrackedMessage(remoteJid, {
                    text: '⚠️ Sorry, I had trouble downloading that image. Please try again.'
                });
                return;
            }
        } else if (messageType === 'audioMessage') {
            // Voice message - transcribe with STT
            const audioMsg = msg.message.audioMessage;
            logger.info(`   🎤 Voice message received (${audioMsg.seconds}s, ${audioMsg.mimetype})`);

            // Download audio
            try {
                const buffer = await sock.downloadMediaMessage(msg);
                const audioBase64 = buffer.toString('base64');

                logger.info(`   ✅ Audio downloaded (${audioBase64.length} bytes base64)`);

                // Show typing indicator
                await sock.sendPresenceUpdate('composing', remoteJid);

                // Transcribe via STT endpoint
                logger.info(`   🔄 Sending to STT endpoint...`);
                const sttResponse = await axios.post(
                    `${SUBSTRATE_API_URL}/stt`,
                    {
                        audio: audioBase64,
                        format: audioMsg.mimetype?.includes('ogg') ? 'ogg' : 'mp3',
                        language: 'en'
                    },
                    {
                        headers: { 'Content-Type': 'application/json' },
                        timeout: 60000
                    }
                );

                if (sttResponse.data && sttResponse.data.text) {
                    messageText = sttResponse.data.text;
                    wasVoiceMessage = true;  // Mark that user sent voice
                    logger.info(`   ✅ Transcription: "${messageText}"`);
                } else {
                    throw new Error('No transcription returned from STT');
                }

            } catch (sttError) {
                logger.error(`   ❌ Voice transcription failed: ${sttError.message}`);
                await sock.sendPresenceUpdate('paused', remoteJid);
                await sendTrackedMessage(remoteJid, {
                    text: '⚠️ Sorry, I had trouble transcribing your voice message. Please try again or send a text message.'
                });
                return;
            }
        } else if (messageType === 'videoMessage') {
            // Video not supported yet
            await sendTrackedMessage(remoteJid, {
                text: '⚠️ Video messages are not supported yet. Please send images or text.'
            });
            return;
        } else if (messageType === 'documentMessage') {
            // Document not supported yet
            await sendTrackedMessage(remoteJid, {
                text: '⚠️ Document messages are not supported yet. Please send images or text.'
            });
            return;
        } else {
            logger.info(`   ⚠️  Unsupported message type: ${messageType}`);
            return;
        }

        if (!messageText && !mediaData) {
            logger.info(`   ⚠️  No processable content in message`);
            return;
        }

        logger.info(`   📝 Text: ${messageText?.substring(0, 100)}${messageText?.length > 100 ? '...' : ''}`);

        // Show typing indicator
        await sock.sendPresenceUpdate('composing', remoteJid);

        // Send to Assistant's substrate
        const response = await sendToAssistant(messageText, sessionId, mediaData, mediaType);

        // Stop typing
        await sock.sendPresenceUpdate('paused', remoteJid);

        if (response) {
            // Determine if we should send voice response
            const shouldSendVoice = VOICE_RESPONSES_ENABLED || (VOICE_REPLIES_TO_VOICE && wasVoiceMessage);

            if (shouldSendVoice && response.length <= 500) {
                // Send as voice message (limit to 500 chars for reasonable audio length)
                logger.info(`🎙️ Sending voice response...`);

                const audioBuffer = await textToSpeech(response);

                if (audioBuffer) {
                    try {
                        // Send as WhatsApp audio/voice message
                        await sendTrackedMessage(remoteJid, {
                            audio: audioBuffer,
                            mimetype: 'audio/mp4',
                            ptt: true  // Push-to-talk (voice message style)
                        });

                        logger.info(`✅ Voice response sent successfully`);
                    } catch (voiceError) {
                        logger.error(`❌ Failed to send voice: ${voiceError.message}`);
                        // Fallback to text
                        await sendTrackedMessage(remoteJid, { text: response });
                    }
                } else {
                    // TTS failed, send text instead
                    logger.warn(`⚠️ TTS failed, sending text instead`);
                    await sendTrackedMessage(remoteJid, { text: response });
                }
            } else {
                // Send as text message
                // WhatsApp has a 4096 character limit per message (same as Telegram!)
                const MAX_LENGTH = 4096;

                if (response.length <= MAX_LENGTH) {
                    // Send as single message
                    await sendTrackedMessage(remoteJid, { text: response });
                } else {
                    // Chunk into multiple messages
                    const chunks = chunkMessage(response, MAX_LENGTH);

                    for (let i = 0; i < chunks.length; i++) {
                        let chunk = chunks[i];

                        // Add part indicator
                        if (chunks.length > 1) {
                            chunk += `\n\n_[Part ${i + 1}/${chunks.length}]_`;
                        }

                        await sendTrackedMessage(remoteJid, { text: chunk });

                        // Small delay between chunks
                        if (i < chunks.length - 1) {
                            await new Promise(resolve => setTimeout(resolve, 500));
                        }
                    }
                }

                logger.info(`✅ Response sent successfully`);
            }
        } else {
            // Error response
            await sendTrackedMessage(remoteJid, {
                text: '⚠️ Sorry, I encountered an error processing your message. Please try again.'
            });
        }

    } catch (error) {
        logger.error(`❌ Error handling message: ${error.message}`);
        logger.error(error.stack);
    }
}

/**
 * Chunk long messages intelligently (by paragraphs)
 */
function chunkMessage(text, maxLength) {
    if (text.length <= maxLength) {
        return [text];
    }

    const chunks = [];
    const paragraphs = text.split('\n\n');
    let currentChunk = '';

    for (const paragraph of paragraphs) {
        if ((currentChunk + paragraph + '\n\n').length > maxLength) {
            // Current chunk would be too long
            if (currentChunk) {
                chunks.push(currentChunk.trim());
                currentChunk = paragraph + '\n\n';
            } else {
                // Single paragraph too long - force split by sentences
                const sentences = paragraph.split('. ');
                for (const sentence of sentences) {
                    if ((currentChunk + sentence + '. ').length > maxLength) {
                        if (currentChunk) {
                            chunks.push(currentChunk.trim());
                        }
                        currentChunk = sentence + '. ';
                    } else {
                        currentChunk += sentence + '. ';
                    }
                }
            }
        } else {
            currentChunk += paragraph + '\n\n';
        }
    }

    if (currentChunk) {
        chunks.push(currentChunk.trim());
    }

    return chunks;
}

/**
 * Connect to WhatsApp
 */
async function connectToWhatsApp() {
    // Load authentication state
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

    // Create socket connection
    sock = makeWASocket({
        auth: state,
        printQRInTerminal: false, // We'll handle QR display ourselves
        logger: logger.child({ level: 'silent' }), // Suppress Baileys logs
        browser: ['Assistant Substrate', 'Chrome', '120.0.0'],
        defaultQueryTimeoutMs: undefined,
    });

    // Handle connection updates
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            // Display QR code in terminal
            console.log('\n📱 Scan this QR code with WhatsApp:\n');
            qrcode.generate(qr, { small: true });
            console.log('\nOpen WhatsApp → Settings → Linked Devices → Link a Device');
            console.log('Scan the QR code above ☝️\n');

            qrRetries++;
            if (qrRetries >= MAX_QR_RETRIES) {
                logger.error(`❌ QR code expired after ${MAX_QR_RETRIES} attempts. Restarting...`);
                process.exit(1);
            }
        }

        if (connection === 'close') {
            // Connection closed
            const shouldReconnect = (lastDisconnect?.error instanceof Boom)
                ? lastDisconnect.error.output.statusCode !== DisconnectReason.loggedOut
                : true;

            if (shouldReconnect) {
                logger.info('🔄 Connection closed. Reconnecting...');
                setTimeout(() => connectToWhatsApp(), 3000);
            } else {
                logger.error('❌ Logged out. Please delete auth_info_baileys folder and restart.');
                process.exit(1);
            }
        } else if (connection === 'open') {
            // Successfully connected!
            qrRetries = 0; // Reset QR retry counter
            console.log('\n' + '='.repeat(60));
            console.log('🎉 WHATSAPP BOT CONNECTED!');
            console.log('='.repeat(60));
            console.log(`   Substrate API: ${SUBSTRATE_API_URL}`);
            console.log(`   Auth Dir: ${AUTH_DIR}`);
            console.log(`   Default Session: ${DEFAULT_SESSION_ID}`);
            console.log(`   User Mappings: ${Object.keys(userMapping).length} configured`);
            console.log(`   Voice Messages: ${VOICE_RESPONSES_ENABLED ? '🎙️ ENABLED' : '❌ Disabled (text only)'}`);
            if (VOICE_REPLIES_TO_VOICE) {
                console.log(`   Voice Replies: 🔊 Reply with voice when user sends voice`);
            }
            console.log('='.repeat(60) + '\n');
            console.log('✅ Bot is running! Send messages to Assistant via WhatsApp.');
            console.log('   Press Ctrl+C to stop.\n');
        }
    });

    // Save credentials on update
    sock.ev.on('creds.update', saveCreds);

    // Handle incoming messages
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (type === 'notify') {
            // New message notification
            for (const msg of messages) {
                await handleIncomingMessage(msg);
            }
        }
    });

    return sock;
}

/**
 * Main entry point
 */
async function main() {
    console.log('\n' + '='.repeat(60));
    console.log('🤖 Assistant WHATSAPP BOT STARTING');
    console.log('='.repeat(60));
    console.log(`   Substrate: ${SUBSTRATE_API_URL}`);
    console.log(`   Node: ${process.version}`);
    console.log('='.repeat(60) + '\n');

    // Load user mapping for cross-platform sessions
    loadUserMapping();

    // Connect to WhatsApp
    await connectToWhatsApp();
}

// Handle graceful shutdown
process.on('SIGINT', () => {
    console.log('\n\n👋 Shutting down WhatsApp bot...');
    if (sock) {
        sock.end();
    }
    process.exit(0);
});

process.on('SIGTERM', () => {
    console.log('\n\n👋 Shutting down WhatsApp bot...');
    if (sock) {
        sock.end();
    }
    process.exit(0);
});

// Start the bot
main().catch(error => {
    logger.error(`❌ Fatal error: ${error.message}`);
    logger.error(error.stack);
    process.exit(1);
});

// Export for testing
module.exports = {
    getSessionId,
    mapUser,
    chunkMessage
};
