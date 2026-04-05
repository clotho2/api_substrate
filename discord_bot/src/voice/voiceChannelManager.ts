/**
 * Voice Channel Manager
 *
 * Handles joining, leaving, and managing Discord voice channel connections.
 */

import {
  joinVoiceChannel,
  VoiceConnection,
  VoiceConnectionStatus,
  entersState,
  getVoiceConnection,
  VoiceConnectionDisconnectReason,
} from '@discordjs/voice';
import { VoiceChannel, StageChannel, GuildMember, Guild, Client } from 'discord.js';

// ============================================
// Types
// ============================================

export interface VoiceConnectionInfo {
  connection: VoiceConnection;
  channelId: string;
  guildId: string;
  joinedAt: Date;
  talkModeEnabled: boolean;
  isMuted: boolean;
}

// ============================================
// Voice Channel Manager
// ============================================

export class VoiceChannelManager {
  private connections: Map<string, VoiceConnectionInfo> = new Map();
  private client: Client;

  constructor(client: Client) {
    this.client = client;
    console.log('🎤 [VoiceChannelManager] Initialized');
  }

  /**
   * Join a voice channel
   */
  async join(channel: VoiceChannel | StageChannel): Promise<VoiceConnection> {
    const guildId = channel.guild.id;

    // Check if already connected to this guild
    const existing = this.connections.get(guildId);
    if (existing) {
      // If connected to a different channel, disconnect first
      if (existing.channelId !== channel.id) {
        console.log(`🎤 [VoiceChannelManager] Moving from channel ${existing.channelId} to ${channel.id}`);
        await this.leave(guildId);
      } else {
        console.log(`🎤 [VoiceChannelManager] Already connected to channel ${channel.id}`);
        return existing.connection;
      }
    }

    console.log(`🎤 [VoiceChannelManager] Joining voice channel: ${channel.name} (${channel.id})`);

    // Create voice connection
    const connection = joinVoiceChannel({
      channelId: channel.id,
      guildId: channel.guild.id,
      adapterCreator: channel.guild.voiceAdapterCreator,
      selfDeaf: false,  // Must be false to receive audio
      selfMute: false,
    });

    // Handle connection state changes
    connection.on(VoiceConnectionStatus.Disconnected, async (oldState, newState) => {
      try {
        // Try to reconnect if disconnected unexpectedly
        await Promise.race([
          entersState(connection, VoiceConnectionStatus.Signalling, 5000),
          entersState(connection, VoiceConnectionStatus.Connecting, 5000),
        ]);
        console.log(`🎤 [VoiceChannelManager] Reconnecting to voice channel...`);
      } catch (error) {
        // Disconnection is intentional or unrecoverable
        console.log(`🎤 [VoiceChannelManager] Disconnected from voice channel`);
        this.connections.delete(guildId);
        connection.destroy();
      }
    });

    connection.on(VoiceConnectionStatus.Destroyed, () => {
      console.log(`🎤 [VoiceChannelManager] Voice connection destroyed for guild ${guildId}`);
      this.connections.delete(guildId);
    });

    connection.on('error', (error) => {
      console.error(`❌ [VoiceChannelManager] Voice connection error:`, error);
    });

    // Wait for connection to be ready
    try {
      await entersState(connection, VoiceConnectionStatus.Ready, 20000);
      console.log(`✅ [VoiceChannelManager] Successfully joined voice channel: ${channel.name}`);
    } catch (error) {
      console.error(`❌ [VoiceChannelManager] Failed to join voice channel:`, error);
      connection.destroy();
      throw error;
    }

    // Store connection info
    this.connections.set(guildId, {
      connection,
      channelId: channel.id,
      guildId,
      joinedAt: new Date(),
      talkModeEnabled: false,
      isMuted: false,
    });

    return connection;
  }

  /**
   * Leave a voice channel
   */
  async leave(guildId: string): Promise<boolean> {
    const info = this.connections.get(guildId);
    if (!info) {
      console.log(`🎤 [VoiceChannelManager] Not connected to any voice channel in guild ${guildId}`);
      return false;
    }

    console.log(`🎤 [VoiceChannelManager] Leaving voice channel ${info.channelId}`);

    try {
      info.connection.destroy();
      this.connections.delete(guildId);
      console.log(`✅ [VoiceChannelManager] Left voice channel`);
      return true;
    } catch (error) {
      console.error(`❌ [VoiceChannelManager] Error leaving voice channel:`, error);
      this.connections.delete(guildId);
      return false;
    }
  }

  /**
   * Get connection for a guild
   */
  getConnection(guildId: string): VoiceConnectionInfo | undefined {
    return this.connections.get(guildId);
  }

  /**
   * Check if connected to a voice channel in a guild
   */
  isConnected(guildId: string): boolean {
    return this.connections.has(guildId);
  }

  /**
   * Enable/disable talk mode for a guild
   */
  setTalkMode(guildId: string, enabled: boolean): boolean {
    const info = this.connections.get(guildId);
    if (!info) {
      return false;
    }
    info.talkModeEnabled = enabled;
    console.log(`🎤 [VoiceChannelManager] Talk mode ${enabled ? 'enabled' : 'disabled'} for guild ${guildId}`);
    return true;
  }

  /**
   * Check if talk mode is enabled
   */
  isTalkModeEnabled(guildId: string): boolean {
    const info = this.connections.get(guildId);
    return info?.talkModeEnabled || false;
  }

  /**
   * Mute/unmute the bot
   */
  setMuted(guildId: string, muted: boolean): boolean {
    const info = this.connections.get(guildId);
    if (!info) {
      return false;
    }
    info.isMuted = muted;
    console.log(`🎤 [VoiceChannelManager] Bot ${muted ? 'muted' : 'unmuted'} for guild ${guildId}`);
    return true;
  }

  /**
   * Check if bot is muted
   */
  isMuted(guildId: string): boolean {
    const info = this.connections.get(guildId);
    return info?.isMuted || false;
  }

  /**
   * Get all active connections
   */
  getAllConnections(): Map<string, VoiceConnectionInfo> {
    return new Map(this.connections);
  }

  /**
   * Disconnect from all voice channels (for graceful shutdown)
   */
  async disconnectAll(): Promise<void> {
    console.log(`🎤 [VoiceChannelManager] Disconnecting from all voice channels...`);

    for (const [guildId, info] of this.connections) {
      try {
        info.connection.destroy();
      } catch (error) {
        console.error(`❌ [VoiceChannelManager] Error disconnecting from guild ${guildId}:`, error);
      }
    }

    this.connections.clear();
    console.log(`✅ [VoiceChannelManager] Disconnected from all voice channels`);
  }

  /**
   * Find user's voice channel from a guild member
   */
  static getUserVoiceChannel(member: GuildMember): VoiceChannel | StageChannel | null {
    return member.voice.channel;
  }
}

// Singleton instance
let voiceChannelManagerInstance: VoiceChannelManager | null = null;

export function getVoiceChannelManager(): VoiceChannelManager | null {
  return voiceChannelManagerInstance;
}

export function initVoiceChannelManager(client: Client): VoiceChannelManager {
  voiceChannelManagerInstance = new VoiceChannelManager(client);
  return voiceChannelManagerInstance;
}
