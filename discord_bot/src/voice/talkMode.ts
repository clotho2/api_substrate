/**
 * Talk Mode
 *
 * Orchestrates the real-time voice conversation loop:
 * 1. Receive user audio → STT
 * 2. Send transcribed text to Chat API
 * 3. Convert response to TTS
 * 4. Play audio response in voice channel
 *
 * Handles interrupt detection (user speaks while bot is responding).
 */

import { VoiceConnection } from '@discordjs/voice';
import { Client, TextChannel, DMChannel, NewsChannel, Message } from 'discord.js';
import { VoiceReceiver, AudioRecording } from './voiceReceiver';
import { VoicePlayer } from './voicePlayer';
import { getSubstrateClient, SubstrateClient } from './substrateClient';
import { VoiceChannelManager, getVoiceChannelManager } from './voiceChannelManager';

// ============================================
// Types
// ============================================

export interface TalkModeConfig {
  guildId: string;
  connection: VoiceConnection;
  client: Client;
  textChannel?: TextChannel | DMChannel | NewsChannel;
  onTranscription?: (userId: string, text: string) => void;
  onResponse?: (text: string) => void;
  onError?: (error: Error) => void;
}

// ============================================
// Talk Mode Controller
// ============================================

export class TalkModeController {
  private config: TalkModeConfig;
  private receiver: VoiceReceiver;
  private player: VoicePlayer;
  private substrateClient: SubstrateClient;
  private isActive: boolean = false;
  private isProcessing: boolean = false;
  private pendingRecordings: AudioRecording[] = [];

  constructor(config: TalkModeConfig) {
    this.config = config;
    this.receiver = new VoiceReceiver(config.connection);
    this.player = new VoicePlayer(config.connection);
    this.substrateClient = getSubstrateClient();

    // Set up interrupt handling
    this.player.setInterruptCallback(() => {
      console.log('🎤 [TalkMode] Playback interrupted');
    });

    console.log(`🎤 [TalkMode] Controller initialized for guild ${config.guildId}`);
  }

  /**
   * Start talk mode
   */
  async start(): Promise<void> {
    if (this.isActive) {
      console.log('🎤 [TalkMode] Already active');
      return;
    }

    this.isActive = true;

    // Start listening for user audio
    this.receiver.startListening(async (recording) => {
      await this.handleRecording(recording);
    });

    // Send initial message
    if (this.config.textChannel) {
      await this.config.textChannel.send('🎤 Talk mode enabled. I\'m listening...');
    }

    console.log('✅ [TalkMode] Started');
  }

  /**
   * Stop talk mode
   */
  async stop(): Promise<void> {
    if (!this.isActive) {
      return;
    }

    this.isActive = false;
    this.receiver.stopListening();
    this.player.stop();
    this.pendingRecordings = [];
    this.isProcessing = false;

    if (this.config.textChannel) {
      await this.config.textChannel.send('🔇 Talk mode disabled.');
    }

    console.log('🎤 [TalkMode] Stopped');
  }

  /**
   * Handle a completed audio recording
   */
  private async handleRecording(recording: AudioRecording): Promise<void> {
    if (!this.isActive) {
      return;
    }

    const manager = getVoiceChannelManager();
    if (manager?.isMuted(this.config.guildId)) {
      console.log('🔇 [TalkMode] Bot is muted, ignoring recording');
      return;
    }

    // Check for interrupt - if bot is playing and user speaks, stop playback
    if (this.player.isCurrentlyPlaying()) {
      console.log('🎤 [TalkMode] User interrupted - stopping playback');
      this.player.stop();
    }

    // Queue recording if already processing
    if (this.isProcessing) {
      console.log('🎤 [TalkMode] Already processing, queueing recording');
      this.pendingRecordings.push(recording);
      return;
    }

    await this.processRecording(recording);
  }

  /**
   * Process a single recording through the STT -> Chat -> TTS pipeline
   */
  private async processRecording(recording: AudioRecording): Promise<void> {
    this.isProcessing = true;

    try {
      console.log(`🎤 [TalkMode] Processing recording from user ${recording.userId}`);

      // Skip very short recordings (likely noise)
      if (recording.durationMs < 500) {
        console.log('🎤 [TalkMode] Recording too short, skipping');
        return;
      }

      // Convert audio to base64 WAV for STT
      const base64Audio = VoiceReceiver.recordingToBase64Wav(recording);

      // Step 1: STT - Convert audio to text
      console.log('🎤 [TalkMode] Step 1: Speech-to-Text...');
      const sttResult = await this.substrateClient.speechToText({
        audio: base64Audio,
        format: 'wav',
        language: 'en',
      });

      if (sttResult.status !== 'success' || !sttResult.text || sttResult.text.trim() === '') {
        console.log('🎤 [TalkMode] STT returned empty result, skipping');
        return;
      }

      const transcribedText = sttResult.text.trim();
      console.log(`🎤 [TalkMode] Transcribed: "${transcribedText}"`);

      // Notify callback
      if (this.config.onTranscription) {
        this.config.onTranscription(recording.userId, transcribedText);
      }

      // Optionally log transcription to text channel
      if (this.config.textChannel) {
        await this.config.textChannel.send(`**${recording.username}**: ${transcribedText}`);
      }

      // Step 2: Chat API - Get response
      console.log('🎤 [TalkMode] Step 2: Chat API...');
      const sessionId = `discord_voice_${recording.userId}`;
      const chatResult = await this.substrateClient.chat({
        message: transcribedText,
        session_id: sessionId,
      });

      if (chatResult.error || !chatResult.response || chatResult.response.trim() === '') {
        console.log('🎤 [TalkMode] Chat API returned empty response');
        return;
      }

      const responseText = chatResult.response.trim();
      console.log(`🎤 [TalkMode] Response: "${responseText.substring(0, 50)}..."`);

      // Notify callback
      if (this.config.onResponse) {
        this.config.onResponse(responseText);
      }

      // Optionally log response to text channel
      if (this.config.textChannel) {
        await this.config.textChannel.send(`**Agent**: ${responseText}`);
      }

      // Step 3: TTS - Convert response to audio
      console.log('🎤 [TalkMode] Step 3: Text-to-Speech...');
      const audioBuffer = await this.substrateClient.textToSpeech({
        text: responseText,
      });

      if (!audioBuffer || audioBuffer.length === 0) {
        console.log('🎤 [TalkMode] TTS returned empty audio');
        return;
      }

      // Step 4: Play audio response
      console.log('🎤 [TalkMode] Step 4: Playing audio response...');

      // Check if still active before playing
      if (!this.isActive) {
        console.log('🎤 [TalkMode] Talk mode stopped, not playing audio');
        return;
      }

      await this.player.playAudio(audioBuffer, 'audio/mpeg');

      // Wait for playback to complete
      await this.player.waitForPlaybackComplete();

      console.log('✅ [TalkMode] Response played successfully');
    } catch (error) {
      console.error('❌ [TalkMode] Error processing recording:', error);
      if (this.config.onError) {
        this.config.onError(error as Error);
      }
    } finally {
      this.isProcessing = false;

      // Process any pending recordings
      if (this.pendingRecordings.length > 0 && this.isActive) {
        const nextRecording = this.pendingRecordings.shift();
        if (nextRecording) {
          await this.processRecording(nextRecording);
        }
      }
    }
  }

  /**
   * Check if talk mode is active
   */
  isActiveMode(): boolean {
    return this.isActive;
  }

  /**
   * Check if currently processing a recording
   */
  isCurrentlyProcessing(): boolean {
    return this.isProcessing;
  }

  /**
   * Destroy the controller and clean up resources
   */
  destroy(): void {
    this.stop();
    this.player.destroy();
    console.log('🎤 [TalkMode] Controller destroyed');
  }
}

// ============================================
// Talk Mode Manager (manages all active talk mode sessions)
// ============================================

export class TalkModeManager {
  private controllers: Map<string, TalkModeController> = new Map();
  private client: Client;

  constructor(client: Client) {
    this.client = client;
    console.log('🎤 [TalkModeManager] Initialized');
  }

  /**
   * Start talk mode for a guild
   */
  async startTalkMode(
    guildId: string,
    connection: VoiceConnection,
    textChannel?: TextChannel | DMChannel | NewsChannel
  ): Promise<TalkModeController> {
    // Stop existing talk mode if any
    await this.stopTalkMode(guildId);

    const controller = new TalkModeController({
      guildId,
      connection,
      client: this.client,
      textChannel,
    });

    await controller.start();
    this.controllers.set(guildId, controller);

    // Update voice channel manager
    const manager = getVoiceChannelManager();
    if (manager) {
      manager.setTalkMode(guildId, true);
    }

    return controller;
  }

  /**
   * Stop talk mode for a guild
   */
  async stopTalkMode(guildId: string): Promise<boolean> {
    const controller = this.controllers.get(guildId);
    if (!controller) {
      return false;
    }

    await controller.stop();
    controller.destroy();
    this.controllers.delete(guildId);

    // Update voice channel manager
    const manager = getVoiceChannelManager();
    if (manager) {
      manager.setTalkMode(guildId, false);
    }

    return true;
  }

  /**
   * Get talk mode controller for a guild
   */
  getController(guildId: string): TalkModeController | undefined {
    return this.controllers.get(guildId);
  }

  /**
   * Check if talk mode is active for a guild
   */
  isTalkModeActive(guildId: string): boolean {
    const controller = this.controllers.get(guildId);
    return controller?.isActiveMode() || false;
  }

  /**
   * Stop all talk mode sessions
   */
  async stopAll(): Promise<void> {
    for (const [guildId] of this.controllers) {
      await this.stopTalkMode(guildId);
    }
    console.log('🎤 [TalkModeManager] Stopped all talk mode sessions');
  }
}

// Singleton instance
let talkModeManagerInstance: TalkModeManager | null = null;

export function getTalkModeManager(): TalkModeManager | null {
  return talkModeManagerInstance;
}

export function initTalkModeManager(client: Client): TalkModeManager {
  talkModeManagerInstance = new TalkModeManager(client);
  return talkModeManagerInstance;
}
