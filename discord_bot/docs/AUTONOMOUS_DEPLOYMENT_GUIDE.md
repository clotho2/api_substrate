# Autonomous System Deployment Guide

**Date:** 2025-10-14  
**Version:** 1.0  
**Target:** Production deployment of autonomous conversation system

---

## 📋 Overview

This guide shows you how to activate the **autonomous conversation system** that enables the bot to:
- ✅ See all messages in channels (not just mentions)
- ✅ Decide whether to respond based on conversation context
- ✅ Prevent bot-to-bot loops with smart detection
- ✅ Track conversation context across multiple bots

---

## 📁 Required Files

You need these **3 files** from the session:

1. ✅ `src/autonomous.ts` - Core autonomous logic
2. ✅ `src/messages.ts` - Updated message handler (with conversation context)

---

## 🔧 Step 1: Update `server.ts`

### Location to Edit

Find the section where the bot processes incoming messages. Look for:

```javascript
client.on('messageCreate', async (message) => {
    // ... existing code ...
});
```

### Changes Required

**1. Import the autonomous module at the top of the file:**

```javascript
const { shouldRespondAutonomously, trackMessage, recordBotReply } = require('./autonomous');
```

**2. Add ENABLE_AUTONOMOUS env variable check (after other imports):**

```javascript
const ENABLE_AUTONOMOUS = process.env.ENABLE_AUTONOMOUS === 'true';
```

**3. Inside the `messageCreate` event handler, BEFORE any other checks:**

```javascript
client.on('messageCreate', async (message) => {
    // Ignore messages from the bot itself
    if (message.author.id === client.user?.id) return;
    
    // Track ALL messages for autonomous system
    if (ENABLE_AUTONOMOUS && client.user?.id) {
        trackMessage(message, client.user.id);
    }
    
    // Check if we should respond (autonomous decision)
    let conversationContext = null;
    if (ENABLE_AUTONOMOUS && client.user?.id) {
        const decision = shouldRespondAutonomously(message, client.user.id, {
            botName: client.user.username,
            allowedChannels: process.env.ALLOWED_CHANNEL_IDS?.split(',') || []
        });
        
        if (!decision.shouldRespond) {
            console.log(`🚫 Not responding: ${decision.reason}`);
            return;
        }
        
        // Save context to pass to Letta (only for Channels, NOT for DMs!)
        const isDM = message.guild === null;
        conversationContext = (!isDM && decision.context) ? decision.context : null;
        
        console.log(`🔒 Responding: ${decision.reason}`);
    }
    
    // ... rest of your existing message handling code ...
});
```

**4. Pass conversationContext to your message sending functions:**

Update your `sendMessage()` calls to include the context:

```javascript
// Example for mentions
const msg = await sendMessage(message, MessageType.MENTION, conversationContext);

// Example for DMs
await processAndSendMessage(message, MessageType.DM, conversationContext);

// Example for generic messages
await processAndSendMessage(message, MessageType.GENERIC, conversationContext);
```

**5. After sending a message, record the bot's reply:**

```javascript
if (ENABLE_AUTONOMOUS && client.user?.id && message.channel?.id) {
    recordBotReply(message.channel.id, client.user.id);
}
```

---

## 🔧 Step 2: Update `messages.ts`

### Changes Required

**1. Update the `sendMessage` function signature:**

Change from:
```javascript
async function sendMessage(discordMessageObject, messageType) {
```

To:
```javascript
async function sendMessage(discordMessageObject, messageType, conversationContext = null) {
```

**2. Prepend conversation context to Letta message:**

Inside `sendMessage()`, before creating the `lettaMessage` object:

```javascript
// Prepend conversation context if provided
const contextPrefix = conversationContext 
    ? `\n\n${conversationContext}\n\n` 
    : '';

const lettaMessage = {
    role: "user",
    name: USE_SENDER_PREFIX ? undefined : senderNameReceipt,
    content: USE_SENDER_PREFIX
        ? messageType === MessageType.MENTION
            ? `${contextPrefix}[${senderNameReceipt} sent a message mentioning you in ${channelContext}] ${message}${attachmentInfo}`
            : messageType === MessageType.REPLY
                ? `${contextPrefix}[${senderNameReceipt} replied to you in ${channelContext}] ${message}${attachmentInfo}`
                : messageType === MessageType.DM
                    ? `${contextPrefix}[${senderNameReceipt} sent you a direct message] ${message}${attachmentInfo}`
                    : `${contextPrefix}[${senderNameReceipt} sent a message in ${channelContext}] ${message}${attachmentInfo}`
        : contextPrefix + message + attachmentInfo
};
```

**3. Update `processAndSendMessage` function signature (if you have it):**

Change from:
```javascript
async function processAndSendMessage(message, messageType) {
```

To:
```javascript
async function processAndSendMessage(message, messageType, conversationContext = null) {
```

And pass it through to `sendMessage()`:
```javascript
const agentMessageResponse = await sendMessage(message, messageType, conversationContext);
```

---

## 🌍 Step 3: Update `.env` file

Add this line to your `.env` file:

```bash
# Autonomous System (enables conversation tracking & smart responses)
ENABLE_AUTONOMOUS=true

# Bot will ignore messages from other bots (unless mentioned with @everyone)
RESPOND_TO_BOTS=false
```

**Important:**
- Set `ENABLE_AUTONOMOUS=true` to activate the system
- Set `RESPOND_TO_BOTS=false` to prevent basic bot-to-bot loops
- The autonomous system handles smart bot interactions

---

## 🚀 Step 4: Deploy & Restart

**1. The source files are in the monorepo:**

```
/home/user/api_substrate/discord_bot/src/autonomous.ts
/home/user/api_substrate/discord_bot/src/messages.ts
/home/user/api_substrate/discord_bot/src/server.ts
```

**2. Update `.env`:**

```bash
nano /home/user/api_substrate/discord_bot/.env
# Add: ENABLE_AUTONOMOUS=true
```

**3. Restart the bot:**

```bash
sudo systemctl restart agent-discord
journalctl -u agent-discord --lines 100
```

---

## 🧪 Step 5: Test It

### Test 1: Bot ignores irrelevant messages
1. Write a message in a channel that doesn't mention the bot
2. Expected: Bot logs `🚫 Not responding: No interest in conversation`

### Test 2: Bot responds to mentions
1. Mention the bot: `@BotName hello`
2. Expected: Bot logs `🔒 Responding: Direct mention from user` and replies

### Test 3: Bot prevents loops
1. Have another bot mention your bot
2. Your bot replies
3. Other bot replies
4. Expected: Your bot logs `👋 Bot sent farewell` and enters cooldown

### Test 4: Conversation context works
1. Have two bots chat in a channel
2. A human sends a message
3. Expected: Your bot sees the previous bot messages as context in Letta

---

## 📊 Monitoring

Watch the logs for these indicators:

```bash
journalctl -u agent-discord -f
```

**Good signs:**
- `📊 Bot replied in channel X. Pingpong count: 0/1`
- `🔒 Responding: Direct mention from user`
- `👤 Human message detected - bot pingpong counter reset`

**Warning signs:**
- `🛑 Bot pingpong limit reached in channel X!`
- `⚠️ Message has no channel ID - skipping tracking`

---

## 🔒 Security Features Built-In

✅ **Bot-Loop Prevention:** Max 1 bot-to-bot exchange before cooldown  
✅ **Cooldown System:** 60-second pause after loop detected  
✅ **RequireHumanAfterCooldown:** Only respond to humans after cooldown  
✅ **Message Length Validation:** Truncates long messages (max 2000 chars)  
✅ **Channel Validation:** Checks if channel exists before processing  
✅ **Conversation Context:** Only sent in channels, NOT in DMs  
✅ **Server Whitelist:** Testing server excluded from some rules  

---

## ⚙️ Configuration Options

You can customize behavior in `src/autonomous.ts`:

```javascript
// At the top of autonomous.ts
const BOT_PINGPONG_MAX = 1;           // Max bot exchanges (1 = 2 messages)
const BOT_LOOP_COOLDOWN_MS = 60000;   // 60 seconds cooldown
const MAX_TRACKED_MESSAGES = 50;       // Keep last 50 messages in memory
const MAX_MESSAGE_LENGTH = 2000;       // Discord's max
const USER_COOLDOWN_MS = 3000;         // 3 seconds between user messages

// Whitelist for bot-only channels (no requireHumanAfterCooldown)
const REQUIRE_HUMAN_WHITELIST = [
    'YOUR_SERVER_ID_HERE' // Your bot-testing server
];
```

---

## 🐛 Troubleshooting

### Bot doesn't respond to anything
- Check `ENABLE_AUTONOMOUS=true` in `.env`
- Check logs for `🚫 Not responding:` messages
- Verify `autonomous.ts` is in `src/` folder

### Bot creates loops with other bots
- Check `BOT_PINGPONG_MAX` is set to `1`
- Verify `recordBotReply()` is called after sending messages
- Check logs for pingpong count

### Conversation context not working
- Verify `conversationContext` is passed to `sendMessage()`
- Check that `buildConversationContext()` is being called
- Confirm it's a channel (not DM)

### Bot responds to its own messages
- Check `if (message.author.id === client.user?.id) return;` is FIRST in handler
- Verify logs show `📩 Ignoring message from myself...`

---

## 📚 Related Documentation

- `SESSION_2025-10-14_BOT_IMPROVEMENTS_FINAL.md` - Full session log
- `API_CALL_TRACKING.md` - API usage monitoring
- `autonomous.ts` - Inline code comments explain each function

---

## ✅ Checklist

Before going live:

- [ ] `autonomous.ts` in `src/`
- [ ] `messages.ts` updated with conversation context
- [ ] `server.ts` updated with autonomous integration
- [ ] `.env` updated with `ENABLE_AUTONOMOUS=true`
- [ ] Bot restarted with `sudo systemctl restart agent-discord`
- [ ] Logs checked for errors
- [ ] Test 1: Bot ignores irrelevant messages ✅
- [ ] Test 2: Bot responds to mentions ✅
- [ ] Test 3: Bot prevents loops ✅
- [ ] Test 4: Conversation context works ✅

---

**Questions?** Check the inline comments in `autonomous.ts` or review the session log.

**Good luck! 🚀**

