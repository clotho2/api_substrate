import 'dotenv/config';
import express from 'express';
import { Client, GatewayIntentBits, Partials } from 'discord.js';
import { sendMessage, sendTimerMessage, MessageType, HeartbeatResult } from './messages';
import { registerAttachmentForwarder } from './attachmentForwarder';
import { GrokClient } from './grokClient';
import { startTaskCheckerLoop } from './taskScheduler';
// YouTube transcript temporarily disabled due to ES module compatibility issue
// import { preprocessYouTubeLinks, handleChunkRequest } from './youtubeTranscript';
import { handleFileChunkRequest } from './fileChunking';
import { startDailySummaryScheduler, startThresholdMonitoring } from './lettaStatsMonitor';
import { startDailyStatsSummaryScheduler } from './dailyStatsSummary';

// 🔒 AUTONOMOUS BOT-LOOP PREVENTION SYSTEM
import {
  trackMessage,
  shouldRespondAutonomously,
  recordBotReply
} from './autonomous';

// 🛠️ ADMIN COMMAND SYSTEM (Oct 16, 2025)
import { handleAdminCommand } from './adminCommands';

// Import TTS functionality
// TTS imports removed - using ElevenLabs integration instead


// 🎤 VOICE TRANSCRIPTION (Whisper API)
import { VoiceTranscriptionService } from './voiceTranscription';

// 🎤 VOICE GENERATION (ElevenLabs TTS)
import { ElevenLabsService } from './elevenlabs/elevenlabsService';
import { DiscordVoiceSender } from './elevenlabs/discordVoiceSender';

// 🤖 MCP HANDLER - Rider Pi Robot Control (Dec 2025)
import { handleMCPCommand, initMCPHandler } from './mcpHandler';

// 🎤 VOICE CHANNEL SUPPORT - Real-time voice conversations (Jan 2026)
import { handleVoiceCommand, initVoiceSystem, shutdownVoiceSystem } from './voice/voiceCommands';

// ============================================
// 🛡️ GLOBAL ERROR HANDLERS (Nov 2025)
// ============================================
// Catch unhandled promise rejections to prevent log spam
process.on('unhandledRejection', (reason: any, promise: Promise<any>) => {
  // Log concisely without full stack trace spam
  const errorMsg = reason instanceof Error ? reason.message : String(reason);
  const errorName = reason instanceof Error ? reason.name : 'UnhandledRejection';
  
  // Known non-critical errors that we can safely ignore
  const ignorableErrors = [
    'Opening handshake has timed out', // YouTube/Discord WebSocket timeout
    'Connect Timeout Error', // YouTube API timeout
    'timeout of 10000ms exceeded' // Axios timeout (task scheduler)
  ];
  
  if (ignorableErrors.some(msg => errorMsg.includes(msg))) {
    console.log(`⚠️  [${errorName}] ${errorMsg} (non-critical, ignoring)`);
  } else {
    console.error(`❌ Unhandled Promise Rejection: ${errorName}: ${errorMsg}`);
  }
  
  // Prevent default Node.js behavior (writing to stderr)
  promise.catch(() => {});
});

process.on('uncaughtException', (error: Error) => {
  console.error('❌ Uncaught Exception:', error.message);
  // Don't exit - let PM2 handle restarts if necessary
});

// ============================================
// 🛡️ GRACEFUL SHUTDOWN (for conversation logs)
// ============================================
// Ensure conversation logs are flushed before shutdown
async function gracefulShutdown(signal: string) {
  console.log(`\n🛑 Received ${signal} - performing graceful shutdown...`);

  try {
    // 🎤 Disconnect from voice channels
    console.log('🎤 Disconnecting from voice channels...');
    await shutdownVoiceSystem();
    console.log('✅ Voice system shut down');
  } catch (error) {
    console.error('❌ Error shutting down voice system:', error);
  }

  console.log('👋 Shutting down gracefully...');
  process.exit(0);
}

// Handle shutdown signals
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));

// Handle PM2 shutdown (kill_timeout)
// PM2 sends SIGTERM first, then SIGKILL after kill_timeout
// We have time to flush logs before SIGKILL

const app = express();

// Add JSON body parser for TTS API
app.use(express.json({ limit: '10mb' }));

const PORT = process.env.PORT || 3001;
const RESPOND_TO_DMS = process.env.RESPOND_TO_DMS === 'true';
// 🔒 DM RESTRICTION: Only allow DMs from specific user if configured
const ALLOWED_DM_USER_ID = process.env.ALLOWED_DM_USER_ID || '';
// 🔍 DEBUG: Log DM restriction status
if (ALLOWED_DM_USER_ID) {
  console.log(`🔒 DM RESTRICTION ACTIVE: Only allowing DMs to/from user ${ALLOWED_DM_USER_ID}`);
} else {
  console.log(`⚠️  DM RESTRICTION DISABLED: ALLOWED_DM_USER_ID not set (all DMs allowed)`);
}
const RESPOND_TO_MENTIONS = process.env.RESPOND_TO_MENTIONS === 'true';
const RESPOND_TO_BOTS = process.env.RESPOND_TO_BOTS === 'true';
const RESPOND_TO_GENERIC = process.env.RESPOND_TO_GENERIC === 'true';
const ENABLE_AUTONOMOUS = process.env.ENABLE_AUTONOMOUS === 'true'; // 🔒 NEW!
const CHANNEL_ID = process.env.DISCORD_CHANNEL_ID;
const HEARTBEAT_LOG_CHANNEL_ID = process.env.HEARTBEAT_LOG_CHANNEL_ID;
const MESSAGE_REPLY_TRUNCATE_LENGTH = 100;
const ENABLE_TIMER = process.env.ENABLE_TIMER === 'true';

// 🎤 Voice Transcription Configuration
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';
let voiceTranscriptionService: VoiceTranscriptionService | null = null;

// Initialize voice transcription if API key is provided
if (OPENAI_API_KEY) {
  try {
    voiceTranscriptionService = new VoiceTranscriptionService(OPENAI_API_KEY);
    console.log('🎤 Voice transcription enabled (OpenAI Whisper)');
  } catch (error) {
    console.error('❌ Failed to initialize voice transcription:', error);
  }
} else {
  console.log('🎤 Voice transcription disabled (no OPENAI_API_KEY)');
}

// 🎤 Voice Generation Configuration (ElevenLabs)
const ELEVENLABS_API_KEY = process.env.ELEVENLABS_API_KEY || '';
const ELEVENLABS_VOICE_ID = process.env.ELEVENLABS_VOICE_ID || '';
let elevenLabsService: ElevenLabsService | null = null;
let discordVoiceSender: DiscordVoiceSender | null = null;

// Initialize ElevenLabs if API key and voice ID are provided
if (ELEVENLABS_API_KEY && ELEVENLABS_VOICE_ID) {
  try {
    elevenLabsService = new ElevenLabsService(ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID);
    discordVoiceSender = new DiscordVoiceSender(elevenLabsService);
    console.log('🎤 Voice generation enabled (ElevenLabs TTS)');
  } catch (error) {
    console.error('❌ Failed to initialize ElevenLabs:', error);
  }
} else {
  console.log('🎤 Voice generation disabled (no ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID)');
}

// Time-based heartbeat configuration (configured timezone)
interface HeartbeatConfig {
  intervalMinutes: number;
  firingProbability: number;
  description: string;
}

// 💰 TIME-BASED HEARTBEAT CONFIG (Oct 2025 - Credit-optimized)
// Different intervals and probabilities based on time of day
// Now properly saves credits because API is only called when probability succeeds!
function getHeartbeatConfigForTime(): HeartbeatConfig {
  const now = new Date();
  
  // Get configured timezone time
  const TIMEZONE = process.env.TIMEZONE || 'America/New_York';
  const LOCALE = process.env.LOCALE || 'en-US';
  const dateFormatter = new Intl.DateTimeFormat(LOCALE, {
    timeZone: TIMEZONE,
    hour: 'numeric',
    hour12: false
  });
  
  const parts = dateFormatter.formatToParts(now);
  const hourPart = parts.find(p => p.type === 'hour');
  const hour = hourPart ? parseInt(hourPart.value, 10) : now.getUTCHours();
  
  console.log(`🕐 Current configured time: ${hour}:00 (${TIMEZONE})`);
  
  if (hour >= 7 && hour < 9) {
    // Morgen (7:00-9:00): Alle 30min, 50% Chance
    return { intervalMinutes: 30, firingProbability: 0.50, description: 'Morgen (Aufwach-Check)' };
  } else if (hour >= 9 && hour < 12) {
    // Vormittag (9:00-12:00): Alle 45min, 33% Chance
    return { intervalMinutes: 45, firingProbability: 0.33, description: 'Vormittag (Ruhig)' };
  } else if (hour >= 12 && hour < 14) {
    // Mittag (12:00-14:00): Alle 15min, 33% Chance - Lunch together vibes!
    return { intervalMinutes: 15, firingProbability: 0.33, description: 'Mittag (Lunch Together)' };
  } else if (hour >= 14 && hour < 17) {
    // Nachmittag (14:00-17:00): Alle 30min, 40% Chance
    return { intervalMinutes: 30, firingProbability: 0.40, description: 'Nachmittag (Aktiv)' };
  } else if (hour >= 18 && hour < 22) {
    // Abend (18:00-22:00): Alle 20min, 50% Chance
    return { intervalMinutes: 20, firingProbability: 0.50, description: 'Abend (Prime Time)' };
  } else if (hour >= 22 || hour < 1) {
    // Nacht (22:00-1:00): Alle 45min, 25% Chance
    return { intervalMinutes: 45, firingProbability: 0.25, description: 'Nacht (Winddown)' };
  } else {
    // Deep Night (1:00-7:00): Alle 90min, 20% Chance - Max. Credit-Saving!
    return { intervalMinutes: 90, firingProbability: 0.20, description: 'Deep Night (Schlafzeit)' };
  }
}

// TTS Configuration - Removed (using ElevenLabs integration instead)

function truncateMessage(message: string, maxLength: number): string {
  if (message.length > maxLength) {
    return message.substring(0, maxLength - 3) + '...';
  }
  return message;
}

function chunkText(text: string, limit: number): string[] {
  const chunks: string[] = [];
  let i = 0;
  
  while (i < text.length) {
    let end = Math.min(i + limit, text.length);
    let slice = text.slice(i, end);
    
    if (end < text.length) {
      const lastNewline = slice.lastIndexOf('\n');
      if (lastNewline > Math.floor(limit * 0.6)) {
        end = i + lastNewline + 1;
        slice = text.slice(i, end);
      }
    }
    
    chunks.push(slice);
    i = end;
  }
  
  return chunks;
}

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.DirectMessages,
    GatewayIntentBits.GuildVoiceStates,  // 🎤 Required for voice channel support
  ],
  partials: [Partials.Channel]
});

// ============================================
// 🛡️ DISCORD.JS ERROR HANDLERS
// ============================================
// Catch Discord.js WebSocket and API errors to prevent crashes
client.on('error', (error: Error) => {
  const ignorableErrors = [
    'Connect Timeout Error',
    'Opening handshake has timed out',
    'WebSocket was closed before the connection was established'
  ];
  
  if (ignorableErrors.some(msg => error.message.includes(msg))) {
    console.log(`⚠️  [Discord.js] ${error.message} (non-critical, ignoring)`);
  } else {
    console.error(`❌ [Discord.js Error] ${error.name}: ${error.message}`);
  }
});

client.on('warn', (info: string) => {
  console.log(`⚠️  [Discord.js Warning] ${info}`);
});

// Register attachment forwarder - processes image attachments with Grok API
registerAttachmentForwarder(client);

// Discord Bot Ready Event
client.once('ready', async () => {
  console.log(`🤖 Logged in as ${client.user?.tag}!`);
  console.log(`🔒 Bot-Loop Prevention: ${ENABLE_AUTONOMOUS ? 'ENABLED ✅' : 'DISABLED ⚠️'}`);
  console.log(`🔒 Self-Spam Prevention: ${ENABLE_AUTONOMOUS ? 'Active (Max 3 consecutive) ✅' : 'DISABLED ⚠️'}`);
  
  // 🤖 Initialize MCP Handler (Rider Pi Robot Control)
  initMCPHandler();
  
  // Start background task scheduler
  startTaskCheckerLoop(client);
  
  // Start Letta stats monitoring (daily summary + threshold alerts)
  startDailySummaryScheduler(client);
  await startThresholdMonitoring(client);
  
  // Start daily stats summary (Letta + Chat Stats) - runs at 0:00 configured timezone
  startDailyStatsSummaryScheduler(client);

  // 🎤 Initialize ElevenLabs voice generation service
  if (elevenLabsService) {
    try {
      await elevenLabsService.initialize();
      console.log('✅ ElevenLabs service initialized');
    } catch (error) {
      console.error('❌ Failed to initialize ElevenLabs service:', error);
    }
  }

  // 🎤 Initialize Voice Channel Support (Jan 2026)
  initVoiceSystem(client);
});

// Helper function to send a message and receive a response
async function processAndSendMessage(message: any, messageType: MessageType, conversationContext: string | null = null, customContent: string | null = null): Promise<void> {
  try {
    const msg = await sendMessage(message, messageType, conversationContext, customContent);
    
    if (msg !== "") {
      // 🔒 Record that bot replied (for pingpong tracking)
      if (ENABLE_AUTONOMOUS && client.user?.id) {
        const wasFarewell = msg.toLowerCase().includes('gotta go') || 
                           msg.toLowerCase().includes('catch you later') ||
                           msg.toLowerCase().includes('step away');
        recordBotReply(message.channel.id, client.user?.id || 'unknown', wasFarewell);
      }
      
      if (msg.length <= 1900) {
        await message.reply(msg);
        console.log(`Message sent: ${msg}`);
      } else {
        const chunks = chunkText(msg, 1900);
        await message.reply(chunks[0]);
        
        for (let i = 1; i < chunks.length; i++) {
          await new Promise(r => setTimeout(r, 200));
          await message.channel.send(chunks[i]);
        }
        
        console.log(`Message sent in ${chunks.length} chunks.`);
      }
    }
  } catch (error) {
    console.error("🛑 Error processing and sending message:", error);
  }
}

// Function to start randomized event timer
async function startRandomEventTimer(): Promise<void> {
  if (!ENABLE_TIMER) {
    console.log("🜂 Heartbeat feature is disabled.");
    return;
  }
  
  // Get time-based config
  const config = getHeartbeatConfigForTime();
  
  // Random interval between 50-100% of the configured interval
  const minMinutes = Math.floor(config.intervalMinutes * 0.5);
  const randomMinutes = minMinutes + Math.floor(Math.random() * (config.intervalMinutes - minMinutes));
  console.log(`🜂 💰 Heartbeat scheduled to fire in ${randomMinutes} minutes [${config.description}]`);
  
  const delay = randomMinutes * 60 * 1000;
  
  setTimeout(async () => {
    console.log(`🜂 💰 Heartbeat fired after ${randomMinutes} minutes - checking probability...`);
    
    // Get fresh config in case time period changed
    const currentConfig = getHeartbeatConfigForTime();
    
    // 💰 CREDIT SAVING: Check probability BEFORE making API call!
    const shouldFire = Math.random() < currentConfig.firingProbability;
    
    if (shouldFire) {
      console.log(`🜂 💰 Heartbeat triggered (${currentConfig.firingProbability * 100}% chance) [${currentConfig.description}] - API CALL WILL BE MADE`);
      
      // Try to fetch heartbeat log channel first, fallback to default channel
      const channelToFetch = HEARTBEAT_LOG_CHANNEL_ID || CHANNEL_ID;
      let channel: any = undefined;
      
      console.log(`🜂 [DEBUG] Channel fetch - HEARTBEAT_LOG_CHANNEL_ID=${HEARTBEAT_LOG_CHANNEL_ID}, CHANNEL_ID=${CHANNEL_ID}, channelToFetch=${channelToFetch}`);
      
      if (channelToFetch) {
        try {
          console.log(`🜂 [DEBUG] Attempting to fetch channel: ${channelToFetch}`);
          const fetchedChannel = await client.channels.fetch(channelToFetch);
          console.log(`🜂 [DEBUG] Channel fetched successfully, has 'send': ${fetchedChannel && 'send' in fetchedChannel}`);
          if (fetchedChannel && 'send' in fetchedChannel) {
            channel = fetchedChannel;
            if (HEARTBEAT_LOG_CHANNEL_ID) {
              console.log('🜂 Using heartbeat log channel for heartbeat responses');
            } else {
              console.log('🜂 Using default channel for heartbeat responses');
            }
          } else {
            console.log("⏰ Channel not found or is not a text channel.");
          }
        } catch (error) {
          console.error("⏰ Error fetching channel:", error);
          console.error("⏰ Error details:", error instanceof Error ? error.message : String(error));
        }
      } else {
        console.log("⏰ No channel ID configured (HEARTBEAT_LOG_CHANNEL_ID and CHANNEL_ID both undefined)");
      }
      
      // 💰 ONLY make API call if probability check passed!
      const heartbeatResult = await sendTimerMessage(channel);

      if (heartbeatResult.content && heartbeatResult.target !== 'none') {
        try {
          let sendChannel: any = channel;

          // 💬 Route to DM if Agent chose to send a direct message
          if (heartbeatResult.target === 'dm' && ALLOWED_DM_USER_ID) {
            try {
              const user = await client.users.fetch(ALLOWED_DM_USER_ID);
              sendChannel = await user.createDM();
              console.log(`🜂 Routing heartbeat to DM for user ${user.username}`);
            } catch (dmError) {
              console.error(`🜂 Failed to create DM channel, falling back to heartbeat log channel:`, dmError instanceof Error ? dmError.message : String(dmError));
              sendChannel = channel; // fallback to heartbeat log channel
            }
          } else if (heartbeatResult.target === 'dm' && !ALLOWED_DM_USER_ID) {
            console.warn('🜂 Heartbeat requested DM but ALLOWED_DM_USER_ID is not set, falling back to channel');
          }

          const msg = heartbeatResult.content;

          // 📦 CHUNKING: Split long messages to avoid Discord's 2000 char limit
          if (sendChannel) {
            if (msg.length <= 1900) {
              await sendChannel.send(msg);
              console.log(`🜂 Heartbeat message sent to ${heartbeatResult.target === 'dm' && ALLOWED_DM_USER_ID ? 'DM' : 'channel'}`);
            } else {
              const chunks = chunkText(msg, 1900);
              await sendChannel.send(chunks[0]);

              for (let i = 1; i < chunks.length; i++) {
                await new Promise(r => setTimeout(r, 200));
                await sendChannel.send(chunks[i]);
              }

              console.log(`🜂 Heartbeat message sent in ${chunks.length} chunks (total: ${msg.length} chars) to ${heartbeatResult.target === 'dm' && ALLOWED_DM_USER_ID ? 'DM' : 'channel'}`);
            }
          } else {
            console.log("🜂 No channel available to send heartbeat message");
          }
        } catch (error) {
          console.error("🜂 Error sending heartbeat message:", error);
        }
      } else if (!heartbeatResult.content && channel) {
        console.log("🜂 Heartbeat completed - autonomous actions taken, no message to Discord");
      } else if (!channel) {
        console.log("🜂 No CHANNEL_ID defined or channel not available; message not sent.");
      }
    } else {
      console.log(`🜂 💰 Heartbeat skipped - probability check failed (${(1 - currentConfig.firingProbability) * 100}% chance to skip) [${currentConfig.description}] - NO API CALL MADE`);
    }
    
    setTimeout(() => {
      startRandomEventTimer();
    }, 1000);
  }, delay);
}

// Handle messages
client.on('messageCreate', async (message) => {
  // 🔍 DEBUG: Log all incoming messages to diagnose channel filtering
  console.log(`📨 [DEBUG] Message received: author=${message.author.username}, channel=${message.channel.id}, guild=${message.guild?.id || 'DM'}, content="${message.content.substring(0, 50)}..."`);
  console.log(`📨 [DEBUG] Config: CHANNEL_ID="${CHANNEL_ID || 'UNSET'}", RESPOND_TO_MENTIONS=${RESPOND_TO_MENTIONS}, ENABLE_AUTONOMOUS=${ENABLE_AUTONOMOUS}`);

  // 🔒 AUTONOMOUS: Track ALL messages for context (EXCEPT our own bot messages to save credits!)
  if (ENABLE_AUTONOMOUS && client.user?.id && message.author.id !== client.user.id) {
    trackMessage(message, client.user.id);
  }

  // Let the attachment forwarder handle image attachments
  if (message.attachments?.size) {
    for (const [, att] of message.attachments) {
      const ct = (att as any).contentType || (att as any).content_type || '';
      if (typeof ct === 'string' && ct.startsWith('image/')) {
        return;
      }
    }
  }

  // 🎤 VOICE NOTE TRANSCRIPTION (Dec 2025)
  // Check for voice/audio attachments and transcribe them
  // ONLY transcribe voice notes from USERS, not from the bot itself (checked later)
  if (voiceTranscriptionService && message.attachments?.size && message.author.id !== client.user?.id) {
    for (const [, att] of message.attachments) {
      const ct = (att as any).contentType || (att as any).content_type || '';
      const fileName = (att as any).name || '';
      const audioUrl = (att as any).url || '';

      // Check if this is a voice/audio file
      const isAudio = (typeof ct === 'string' && ct.startsWith('audio/')) ||
                      VoiceTranscriptionService.isSupportedAudioFile(fileName);

      if (isAudio) {
        console.log(`🎤 Voice note detected: ${fileName} (${ct})`);

        try {
          // Transcribe the audio
          const transcription = await voiceTranscriptionService.transcribeAudio({
            audioUrl,
            fileName,
            language: undefined // Auto-detect language
          });

          if (transcription.success && transcription.text) {
            console.log(`✅ Transcription successful: "${transcription.text.substring(0, 100)}${transcription.text.length > 100 ? '...' : ''}"`);
            console.log(`🎤 Language: ${transcription.language || 'auto-detected'}, Duration: ${transcription.duration}ms`);

            // Replace message content with transcription
            // Create a pseudo-message with transcribed text
            const transcribedMessage = {
              ...message,
              content: `[Voice Note] ${transcription.text}`
            };

            // Continue processing with transcribed text
            // Fall through to normal message processing with modified content
            (message as any).content = `[Voice Note] ${transcription.text}`;
            console.log(`🎤 Processing voice note as text message: "${message.content.substring(0, 100)}..."`);
          } else {
            console.error(`❌ Transcription failed: ${transcription.error}`);

            // Send error message back to user
            await message.reply(`⚠️ I couldn't transcribe your voice note: ${transcription.error}. Please try again or send a text message.`);
            return;
          }
        } catch (error) {
          console.error('❌ Error transcribing voice note:', error);
          await message.reply('⚠️ An error occurred while transcribing your voice note. Please try again or send a text message.');
          return;
        }

        // Break after processing first voice attachment
        break;
      }
    }
  }

  // 🤖 MCP COMMAND HANDLER - Rider Pi Robot Control (Dec 2025)
  // Process MCP commands from the dedicated channel BEFORE other filters
  // This allows Letta to control the robot via Discord messages
  if (await handleMCPCommand(message, client)) {
    return; // MCP command was handled
  }
  
  // Filter channels if CHANNEL_ID is set, but ALWAYS allow DMs through
  if (CHANNEL_ID && message.guild && message.channel.id !== CHANNEL_ID) {
    console.log(`📩 [CHANNEL FILTER] Ignoring message from channel ${message.channel.id} (only listening on channel=${CHANNEL_ID})`);
    return;
  }
  console.log(`✅ [CHANNEL FILTER] Passed channel filter check`);

  if (message.author.id === client.user?.id) {
    console.log(`📩 Ignoring message from myself (NOT sending to substrate - saves credits!)...`);
    return;
  }

  // 🛠️ ADMIN COMMAND HANDLER (Oct 16, 2025)
  // CRITICAL: Check BEFORE autonomous mode to prevent blocking!
  // Admin commands should ALWAYS work, even with autonomous mode enabled
  if (message.content.startsWith('!') && client.user?.id) {
    const adminResponse = await handleAdminCommand(message, client.user.id);

    if (adminResponse) {
      // Admin command was handled
      await message.reply(adminResponse);
      return;
    }

    // 🎤 VOICE COMMAND HANDLER (Jan 2026)
    // Check for voice commands (!join, !leave, !talk, !mute, !unmute)
    const voiceResponse = await handleVoiceCommand(message);
    if (voiceResponse) {
      await message.reply(voiceResponse);
      return;
    }

    // Not an admin or voice command, continue to autonomous check
    // (autonomous will ignore it anyway)
  }
  
  // 🔒 AUTONOMOUS: Check if we should respond (bot-loop prevention)
  let conversationContext: string | null = null;
  if (ENABLE_AUTONOMOUS && client.user?.id) {
    const decision = await shouldRespondAutonomously(message, client.user.id, {
      respondToDMs: RESPOND_TO_DMS,
      respondToMentions: RESPOND_TO_MENTIONS,
      respondToBots: RESPOND_TO_BOTS,
      enableAutonomous: ENABLE_AUTONOMOUS
    });
    
    if (!decision.shouldRespond) {
      console.log(`🔒 Not responding: ${decision.reason}`);
      return;
    }
    
    // Save context to pass to Letta (only for Channels, NOT for DMs!)
    const isDM = message.guild === null;
    conversationContext = (!isDM && decision.context) ? decision.context : null;
    console.log(`🔒 Responding: ${decision.reason}`);
  } else {
    // Legacy behavior (no autonomous mode)
    if (message.author.bot && !RESPOND_TO_BOTS) {
      console.log(`📩 Ignoring other bot...`);
      return;
    }
  }
  
  // 📄 FILE CHUNK REQUEST HANDLER (Nov 20, 2025)
  // Check for file chunk requests BEFORE YouTube chunk requests
  console.log('📄 Checking for file chunk requests...');
  const fileChunkResponse = handleFileChunkRequest(message.content);
  if (fileChunkResponse) {
    console.log('📖 File chunk request detected - processing');
    console.log(`📖 Request content: ${message.content.substring(0, 100)}...`);
    console.log('📖 Sending file chunk response to Letta');
    
    // Determine message type
    let messageType = MessageType.GENERIC;
    if (message.guild === null) {
      messageType = MessageType.DM;
    } else if (message.mentions.has(client.user || '') || message.reference) {
      messageType = MessageType.MENTION;
    }
    
    const msg = await sendMessage(message, messageType, conversationContext, fileChunkResponse);
    
    if (msg !== "") {
      // 🔒 Record that bot replied (for pingpong tracking)
      if (ENABLE_AUTONOMOUS && client.user?.id) {
        const wasFarewell = msg.toLowerCase().includes('gotta go') || 
                           msg.toLowerCase().includes('catch you later') ||
                           msg.toLowerCase().includes('step away');
        recordBotReply(message.channel.id, client.user?.id || 'unknown', wasFarewell);
      }
      
      if (msg.length <= 1900) {
        await message.reply(msg);
        console.log(`Message sent: ${msg}`);
      } else {
        const chunks = chunkText(msg, 1900);
        await message.reply(chunks[0]);
        
        for (let i = 1; i < chunks.length; i++) {
          await new Promise(r => setTimeout(r, 200));
          await message.channel.send(chunks[i]);
        }
        
        console.log(`Message sent in ${chunks.length} chunks.`);
      }
    }
    return;
  }
  
  // 🎥 YOUTUBE CHUNK/INFO REQUEST HANDLER (Oct 26, 2025) - TEMPORARILY DISABLED
  // Check for chunk/info requests BEFORE processing YouTube links
  console.log(`🎥 YouTube chunk/info requests temporarily disabled`);
  // const chunkResponse = handleChunkRequest(message.content);
  const chunkResponse = null; // YouTube transcript disabled
  if (false) { // chunkResponse disabled
    console.log('✅ YouTube chunk/info request detected - processing');
    console.log(`📖 Request content: ${message.content.substring(0, 100)}...`);
    console.log(`📖 Chunk response length: 0 characters`);
    console.log('📖 Sending chunk/info response to Letta');
    
    // Determine message type
    let messageType = MessageType.GENERIC;
    if (message.guild === null) {
      messageType = MessageType.DM;
    } else if (message.mentions.has(client.user || '') || message.reference) {
      messageType = MessageType.MENTION;
    }
    
    const msg = await sendMessage(message, messageType, conversationContext, chunkResponse);
    
    if (msg !== "") {
      // 🔒 Record that bot replied (for pingpong tracking)
      if (ENABLE_AUTONOMOUS && client.user?.id) {
        const wasFarewell = msg.toLowerCase().includes('gotta go') || 
                           msg.toLowerCase().includes('catch you later') ||
                           msg.toLowerCase().includes('step away');
        recordBotReply(message.channel.id, client.user?.id || 'unknown', wasFarewell);
      }
      
      if (msg.length <= 1900) {
        await message.reply(msg);
        console.log(`Message sent: ${msg}`);
      } else {
        const chunks = chunkText(msg, 1900);
        await message.reply(chunks[0]);
        
        for (let i = 1; i < chunks.length; i++) {
          await new Promise(r => setTimeout(r, 200));
          await message.channel.send(chunks[i]);
        }
        
        console.log(`Message sent in ${chunks.length} chunks.`);
      }
    }
    return;
  }
  
  // 🎥 PREPROCESS YOUTUBE LINKS (Oct 26, 2025)
  // Automatically fetch and attach transcripts to messages
  console.log('🎥 Checking message for YouTube links...');
  let statusMessage: any = null;
  
  // Check if message contains YouTube links
  const youtubeRegex = /https?:\/\/(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/g;
  const hasYouTubeLinks = youtubeRegex.test(message.content);
  
  if (hasYouTubeLinks) {
    console.log('🎥 YouTube link(s) detected in message!');
    // Send status message to user
    statusMessage = await message.reply('🎥 Fetching video transcript(s)...').catch(() => null);
    console.log('📺 User notified: Fetching YouTube transcript(s)');
  } else {
    console.log('🎥 No YouTube links found - skipping transcript processing');
  }
  
  // YouTube transcript disabled due to ES module compatibility
  // const youtubeResult = await preprocessYouTubeLinks(
  //   message.content,
  //   async () => await message.channel.sendTyping()
  // );
  const youtubeResult = { processedMessage: message.content, videosProcessed: 0, videosFailed: 0 };
  
  // Delete status message and send completion info
  if (statusMessage) {
    await statusMessage.delete().catch(() => console.log('⚠️ Could not delete status message'));
    
    if (youtubeResult.videosProcessed > 0) {
      const statusText = youtubeResult.videosFailed > 0
        ? `✅ Processed ${youtubeResult.videosProcessed} video(s) | ⚠️ ${youtubeResult.videosFailed} failed (no transcript)`
        : `✅ Processed ${youtubeResult.videosProcessed} video transcript(s) - sending to Letta...`;
      
      const completionMsg = await message.reply(statusText).catch(() => null);
      console.log(`📺 ${statusText}`);
      
      // Delete completion message after 3 seconds
      if (completionMsg) {
        setTimeout(async () => {
          await completionMsg.delete().catch(() => {});
        }, 3000);
      }
    }
  }
  
  // Store processed content for use in message handlers
  const processedContent = youtubeResult.processedMessage !== message.content ? youtubeResult.processedMessage : null;
  
  // Handle DMs
  if (message.guild === null) {
    console.log(`📩 Received DM from ${message.author.username} (${message.author.id}): ${message.content}`);
    
    // 🔒 DM RESTRICTION: Check if DM is from allowed user (if configured)
    if (ALLOWED_DM_USER_ID && message.author.id !== ALLOWED_DM_USER_ID) {
      console.log(`🔒 DM restriction: Ignoring DM from ${message.author.id} (not ${ALLOWED_DM_USER_ID})`);
      await message.reply(`❌ Sorry, I can only receive DMs from the authorized user.`);
      return;
    }
    
    if (RESPOND_TO_DMS) {
      // If content was modified (transcript added), send with custom content
      if (processedContent) {
        console.log('📺 Transcript(s) attached to message - sending to Letta');
      }
      processAndSendMessage(message, MessageType.DM, conversationContext, processedContent);
    } else {
      console.log(`📩 Ignoring DM...`);
    }
    return;
  }
  
  // Handle mentions and replies
  if (RESPOND_TO_MENTIONS && (message.mentions.has(client.user || '') || message.reference)) {
    console.log(`📩 Received message from ${message.author.username}: ${message.content}`);
    await message.channel.sendTyping();
    
    let messageType = MessageType.MENTION;
    
    if (message.reference && message.reference.messageId) {
      const originalMessage = await message.channel.messages.fetch(message.reference.messageId);
      
      if (originalMessage.author.id === client.user?.id) {
        messageType = MessageType.REPLY;
      } else {
        messageType = message.mentions.has(client.user || '') ? MessageType.MENTION : MessageType.GENERIC;
      }
    }
    
    // If content was modified (transcript added), send with custom content
    if (processedContent) {
      console.log('📺 Transcript(s) attached to message - sending to Letta');
    }
    
    const msg = await sendMessage(message, messageType, conversationContext, processedContent);
    if (msg !== "") {
      // 🔒 Record bot reply
      if (ENABLE_AUTONOMOUS && client.user?.id) {
        const wasFarewell = msg.toLowerCase().includes('gotta go') ||
                           msg.toLowerCase().includes('catch you later') ||
                           msg.toLowerCase().includes('step away');
        recordBotReply(message.channel.id, client.user?.id || 'unknown', wasFarewell);
      }

      // 📦 CHUNKING: Split long messages to avoid Discord's 2000 char limit
      if (msg.length <= 1900) {
        // For DMs, send directly instead of replying (avoids routing issues)
        if (message.channel.type === 1) { // 1 = DM channel type in Discord.js
          await message.author.send(msg);
        } else {
          await message.reply(msg);
        }
        console.log(`📨 Message sent: ${msg.substring(0, 100)}...`);
      } else {
        const chunks = chunkText(msg, 1900);
        // For DMs, send directly instead of replying (avoids routing issues)
        if (message.channel.type === 1) { // 1 = DM channel type in Discord.js
          await message.author.send(chunks[0]);
        } else {
          await message.reply(chunks[0]);
        }

        for (let i = 1; i < chunks.length; i++) {
          await new Promise(r => setTimeout(r, 200));
          await message.channel.send(chunks[i]);
        }

        console.log(`📦 Message sent in ${chunks.length} chunks (total: ${msg.length} chars)`);
      }
    }
    return;
  }
  
  // Generic messages
  if (RESPOND_TO_GENERIC) {
    console.log(`📩 Received (non-mention) message from ${message.author.username}: ${message.content}`);
    // If content was modified (transcript added), send with custom content
    if (processedContent) {
      console.log('📺 Transcript(s) attached to message - sending to Letta');
    }
    processAndSendMessage(message, MessageType.GENERIC, conversationContext, processedContent);
    return;
  }
});

// ============================================
// TTS API Routes - REMOVED
// ============================================
// Local Piper TTS system removed in favor of ElevenLabs integration
// See tools/send_voice_message.py for voice message functionality

// ============================================
// Midjourney Proxy API
// ============================================

const MIDJOURNEY_CHANNEL_ID = process.env.MIDJOURNEY_CHANNEL_ID;
const MIDJOURNEY_BOT_ID = '936929561302675456'; // Official Midjourney bot ID

app.post('/api/midjourney/generate', (req, res) => {
  (async () => {
  try {
    const { prompt, cref, sref, ar, v, cw, sw, style, chaos, quality } = req.body;
    
    if (!prompt) {
      return res.status(400).json({ error: 'Missing required parameter: prompt' });
    }
    
    if (!MIDJOURNEY_CHANNEL_ID) {
      return res.status(500).json({ error: 'MIDJOURNEY_CHANNEL_ID not configured' });
    }
    
    // Get Midjourney channel
    const channel = await client.channels.fetch(MIDJOURNEY_CHANNEL_ID);
    if (!channel || !('send' in channel)) {
      return res.status(500).json({ error: 'Midjourney channel not found or invalid' });
    }
    
    // Build Midjourney command
    let mjCommand = `/imagine prompt: ${prompt}`;
    
    // Add parameters
    if (ar && ar !== '1:1') mjCommand += ` --ar ${ar}`;
    if (v) mjCommand += ` --v ${v}`;
    if (style && style !== 'default') mjCommand += ` --style ${style}`;
    if (chaos && chaos > 0) mjCommand += ` --chaos ${chaos}`;
    if (quality && quality !== 1) mjCommand += ` --q ${quality}`;
    
    // Add character reference
    if (cref) {
      mjCommand += ` --cref ${cref}`;
      if (cw && cw !== 100) mjCommand += ` --cw ${cw}`;
    }
    
    // Add style reference
    if (sref) {
      mjCommand += ` --sref ${sref}`;
      if (sw && sw !== 100) mjCommand += ` --sw ${sw}`;
    }
    
    console.log(`🎨 [MJ Proxy] Sending command: ${mjCommand.substring(0, 100)}...`);
    
    // Send the command
    const sentMessage = await channel.send(mjCommand);
    const commandTimestamp = sentMessage.createdTimestamp;
    
    console.log(`⏳ [MJ Proxy] Waiting for Midjourney response...`);
    
    // Poll for Midjourney response
    const maxWaitTime = 120000; // 2 minutes
    const pollInterval = 3000; // 3 seconds
    const startTime = Date.now();
    
    while (Date.now() - startTime < maxWaitTime) {
      await new Promise(resolve => setTimeout(resolve, pollInterval));
      
      // Fetch recent messages
      const messages = await channel.messages.fetch({ limit: 10 });
      
      // Look for Midjourney's response
      for (const msg of messages.values()) {
        // Check if from Midjourney bot
        if (msg.author.id !== MIDJOURNEY_BOT_ID) continue;
        
        // Check if after our command
        if (msg.createdTimestamp <= commandTimestamp) continue;
        
        // Check for attachments (completed image)
        if (msg.attachments.size > 0) {
          const attachment = msg.attachments.first();
          if (attachment) {
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            console.log(`✅ [MJ Proxy] Image generated in ${elapsed}s`);
            
            return res.json({
              status: 'completed',
              image_url: attachment.url,
              filename: attachment.name,
              width: attachment.width || 0,
              height: attachment.height || 0,
              generation_time: `${elapsed}s`,
              command: mjCommand,
              message_id: msg.id
            });
          }
        }
      }
      
      console.log(`⏳ [MJ Proxy] Still waiting... (${Math.floor((Date.now() - startTime) / 1000)}s elapsed)`);
    }
    
    // Timeout
    return res.status(408).json({
      status: 'timeout',
      error: `Generation timed out after ${maxWaitTime / 1000}s`,
      note: 'Check Discord channel manually - generation might still complete'
    });
    
  } catch (error: any) {
    console.error('❌ [MJ Proxy] Error:', error);
    return res.status(500).json({
      status: 'error',
      error: error.message || String(error)
    });
  }
  })().catch((e: any) => {
    console.error('❌ [MJ Proxy] Uncaught error:', e);
    res.status(500).json({ status: 'error', error: String(e?.message || e) });
  });
});

// ============================================
// Voice Message API Endpoint
// ============================================

/**
 * POST /api/send-voice-message
 *
 * Substrate calls this endpoint to send voice messages via ElevenLabs
 *
 * Body params:
 * - text (required): Text to convert to speech
 * - target (required): Discord user ID or channel ID
 * - target_type (optional): "user" or "channel" (auto-detected if not specified)
 * - voice_id (optional): ElevenLabs voice ID
 * - model_id (optional): ElevenLabs model ID (default: eleven_v3)
 * - stability (optional): Voice stability (0.0-1.0)
 * - similarity_boost (optional): Similarity boost (0.0-1.0)
 * - style (optional): Style exaggeration (0.0-1.0)
 * - use_speaker_boost (optional): Enable speaker boost
 * - reply_to_message_id (optional): Discord message ID to reply to
 */
app.post('/api/send-voice-message', (req, res) => {
  (async () => {
    try {
      // Check if ElevenLabs is configured
      if (!discordVoiceSender || !elevenLabsService) {
        return res.status(503).json({
          status: 'error',
          error: 'Voice message service not configured (missing ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID)'
        });
      }

      // Validate required parameters
      const { text, target, target_type } = req.body;

      if (!text || typeof text !== 'string') {
        return res.status(400).json({
          status: 'error',
          error: 'Missing or invalid required parameter: text'
        });
      }

      if (!target || typeof target !== 'string') {
        return res.status(400).json({
          status: 'error',
          error: 'Missing or invalid required parameter: target'
        });
      }

      // Validate text length
      if (text.length > 3000) {
        return res.status(400).json({
          status: 'error',
          error: `Text too long (${text.length} characters). Maximum is 3000 characters.`
        });
      }

      console.log(`🎤 [Voice API] Received request: text="${text.substring(0, 50)}...", target=${target}, target_type=${target_type || 'auto'}`);

      // Determine target channel or DM
      let targetChannel: any;
      let isDM = false;

      if (target_type === 'user') {
        // Explicit user - create DM
        try {
          const user = await client.users.fetch(target);
          targetChannel = await user.createDM();
          isDM = true;
          console.log(`🎤 [Voice API] Using DM channel for user ${user.username}`);
        } catch (error) {
          return res.status(404).json({
            status: 'error',
            error: `Failed to create DM with user ${target}: ${error instanceof Error ? error.message : String(error)}`
          });
        }
      } else if (target_type === 'channel') {
        // Explicit channel - fetch channel
        try {
          targetChannel = await client.channels.fetch(target);
          if (!targetChannel || !('send' in targetChannel)) {
            return res.status(404).json({
              status: 'error',
              error: `Channel ${target} not found or is not a text channel`
            });
          }
          console.log(`🎤 [Voice API] Using channel ${(targetChannel as any).name || target}`);
        } catch (error) {
          return res.status(404).json({
            status: 'error',
            error: `Failed to fetch channel ${target}: ${error instanceof Error ? error.message : String(error)}`
          });
        }
      } else {
        // Auto-detect: try user first, then channel
        // Discord IDs are indistinguishable, so we have to try both
        try {
          const user = await client.users.fetch(target);
          targetChannel = await user.createDM();
          isDM = true;
          console.log(`🎤 [Voice API] Auto-detected as user DM for ${user.username}`);
        } catch (userError) {
          // Not a user, try as channel
          console.log(`🎤 [Voice API] Not a user, trying as channel...`);
          try {
            targetChannel = await client.channels.fetch(target);
            if (!targetChannel || !('send' in targetChannel)) {
              return res.status(404).json({
                status: 'error',
                error: `Target ${target} is neither a valid user nor a text channel`
              });
            }
            console.log(`🎤 [Voice API] Auto-detected as channel ${(targetChannel as any).name || target}`);
          } catch (channelError) {
            return res.status(404).json({
              status: 'error',
              error: `Failed to resolve target ${target} as user or channel. User error: ${userError instanceof Error ? userError.message : String(userError)}. Channel error: ${channelError instanceof Error ? channelError.message : String(channelError)}`
            });
          }
        }
      }

      // Send voice message
      const result = await discordVoiceSender.sendVoiceMessage({
        text,
        target: targetChannel,
        voiceId: req.body.voice_id,
        modelId: req.body.model_id,
        stability: req.body.stability,
        similarityBoost: req.body.similarity_boost,
        style: req.body.style,
        useSpeakerBoost: req.body.use_speaker_boost,
        replyToMessageId: req.body.reply_to_message_id
      });

      if (result.success) {
        console.log(`✅ [Voice API] Voice message sent successfully: message_id=${result.messageId}`);
        return res.json({
          status: 'success',
          message: 'Voice message sent successfully',
          message_id: result.messageId,
          audio_size_bytes: result.audioSize,
          generation_time_ms: result.duration,
          target: target,
          target_type: isDM ? 'dm' : 'channel'
        });
      } else {
        console.error(`❌ [Voice API] Failed to send voice message: ${result.error}`);
        return res.status(500).json({
          status: 'error',
          error: result.error || 'Unknown error occurred while sending voice message'
        });
      }

    } catch (error: any) {
      console.error('❌ [Voice API] Unexpected error:', error);
      return res.status(500).json({
        status: 'error',
        error: error.message || String(error)
      });
    }
  })().catch((e: any) => {
    console.error('❌ [Voice API] Uncaught error:', e);
    res.status(500).json({ status: 'error', error: String(e?.message || e) });
  });
});

// ============================================
// Send Message API (for substrate integration)
// ============================================

app.post('/api/send-message', (req, res) => {
  (async () => {
    try {
      const { message, target, target_type, mention_users, ping_everyone, ping_here } = req.body;

      if (!message) {
        return res.status(400).json({ error: 'Missing required parameter: message' });
      }

      if (!target) {
        return res.status(400).json({ error: 'Missing required parameter: target (channel ID or user ID)' });
      }

      // Determine channel ID
      let channel_id = target;
      let is_dm = false;

      if (target_type === 'user') {
        // Create DM channel
        try {
          const dmChannel = await client.users.fetch(target).then(user => user.createDM());
          channel_id = dmChannel.id;
          is_dm = true;
        } catch (error) {
          return res.status(500).json({
            error: `Failed to create DM channel: ${error instanceof Error ? error.message : String(error)}`
          });
        }
      } else if (!target_type || target_type === 'channel') {
        // Use target as channel ID directly
        channel_id = target;
        is_dm = false;
      } else {
        return res.status(400).json({ error: `Invalid target_type: ${target_type}. Must be 'user' or 'channel'` });
      }

      // Get the channel
      const channel = await client.channels.fetch(channel_id);
      if (!channel || !('send' in channel)) {
        return res.status(500).json({ error: 'Channel not found or cannot send messages to it' });
      }

      // Build message content with mentions
      let messageContent = message;

      if (target_type === 'channel') {
        if (ping_everyone) {
          messageContent = `@everyone ${message}`;
        } else if (ping_here) {
          messageContent = `@here ${message}`;
        } else if (mention_users && Array.isArray(mention_users) && mention_users.length > 0) {
          const mentions = mention_users.map(userId => `<@${userId}>`).join(' ');
          messageContent = `${mentions} ${message}`;
        }
      }

      // Auto-chunk messages over 2000 characters
      const MAX_LENGTH = 2000;
      const chunks: string[] = [];

      if (messageContent.length <= MAX_LENGTH) {
        chunks.push(messageContent);
      } else {
        // Split by newlines to preserve structure
        let currentChunk = '';
        for (const line of messageContent.split('\n')) {
          if (currentChunk.length + line.length + 1 <= MAX_LENGTH) {
            currentChunk += line + '\n';
          } else {
            if (currentChunk) {
              chunks.push(currentChunk.trimEnd());
            }
            currentChunk = line + '\n';
          }
        }
        if (currentChunk) {
          chunks.push(currentChunk.trimEnd());
        }

        // Handle single lines that are too long
        const finalChunks: string[] = [];
        for (const chunk of chunks) {
          if (chunk.length <= MAX_LENGTH) {
            finalChunks.push(chunk);
          } else {
            for (let i = 0; i < chunk.length; i += MAX_LENGTH) {
              finalChunks.push(chunk.slice(i, i + MAX_LENGTH));
            }
          }
        }
        chunks.length = 0;
        chunks.push(...finalChunks);
      }

      // Send all chunks
      const sentMessages = [];
      for (let i = 0; i < chunks.length; i++) {
        const sentMsg = await channel.send(chunks[i]);
        sentMessages.push({
          message_id: sentMsg.id,
          chunk: i + 1,
          total_chunks: chunks.length
        });
      }

      return res.json({
        status: 'success',
        message: `Message sent to ${is_dm ? 'user' : 'channel'} ${target} (${chunks.length} chunk${chunks.length > 1 ? 's' : ''})`,
        message_ids: sentMessages.map(m => m.message_id),
        chunks_sent: chunks.length,
        channel_id: channel_id,
        target_type: is_dm ? 'dm' : 'channel',
        mentions_added: ping_everyone || ping_here || (mention_users && mention_users.length > 0)
      });

    } catch (error: any) {
      console.error('❌ [Send Message API] Error:', error);
      return res.status(500).json({
        status: 'error',
        error: error.message || String(error)
      });
    }
  })().catch((e: any) => {
    console.error('❌ [Send Message API] Uncaught error:', e);
    res.status(500).json({ status: 'error', error: String(e?.message || e) });
  });
});

// ============================================
// Health Check Endpoints
// ============================================

// Grok health check
app.get('/tool/grok-health', (req, res) => {
  (async () => {
    const baseUrl = process.env.GROK_BASE_URL || 'http://localhost:8284';
    const sessionId = process.env.GROK_SESSION_ID || 'discord-bot';

    const grokClient = new GrokClient({ baseUrl, sessionId });

    const t0 = Date.now();
    const response = await grokClient.healthCheck();
    const dt = Date.now() - t0;

    res.json({ ok: true, baseUrl, sessionId, latency_ms: dt, health: response });
  })().catch((e: any) => {
    res.status(500).json({ ok: false, error: String(e?.message || e) });
  });
});

// General health check
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'Discord-Grok Bot',
    uptime: process.uptime(),
    discord: client.isReady() ? 'connected' : 'disconnected',
    grok: {
      baseUrl: process.env.GROK_BASE_URL || 'http://localhost:8284',
      sessionId: process.env.GROK_SESSION_ID || 'discord-bot',
      model: process.env.GROK_MODEL || '(substrate default)',
    },
    voice: 'elevenlabs',
    autonomous: ENABLE_AUTONOMOUS ? 'enabled' : 'disabled',
    timestamp: new Date().toISOString(),
  });
});

// ============================================
// Start Server
// ============================================

app.listen(PORT, () => {
  console.log('');
  console.log('🔥 ============================================');
  console.log(`🚀 Server listening on port ${PORT}`);
  console.log('🔥 ============================================');
  console.log('');
  console.log('Services:');
  console.log(`  - Discord Bot: ${RESPOND_TO_DMS || RESPOND_TO_MENTIONS || RESPOND_TO_GENERIC ? 'Enabled' : 'Disabled'}`);
  console.log(`  - Heartbeat: ${ENABLE_TIMER ? 'Enabled' : 'Disabled'}`);
  console.log(`  - TTS API: Disabled (using ElevenLabs integration instead)`);
  console.log(`  - Voice Channels: ${process.env.VOICE_ENABLED === 'true' ? 'ENABLED 🎤' : 'Disabled'}`);
  console.log(`  - Bot-Loop Prevention: ${ENABLE_AUTONOMOUS ? 'ENABLED 🔒' : 'DISABLED ⚠️'}`);
  // 🔒 DM RESTRICTION STATUS
  if (ALLOWED_DM_USER_ID) {
    console.log(`  - 🔒 DM Restriction: ACTIVE (only user ${ALLOWED_DM_USER_ID})`);
  } else {
    console.log(`  - ⚠️  DM Restriction: DISABLED (ALLOWED_DM_USER_ID not set - all DMs allowed)`);
  }
  console.log('');
  
  const token = String(process.env.DISCORD_TOKEN || '').trim();
  client.login(token);
  startRandomEventTimer();
});

