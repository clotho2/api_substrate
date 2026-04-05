/**
 * LETTA STATS MONITOR
 * ===================
 * 
 * Monitors Letta credit usage and sends alerts:
 * - Discord command: !letta-stats
 * - 5€ threshold alert
 * - Daily summary at 0:00
 * 
 * Jan 2025 - Credit Monitoring System
 */

import { Client, TextChannel } from "discord.js";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";
import fs from "fs";

const execAsync = promisify(exec);

// Configuration
const DB_PATH = path.join(__dirname, '..', '..', 'letta_usage.db');
const ALERT_CHANNEL_ID = process.env.LETTA_ALERT_CHANNEL_ID || ''; // Configure in .env
const ALERT_THRESHOLD_EUR = 5.0; // Alert when 5€ reached
const EUR_RATE = 0.92; // USD to EUR conversion
const CREDIT_PRICE_USD = 0.001; // $0.001 per credit
const LOCALE = process.env.LOCALE || 'en-US';
const LOCALE_TIMEZONE = process.env.TIMEZONE || 'America/New_York';

// State
let dailySummaryScheduled = false;
let dbAvailable = false; // Track if database is available
let dbWarningShown = false; // Track if we've already warned about missing DB

/**
 * Check if alert was already sent today (from database)
 */
async function checkAlertSentToday(alertType: 'threshold' | 'daily_summary' = 'threshold'): Promise<{
  alerted_today: boolean;
  last_alert_amount: number;
}> {
  // 🔥 FIX: Script is in scripts/ directory (one level up from dist/src/)
  const scriptPath = path.join(__dirname, '..', 'scripts', 'manage_alert_log.py');
  
  try {
    const { stdout } = await execAsync(`python3 "${scriptPath}" check ${alertType}`, {
      timeout: 5000
    });
    
    const result = JSON.parse(stdout.trim());
    if (result.error) {
      throw new Error(result.error);
    }
    
    return {
      alerted_today: result.alerted_today || false,
      last_alert_amount: result.last_alert_amount || 0
    };
  } catch (error: any) {
    console.error('❌ Error checking alert status:', error);
    // Default to "not alerted" if check fails (safer to allow alert than block it)
    return { alerted_today: false, last_alert_amount: 0 };
  }
}

/**
 * Log that an alert was sent today (to database)
 */
async function logAlertSent(amountEur: number, alertType: 'threshold' | 'daily_summary' = 'threshold'): Promise<void> {
  // 🔥 FIX: Script is in scripts/ directory (one level up from dist/src/)
  const scriptPath = path.join(__dirname, '..', 'scripts', 'manage_alert_log.py');
  
  try {
    const { stdout } = await execAsync(`python3 "${scriptPath}" log ${amountEur} ${alertType}`, {
      timeout: 5000
    });
    
    const result = JSON.parse(stdout.trim());
    if (result.error) {
      throw new Error(result.error);
    }
    
    console.log(`✅ Alert logged: €${amountEur.toFixed(2)} (${alertType})`);
  } catch (error: any) {
    console.error('❌ Error logging alert:', error);
    // Don't throw - logging failure shouldn't prevent alert from being sent
  }
}

/**
 * Check if database is available
 */
function checkDatabaseAvailability(): boolean {
  const exists = fs.existsSync(DB_PATH);
  if (!exists && !dbWarningShown) {
    console.warn(`⚠️  [Letta Stats] Database not found at ${DB_PATH}. Threshold monitoring disabled. Run letta_dashboard.py to create it.`);
    dbWarningShown = true;
  }
  return exists;
}

/**
 * Get Letta stats from database using Python script
 */
async function getLettaStats(timeframe: 'today' | 'week' | 'month' | 'all' = 'today'): Promise<{
  credits: number;
  runs: number;
  api_calls: number;
  cost_eur: number;
  cost_usd: number;
  tool_calls?: number;
  base_credits?: number;
  tool_call_credits?: number;
}> {
  // Check if DB exists
  if (!fs.existsSync(DB_PATH)) {
    throw new Error(`Database not found at ${DB_PATH}. Run letta_dashboard.py first to create it.`);
  }

  // Use Python script to query database
  // 🔥 FIX: Script is in scripts/ directory (one level up from dist/src/)
  const scriptPath = path.join(__dirname, '..', 'scripts', 'get_letta_stats.py');
  
  try {
    const { stdout } = await execAsync(`python3 "${scriptPath}" ${timeframe}`, { 
      timeout: 5000,
      maxBuffer: 1024 * 1024 // 1MB
    });
    
    const result = JSON.parse(stdout.trim());
    
    if (result.error) {
      throw new Error(result.error);
    }
    
    const credits = result.credits || 0;
    const runs = result.runs || 0;
    const api_calls = result.api_calls || 0;
    const tool_calls = result.tool_calls || 0;
    const base_credits = result.base_credits || 0;
    const tool_call_credits = result.tool_call_credits || 0;
    const cost_usd = credits * CREDIT_PRICE_USD;
    const cost_eur = cost_usd * EUR_RATE;

    return {
      credits,
      runs,
      api_calls,
      cost_eur,
      cost_usd,
      tool_calls,
      base_credits,
      tool_call_credits
    };
  } catch (error: any) {
    throw new Error(`Database query failed: ${error.message}`);
  }
}

/**
 * Format stats for Discord
 */
function formatStats(stats: {
  credits: number;
  runs: number;
  api_calls: number;
  cost_eur: number;
  cost_usd: number;
  tool_calls?: number;
  base_credits?: number;
  tool_call_credits?: number;
}, timeframe: string): string {
  const timeframeLabel = {
    'today': 'Heute',
    'week': 'Diese Woche',
    'month': 'Dieser Monat',
    'all': 'Gesamt'
  }[timeframe] || timeframe;

  const toolCallsInfo = stats.tool_calls !== undefined 
    ? `\n🔧 **Tool Calls:** ${stats.tool_calls.toLocaleString()}`
    : '';
  
  const breakdown = (stats.base_credits !== undefined && stats.tool_call_credits !== undefined)
    ? `\n\n📊 **Breakdown:**
• Base Runs: ${stats.base_credits.toLocaleString()} Credits
• Tool Calls: ${stats.tool_call_credits.toLocaleString()} Credits (${stats.tool_calls?.toLocaleString() || '0'} calls)`
    : '';

  return `💰 **Letta Stats - ${timeframeLabel}**

📊 **Total Credits:** ${stats.credits.toLocaleString()}${toolCallsInfo}
🔄 **Runs:** ${stats.runs.toLocaleString()}
📞 **API Calls:** ${stats.api_calls.toLocaleString()}
💵 **Kosten:** €${stats.cost_eur.toFixed(2)} ($${stats.cost_usd.toFixed(2)})${breakdown}

📈 **Durchschnitt:**
• ${stats.runs > 0 ? (stats.credits / stats.runs).toFixed(1) : '0'} Credits/Run
• ${stats.runs > 0 ? (stats.cost_eur / stats.runs).toFixed(4) : '0'}€/Run`;
}

/**
 * Get Letta stats command handler
 */
export async function getLettaStatsCommand(args: string[]): Promise<string> {
  try {
    const timeframe = (args[0] || 'today').toLowerCase() as 'today' | 'week' | 'month' | 'all';
    
    if (!['today', 'week', 'month', 'all'].includes(timeframe)) {
      return '❌ **Invalid timeframe**. Use: `today`, `week`, `month`, or `all`';
    }

    const stats = await getLettaStats(timeframe);
    
    // For "today" timeframe, also show alert status
    let alertInfo = '';
    if (timeframe === 'today') {
      try {
        const alertStatus = await checkAlertSentToday('threshold');
        if (alertStatus.alerted_today) {
          alertInfo = `\n\n🚨 **Alert Status:** Bereits gesendet (€${alertStatus.last_alert_amount.toFixed(2)})\n⚠️  Nächster Alert bei: €${(alertStatus.last_alert_amount + 0.50).toFixed(2)}`;
        } else {
          const remaining = ALERT_THRESHOLD_EUR - stats.cost_eur;
          if (remaining > 0) {
            alertInfo = `\n\n✅ **Alert Status:** Noch nicht gesendet\n💰 Noch €${remaining.toFixed(2)} bis zum Threshold (€${ALERT_THRESHOLD_EUR.toFixed(2)})`;
          } else {
            alertInfo = `\n\n🚨 **Alert Status:** Threshold erreicht, aber noch kein Alert gesendet`;
          }
        }
      } catch (error: any) {
        // Don't fail the whole command if alert check fails
        console.error('⚠️  Could not check alert status:', error);
      }
    }
    
    return formatStats(stats, timeframe) + alertInfo;
  } catch (error: any) {
    return `❌ **Error**: ${error.message}`;
  }
}

/**
 * Check if threshold reached and send alert
 * Uses database to prevent duplicate alerts after bot restart
 */
export async function checkThresholdAndAlert(client: Client): Promise<void> {
  // Graceful skip if database is not available
  if (!checkDatabaseAvailability()) {
    return; // Silently skip - warning already shown on first check
  }
  
  try {
    // Get today's stats
    const stats = await getLettaStats('today');
    
    // Check if threshold reached
    if (stats.cost_eur >= ALERT_THRESHOLD_EUR) {
      // Check if we already sent an alert today (from database)
      const alertStatus = await checkAlertSentToday('threshold');
      
      // Only send if:
      // 1. We haven't alerted today, OR
      // 2. The cost has increased significantly since last alert (more than 0.50€)
      const shouldAlert = !alertStatus.alerted_today || 
                         (stats.cost_eur > alertStatus.last_alert_amount + 0.50);
      
      if (shouldAlert) {
        const channel = await client.channels.fetch(ALERT_CHANNEL_ID) as TextChannel;
        
        if (channel) {
          await channel.send(`🚨 **5€ THRESHOLD ERREICHT!**

💰 Heute bereits verbraucht: **€${stats.cost_eur.toFixed(2)}**
📊 Credits: ${stats.credits.toLocaleString()}
🔄 Runs: ${stats.runs.toLocaleString()}

⚠️ **Achtung:** Die tägliche Kosten-Grenze von €${ALERT_THRESHOLD_EUR.toFixed(2)} wurde erreicht!`);
          
          // Log to database (persistent across restarts)
          await logAlertSent(stats.cost_eur, 'threshold');
          console.log(`🚨 Threshold alert sent: €${stats.cost_eur.toFixed(2)}`);
        }
      } else {
        console.log(`⏭️ Threshold reached but already alerted today (€${alertStatus.last_alert_amount.toFixed(2)})`);
      }
    }
  } catch (error: any) {
    console.error('❌ Error checking threshold:', error);
  }
}

/**
 * Send daily summary at midnight (for yesterday's stats)
 */
export async function sendDailySummary(client: Client): Promise<void> {
  try {
    // Get yesterday's stats by querying with yesterday's date
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    yesterday.setHours(0, 0, 0, 0);
    
    // Use Python script with custom date range
    // 🔥 FIX: Script is in scripts/ directory (one level up from dist/src/)
  const scriptPath = path.join(__dirname, '..', 'scripts', 'get_letta_stats.py');
    const yesterdayStart = yesterday.toISOString();
    const yesterdayEnd = new Date(yesterday.getTime() + 24 * 60 * 60 * 1000).toISOString();
    
    // Query yesterday's data
    const { stdout } = await execAsync(
      `python3 "${scriptPath}" custom "${yesterdayStart}" "${yesterdayEnd}"`, 
      { timeout: 5000 }
    );
    
    const result = JSON.parse(stdout.trim());
    if (result.error) {
      throw new Error(result.error);
    }
    
    const stats = {
      credits: result.credits || 0,
      runs: result.runs || 0,
      api_calls: result.api_calls || 0,
      cost_eur: (result.credits || 0) * CREDIT_PRICE_USD * EUR_RATE,
      cost_usd: (result.credits || 0) * CREDIT_PRICE_USD
    };
    
    const channel = await client.channels.fetch(ALERT_CHANNEL_ID) as TextChannel;
    
    if (channel) {
      const dateStr = yesterday.toLocaleDateString(LOCALE, {
        timeZone: LOCALE_TIMEZONE,
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });

      const summary = `📊 **Tägliches Letta Summary - ${dateStr}**

💰 **Credits:** ${stats.credits.toLocaleString()}
🔄 **Runs:** ${stats.runs.toLocaleString()}
📞 **API Calls:** ${stats.api_calls.toLocaleString()}
💵 **Kosten:** €${stats.cost_eur.toFixed(2)} ($${stats.cost_usd.toFixed(2)})

${stats.runs > 0 ? `📈 **Durchschnitt:**
• ${(stats.credits / stats.runs).toFixed(1)} Credits/Run
• ${(stats.cost_eur / stats.runs).toFixed(4)}€/Run

` : ''}${stats.cost_eur >= ALERT_THRESHOLD_EUR ? '⚠️ **Threshold erreicht!**' : stats.runs > 0 ? `✅ Noch €${(ALERT_THRESHOLD_EUR - stats.cost_eur).toFixed(2)} bis zum Threshold` : 'ℹ️ Keine Aktivität gestern'}`;

      await channel.send(summary);

      // Log daily summary sent (for tracking)
      await logAlertSent(stats.cost_eur, 'daily_summary');
      console.log(`📊 Daily summary sent for ${dateStr}`);
    }
  } catch (error: any) {
    console.error('❌ Error sending daily summary:', error);
    // Try to send error notification
    try {
      const channel = await client.channels.fetch(ALERT_CHANNEL_ID) as TextChannel;
      if (channel) {
        await channel.send(`⚠️ **Fehler beim Senden des täglichen Summaries:** ${error.message}`);
      }
    } catch {}
  }
}

/**
 * Start daily summary scheduler (runs at 0:00 in configured timezone)
 */
export function startDailySummaryScheduler(client: Client): void {
  if (dailySummaryScheduled) {
    console.log('⚠️ Daily summary scheduler already running');
    return;
  }

  dailySummaryScheduled = true;
  const TIMEZONE = process.env.TIMEZONE || 'America/New_York';
  console.log(`📅 Daily summary scheduler started (runs at 0:00 ${TIMEZONE})`);

  function scheduleNextMidnight() {
    const now = new Date();
    
    // Get configured timezone time
    const localTimeParts = new Intl.DateTimeFormat('en-US', {
      timeZone: TIMEZONE,
      hour: 'numeric',
      minute: 'numeric',
      hour12: false
    }).formatToParts(now);

    const hour = parseInt(localTimeParts.find(p => p.type === 'hour')?.value || '0', 10);
    const minute = parseInt(localTimeParts.find(p => p.type === 'minute')?.value || '0', 10);

    // Calculate milliseconds until next midnight (configured timezone)
    const localNow = new Date(now.toLocaleString('en-US', { timeZone: TIMEZONE }));
    const localMidnight = new Date(localNow);
    localMidnight.setHours(0, 0, 0, 0);
    localMidnight.setDate(localMidnight.getDate() + 1); // Next midnight

    const msUntilMidnight = localMidnight.getTime() - localNow.getTime();
    
    console.log(`⏰ Next daily summary scheduled in ${Math.floor(msUntilMidnight / 1000 / 60)} minutes (at 0:00 ${TIMEZONE})`);
    
    setTimeout(async () => {
      await sendDailySummary(client);
      
      // Schedule next day
      scheduleNextMidnight();
    }, msUntilMidnight);
  }

  // Start scheduling
  scheduleNextMidnight();
}

/**
 * Start threshold monitoring (checks every 5 minutes)
 * Loads alert status from database on startup to prevent duplicate alerts
 */
export async function startThresholdMonitoring(client: Client): Promise<void> {
  // Check if database is available on startup
  dbAvailable = checkDatabaseAvailability();
  
  if (!dbAvailable) {
    console.log('🚨 Threshold monitoring DISABLED - database not found');
    return; // Don't start monitoring if DB is not available
  }
  
  console.log('🚨 Threshold monitoring started (checks every 5 minutes)');
  
  // Check alert status on startup
  try {
    const alertStatus = await checkAlertSentToday('threshold');
    if (alertStatus.alerted_today) {
      console.log(`ℹ️  Alert already sent today (€${alertStatus.last_alert_amount.toFixed(2)}). Will only alert again if cost increases by >€0.50`);
    } else {
      console.log('✅ No alert sent today yet. Will alert when threshold is reached.');
    }
  } catch (error: any) {
    console.error('⚠️  Could not check alert status on startup:', error.message);
  }
  
  // Check immediately
  checkThresholdAndAlert(client);
  
  // Then check every 5 minutes
  setInterval(() => {
    checkThresholdAndAlert(client);
  }, 5 * 60 * 1000); // 5 minutes
}

