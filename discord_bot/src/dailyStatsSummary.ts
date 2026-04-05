/**
 * DAILY STATS SUMMARY
 * ===================
 * 
 * Automatische tägliche Zusammenfassung um 0:00 Uhr:
 * - Letta Stats (gestern)
 * - Chat Statistik (gestern)
 * 
 * Läuft direkt im Bot, nicht als Agent-Task
 */

import { Client, TextChannel } from "discord.js";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";

const execAsync = promisify(exec);

// Configuration
const TARGET_CHANNEL_ID = process.env.LETTA_ALERT_CHANNEL_ID || ""; // Configure in .env

// Auto-detect PI or Mac path
import fs from "fs";
const PI_SCRIPT_PATH = path.join(process.env.HOME || "~", "miore-discord-bot", "daily_stats_summary.py");
const MAC_SCRIPT_PATH = path.join(__dirname, "..", "..", "daily_stats_summary.py");
const SCRIPT_PATH = fs.existsSync(PI_SCRIPT_PATH) ? PI_SCRIPT_PATH : MAC_SCRIPT_PATH;

// State
let dailyStatsScheduled = false;

/**
 * Send daily stats summary (Letta + Chat Stats)
 */
export async function sendDailyStatsSummary(client: Client): Promise<void> {
  try {
    console.log("📊 Starting daily stats summary...");
    
    // Get target channel
    const channel = (await client.channels.fetch(TARGET_CHANNEL_ID)) as TextChannel | null;
    if (!channel) {
      console.error(`❌ Channel ${TARGET_CHANNEL_ID} not found`);
      return;
    }

    // Execute Python script
    try {
      const { stdout, stderr } = await execAsync(`python3 "${SCRIPT_PATH}"`, {
        timeout: 30000, // 30 seconds timeout
        maxBuffer: 1024 * 1024 // 1MB
      });

      if (stderr && !stderr.includes("⚠️")) {
        console.warn(`⚠️  Script warnings: ${stderr}`);
      }

      // Script should send message itself via Discord API
      // But we can also check if it succeeded
      if (stdout.includes("✅ Nachricht erfolgreich gesendet")) {
        console.log("✅ Daily stats summary sent successfully");
      } else {
        console.log(`📊 Script output: ${stdout}`);
      }
    } catch (error: any) {
      console.error("❌ Error executing daily_stats_summary.py:", error);
      
      // Send error message to channel
      await channel.send(`❌ **Fehler beim Erstellen der täglichen Zusammenfassung:**\n\`\`\`${error.message}\`\`\``);
    }
  } catch (error: any) {
    console.error("❌ Error in sendDailyStatsSummary:", error);
  }
}

/**
 * Start daily stats summary scheduler (runs at 0:00 in configured timezone)
 */
export function startDailyStatsSummaryScheduler(client: Client): void {
  if (dailyStatsScheduled) {
    console.log("⚠️  Daily stats summary scheduler already running");
    return;
  }

  dailyStatsScheduled = true;
  const TIMEZONE = process.env.TIMEZONE || 'America/New_York';
  console.log(`📅 Daily stats summary scheduler started (runs at 0:00 ${TIMEZONE})`);

  function scheduleNextMidnight() {
    const now = new Date();
    
    // Get configured timezone time
    const localTimeParts = new Intl.DateTimeFormat("en-US", {
      timeZone: TIMEZONE,
      hour: "numeric",
      minute: "numeric",
      hour12: false,
    }).formatToParts(now);

    const hour = parseInt(localTimeParts.find((p) => p.type === "hour")?.value || "0", 10);
    const minute = parseInt(localTimeParts.find((p) => p.type === "minute")?.value || "0", 10);

    // Calculate milliseconds until next midnight (configured timezone)
    const localNow = new Date(now.toLocaleString("en-US", { timeZone: TIMEZONE }));
    const localMidnight = new Date(localNow);
    localMidnight.setHours(0, 0, 0, 0);
    localMidnight.setDate(localMidnight.getDate() + 1); // Next midnight

    const msUntilMidnight = localMidnight.getTime() - localNow.getTime();
    
    console.log(
      `⏰ Next daily stats summary scheduled in ${Math.floor(msUntilMidnight / 1000 / 60)} minutes (at 0:00 ${TIMEZONE})`
    );
    
    setTimeout(async () => {
      await sendDailyStatsSummary(client);
      
      // Schedule next day
      scheduleNextMidnight();
    }, msUntilMidnight);
  }

  // Start scheduling
  scheduleNextMidnight();
}

