/**
 * AUTONOMOUS CONVERSATION SYSTEM
 * ===============================
 * 
 * Allows the bot to:
 * 1. See ALL messages in channels (not just @mentions)
 * 2. Decide autonomously whether to respond
 * 3. Prevent infinite bot-to-bot loops (CRITICAL for credit conservation!)
 * 
 * Features:
 * - Conversation context tracking
 * - Bot-loop detection (prevents bot-to-bot infinite conversations)
 * - Cooldown system (prevents spam)
 * - Interest scoring (measures conversation relevance)
 */

import { Message } from "discord.js";

// ===== CONFIGURATION =====
const BOT_PINGPONG_MAX = 1; // Max bot-to-bot exchanges (1 = 2 messages total: Bot1 → Bot2 → STOP)
const BOT_LOOP_COOLDOWN_MS = 60000; // 60 seconds cooldown after limit reached
const MAX_TRACKED_MESSAGES = 50; // Keep last N messages in memory
const MAX_MESSAGE_LENGTH = 2000; // Discord's max message length
const MAX_CONSECUTIVE_SELF_MESSAGES = 3; // 🚨 CRITICAL: Max consecutive messages from our bot without human/other bot (Self-Spam Prevention Oct 16, 2025)
// REMOVED: USER_COOLDOWN_MS - humans can message freely (bot-loop prevention still active)

// WHITELIST: Servers wo requireHumanAfterCooldown NICHT aktiviert wird
// Loop Prevention trotzdem aktiv! Nur: nach Cooldown kein Human nötig
const REQUIRE_HUMAN_WHITELIST: string[] = [
    // 'YOUR_SERVER_ID_HERE' // Add your bot-testing server ID here
];

// CHANNEL WHITELIST: Channels wo Bot-Loop-Prevention KOMPLETT deaktiviert ist (nur Menschen + unser Bot)
// DISABLED nach Spam-Incident Oct 15, 2025 - Bot-Loop Prevention ÜBERALL aktiv für Safety
const BOT_LOOP_DISABLED_CHANNELS: string[] = [
    // REMOVED - Loop Prevention is active everywhere for safety
    // Add channel IDs here to disable loop prevention (NOT RECOMMENDED)
];

// Bot farewell messages when limit reached (bot can choose one or create own)
const FAREWELL_SUGGESTIONS = [
  "I need to step away - let's continue this later! 👋",
  "Reached my conversation limit for now. Catch you later!",
  "I'll let you folks take it from here. Have a great discussion! ✨",
  "Gotta go - don't want to monopolize the chat! 😄"
];

// ===== STATE TRACKING =====
interface ConversationMessage {
  author: string;
  authorId: string;
  isBot: boolean;
  content: string;
  timestamp: number;
  channelId: string;
}

interface ChannelState {
  messages: ConversationMessage[];
  lastBotReply: number;
  botPingPongCount: number; // Count of bot-to-bot exchanges
  lastHumanMessage: number; // Timestamp of last human message (resets counter)
  cooldownUntil: number;
  shouldFarewell: boolean; // Flag to indicate bot should say goodbye
  userLastMessage: Map<string, number>; // Track last message time per user (rate limiting)
  requireHumanAfterCooldown: boolean; // SECURITY: After bot-loop cooldown, only respond to humans until one speaks
  guildId: string | null; // Store guild ID for whitelist checks
}

const channelStates = new Map<string, ChannelState>();

/**
 * Get or create channel state
 */
function getChannelState(channelId: string): ChannelState {
  if (!channelStates.has(channelId)) {
    channelStates.set(channelId, {
      messages: [],
      lastBotReply: 0,
      botPingPongCount: 0,
      lastHumanMessage: 0,
      cooldownUntil: 0,
      shouldFarewell: false,
      userLastMessage: new Map<string, number>(),
      requireHumanAfterCooldown: false,
      guildId: null // Store guild ID for whitelist checks
    });
  }
  return channelStates.get(channelId)!;
}

/**
 * Add message to conversation tracking
 * SECURITY: Validates message length and tracks user activity
 */
export function trackMessage(message: Message, botUserId: string) {
  // SECURITY: Validate channel exists
  if (!message.channel?.id) {
    console.error('⚠️ Message has no channel ID - skipping tracking');
    return;
  }
  
  const state = getChannelState(message.channel.id);
  const now = Date.now();
  
  // Store guild ID for whitelist checks
  if (message.guild && !state.guildId) {
    state.guildId = message.guild.id;
  }
  
  // SECURITY: Truncate excessively long messages
  const safeContent = message.content?.substring(0, MAX_MESSAGE_LENGTH) || '';
  
  const conversationMessage: ConversationMessage = {
    author: message.author?.username || 'Unknown',
    authorId: message.author?.id || 'unknown',
    isBot: message.author?.bot || false,
    content: safeContent,
    timestamp: now,
    channelId: message.channel.id
  };
  
  state.messages.push(conversationMessage);
  
  // Track user activity for rate limiting
  if (message.author?.id) {
    state.userLastMessage.set(message.author.id, now);
  }
  
  // CRITICAL: Reset bot pingpong counter when human speaks!
  if (!message.author.bot) {
    state.lastHumanMessage = now;
    state.botPingPongCount = 0;
    state.shouldFarewell = false;
    state.requireHumanAfterCooldown = false; // Reset: Human has spoken!
    console.log(`👤 Human message detected - bot pingpong counter reset`);
  }
  
  // Keep only recent messages
  if (state.messages.length > MAX_TRACKED_MESSAGES) {
    state.messages.shift();
  }
}

/**
 * 🚨 SELF-SPAM PREVENTION (Oct 16, 2025 - Critical Security Fix!)
 * ================================================================
 * Prevents bot from creating infinite self-loops (e.g. responding to its own messages)
 * 
 * Counts consecutive messages from OUR bot without ANY other message (human or bot) in between
 * 
 * Example of what this PREVENTS:
 *   the bot: "Hey everyone!"
 *   the bot: "Oh and another thing..."
 *   the bot: "Also I wanted to mention..."
 *   the bot: "And one more thing..." ← STOP HERE! (3 consecutive = limit)
 * 
 * SECURITY: Resets counter when ANY other user (human or bot) speaks
 */
function detectSelfSpam(state: ChannelState, myBotId: string): {
  limitReached: boolean;
  consecutiveCount: number;
} {
  if (state.messages.length === 0) {
    return { limitReached: false, consecutiveCount: 0 };
  }

  // Count consecutive messages from our bot (starting from most recent)
  let consecutiveCount = 0;
  for (let i = state.messages.length - 1; i >= 0; i--) {
    const msg = state.messages[i];
    
    if (msg.authorId === myBotId) {
      consecutiveCount++;
    } else {
      // Different user (human or other bot) → stop counting
      break;
    }
  }

  return {
    limitReached: consecutiveCount >= MAX_CONSECUTIVE_SELF_MESSAGES,
    consecutiveCount
  };
}

/**
 * Detect if we're in a bot-to-bot pingpong that needs to stop
 * CRITICAL: Prevents infinite conversations that waste credits!
 * 
 * Counts bot-to-bot exchanges involving OUR bot (not time-based, so works even with slow Letta tools)
 * Resets when humans speak!
 * SECURITY: Only counts exchanges where our bot is involved
 */
function detectBotPingPong(state: ChannelState, myBotId: string): { limitReached: boolean; count: number; involvedInPingPong: boolean } {
  if (state.messages.length < 4) {
    return { limitReached: false, count: 0, involvedInPingPong: false };
  }
  
  // Get messages since last human message
  // Find last non-bot message (manual search for compatibility)
  let lastHumanIndex = -1;
  for (let i = state.messages.length - 1; i >= 0; i--) {
    if (!state.messages[i].isBot) {
      lastHumanIndex = i;
      break;
    }
  }
  const messagesSinceHuman = lastHumanIndex >= 0 
    ? state.messages.slice(lastHumanIndex + 1)
    : state.messages;
  
  // Count bot-to-bot exchanges where ANOTHER bot responds to OUR bot
  // CRITICAL: Our bot responding doesn't count - only OTHER bots responding to us!
  let exchanges = 0;
  let lastBotId: string | null = null;
  let otherBotInvolved = false;
  
  for (const msg of messagesSinceHuman) {
    if (msg.isBot) {
      // Track if any OTHER bot is involved
      if (msg.authorId !== myBotId) {
        otherBotInvolved = true;
      }
      
      if (lastBotId && lastBotId !== msg.authorId) {
        // Different bot replied = pingpong!
        // ONLY count if: previous msg was OUR bot AND current msg is ANOTHER bot
        // (Our bot replying to anyone doesn't count as pingpong!)
        if (lastBotId === myBotId && msg.authorId !== myBotId) {
          exchanges++;
        }
      }
      lastBotId = msg.authorId;
    }
  }
  
  // If we hit the limit AND another bot is involved, it's time to stop!
  return { 
    limitReached: exchanges >= BOT_PINGPONG_MAX && otherBotInvolved,
    count: exchanges,
    involvedInPingPong: otherBotInvolved
  };
}

/**
 * Format timestamp to configured timezone (same format as in messages.ts)
 * Format: "Mo, 20.11., 14:30"
 */
function formatTimestamp(timestamp: number): string {
  try {
    const date = new Date(timestamp);
    // Validate date before formatting
    if (isNaN(date.getTime())) {
      return '';
    }
    
    // Format: "Mo, 20.11., 14:30" (Wochentag, Datum, Zeit)
    const TIMEZONE = process.env.TIMEZONE || 'America/New_York';
    const LOCALE = process.env.LOCALE || 'en-US';
    const dateFormatter = new Intl.DateTimeFormat(LOCALE, {
      timeZone: TIMEZONE,
      weekday: 'short',  // Mo, Di, Mi, etc.
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
    
    const formatted = dateFormatter.format(date);
    // Format: "Mo., 20.11., 14:30" -> "Mo, 20.11., 14:30" (remove period after weekday)
    return formatted.replace(/^(\w+)\./, '$1');
  } catch (err) {
    console.error('⚠️ Timestamp formatting failed:', err instanceof Error ? err.message : err);
    return '';
  }
}

/**
 * Build conversation context for Letta
 * Shows ONLY messages AFTER MIORÉ'S (this bot's) last reply (what the bot "missed")
 * IMPORTANT: Excludes the current/triggering message (it's sent separately!)
 * 
 * Example:
 *   the bot: "Hey wie geht's?"
 *   User1: "Gut!"
 *   User2: "Mir auch!"
 *   User3: "@the bot danke!"
 * 
 * → Context shows: User1, User2 (messages SINCE the bot's last reply)
 * → Current message: User3 (sent separately)
 */
export function buildConversationContext(channelId: string, botUserId: string, channelName?: string): string {
  const state = getChannelState(channelId);
  
  if (state.messages.length === 0) {
    return "[No recent conversation]";
  }
  
  // Find the last message from THIS bot (the bot), not any other bot
  let lastMioreMessageIndex = -1;
  for (let i = state.messages.length - 1; i >= 0; i--) {
    if (state.messages[i].authorId === botUserId) {
      lastMioreMessageIndex = i;
      break;
    }
  }
  
  // Get messages AFTER the bot's last reply, EXCLUDING the current/triggering message
  // Current message is the last one, so we use -1 to exclude it
  let recentMessages: ConversationMessage[];
  
  if (lastMioreMessageIndex === -1) {
    // the bot hasn't replied yet - show last few messages (excluding current)
    recentMessages = state.messages.slice(-6, -1);
  } else {
    // Show messages AFTER the bot's last reply (excluding current)
    recentMessages = state.messages.slice(lastMioreMessageIndex + 1, -1);
  }
  
  if (recentMessages.length === 0) {
    return "[No messages since your last reply]";
  }
  
  // Build header with channel name if provided
  const header = channelName 
    ? `=== Messages since your last reply in ${channelName} ===`
    : "=== Messages since your last reply ===";
  
  const lines: string[] = [
    header,
    ""
  ];
  
  for (const msg of recentMessages) {
    const prefix = msg.authorId === botUserId ? "🤖 YOU" : 
                   msg.isBot ? `🤖 ${msg.author}` : 
                   `👤 ${msg.author}`;
    
    // Format timestamp (configured timezone)
    const timeStr = formatTimestamp(msg.timestamp);
    const timeDisplay = timeStr ? ` [${timeStr}]` : '';
    
    lines.push(`${prefix}${timeDisplay}: ${msg.content.substring(0, 150)}`);
  }
  
  lines.push("");
  lines.push("=== End of Context ===");
  
  return lines.join("\n");
}

/**
 * Check if bot should respond to this message
 * Returns: {shouldRespond: boolean, reason: string}
 */
export function shouldRespondAutonomously(
  message: Message,
  botUserId: string,
  opts: {
    respondToDMs: boolean;
    respondToMentions: boolean;
    respondToBots: boolean;
    enableAutonomous: boolean;
  }
): { shouldRespond: boolean; reason: string; context?: string } {
  
  const state = getChannelState(message.channel.id);
  const now = Date.now();
  
  // 1. ALWAYS ignore self
  if (message.author.id === botUserId) {
    return { shouldRespond: false, reason: "Self message" };
  }
  
  // 2. ALWAYS ignore commands (!)
  if (message.content.startsWith('!')) {
    return { shouldRespond: false, reason: "Command message" };
  }
  
  // 3. Check if channel is whitelisted (bot-loop prevention disabled)
  const channelId = message.channel.id;
  const isChannelWhitelisted = BOT_LOOP_DISABLED_CHANNELS.includes(channelId);
  
  if (isChannelWhitelisted) {
    console.log(`🔓 Channel ${channelId} is whitelisted - bot-loop prevention DISABLED`);
  }
  
  // 3a. Check cooldown (bot loop prevention) - SKIP if channel is whitelisted
  if (!isChannelWhitelisted && state.cooldownUntil > now) {
    const remainingSeconds = Math.ceil((state.cooldownUntil - now) / 1000);
    return { 
      shouldRespond: false, 
      reason: `Cooldown active (${remainingSeconds}s remaining - bot loop prevention)` 
    };
  }
  
  // 3b. SECURITY: After cooldown, only respond to humans until one speaks (prevents loop restart)
  // EXCEPTION: Whitelisted servers OR whitelisted channels
  const guildId = message.guild ? message.guild.id : null;
  const isWhitelisted = guildId && REQUIRE_HUMAN_WHITELIST.includes(guildId);
  
  if (state.requireHumanAfterCooldown && message.author.bot && !isWhitelisted && !isChannelWhitelisted) {
    return {
      shouldRespond: false,
      reason: "Post-cooldown: Waiting for human message before responding to bots again"
    };
  }
  
  // 3b. REMOVED: User rate limiting - humans can message freely
  // (Bot-to-bot loop prevention is still active above)
  
  // 3c. 🚨 SELF-SPAM PREVENTION (Oct 16, 2025 - Critical Security Fix!)
  // Check if bot has sent too many consecutive messages without any other user responding
  // CRITICAL: Prevents infinite self-loops where bot responds to its own messages!
  if (!isChannelWhitelisted) {
    const selfSpam = detectSelfSpam(state, botUserId);
    if (selfSpam.limitReached) {
      console.warn(`🛑 SELF-SPAM DETECTED in channel ${message.channel.id}! Bot sent ${selfSpam.consecutiveCount} consecutive messages without response!`);
      state.cooldownUntil = now + BOT_LOOP_COOLDOWN_MS;
      state.shouldFarewell = true; // Signal bot to say goodbye
      
      // SECURITY: Only respond to humans after cooldown
      if (!isWhitelisted) {
        state.requireHumanAfterCooldown = true;
      }
      
      // Return context so agent can craft farewell message
      const farewellContext = `\n\n[SYSTEM NOTE: You've sent ${selfSpam.consecutiveCount} consecutive messages without anyone else responding. Please send a brief, friendly farewell message and give others space to respond. Suggestions: ${FAREWELL_SUGGESTIONS.join(' | ')}]`;
      
      // Get channel name for context
      const channelNameForFarewell = 'name' in message.channel ? `#${message.channel.name}` : 'DM';
      
      return { 
        shouldRespond: true, // Let bot say goodbye!
        reason: `Self-spam limit reached (${selfSpam.consecutiveCount} consecutive messages) - sending farewell`,
        context: buildConversationContext(message.channel.id, botUserId, channelNameForFarewell) + farewellContext
      };
    }
    
    // Warn when approaching limit
    if (selfSpam.consecutiveCount === MAX_CONSECUTIVE_SELF_MESSAGES - 1) {
      console.warn(`⚠️ Approaching self-spam limit in channel ${message.channel.id} (${selfSpam.consecutiveCount}/${MAX_CONSECUTIVE_SELF_MESSAGES})`);
    }
  }
  
  // 4. Detect bot pingpong limit - SKIP if channel is whitelisted
  if (!isChannelWhitelisted) {
    const pingpong = detectBotPingPong(state, botUserId);
    if (pingpong.limitReached) {
      console.warn(`🛑 Bot pingpong limit reached in channel ${message.channel.id}! (${pingpong.count} exchanges)`);
      state.cooldownUntil = now + BOT_LOOP_COOLDOWN_MS;
      state.botPingPongCount = 0;
      state.shouldFarewell = true; // Signal bot to say goodbye
      // SECURITY: Only respond to humans after cooldown (unless whitelisted server)
      if (!isWhitelisted) {
        state.requireHumanAfterCooldown = true;
      }
      
      // Return context so agent can craft farewell message
      const farewellContext = `\n\n[SYSTEM NOTE: You've reached the bot conversation limit (${BOT_PINGPONG_MAX} exchanges). Please send a brief, friendly farewell message to end the conversation gracefully. Suggestions: ${FAREWELL_SUGGESTIONS.join(' | ')}]`;
      
      // Get channel name for context
      const channelNameForPingpong = 'name' in message.channel ? `#${message.channel.name}` : 'DM';
      
      return { 
        shouldRespond: true, // Let bot say goodbye!
        reason: `Bot pingpong limit reached (${pingpong.count} exchanges) - sending farewell`,
        context: buildConversationContext(message.channel.id, botUserId, channelNameForPingpong) + farewellContext
      };
    }
    
    // Warn when approaching limit (only makes sense if MAX > 1)
    if (BOT_PINGPONG_MAX > 1 && pingpong.count === BOT_PINGPONG_MAX - 1) {
      console.warn(`⚠️ Approaching bot pingpong limit in channel ${message.channel.id} (${pingpong.count}/${BOT_PINGPONG_MAX})`);
    }
  }
  
  // 5. Check if it's a bot (and if we should respond to bots)
  if (message.author.bot && !opts.respondToBots) {
    return { shouldRespond: false, reason: "Bot message (RESPOND_TO_BOTS=false)" };
  }
  
  // 6. DM handling
  if (!message.guild) {
    if (opts.respondToDMs) {
      return { 
        shouldRespond: true, 
        reason: "Direct Message",
        context: buildConversationContext(message.channel.id, botUserId, 'DM')
      };
    }
    return { shouldRespond: false, reason: "DM (RESPOND_TO_DMS=false)" };
  }
  
  // Get channel name for context (used in multiple places below)
  const channelName = 'name' in message.channel ? `#${message.channel.name}` : 'DM';
  
  // 7. Mentioned or reply
  if (message.mentions.has(botUserId) || message.reference) {
    if (opts.respondToMentions) {
      return { 
        shouldRespond: true, 
        reason: "Mentioned or replied to",
        context: buildConversationContext(message.channel.id, botUserId, channelName)
      };
    }
  }
  
  // 8. AUTONOMOUS MODE - bot decides itself!
  if (opts.enableAutonomous) {
    const context = buildConversationContext(message.channel.id, botUserId, channelName);
    
    // Build decision prompt for agent
    return {
      shouldRespond: true, // Let Letta decide
      reason: "Autonomous mode - agent will decide",
      context: context
    };
  }
  
  // 9. Default: don't respond
  return { shouldRespond: false, reason: "No matching conditions" };
}

/**
 * Record that bot replied
 * CRITICAL: Updates state for pingpong detection
 */
export function recordBotReply(channelId: string, botUserId: string, wasFarewell: boolean = false) {
  const state = getChannelState(channelId);
  const now = Date.now();
  
  state.lastBotReply = now;
  
  // Check if channel is whitelisted (no cooldowns!)
  const isChannelWhitelisted = BOT_LOOP_DISABLED_CHANNELS.includes(channelId);
  
  // If this was a farewell, activate cooldown (SKIP if channel is whitelisted)
  if (wasFarewell && !isChannelWhitelisted) {
    state.cooldownUntil = now + BOT_LOOP_COOLDOWN_MS;
    state.shouldFarewell = false;
    // SECURITY: Only respond to humans after cooldown (unless whitelisted server)
    const isWhitelisted = state.guildId && REQUIRE_HUMAN_WHITELIST.includes(state.guildId);
    if (!isWhitelisted) {
      state.requireHumanAfterCooldown = true;
    }
    console.log(`👋 Bot sent farewell in channel ${channelId}. Cooldown active for ${BOT_LOOP_COOLDOWN_MS/1000}s - will only respond to humans after`);
  }
  else if (wasFarewell && isChannelWhitelisted) {
    console.log(`👋 Bot sent farewell in whitelisted channel ${channelId} - NO COOLDOWN`);
  }
  else {
    // Count the pingpong
    const pingpong = detectBotPingPong(state, botUserId);
    console.log(`📊 Bot replied in channel ${channelId}. Pingpong count: ${pingpong.count}/${BOT_PINGPONG_MAX} (involved: ${pingpong.involvedInPingPong})`);
  }
}

/**
 * Get conversation stats for debugging
 */
export function getConversationStats(channelId: string, botUserId: string = '') {
  const state = getChannelState(channelId);
  const pingpong = detectBotPingPong(state, botUserId);
  const selfSpam = detectSelfSpam(state, botUserId);
  
  return {
    messageCount: state.messages.length,
    botPingPongCount: pingpong.count,
    pingPongLimit: BOT_PINGPONG_MAX,
    consecutiveSelfMessages: selfSpam.consecutiveCount,
    selfSpamLimit: MAX_CONSECUTIVE_SELF_MESSAGES,
    shouldFarewell: state.shouldFarewell,
    cooldownActive: state.cooldownUntil > Date.now(),
    cooldownRemaining: Math.max(0, state.cooldownUntil - Date.now()),
    timeSinceLastHuman: Date.now() - state.lastHumanMessage,
    involvedInPingPong: pingpong.involvedInPingPong,
    requireHumanAfterCooldown: state.requireHumanAfterCooldown
  };
}

