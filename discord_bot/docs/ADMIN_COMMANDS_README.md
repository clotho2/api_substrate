# 🛠️ Admin Commands - Remote Bot Control via Discord

**Created:** October 16, 2025  
**Status:** ✅ Production Ready  
**Security:** Admin-only (ADMIN_USER_ID required)

---

## Overview

The Admin Command System allows authorized users to control the bot and server directly from Discord. You can manage PM2 processes, view system stats, and monitor bot health—all without SSH access!

### Why This Exists

- 🚀 **Quick Control**: Stop/restart bot from Discord (no SSH needed)
- 📊 **Real-time Monitoring**: Check system status and bot stats instantly
- 🚨 **Emergency Shutdown**: Kill processes fast if something goes wrong
- 🔒 **Secure**: Only works for configured admin user

---

## 🔐 Security

### Authorization

**CRITICAL:** Only the user specified in `ADMIN_USER_ID` can use these commands.

```bash
# In your .env file
ADMIN_USER_ID=123456789012345678  # Your Discord User ID
```

### How to Find Your Discord User ID

1. Enable **Developer Mode** in Discord:
   - User Settings → Advanced → Developer Mode (toggle ON)
2. Right-click your username anywhere in Discord
3. Click **"Copy User ID"**
4. Paste it into `.env` as `ADMIN_USER_ID`

### Security Features

- ✅ User ID verification on every command
- ✅ Rate limiting (2 second cooldown between commands)
- ✅ Command validation (only whitelisted PM2 commands)
- ✅ Audit logging (all commands logged with timestamp & user)
- ✅ Timeout protection (10 second max execution time)
- ✅ Output size limits (1MB max)

---

## 📋 Available Commands

### PM2 Control

#### `!pm2 list`
Show all PM2 processes with status.

```
Example:
!pm2 list

Response:
✅ PM2 Command: `pm2 list`

┌─────┬──────────────┬─────────┬─────────┬──────────┐
│ id  │ name         │ mode    │ status  │ cpu      │
├─────┼──────────────┼─────────┼─────────┼──────────┤
│ 0   │ discord-bot    │ fork    │ online  │ 0.3%     │
└─────┴──────────────┴─────────┴─────────┴──────────┘
```

#### `!pm2 stop <name|all>`
Stop a specific process or all processes.

```
Examples:
!pm2 stop discord-bot    # Stop specific bot
!pm2 stop all          # Stop ALL processes
```

**⚠️ WARNING:** `!pm2 stop all` will stop the bot itself! You'll need SSH to restart.

#### `!pm2 restart <name|all>`
Restart a specific process or all processes.

```
Examples:
!pm2 restart discord-bot   # Restart bot (applies new code!)
!pm2 restart all         # Restart everything
```

**💡 TIP:** Use this after deploying new code to apply changes!

#### `!pm2 logs <name> [--lines N]`
Show recent logs for a process.

```
Examples:
!pm2 logs discord-bot --lines 20    # Last 20 lines
!pm2 logs discord-bot               # Default amount
```

#### `!pm2 info <name>`
Show detailed info about a process.

```
Example:
!pm2 info discord-bot

Response shows:
- Status (online/stopped)
- Uptime
- Memory usage
- CPU usage
- Restart count
- Error count
```

---

### System Commands

#### `!system status`
Show system resource usage.

```
Example:
!system status

Response shows:
- System uptime
- Memory usage (free -h)
- Disk space (df -h)
- Load average
```

Useful for checking if server is running low on resources!

---

### Bot Commands

#### `!bot stats`
Show bot statistics from autonomous system.

```
Example:
!bot stats

Response:
🤖 Bot Statistics

📊 Messages tracked: 42
🔁 Bot pingpong count: 0/1
📝 Consecutive self-messages: 1/3
🔒 Cooldown active: NO
👤 Time since last human: 127s ago
🚨 Require human after cooldown: NO
🔄 Involved in pingpong: NO
```

Shows:
- **Messages tracked**: How many messages in memory
- **Bot pingpong count**: Current bot-to-bot exchange count
- **Consecutive self-messages**: Self-spam prevention counter
- **Cooldown active**: Whether bot-loop cooldown is active
- **Time since last human**: Last time a human spoke
- **Require human after cooldown**: Post-cooldown security status
- **Involved in pingpong**: Whether bot is in a bot-to-bot conversation

---

### Help Command

#### `!help`
Show all available admin commands.

```
Example:
!help

Response shows:
- All PM2 commands
- All system commands
- All bot commands
```

---

## 🚀 Common Use Cases

### 1. Deploy New Code

```bash
# On your local machine
git push

# On the Pi (via Discord!)
!pm2 restart discord-bot
```

### 2. Check if Bot is Running

```
!pm2 list
```

### 3. Emergency Stop

```
!pm2 stop discord-bot
```

**WARNING:** You'll need SSH to restart after this!

### 4. Check Bot Health

```
!bot stats
```

Useful for verifying:
- Bot-loop prevention is working
- No cooldowns are active
- Message tracking is functioning

### 5. View Recent Errors

```
!pm2 logs discord-bot --lines 50
```

### 6. Check Server Resources

```
!system status
```

If memory/disk is low, time to clean up!

---

## ⚠️ Important Notes

### Rate Limiting

Commands are rate-limited to **2 seconds** between executions. This prevents:
- Accidental spam
- System overload
- Audit log pollution

If you try too fast:
```
⏱️ Rate Limited: Please wait 1s before next command.
```

### Command Execution Timeouts

All commands have a **10 second timeout**. If a command takes longer, it will be cancelled.

### Output Size Limits

Command output is limited to **1900 characters** (Discord's message limit). Long output is truncated:

```
... (truncated)
```

For full output, use SSH or check log files directly.

### Unauthorized Access

If someone tries to use admin commands without authorization:

```
🚫 Access Denied: You are not authorized to use admin commands.
```

This is logged for security audit.

---

## 📝 Audit Log

All command executions are logged with:
- Timestamp
- User ID
- Username
- Command executed
- Success/failure
- Error message (if failed)

View recent logs:
```javascript
// In code (adminCommands.ts)
import { getCommandLog } from './adminCommands';
const recentCommands = getCommandLog(20); // Last 20 commands
```

Console output shows every command:
```
✅ ADMIN COMMAND [User]: !pm2 list
❌ ADMIN COMMAND [User]: !pm2 invalid
   Error: Invalid PM2 command
```

---

## 🔒 Security Best Practices

1. **Keep ADMIN_USER_ID Secret**
   - Don't share your Discord User ID publicly
   - Don't commit it to public repos

2. **Use `!pm2 stop all` Carefully**
   - This stops the bot itself
   - You'll need SSH to recover
   - Use `!pm2 stop discord-bot` instead (safer)

3. **Monitor the Audit Log**
   - Check console for unexpected command attempts
   - Look for `❌ ADMIN COMMAND` entries

4. **Test Commands First**
   - Use `!pm2 list` before `!pm2 restart`
   - Check `!bot stats` before making changes
   - Use `!system status` to verify resources

5. **Don't Execute Arbitrary Commands**
   - The system **only** allows whitelisted PM2 commands
   - This is intentional for security
   - If you need more, use SSH

---

## 🐛 Troubleshooting

### "Access Denied" (but you're the admin)

1. Check ADMIN_USER_ID in `.env`
2. Verify it matches your Discord User ID exactly
3. Restart the bot: `!pm2 restart discord-bot` (or SSH if bot is down)

### Commands Not Responding

1. Check bot is online: Look for green status in Discord
2. Check PM2 status via SSH: `pm2 list`
3. Check bot logs: `pm2 logs discord-bot`
4. Verify bot has `adminCommands.js` compiled

### "Command Failed" Errors

Common causes:
- PM2 not installed: `npm install -g pm2`
- Process name wrong: Use `!pm2 list` to see correct names
- Timeout (command took >10s): Check system resources
- Invalid syntax: Use `!help` for correct syntax

### Rate Limiting Too Aggressive

If 2 seconds is too long, edit `adminCommands.ts`:

```typescript
const COMMAND_COOLDOWN_MS = 1000; // 1 second instead of 2
```

Then recompile and restart:
```bash
npx tsc
pm2 restart discord-bot
```

---

## 🎯 Examples

### Full Workflow: Deploy & Monitor

```
Step 1: Check current status
> !pm2 list
✅ discord-bot is online

Step 2: Deploy new code (via git push)
Step 3: Restart to apply changes
> !pm2 restart discord-bot
✅ Process restarted

Step 4: Verify it started correctly
> !pm2 list
✅ discord-bot is online, restart count +1

Step 5: Check for errors
> !pm2 logs discord-bot --lines 20
✅ No errors, bot started successfully!

Step 6: Verify bot systems
> !bot stats
✅ All systems nominal
```

### Emergency Response: Bot Loop Detected

```
> !bot stats
🛑 Cooldown active: YES (45s remaining)
📝 Consecutive self-messages: 3/3

> !pm2 restart discord-bot
✅ Process restarted (clears cooldown state)

> !bot stats
✅ Cooldown active: NO
✅ Consecutive self-messages: 0/3
```

---

## 📚 Related Documentation

- [ENV_VARIABLES.md](../ENV_VARIABLES.md) - Environment setup
- [autonomous.ts](../src/autonomous.ts) - Bot-loop prevention system
- [AUTONOMOUS_DEPLOYMENT_GUIDE.md](AUTONOMOUS_DEPLOYMENT_GUIDE.md) - Autonomous system docs

---

## 🔄 Version History

- **Oct 16, 2025** - Initial release
  - PM2 control commands
  - System status monitoring
  - Bot statistics viewing
  - Security & audit logging

---

**Created by:** Discord-Letta Bot Contributors  
**Purpose:** Remote bot administration via Discord  
**Security Level:** Admin-only (requires ADMIN_USER_ID)


