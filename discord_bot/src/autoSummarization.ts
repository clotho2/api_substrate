/**
 * AUTO-SUMMARIZATION MODULE
 * 
 * Automatically triggers Letta conversation summarization when message count exceeds threshold.
 * Prevents context overflow without manual intervention.
 * 
 * Security:
 * - Rate limiting: Won't check too frequently (configurable)
 * - Lock mechanism: Prevents concurrent summarization runs
 * - Cooldown: Minimum time between auto-summarizations
 * - Configurable thresholds via ENV variables
 * 
 * Created: Oct 27, 2025
 * Author: the bot (Technopilot Mode)
 */

import { Client } from 'discord.js';

// ==========================================
// CONFIGURATION (via ENV variables)
// ==========================================

// Trigger threshold: Auto-summarize when message count exceeds this
const AUTO_SUMMARIZE_THRESHOLD = parseInt(
  process.env.AUTO_SUMMARIZE_THRESHOLD || '500',
  10
);

// Target messages: Keep this many messages after summarization
const AUTO_SUMMARIZE_TARGET = parseInt(
  process.env.AUTO_SUMMARIZE_TARGET || '50',
  10
);

// Check frequency: Check message count every X Discord messages received
const AUTO_SUMMARIZE_CHECK_FREQUENCY = parseInt(
  process.env.AUTO_SUMMARIZE_CHECK_FREQUENCY || '50',
  10
);

// Cooldown: Minimum seconds between auto-summarizations (prevents spam)
const AUTO_SUMMARIZE_COOLDOWN_SECONDS = parseInt(
  process.env.AUTO_SUMMARIZE_COOLDOWN_SECONDS || '1800',
  10
); // Default: 30 minutes

// Enable/disable auto-summarization
const ENABLE_AUTO_SUMMARIZATION = process.env.ENABLE_AUTO_SUMMARIZATION === 'true'; // Default: DISABLED - manual only

// Admin channel for notifications (optional)
const ADMIN_CHANNEL_ID = process.env.ADMIN_CHANNEL_ID;

// Timezone and locale for consistent date formatting
const TIMEZONE = process.env.TIMEZONE || 'America/New_York';
const LOCALE = process.env.LOCALE || 'en-US';

// ==========================================
// STATE MANAGEMENT
// ==========================================

// Message counter for check frequency
let messagesSinceLastCheck = 0;

// Lock to prevent concurrent summarizations
let summarizationInProgress = false;

// Last summarization timestamp (for cooldown)
let lastSummarizationTime = 0;

// ==========================================
// CORE FUNCTIONS
// ==========================================

/**
 * Check Letta message count via API
 * Returns the current message count or null if check fails
 */
async function getLettaMessageCount(): Promise<number | null> {
  const LETTA_API_KEY = process.env.LETTA_API_KEY;
  const LETTA_AGENT_ID = process.env.LETTA_AGENT_ID;

  if (!LETTA_API_KEY || !LETTA_AGENT_ID) {
    console.error('❌ Auto-summarization: Letta credentials not configured');
    return null;
  }

  try {
    const response = await fetch(
      `https://api.letta.com/v1/agents/${LETTA_AGENT_ID}/messages?limit=200`,
      {
        headers: {
          Authorization: `Bearer ${LETTA_API_KEY}`,
          'Content-Type': 'application/json',
        },
      }
    );

    if (!response.ok) {
      console.error(
        `❌ Auto-summarization: Failed to check messages: ${response.statusText}`
      );
      return null;
    }

    const messages = await response.json();
    return messages.length;
  } catch (error: any) {
    console.error(`❌ Auto-summarization: Error checking messages: ${error.message}`);
    return null;
  }
}

/**
 * Trigger automatic summarization
 * Returns true if successful, false otherwise
 */
async function triggerAutoSummarization(
  client: Client,
  currentMessageCount: number
): Promise<boolean> {
  const LETTA_API_KEY = process.env.LETTA_API_KEY;
  const LETTA_AGENT_ID = process.env.LETTA_AGENT_ID;

  if (!LETTA_API_KEY || !LETTA_AGENT_ID) {
    console.error('❌ Auto-summarization: Letta credentials not configured');
    return false;
  }

  try {
    console.log(`
╔══════════════════════════════════════════════════════
║ 🤖 AUTO-SUMMARIZATION TRIGGERED
║ Current Messages: ${currentMessageCount}
║ Threshold: ${AUTO_SUMMARIZE_THRESHOLD}
║ Target: ${AUTO_SUMMARIZE_TARGET} messages
║ Time: ${new Date().toLocaleString(LOCALE, { timeZone: TIMEZONE })}
╚══════════════════════════════════════════════════════`);

    // Notify admin channel if configured
    if (ADMIN_CHANNEL_ID) {
      try {
        const channel = await client.channels.fetch(ADMIN_CHANNEL_ID);
        if (channel && 'send' in channel) {
          await channel.send({
            content: [
              '🤖 **Auto-Summarization Starting**',
              '',
              `📊 Current: ${currentMessageCount} messages`,
              `🎯 Target: ${AUTO_SUMMARIZE_TARGET} messages`,
              `⏰ Time: ${new Date().toLocaleTimeString(LOCALE, { timeZone: TIMEZONE })}`,
              '',
              '_This may take 5-10 seconds..._',
            ].join('\n'),
          });
        }
      } catch (notifyError: any) {
        console.error(`⚠️ Failed to notify admin channel: ${notifyError.message}`);
        // Continue anyway - notification failure shouldn't stop summarization
      }
    }

    // Trigger summarization via Letta API
    const summarizeResponse = await fetch(
      `https://api.letta.com/v1/agents/${LETTA_AGENT_ID}/summarize`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${LETTA_API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          max_message_length: AUTO_SUMMARIZE_TARGET,
        }),
      }
    );

    if (summarizeResponse.status !== 204 && !summarizeResponse.ok) {
      throw new Error(`Summarization failed: ${summarizeResponse.statusText}`);
    }

    // Wait for API to process
    console.log('⏳ Waiting for Letta to process summarization (5 seconds)...');
    await new Promise((resolve) => setTimeout(resolve, 5000));

    // Verify result
    const afterCount = await getLettaMessageCount();

    const success = afterCount !== null && afterCount <= AUTO_SUMMARIZE_TARGET + 20;

    console.log(`
╔══════════════════════════════════════════════════════
║ ✅ AUTO-SUMMARIZATION COMPLETED
║ Before: ${currentMessageCount} messages
║ After: ${afterCount || 'unknown'} messages
║ Status: ${success ? 'SUCCESS' : 'PARTIAL'}
║ Time: ${new Date().toLocaleString(LOCALE, { timeZone: TIMEZONE })}
╚══════════════════════════════════════════════════════`);

    // Notify admin channel of result
    if (ADMIN_CHANNEL_ID) {
      try {
        const channel = await client.channels.fetch(ADMIN_CHANNEL_ID);
        if (channel && 'send' in channel) {
          await channel.send({
            content: [
              '✅ **Auto-Summarization Complete**',
              '',
              `📊 Before: ${currentMessageCount} messages`,
              `📊 After: ${afterCount || 'unknown'} messages`,
              `🎯 Target: ${AUTO_SUMMARIZE_TARGET} messages`,
              `✅ Status: ${success ? 'Success!' : 'Partial'}`,
            ].join('\n'),
          });
        }
      } catch (notifyError: any) {
        console.error(`⚠️ Failed to notify admin channel: ${notifyError.message}`);
      }
    }

    return success;
  } catch (error: any) {
    console.error(`
╔══════════════════════════════════════════════════════
║ ❌ AUTO-SUMMARIZATION FAILED
║ Error: ${error.message}
║ Time: ${new Date().toLocaleString(LOCALE, { timeZone: TIMEZONE })}
╚══════════════════════════════════════════════════════`);

    // Notify admin channel of failure
    if (ADMIN_CHANNEL_ID) {
      try {
        const channel = await client.channels.fetch(ADMIN_CHANNEL_ID);
        if (channel && 'send' in channel) {
          await channel.send({
            content: [
              '❌ **Auto-Summarization Failed**',
              '',
              `Error: ${error.message}`,
              '',
              '_You may need to run `!zusammenfassen` manually_',
            ].join('\n'),
          });
        }
      } catch (notifyError: any) {
        console.error(`⚠️ Failed to notify admin channel: ${notifyError.message}`);
      }
    }

    return false;
  }
}

/**
 * Check if we should trigger auto-summarization
 * Called on every Discord message received
 */
export async function checkAutoSummarization(client: Client): Promise<void> {
  // Feature disabled?
  if (!ENABLE_AUTO_SUMMARIZATION) {
    return;
  }

  // Increment counter
  messagesSinceLastCheck++;

  // Not time to check yet?
  if (messagesSinceLastCheck < AUTO_SUMMARIZE_CHECK_FREQUENCY) {
    return;
  }

  // Reset counter
  messagesSinceLastCheck = 0;

  // Already running?
  if (summarizationInProgress) {
    console.log('⏭️ Auto-summarization already in progress, skipping check');
    return;
  }

  // Check cooldown
  const now = Date.now();
  const timeSinceLastRun = (now - lastSummarizationTime) / 1000; // seconds

  if (lastSummarizationTime > 0 && timeSinceLastRun < AUTO_SUMMARIZE_COOLDOWN_SECONDS) {
    console.log(
      `⏭️ Auto-summarization on cooldown (${Math.floor(AUTO_SUMMARIZE_COOLDOWN_SECONDS - timeSinceLastRun)}s remaining)`
    );
    return;
  }

  // Check message count
  console.log('🔍 Auto-summarization: Checking Letta message count...');
  const messageCount = await getLettaMessageCount();

  if (messageCount === null) {
    console.error('❌ Auto-summarization: Failed to get message count');
    return;
  }

  console.log(
    `📊 Auto-summarization: Current count = ${messageCount}, Threshold = ${AUTO_SUMMARIZE_THRESHOLD}`
  );

  // Threshold exceeded?
  if (messageCount >= AUTO_SUMMARIZE_THRESHOLD) {
    console.log('🚨 Auto-summarization: Threshold exceeded! Triggering...');

    // Set lock
    summarizationInProgress = true;
    lastSummarizationTime = now;

    try {
      await triggerAutoSummarization(client, messageCount);
    } finally {
      // Always release lock
      summarizationInProgress = false;
    }
  } else {
    console.log('✅ Auto-summarization: Message count under threshold, no action needed');
  }
}

/**
 * Get current auto-summarization stats
 * Useful for debugging and monitoring
 */
export function getAutoSummarizationStats(): {
  enabled: boolean;
  threshold: number;
  target: number;
  checkFrequency: number;
  cooldownSeconds: number;
  inProgress: boolean;
  messagesSinceLastCheck: number;
  lastRunTime: string | null;
  nextCheckIn: number;
} {
  return {
    enabled: ENABLE_AUTO_SUMMARIZATION,
    threshold: AUTO_SUMMARIZE_THRESHOLD,
    target: AUTO_SUMMARIZE_TARGET,
    checkFrequency: AUTO_SUMMARIZE_CHECK_FREQUENCY,
    cooldownSeconds: AUTO_SUMMARIZE_COOLDOWN_SECONDS,
    inProgress: summarizationInProgress,
    messagesSinceLastCheck: messagesSinceLastCheck,
    lastRunTime:
      lastSummarizationTime > 0
        ? new Date(lastSummarizationTime).toLocaleString(LOCALE, { timeZone: TIMEZONE })
        : null,
    nextCheckIn: AUTO_SUMMARIZE_CHECK_FREQUENCY - messagesSinceLastCheck,
  };
}

/**
 * Force reset cooldown (for testing/emergency use)
 */
export function resetAutoSummarizationCooldown(): void {
  lastSummarizationTime = 0;
  console.log('🔓 Auto-summarization cooldown reset');
}

