/**
 * Voice Player
 *
 * Handles playing audio (from TTS) in Discord voice channels using AudioPlayer.
 */

import {
  VoiceConnection,
  createAudioPlayer,
  createAudioResource,
  AudioPlayer,
  AudioPlayerStatus,
  NoSubscriberBehavior,
  StreamType,
  AudioResource,
} from '@discordjs/voice';
import { Readable } from 'stream';

// ============================================
// Types
// ============================================

export type PlaybackCompleteCallback = () => void;
export type PlaybackInterruptedCallback = () => void;

// ============================================
// Voice Player
// ============================================

export class VoicePlayer {
  private player: AudioPlayer;
  private connection: VoiceConnection;
  private isPlaying: boolean = false;
  private onPlaybackComplete: PlaybackCompleteCallback | null = null;
  private onPlaybackInterrupted: PlaybackInterruptedCallback | null = null;
  private currentResource: AudioResource | null = null;

  constructor(connection: VoiceConnection) {
    this.connection = connection;

    // Create audio player with specific behavior
    this.player = createAudioPlayer({
      behaviors: {
        noSubscriber: NoSubscriberBehavior.Pause,
      },
    });

    // Subscribe the player to the connection
    this.connection.subscribe(this.player);

    // Handle player state changes
    this.player.on(AudioPlayerStatus.Idle, () => {
      if (this.isPlaying) {
        this.isPlaying = false;
        this.currentResource = null;
        console.log('🔊 [VoicePlayer] Playback finished');
        if (this.onPlaybackComplete) {
          this.onPlaybackComplete();
        }
      }
    });

    this.player.on(AudioPlayerStatus.Playing, () => {
      console.log('🔊 [VoicePlayer] Playback started');
    });

    this.player.on('error', (error) => {
      console.error('❌ [VoicePlayer] Audio player error:', error);
      this.isPlaying = false;
      this.currentResource = null;
    });

    console.log('🔊 [VoicePlayer] Initialized');
  }

  /**
   * Play audio from a buffer (MP3 or WAV from TTS)
   */
  async playAudio(
    audioBuffer: Buffer,
    contentType?: string,
    onComplete?: PlaybackCompleteCallback
  ): Promise<boolean> {
    try {
      // Stop any current playback
      if (this.isPlaying) {
        this.stop();
      }

      this.onPlaybackComplete = onComplete || null;

      // Create a readable stream from the buffer
      const stream = Readable.from(audioBuffer);

      // Determine stream type based on content type
      let inputType: StreamType = StreamType.Arbitrary;
      if (contentType?.includes('mp3') || contentType?.includes('mpeg')) {
        inputType = StreamType.Arbitrary; // prism-media will handle MP3
      } else if (contentType?.includes('ogg')) {
        inputType = StreamType.OggOpus;
      } else if (contentType?.includes('webm')) {
        inputType = StreamType.WebmOpus;
      }

      // Create audio resource
      const resource = createAudioResource(stream, {
        inputType,
        inlineVolume: true,
      });

      // Set volume (optional)
      if (resource.volume) {
        resource.volume.setVolume(1.0);
      }

      this.currentResource = resource;
      this.isPlaying = true;

      // Play the audio
      this.player.play(resource);

      console.log(`🔊 [VoicePlayer] Playing audio: ${audioBuffer.length} bytes, type: ${contentType || 'unknown'}`);

      return true;
    } catch (error) {
      console.error('❌ [VoicePlayer] Error playing audio:', error);
      this.isPlaying = false;
      this.currentResource = null;
      return false;
    }
  }

  /**
   * Play audio from a stream
   */
  async playStream(
    stream: Readable,
    inputType: StreamType = StreamType.Arbitrary,
    onComplete?: PlaybackCompleteCallback
  ): Promise<boolean> {
    try {
      // Stop any current playback
      if (this.isPlaying) {
        this.stop();
      }

      this.onPlaybackComplete = onComplete || null;

      // Create audio resource
      const resource = createAudioResource(stream, {
        inputType,
        inlineVolume: true,
      });

      this.currentResource = resource;
      this.isPlaying = true;

      // Play the audio
      this.player.play(resource);

      console.log(`🔊 [VoicePlayer] Playing audio stream`);

      return true;
    } catch (error) {
      console.error('❌ [VoicePlayer] Error playing stream:', error);
      this.isPlaying = false;
      this.currentResource = null;
      return false;
    }
  }

  /**
   * Stop current playback
   */
  stop(): void {
    if (this.isPlaying) {
      console.log('🔊 [VoicePlayer] Stopping playback');
      this.player.stop();
      this.isPlaying = false;
      this.currentResource = null;

      // Trigger interrupted callback
      if (this.onPlaybackInterrupted) {
        this.onPlaybackInterrupted();
      }
    }
  }

  /**
   * Pause current playback
   */
  pause(): boolean {
    if (this.isPlaying) {
      const success = this.player.pause();
      if (success) {
        console.log('🔊 [VoicePlayer] Playback paused');
      }
      return success;
    }
    return false;
  }

  /**
   * Resume paused playback
   */
  resume(): boolean {
    const success = this.player.unpause();
    if (success) {
      console.log('🔊 [VoicePlayer] Playback resumed');
    }
    return success;
  }

  /**
   * Set volume (0.0 to 2.0)
   */
  setVolume(volume: number): void {
    if (this.currentResource?.volume) {
      const clampedVolume = Math.max(0, Math.min(2, volume));
      this.currentResource.volume.setVolume(clampedVolume);
      console.log(`🔊 [VoicePlayer] Volume set to ${clampedVolume}`);
    }
  }

  /**
   * Check if currently playing
   */
  isCurrentlyPlaying(): boolean {
    return this.isPlaying;
  }

  /**
   * Set callback for when playback is interrupted
   */
  setInterruptCallback(callback: PlaybackInterruptedCallback): void {
    this.onPlaybackInterrupted = callback;
  }

  /**
   * Get the underlying audio player
   */
  getPlayer(): AudioPlayer {
    return this.player;
  }

  /**
   * Wait for current playback to complete
   */
  async waitForPlaybackComplete(): Promise<void> {
    if (!this.isPlaying) {
      return;
    }

    return new Promise((resolve) => {
      const originalCallback = this.onPlaybackComplete;

      this.onPlaybackComplete = () => {
        if (originalCallback) {
          originalCallback();
        }
        resolve();
      };
    });
  }

  /**
   * Destroy the player
   */
  destroy(): void {
    this.stop();
    this.player.stop(true);
    console.log('🔊 [VoicePlayer] Destroyed');
  }
}
