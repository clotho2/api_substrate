/**
 * Voice Receiver
 *
 * Listens to user audio streams in voice channels, detects silence (end of speech),
 * buffers audio, and converts it to a format suitable for STT.
 */

import { VoiceConnection, EndBehaviorType } from '@discordjs/voice';
import { User } from 'discord.js';
import { Readable, Transform } from 'stream';
import { OpusEncoder } from '@discordjs/opus';

// ============================================
// Types
// ============================================

export interface AudioRecording {
  userId: string;
  username: string;
  audioBuffer: Buffer;
  startTime: Date;
  endTime: Date;
  durationMs: number;
}

export type AudioRecordingCallback = (recording: AudioRecording) => void;

// ============================================
// Voice Receiver
// ============================================

export class VoiceReceiver {
  private connection: VoiceConnection;
  private activeStreams: Map<string, {
    chunks: Buffer[];
    startTime: Date;
    username: string;
    timeout: NodeJS.Timeout | null;
  }> = new Map();
  private onRecordingComplete: AudioRecordingCallback | null = null;
  private silenceThresholdMs: number;
  private isListening: boolean = false;
  private opusDecoder: OpusEncoder;

  constructor(connection: VoiceConnection, silenceThresholdMs?: number) {
    this.connection = connection;
    this.silenceThresholdMs = silenceThresholdMs || parseInt(process.env.SILENCE_THRESHOLD_MS || '800', 10);

    // Create Opus decoder for 48kHz stereo audio (Discord's format)
    this.opusDecoder = new OpusEncoder(48000, 2);

    console.log(`🎤 [VoiceReceiver] Initialized with silence threshold: ${this.silenceThresholdMs}ms`);
  }

  /**
   * Start listening for user audio
   */
  startListening(callback: AudioRecordingCallback): void {
    if (this.isListening) {
      console.log('🎤 [VoiceReceiver] Already listening');
      return;
    }

    this.onRecordingComplete = callback;
    this.isListening = true;

    const receiver = this.connection.receiver;

    // Listen for when users start speaking
    receiver.speaking.on('start', (userId) => {
      if (!this.isListening) return;

      // Get user info
      const user = this.connection.receiver.subscriptions.get(userId);

      // Start recording this user
      this.startRecording(userId);
    });

    // Subscribe to the speaking events to capture audio
    receiver.speaking.on('start', (userId) => {
      if (!this.isListening) return;

      console.log(`🎤 [VoiceReceiver] User ${userId} started speaking`);

      // Subscribe to user's audio stream
      const audioStream = receiver.subscribe(userId, {
        end: {
          behavior: EndBehaviorType.AfterSilence,
          duration: this.silenceThresholdMs,
        },
      });

      // Initialize or get recording state
      let recordingState = this.activeStreams.get(userId);
      if (!recordingState) {
        recordingState = {
          chunks: [],
          startTime: new Date(),
          username: userId, // Will be updated if we can resolve
          timeout: null,
        };
        this.activeStreams.set(userId, recordingState);
      }

      // Clear any existing timeout
      if (recordingState.timeout) {
        clearTimeout(recordingState.timeout);
        recordingState.timeout = null;
      }

      // Collect audio chunks
      audioStream.on('data', (chunk: Buffer) => {
        const state = this.activeStreams.get(userId);
        if (state) {
          // Decode Opus to PCM
          try {
            const pcmData = this.opusDecoder.decode(chunk);
            state.chunks.push(pcmData);
          } catch (error) {
            // If decoding fails, store raw chunk
            state.chunks.push(chunk);
          }
        }
      });

      // Handle end of stream (silence detected)
      audioStream.on('end', () => {
        console.log(`🎤 [VoiceReceiver] User ${userId} stopped speaking (silence detected)`);
        this.finishRecording(userId);
      });

      audioStream.on('error', (error) => {
        console.error(`❌ [VoiceReceiver] Audio stream error for user ${userId}:`, error);
        this.cancelRecording(userId);
      });
    });

    console.log('✅ [VoiceReceiver] Started listening for user audio');
  }

  /**
   * Stop listening for user audio
   */
  stopListening(): void {
    this.isListening = false;

    // Cancel all active recordings
    for (const [userId] of this.activeStreams) {
      this.cancelRecording(userId);
    }

    this.onRecordingComplete = null;

    console.log('🎤 [VoiceReceiver] Stopped listening');
  }

  /**
   * Start recording for a user
   */
  private startRecording(userId: string): void {
    if (this.activeStreams.has(userId)) {
      return; // Already recording
    }

    this.activeStreams.set(userId, {
      chunks: [],
      startTime: new Date(),
      username: userId,
      timeout: null,
    });

    console.log(`🎤 [VoiceReceiver] Started recording for user ${userId}`);
  }

  /**
   * Finish recording and trigger callback
   */
  private finishRecording(userId: string): void {
    const state = this.activeStreams.get(userId);
    if (!state || state.chunks.length === 0) {
      this.activeStreams.delete(userId);
      return;
    }

    const endTime = new Date();
    const durationMs = endTime.getTime() - state.startTime.getTime();

    // Combine all chunks into a single buffer
    const audioBuffer = Buffer.concat(state.chunks);

    // Create recording object
    const recording: AudioRecording = {
      userId,
      username: state.username,
      audioBuffer,
      startTime: state.startTime,
      endTime,
      durationMs,
    };

    // Clear state
    if (state.timeout) {
      clearTimeout(state.timeout);
    }
    this.activeStreams.delete(userId);

    console.log(`✅ [VoiceReceiver] Recording complete for user ${userId}: ${audioBuffer.length} bytes, ${durationMs}ms`);

    // Trigger callback
    if (this.onRecordingComplete && audioBuffer.length > 0) {
      this.onRecordingComplete(recording);
    }
  }

  /**
   * Cancel a recording without triggering callback
   */
  private cancelRecording(userId: string): void {
    const state = this.activeStreams.get(userId);
    if (state) {
      if (state.timeout) {
        clearTimeout(state.timeout);
      }
      this.activeStreams.delete(userId);
      console.log(`🎤 [VoiceReceiver] Cancelled recording for user ${userId}`);
    }
  }

  /**
   * Update username for a recording (if resolved later)
   */
  updateUsername(userId: string, username: string): void {
    const state = this.activeStreams.get(userId);
    if (state) {
      state.username = username;
    }
  }

  /**
   * Check if currently listening
   */
  isCurrentlyListening(): boolean {
    return this.isListening;
  }

  /**
   * Get number of active recordings
   */
  getActiveRecordingCount(): number {
    return this.activeStreams.size;
  }

  /**
   * Convert PCM audio buffer to WAV format for STT
   */
  static pcmToWav(pcmBuffer: Buffer, sampleRate: number = 48000, channels: number = 2, bitsPerSample: number = 16): Buffer {
    const dataLength = pcmBuffer.length;
    const wavBuffer = Buffer.alloc(44 + dataLength);

    // WAV header
    // RIFF header
    wavBuffer.write('RIFF', 0);
    wavBuffer.writeUInt32LE(36 + dataLength, 4);
    wavBuffer.write('WAVE', 8);

    // fmt chunk
    wavBuffer.write('fmt ', 12);
    wavBuffer.writeUInt32LE(16, 16); // Chunk size
    wavBuffer.writeUInt16LE(1, 20); // Audio format (PCM)
    wavBuffer.writeUInt16LE(channels, 22); // Number of channels
    wavBuffer.writeUInt32LE(sampleRate, 24); // Sample rate
    wavBuffer.writeUInt32LE(sampleRate * channels * bitsPerSample / 8, 28); // Byte rate
    wavBuffer.writeUInt16LE(channels * bitsPerSample / 8, 32); // Block align
    wavBuffer.writeUInt16LE(bitsPerSample, 34); // Bits per sample

    // data chunk
    wavBuffer.write('data', 36);
    wavBuffer.writeUInt32LE(dataLength, 40);
    pcmBuffer.copy(wavBuffer, 44);

    return wavBuffer;
  }

  /**
   * Convert audio recording to base64 WAV for STT API
   */
  static recordingToBase64Wav(recording: AudioRecording): string {
    const wavBuffer = VoiceReceiver.pcmToWav(recording.audioBuffer);
    return wavBuffer.toString('base64');
  }
}
