/**
 * Voice Commands Handler
 *
 * Handles voice-related commands:
 * - !join / !voice - Join user's voice channel
 * - !leave / !disconnect - Leave voice channel
 * - !talk - Enable talk mode (continuous conversation)
 * - !mute - Temporarily stop listening
 * - !unmute - Resume listening
 */

import { Message, VoiceChannel, StageChannel, TextChannel, GuildMember } from 'discord.js';
import {
  VoiceChannelManager,
  getVoiceChannelManager,
  initVoiceChannelManager,
} from './voiceChannelManager';
import {
  TalkModeManager,
  getTalkModeManager,
  initTalkModeManager,
} from './talkMode';
import { initSubstrateClient } from './substrateClient';

// ============================================
// Voice Command Handler
// ============================================

/**
 * Handle voice-related commands
 * Returns a response string if command was handled, null otherwise
 */
export async function handleVoiceCommand(message: Message): Promise<string | null> {
  const content = message.content.trim().toLowerCase();

  // Check if voice is enabled
  if (process.env.VOICE_ENABLED !== 'true') {
    // Only respond to voice commands if they're actually being used
    if (content.startsWith('!join') || content.startsWith('!voice') ||
        content.startsWith('!leave') || content.startsWith('!disconnect') ||
        content.startsWith('!talk') || content.startsWith('!mute') ||
        content.startsWith('!unmute')) {
      return '🔇 Voice channel support is disabled. Set VOICE_ENABLED=true to enable.';
    }
    return null;
  }

  // Get guild (voice commands only work in guilds)
  if (!message.guild) {
    if (content.startsWith('!join') || content.startsWith('!voice') ||
        content.startsWith('!leave') || content.startsWith('!disconnect') ||
        content.startsWith('!talk') || content.startsWith('!mute') ||
        content.startsWith('!unmute')) {
      return '❌ Voice commands can only be used in servers, not in DMs.';
    }
    return null;
  }

  const guildId = message.guild.id;
  const voiceManager = getVoiceChannelManager();
  const talkManager = getTalkModeManager();

  if (!voiceManager || !talkManager) {
    return '❌ Voice system not initialized.';
  }

  // !join or !voice - Join user's voice channel
  if (content === '!join' || content === '!voice') {
    const member = message.member as GuildMember;
    const voiceChannel = VoiceChannelManager.getUserVoiceChannel(member);

    if (!voiceChannel) {
      return '❌ You need to be in a voice channel first!';
    }

    try {
      await voiceManager.join(voiceChannel);
      return `✅ Joined voice channel: **${voiceChannel.name}**\n\nUse \`!talk\` to enable continuous conversation, or \`!leave\` to disconnect.`;
    } catch (error) {
      console.error('❌ [VoiceCommands] Error joining voice channel:', error);
      return `❌ Failed to join voice channel: ${(error as Error).message}`;
    }
  }

  // !leave or !disconnect - Leave voice channel
  if (content === '!leave' || content === '!disconnect') {
    // Stop talk mode first
    if (talkManager.isTalkModeActive(guildId)) {
      await talkManager.stopTalkMode(guildId);
    }

    const left = await voiceManager.leave(guildId);
    if (left) {
      return '👋 Left the voice channel.';
    } else {
      return '❌ Not connected to a voice channel in this server.';
    }
  }

  // !talk - Enable/toggle talk mode
  if (content === '!talk') {
    const connectionInfo = voiceManager.getConnection(guildId);

    if (!connectionInfo) {
      // Try to join user's voice channel first
      const member = message.member as GuildMember;
      const voiceChannel = VoiceChannelManager.getUserVoiceChannel(member);

      if (!voiceChannel) {
        return '❌ You need to be in a voice channel, or use `!join` first.';
      }

      try {
        await voiceManager.join(voiceChannel);
      } catch (error) {
        return `❌ Failed to join voice channel: ${(error as Error).message}`;
      }
    }

    // Get updated connection info
    const updatedConnectionInfo = voiceManager.getConnection(guildId);
    if (!updatedConnectionInfo) {
      return '❌ Failed to establish voice connection.';
    }

    // Toggle talk mode
    if (talkManager.isTalkModeActive(guildId)) {
      await talkManager.stopTalkMode(guildId);
      return '🔇 Talk mode disabled. I\'m no longer listening.';
    } else {
      const textChannel = message.channel as TextChannel;
      await talkManager.startTalkMode(guildId, updatedConnectionInfo.connection, textChannel);
      return '🎤 Talk mode enabled! I\'m listening...\n\nSpeak naturally and I\'ll respond. Use `!talk` again to disable, or `!mute` to temporarily pause.';
    }
  }

  // !mute - Temporarily stop listening
  if (content === '!mute') {
    if (!voiceManager.isConnected(guildId)) {
      return '❌ Not connected to a voice channel.';
    }

    voiceManager.setMuted(guildId, true);
    return '🔇 Muted. I\'m still in the voice channel but not listening. Use `!unmute` to resume.';
  }

  // !unmute - Resume listening
  if (content === '!unmute') {
    if (!voiceManager.isConnected(guildId)) {
      return '❌ Not connected to a voice channel.';
    }

    voiceManager.setMuted(guildId, false);
    return '🎤 Unmuted. I\'m listening again!';
  }

  // Not a voice command
  return null;
}

// ============================================
// Voice System Initialization
// ============================================

let isVoiceSystemInitialized = false;

/**
 * Initialize the voice system
 */
export function initVoiceSystem(client: any): void {
  if (isVoiceSystemInitialized) {
    console.log('🎤 [VoiceCommands] Voice system already initialized');
    return;
  }

  const voiceEnabled = process.env.VOICE_ENABLED === 'true';

  if (!voiceEnabled) {
    console.log('🔇 [VoiceCommands] Voice channel support disabled (VOICE_ENABLED !== true)');
    return;
  }

  // Initialize substrate client
  const substrateUrl = process.env.SUBSTRATE_API_URL || process.env.GROK_BASE_URL || 'http://localhost:8284';
  initSubstrateClient(substrateUrl);

  // Initialize voice channel manager
  initVoiceChannelManager(client);

  // Initialize talk mode manager
  initTalkModeManager(client);

  isVoiceSystemInitialized = true;
  console.log('✅ [VoiceCommands] Voice system initialized');
  console.log(`   Substrate URL: ${substrateUrl}`);
  console.log(`   Silence threshold: ${process.env.SILENCE_THRESHOLD_MS || '800'}ms`);
}

/**
 * Shutdown the voice system (for graceful shutdown)
 */
export async function shutdownVoiceSystem(): Promise<void> {
  const voiceManager = getVoiceChannelManager();
  const talkManager = getTalkModeManager();

  if (talkManager) {
    await talkManager.stopAll();
  }

  if (voiceManager) {
    await voiceManager.disconnectAll();
  }

  console.log('🎤 [VoiceCommands] Voice system shut down');
}

/**
 * Check if voice system is initialized
 */
export function isVoiceInitialized(): boolean {
  return isVoiceSystemInitialized;
}
