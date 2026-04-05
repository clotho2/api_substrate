// app/lib/voiceEngine.ts
// Voice Engine with real-time WebSocket voice pipeline
// Primary: WebSocket (Deepgram STT + Cartesia TTS) for low-latency conversation
// Fallback: REST-based STT/TTS for read-aloud and offline scenarios

import {
  setAudioModeAsync,
  requestRecordingPermissionsAsync,
  RecordingPresets,
  AudioModule,
  PLAYBACK_STATUS_UPDATE,
  createAudioPlayer,
} from 'expo-audio';
import type { AudioPlayer, AudioRecorder } from 'expo-audio';
import type { RecordingOptions, AudioStatus } from 'expo-audio';
import { createRecordingOptions } from 'expo-audio';
import * as Speech from 'expo-speech';
import * as FileSystem from 'expo-file-system/legacy';
import { SUBSTRATE_URL, ENDPOINTS, SESSION_ID, USER_ID } from '../config/substrate';

interface VoiceConfig {
  baseUrl: string;
  ttsEndpoint: string;
  sttEndpoint: string;
  language: string;
  voiceSpeed: number;
}

interface VoiceState {
  isRecording: boolean;
  isSpeaking: boolean;
  isInitialized: boolean;
  isListening: boolean;
  isTranscribing: boolean;
  recorder?: AudioRecorder;
  player?: AudioPlayer;
  currentEmotion: string;
  preferredMaleVoice?: string;
  conversationMode: boolean;
  speakerMode: boolean;
  initializationError?: string;
  sttAvailable: boolean;
  ttsAvailable: boolean;
  wsConnected: boolean;
  isProcessing: boolean;
}

interface ConversationSettings {
  autoListen: boolean;
  silenceTimeout: number;
  voiceActivityThreshold: number;
  maxRecordingTime: number;
  volumeBoost: number;
}

class SubstrateVoiceEngine {
  private config: VoiceConfig;
  private state: VoiceState;
  private conversationSettings: ConversationSettings;
  private silenceTimer?: NodeJS.Timeout;
  private voiceActivityTimer?: NodeJS.Timeout;
  private onTranscriptCallback?: (transcript: string) => void;
  private onConversationStateChanged?: (state: any) => void;
  private onInterimTranscriptCallback?: (text: string, isFinal: boolean) => void;
  private onResponseTextCallback?: (text: string, userTranscript: string) => void;

  // Speech queue for streaming TTS (REST fallback)
  private speechQueue: string[] = [];
  private isProcessingQueue: boolean = false;

  // WebSocket voice pipeline
  private ws?: WebSocket;
  private wsReconnectTimer?: NodeJS.Timeout;
  private wsAudioChunks: string[] = [];
  private useWebSocket: boolean = true;

  constructor() {
    this.config = {
      // All voice endpoints go through the substrate
      baseUrl: SUBSTRATE_URL,
      ttsEndpoint: ENDPOINTS.tts,
      sttEndpoint: ENDPOINTS.stt,
      language: 'en-US',
      voiceSpeed: 1.0
    };

    this.state = {
      isRecording: false,
      isSpeaking: false,
      isInitialized: false,
      isListening: false,
      isTranscribing: false,
      currentEmotion: 'neutral',
      conversationMode: false,
      speakerMode: true,
      sttAvailable: false,
      ttsAvailable: false,
      wsConnected: false,
      isProcessing: false,
    };

    this.conversationSettings = {
      autoListen: true,
      silenceTimeout: 1500,
      voiceActivityThreshold: 0.1,
      maxRecordingTime: 60000,
      volumeBoost: 1.0
    };
  }

  // Initialize voice engine
  async initialize(): Promise<boolean> {
    try {
      console.log('🎤 Starting Substrate Voice Engine initialization...');

      // Step 1: Check audio permissions
      console.log('📋 Requesting audio permissions...');
      const permResponse = await requestRecordingPermissionsAsync();
      const status = permResponse.status;
      if (status !== 'granted') {
        console.warn('⚠️ Audio permission denied');
        this.state.initializationError = 'Audio permissions not granted';
      } else {
        console.log('✅ Audio permissions granted');
      }

      // Step 2: Configure audio mode
      console.log('🔧 Configuring audio mode...');
      try {
        await setAudioModeAsync({
          allowsRecording: true,
          playsInSilentMode: true,
          shouldRouteThroughEarpiece: false,
          shouldPlayInBackground: true,
          interruptionMode: 'doNotMix',
          interruptionModeAndroid: 'doNotMix',
        });
        console.log('✅ Audio mode configured');
      } catch (audioError) {
        console.error('❌ Audio mode configuration failed:', audioError);
        this.state.initializationError = 'Audio configuration failed';
      }

      // Step 3: Set speaker mode
      await this.setSpeakerMode(this.state.speakerMode);

      // Step 4: Find best male voice (fallback)
      await this.findBestMaleVoice();

      // Step 5: Test STT connection (Whisper)
      console.log('🎙️ Testing STT (Whisper) connection...');
      this.state.sttAvailable = await this.testSTTConnection();

      // Step 6: Test TTS connection (ElevenLabs)
      console.log('🔊 Testing TTS (ElevenLabs) connection...');
      this.state.ttsAvailable = await this.testTTSConnection();

      this.state.isInitialized = true;
      console.log('✅ Substrate Voice Engine initialized');
      console.log(`🎤 Features:
        - Audio permissions: ${status === 'granted' ? 'Yes' : 'No'}
        - STT (Whisper): ${this.state.sttAvailable ? 'Yes' : 'No'}
        - TTS (Substrate): ${this.state.ttsAvailable ? 'Yes' : 'No (will use system voice)'}
        - System voice fallback: Yes
        - Recording: ${status === 'granted' ? 'Yes' : 'No'}
        - Speaker mode: Yes`);

      return true;

    } catch (error) {
      console.error('❌ Voice engine initialization failed:', error);
      this.state.initializationError = (error as Error).message;
      // Still mark as initialized so system voice fallback works
      this.state.isInitialized = true;
      // Return true so the app can still use system voice fallback for read-aloud
      return true;
    }
  }

  // Test STT (Whisper) connection
  private async testSTTConnection(): Promise<boolean> {
    try {
      const response = await fetch(ENDPOINTS.sttHealth, {
        method: 'GET'
      });

      if (response.ok) {
        console.log('✅ STT (Whisper) connection successful');
        return true;
      }

      console.warn('⚠️ STT health check failed:', response.status);
      return false;

    } catch (error) {
      console.warn('⚠️ STT test failed:', error);
      return false;
    }
  }

  // Test TTS (ElevenLabs) connection
  private async testTTSConnection(): Promise<boolean> {
    try {
      const response = await fetch(ENDPOINTS.ttsHealth, {
        method: 'GET'
      });

      if (response.ok) {
        console.log('✅ TTS (ElevenLabs) connection successful');
        return true;
      }

      console.warn('⚠️ TTS health check failed:', response.status);
      return false;

    } catch (error) {
      console.warn('⚠️ TTS test failed:', error);
      return false;
    }
  }

  // Find the best male voice available (for fallback)
  private async findBestMaleVoice(): Promise<void> {
    try {
      const voices = await Speech.getAvailableVoicesAsync();
      console.log(`🎤 Found ${voices.length} available system voices`);

      const preferredMaleVoices = [
        'com.apple.ttsbundle.Daniel-compact',
        'com.apple.ttsbundle.siri_male_en-US_compact',
        'com.apple.voice.enhanced.en-US.Alex',
        'com.apple.voice.compact.en-US.Alex',
        'en-us-x-sfg#male_1-local',
        'en-us-x-sfg#male_2-local',
        'en-us-x-sfg#male_3-local',
      ];

      for (const preferredVoice of preferredMaleVoices) {
        const foundVoice = voices.find((voice: any) =>
          voice.identifier === preferredVoice ||
          voice.name?.toLowerCase().includes('male') ||
          voice.name?.toLowerCase().includes('daniel') ||
          voice.name?.toLowerCase().includes('alex')
        );

        if (foundVoice) {
          this.state.preferredMaleVoice = foundVoice.identifier;
          console.log(`🎤 Selected fallback voice: ${foundVoice.name}`);
          return;
        }
      }

      console.log('🎤 No specific male voice found, using system default');

    } catch (error) {
      console.error('❌ Error finding male voice:', error);
    }
  }

  // Speak with Agent's voice (TTS)
  async speakWithAgent(text: string, emotionalContext?: string): Promise<void> {
    try {
      await this.stopSpeaking();
    } catch (e) {
      console.warn('⚠️ Stop speaking error (ignoring):', e);
    }

    try {
      this.state.isSpeaking = true;
      this.notifyStateChange();
      console.log('🔊 Agent speaking:', text.substring(0, 50) + '...');

      // Try ElevenLabs (substrate TTS) first, then fall back to system voice
      let elevenLabsSuccess = false;
      try {
        elevenLabsSuccess = await this.speakWithElevenLabs(text);
      } catch (e) {
        console.warn('⚠️ ElevenLabs error:', e);
      }
      if (!elevenLabsSuccess) {
        console.log('🔄 ElevenLabs unavailable, using system voice');
        await this.speakWithSystemVoice(text);
      }

      // Auto-continue conversation if in conversation mode
      if (this.state.conversationMode && this.conversationSettings.autoListen) {
        setTimeout(() => {
          console.log('🎤 Auto-starting listening after Agent spoke...');
          this.startListening();
        }, 1000);
      }

    } catch (error) {
      console.error('❌ Failed to speak:', error);
      this.state.isSpeaking = false;
      this.notifyStateChange();
    }
  }

  // Queue speech for streaming TTS (doesn't interrupt current speech)
  // Chunks long text to avoid TTS timeouts
  async queueSpeech(text: string): Promise<void> {
    if (!text.trim()) return;

    // Split long text into smaller chunks to avoid TTS timeouts
    // Keep chunks under ~100 chars for streaming TTS
    const chunks = this.splitTextIntoChunks(text, 100);

    for (const chunk of chunks) {
      if (chunk.trim()) {
        console.log('📝 Queuing speech chunk:', chunk.substring(0, 30) + '...');
        this.speechQueue.push(chunk);
      }
    }

    // Start processing if not already
    if (!this.isProcessingQueue) {
      this.processQueue();
    }
  }

  // Split text into smaller chunks at natural break points
  private splitTextIntoChunks(text: string, maxLength: number): string[] {
    const chunks: string[] = [];
    let remaining = text.trim();

    while (remaining.length > 0) {
      if (remaining.length <= maxLength) {
        chunks.push(remaining);
        break;
      }

      // Find a good break point (comma, semicolon, or space before maxLength)
      let breakPoint = -1;

      // First try comma or semicolon
      for (let i = maxLength; i >= maxLength / 2; i--) {
        if (remaining[i] === ',' || remaining[i] === ';' || remaining[i] === ':') {
          breakPoint = i + 1;
          break;
        }
      }

      // If no punctuation, find last space before maxLength
      if (breakPoint === -1) {
        for (let i = maxLength; i >= maxLength / 2; i--) {
          if (remaining[i] === ' ') {
            breakPoint = i;
            break;
          }
        }
      }

      // If still no break point, just cut at maxLength
      if (breakPoint === -1) {
        breakPoint = maxLength;
      }

      chunks.push(remaining.substring(0, breakPoint).trim());
      remaining = remaining.substring(breakPoint).trim();
    }

    return chunks;
  }

  // Process the speech queue one item at a time
  private async processQueue(): Promise<void> {
    if (this.isProcessingQueue || this.speechQueue.length === 0) {
      return;
    }

    this.isProcessingQueue = true;
    this.state.isSpeaking = true;
    this.notifyStateChange();

    while (this.speechQueue.length > 0) {
      const text = this.speechQueue.shift();
      if (text) {
        console.log('🔊 Processing queued speech:', text.substring(0, 30) + '...');

        // Try ElevenLabs first, fall back to system voice
        const success = await this.speakWithElevenLabs(text);
        if (!success) {
          await this.speakWithSystemVoice(text);
        }

        // Small pause between sentences for natural flow
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    }

    this.isProcessingQueue = false;
    this.state.isSpeaking = false;
    this.notifyStateChange();
    console.log('✅ Speech queue empty');

    // Auto-continue conversation if in conversation mode
    if (this.state.conversationMode && this.conversationSettings.autoListen) {
      setTimeout(() => {
        console.log('🎤 Auto-starting listening after queue complete...');
        this.startListening();
      }, 1000);
    }
  }

  // Clear the speech queue (for interruptions)
  clearSpeechQueue(): void {
    this.speechQueue = [];
    console.log('🗑️ Speech queue cleared');
  }

  // Speak using substrate TTS (ElevenLabs Turbo)
  private async speakWithElevenLabs(text: string): Promise<boolean> {
    try {
      console.log('🔊 Requesting TTS from substrate...');
      this.state.isSpeaking = true;
      this.notifyStateChange();

      const cleanText = this.cleanTextForSpeech(text);

      const response = await fetch(this.config.ttsEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: cleanText,
          speed: this.config.voiceSpeed,
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error('❌ TTS failed:', response.status, errorText);
        return false;
      }

      // Get provider info from headers
      const provider = response.headers.get('X-TTS-Provider') || 'unknown';
      console.log(`🎤 TTS provider: ${provider}`);

      // Handle response based on content type
      const contentType = response.headers.get('content-type') || '';

      // Get audio blob
      const audioBlob = await response.blob();
      
      // Determine file extension based on content type
      let extension = 'wav';
      if (contentType.includes('mpeg') || contentType.includes('mp3')) {
        extension = 'mp3';
      }
      
      const audioUri = `${FileSystem.cacheDirectory}agent_speech_${Date.now()}.${extension}`;

      // Convert blob to base64 and save
      const reader = new FileReader();
      const base64Promise = new Promise<string>((resolve, reject) => {
        reader.onloadend = () => {
          const result = reader.result as string;
          const base64 = result.split(',')[1];
          resolve(base64);
        };
        reader.onerror = () => reject(new Error('Failed to read audio blob'));
        reader.readAsDataURL(audioBlob);
      });

      const base64Audio = await base64Promise;
      await FileSystem.writeAsStringAsync(audioUri, base64Audio, {
        encoding: 'base64',
      });

      await this.playAudioFile(audioUri);
      console.log(`✅ TTS completed via ${provider}`);
      return true;

    } catch (error) {
      console.error('❌ TTS error:', error);
      return false;
    } finally {
      this.state.isSpeaking = false;
      this.notifyStateChange();
    }
  }

  // Transcribe audio using substrate STT (Whisper)
  private async transcribeAudio(audioUri: string): Promise<string | null> {
    if (!this.state.sttAvailable) {
      console.log('⚠️ STT not available, cannot transcribe');
      return null;
    }

    try {
      console.log('🎙️ Transcribing audio via substrate STT...');
      this.state.isTranscribing = true;
      this.notifyStateChange();

      // Read audio file as base64
      const audioBase64 = await FileSystem.readAsStringAsync(audioUri, {
        encoding: 'base64',
      });

      // Send to substrate STT endpoint
      const response = await fetch(this.config.sttEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          audio: audioBase64,
          format: 'wav',
          language: this.config.language
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error('❌ STT failed:', response.status, errorText);
        return null;
      }

      const data = await response.json();

      // Handle various response formats
      let transcript = '';
      if (data.text) {
        transcript = data.text;
      } else if (data.transcript) {
        transcript = data.transcript;
      } else if (data.transcription) {
        transcript = data.transcription;
      } else if (typeof data === 'string') {
        transcript = data;
      }

      console.log('✅ Transcription:', transcript.substring(0, 50) + '...');
      return transcript.trim() || null;

    } catch (error) {
      console.error('❌ STT transcription error:', error);
      return null;
    } finally {
      this.state.isTranscribing = false;
      this.notifyStateChange();
    }
  }

  // Play audio from base64 data
  private async playAudioData(base64Audio: string): Promise<void> {
    try {
      const audioUri = `${FileSystem.cacheDirectory}agent_speech_${Date.now()}.wav`;

      await FileSystem.writeAsStringAsync(audioUri, base64Audio, {
        encoding: 'base64',
      });

      await this.playAudioFile(audioUri);

    } catch (error) {
      console.error('❌ Failed to play audio data:', error);
      this.state.isSpeaking = false;
      this.notifyStateChange();
    }
  }

  // Play audio from URL
  private async playAudioUrl(audioUrl: string): Promise<void> {
    const player = createAudioPlayer(audioUrl);
    player.volume = Math.min(this.conversationSettings.volumeBoost, 1.0);
    this.state.player = player;

    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        subscription.remove();
        player.remove();
        reject(new Error('Audio playback timed out'));
      }, 30000);

      const subscription = player.addListener(PLAYBACK_STATUS_UPDATE, (status: AudioStatus) => {
        if (status.didJustFinish) {
          clearTimeout(timeout);
          this.state.isSpeaking = false;
          this.notifyStateChange();
          subscription.remove();
          player.remove();
          console.log('🎵 Audio playback completed');
          resolve();
        }
      });
      player.play();
    });
  }

  // Play audio from file - waits for playback to complete before resolving
  private async playAudioFile(audioUri: string): Promise<void> {
    const player = createAudioPlayer(audioUri);
    player.volume = Math.min(this.conversationSettings.volumeBoost, 1.0);
    this.state.player = player;

    console.log(`🔊 Playing ElevenLabs audio`);

    // Wait for playback to actually finish before resolving
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        subscription.remove();
        player.remove();
        FileSystem.deleteAsync(audioUri, { idempotent: true });
        reject(new Error('Audio playback timed out'));
      }, 30000);

      const subscription = player.addListener(PLAYBACK_STATUS_UPDATE, (status: AudioStatus) => {
        if (status.didJustFinish) {
          clearTimeout(timeout);
          subscription.remove();
          player.remove();
          FileSystem.deleteAsync(audioUri, { idempotent: true });
          console.log('🎵 Audio playback completed');
          resolve();
        }
      });
      player.play();
    });
  }

  // System voice fallback
  private async speakWithSystemVoice(text: string): Promise<void> {
    try {
      const cleanText = this.cleanTextForSpeech(text);

      const speechOptions: Speech.SpeechOptions = {
        language: this.config.language,
        rate: Math.min(this.config.voiceSpeed * 0.8, 1.0),
        pitch: 0.7,
        onStart: () => {
          console.log('🎵 System speech started');
        },
        onDone: () => {
          this.state.isSpeaking = false;
          this.notifyStateChange();
          console.log('🎵 System speech completed');
        },
        onStopped: () => {
          this.state.isSpeaking = false;
          this.notifyStateChange();
          console.log('🎵 System speech stopped');
        },
        onError: (error: any) => {
          this.state.isSpeaking = false;
          this.notifyStateChange();
          console.error('❌ System speech error:', error);
        }
      };

      if (this.state.preferredMaleVoice) {
        speechOptions.voice = this.state.preferredMaleVoice;
        console.log(`🎤 Using fallback voice: ${this.state.preferredMaleVoice}`);
      }

      await Speech.speak(cleanText, speechOptions);

    } catch (error) {
      console.error('❌ System speech failed:', error);
      this.state.isSpeaking = false;
      this.notifyStateChange();
    }
  }

  // ============================================
  // WEBSOCKET VOICE PIPELINE
  // ============================================

  /**
   * Connect to the real-time voice WebSocket endpoint.
   * The server handles STT (Deepgram) and TTS (Cartesia) - mobile just
   * sends/receives audio and gets transcripts + response text.
   */
  private connectWebSocket(): Promise<boolean> {
    return new Promise((resolve) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve(true);
        return;
      }

      const wsUrl = ENDPOINTS.voiceStream;
      console.log(`🔌 Connecting to voice WebSocket: ${wsUrl}`);

      try {
        this.ws = new WebSocket(wsUrl);
      } catch (err) {
        console.error('❌ WebSocket creation failed:', err);
        resolve(false);
        return;
      }

      const connectTimeout = setTimeout(() => {
        console.warn('⚠️ WebSocket connection timed out');
        this.ws?.close();
        resolve(false);
      }, 10000);

      this.ws.onopen = () => {
        clearTimeout(connectTimeout);
        console.log('✅ Voice WebSocket connected');

        // Send start message with session info
        this.wsSend({
          type: 'start',
          session_id: SESSION_ID,
          user_id: USER_ID,
        });
      };

      this.ws.onmessage = (event: MessageEvent) => {
        this.handleWSMessage(event.data);
      };

      this.ws.onerror = (error: Event) => {
        clearTimeout(connectTimeout);
        console.error('❌ WebSocket error:', error);
        this.state.wsConnected = false;
        this.notifyStateChange();
        resolve(false);
      };

      this.ws.onclose = () => {
        console.log('🔌 Voice WebSocket disconnected');
        this.state.wsConnected = false;
        this.notifyStateChange();

        // Auto-reconnect if still in conversation mode
        if (this.state.conversationMode) {
          console.log('🔄 Scheduling WebSocket reconnect...');
          this.wsReconnectTimer = setTimeout(() => {
            if (this.state.conversationMode) {
              this.connectWebSocket();
            }
          }, 2000);
        }
      };

      // Wait for the "ready" message from server to resolve
      const originalHandler = this.ws.onmessage;
      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'ready') {
            this.state.wsConnected = true;
            this.notifyStateChange();
            // Restore normal message handler
            if (this.ws) this.ws.onmessage = originalHandler;
            resolve(true);
            // Process this message too
            this.handleWSMessage(event.data);
            return;
          }
          if (data.type === 'error') {
            console.error('❌ WebSocket server error:', data.message);
            resolve(false);
            return;
          }
        } catch (e) {
          // Not JSON, ignore
        }
        // Forward to normal handler
        this.handleWSMessage(event.data);
      };
    });
  }

  private wsSend(data: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  private disconnectWebSocket(): void {
    if (this.wsReconnectTimer) {
      clearTimeout(this.wsReconnectTimer);
      this.wsReconnectTimer = undefined;
    }

    if (this.ws) {
      this.wsSend({ type: 'stop' });
      this.ws.onclose = null; // Prevent reconnect
      this.ws.close();
      this.ws = undefined;
    }

    this.state.wsConnected = false;
    this.wsAudioChunks = [];
  }

  /**
   * Handle incoming WebSocket messages from the server.
   */
  private handleWSMessage(raw: string): void {
    let data: any;
    try {
      data = JSON.parse(raw);
    } catch {
      return;
    }

    switch (data.type) {
      case 'ready':
        console.log('✅ Voice session ready');
        this.state.wsConnected = true;
        this.notifyStateChange();
        break;

      case 'listening':
        console.log('🎤 Server ready for audio');
        // If in conversation mode and not already listening, start recording
        if (this.state.conversationMode && !this.state.isListening && !this.state.isSpeaking) {
          this.startListening();
        }
        break;

      case 'transcript':
        // Real-time transcript from Deepgram
        this.onInterimTranscriptCallback?.(data.text, data.is_final);
        if (data.is_final) {
          console.log(`🎤 Transcript (final): ${data.text}`);
        }
        break;

      case 'processing':
        console.log('🧠 Server processing response...');
        this.state.isProcessing = true;
        this.notifyStateChange();
        break;

      case 'response_text':
        // Full response text for chat display
        console.log(`🗣️ Response: ${data.text?.substring(0, 50)}...`);
        this.state.isProcessing = false;
        this.notifyStateChange();
        this.onResponseTextCallback?.(data.text, data.user_transcript);
        break;

      case 'speaking_start':
        console.log('🔊 Server TTS started');
        this.state.isSpeaking = true;
        this.wsAudioChunks = [];
        this.notifyStateChange();
        break;

      case 'audio':
        // Accumulate audio chunks from Cartesia TTS
        if (data.data) {
          this.wsAudioChunks.push(data.data);
        }
        break;

      case 'speaking_end':
        console.log('🔊 Server TTS complete');
        // Play accumulated audio
        this.playWSAudio();
        break;

      case 'error':
        console.error('�� Server voice error:', data.message);
        this.state.isProcessing = false;
        this.state.isSpeaking = false;
        this.notifyStateChange();
        break;
    }
  }

  /**
   * Play accumulated WebSocket audio chunks.
   * Concateagents base64 PCM chunks, wraps in WAV, saves to file, plays.
   */
  private async playWSAudio(): Promise<void> {
    if (this.wsAudioChunks.length === 0) {
      this.state.isSpeaking = false;
      this.notifyStateChange();
      return;
    }

    try {
      // Concateagent all base64 PCM chunks
      const allBase64 = this.wsAudioChunks.join('');
      this.wsAudioChunks = [];

      // Decode base64 to raw bytes
      // We need to create a WAV file from the raw PCM (24kHz, 16-bit, mono)
      const pcmBase64 = allBase64;
      const wavBase64 = this.createWavFromPCM(pcmBase64, 24000, 1, 16);

      const audioUri = `${FileSystem.cacheDirectory}agent_ws_speech_${Date.now()}.wav`;
      await FileSystem.writeAsStringAsync(audioUri, wavBase64, {
        encoding: 'base64',
      });

      await this.playAudioFile(audioUri);

    } catch (error) {
      console.error('❌ Failed to play WebSocket audio:', error);
    } finally {
      this.state.isSpeaking = false;
      this.notifyStateChange();

      // Auto-resume listening
      if (this.state.conversationMode && this.state.wsConnected) {
        setTimeout(() => this.startListening(), 500);
      }
    }
  }

  /**
   * Create a WAV file (base64) from raw PCM data (base64).
   * Adds the 44-byte WAV header to raw PCM audio.
   */
  private createWavFromPCM(
    pcmBase64: string,
    sampleRate: number,
    numChannels: number,
    bitsPerSample: number
  ): string {
    // Decode PCM from base64
    const pcmBinaryString = atob(pcmBase64);
    const pcmLength = pcmBinaryString.length;

    // WAV header is 44 bytes
    const wavLength = 44 + pcmLength;
    const buffer = new Uint8Array(wavLength);
    const view = new DataView(buffer.buffer);

    const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
    const blockAlign = numChannels * (bitsPerSample / 8);

    // RIFF header
    buffer[0] = 0x52; buffer[1] = 0x49; buffer[2] = 0x46; buffer[3] = 0x46; // "RIFF"
    view.setUint32(4, wavLength - 8, true); // File size - 8
    buffer[8] = 0x57; buffer[9] = 0x41; buffer[10] = 0x56; buffer[11] = 0x45; // "WAVE"

    // fmt subchunk
    buffer[12] = 0x66; buffer[13] = 0x6D; buffer[14] = 0x74; buffer[15] = 0x20; // "fmt "
    view.setUint32(16, 16, true); // Subchunk1Size (16 for PCM)
    view.setUint16(20, 1, true); // AudioFormat (1 = PCM)
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);

    // data subchunk
    buffer[36] = 0x64; buffer[37] = 0x61; buffer[38] = 0x74; buffer[39] = 0x61; // "data"
    view.setUint32(40, pcmLength, true);

    // Copy PCM data
    for (let i = 0; i < pcmLength; i++) {
      buffer[44 + i] = pcmBinaryString.charCodeAt(i);
    }

    // Convert to base64
    let binary = '';
    for (let i = 0; i < buffer.length; i++) {
      binary += String.fromCharCode(buffer[i]);
    }
    return btoa(binary);
  }

  /**
   * Send recorded audio over WebSocket (batch mode).
   * Records with expo-audio, then sends the complete audio to the server
   * which handles STT + AI response + TTS and streams audio back.
   */
  private async sendRecordedAudioOverWS(audioUri: string): Promise<void> {
    if (!this.state.wsConnected || !this.ws) {
      console.warn('⚠️ WebSocket not connected, falling back to REST');
      // Fall back to REST-based transcription
      await this.processRecordingREST(audioUri);
      return;
    }

    try {
      const audioBase64 = await FileSystem.readAsStringAsync(audioUri, {
        encoding: 'base64',
      });

      // Send audio data to server
      this.wsSend({
        type: 'audio',
        data: audioBase64,
      });

      console.log('📤 Sent recorded audio over WebSocket');

    } catch (error) {
      console.error('❌ Failed to send audio over WebSocket:', error);
    } finally {
      // Clean up audio file
      FileSystem.deleteAsync(audioUri, { idempotent: true });
    }
  }

  // ============================================
  // CONVERSATION MODE
  // ============================================

  async startConversationMode(): Promise<boolean> {
    if (!this.state.isInitialized) {
      console.warn('⚠️ Voice engine not initialized');
      return false;
    }

    try {
      console.log('🎯 Starting conversation mode...');
      this.state.conversationMode = true;
      this.notifyStateChange();

      // Try WebSocket first for real-time voice
      if (this.useWebSocket) {
        const wsConnected = await this.connectWebSocket();
        if (wsConnected) {
          console.log('✅ Conversation mode started (WebSocket pipeline)');
          // WebSocket "listening" message will trigger startListening()
          return true;
        }
        console.warn('⚠️ WebSocket unavailable, falling back to REST pipeline');
      }

      // Fallback: REST-based conversation mode
      return await this.startListening();

    } catch (error) {
      console.error('❌ Failed to start conversation mode:', error);
      return false;
    }
  }

  async stopConversationMode(): Promise<void> {
    console.log('🛑 Stopping conversation mode...');

    this.state.conversationMode = false;
    this.disconnectWebSocket();
    await this.stopListening();
    await this.stopSpeaking();
    this.clearTimers();
    this.notifyStateChange();
  }

  // Listening
  async startListening(): Promise<boolean> {
    if (!this.state.isInitialized || this.state.isListening || this.state.isSpeaking) {
      return false;
    }

    try {
      console.log('🎤 Starting listening...');

      const platformOptions = createRecordingOptions(RecordingPresets.HIGH_QUALITY);
      const recorder = new AudioModule.AudioRecorder(platformOptions);
      await recorder.prepareToRecordAsync();
      recorder.record();

      this.state.recorder = recorder;
      this.state.isListening = true;
      this.notifyStateChange();

      this.setupSilenceDetection();

      this.voiceActivityTimer = setTimeout(() => {
        if (this.state.isListening) {
          console.log('⏰ Max recording time reached, processing...');
          this.processRecording();
        }
      }, this.conversationSettings.maxRecordingTime);

      console.log('✅ Listening started');
      return true;

    } catch (error) {
      console.error('❌ Failed to start listening:', error);
      this.state.isListening = false;
      this.notifyStateChange();
      return false;
    }
  }

  async stopListening(): Promise<void> {
    if (!this.state.isListening || !this.state.recorder) {
      return;
    }

    try {
      console.log('🎤 Stopping listening...');
      this.clearTimers();
      await this.processRecording();

    } catch (error) {
      console.error('❌ Error stopping listening:', error);
    }
  }

  // Process recording - routes to WebSocket or REST based on connection state
  private isProcessingRecording: boolean = false;
  private async processRecording(): Promise<void> {
    if (!this.state.recorder || this.isProcessingRecording) return;
    this.isProcessingRecording = true;

    try {
      console.log('🎤 Processing speech...');
      this.clearTimers();

      const recorder = this.state.recorder;
      this.state.isListening = false;
      this.state.recorder = undefined;
      this.notifyStateChange();

      await recorder.stop();
      const uri = recorder.uri;

      if (uri) {
        if (this.state.wsConnected) {
          // WebSocket mode: send audio to server for STT + AI + TTS
          await this.sendRecordedAudioOverWS(uri);
        } else {
          // REST fallback: transcribe locally then send text
          await this.processRecordingREST(uri);
        }
      }

    } catch (error) {
      console.error('❌ Failed to process recording:', error);
      this.state.isListening = false;
      this.state.recorder = undefined;
      this.notifyStateChange();
    } finally {
      this.isProcessingRecording = false;
    }
  }

  // REST-based recording processing (fallback when WebSocket unavailable)
  private async processRecordingREST(uri: string): Promise<void> {
    try {
      let transcript: string | null = null;

      if (this.state.sttAvailable) {
        transcript = await this.transcribeAudio(uri);
      } else {
        console.warn('⚠️ STT service unavailable - cannot transcribe audio');
      }

      if (transcript && transcript.trim()) {
        console.log('🎤 Final transcript:', transcript);
        this.onTranscriptCallback?.(transcript);
      } else {
        console.log('🔇 No speech detected or STT unavailable');

        if (this.state.conversationMode) {
          setTimeout(() => {
            this.startListening();
          }, 1000);
        }
      }

      // Clean up audio file
      FileSystem.deleteAsync(uri, { idempotent: true });

    } catch (error) {
      console.error('❌ REST processing failed:', error);
      FileSystem.deleteAsync(uri, { idempotent: true });
    }
  }

  // Silence detection
  private setupSilenceDetection(): void {
    this.silenceTimer = setTimeout(() => {
      if (this.state.isListening) {
        console.log('🔇 Silence detected, processing speech...');
        this.processRecording();
      }
    }, this.conversationSettings.silenceTimeout);
  }

  // Clear timers
  private clearTimers(): void {
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = undefined;
    }
    if (this.voiceActivityTimer) {
      clearTimeout(this.voiceActivityTimer);
      this.voiceActivityTimer = undefined;
    }
  }

  // Speaker mode
  async setSpeakerMode(useSpeaker: boolean): Promise<void> {
    try {
      console.log(`🔊 Setting audio to ${useSpeaker ? 'speaker' : 'earpiece'} mode`);

      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
        shouldRouteThroughEarpiece: !useSpeaker,
        shouldPlayInBackground: true,
        interruptionMode: 'doNotMix',
        interruptionModeAndroid: 'doNotMix',
      });

      this.state.speakerMode = useSpeaker;
      this.notifyStateChange();

      console.log(`✅ Audio mode set to ${useSpeaker ? 'speaker' : 'earpiece'}`);
    } catch (error) {
      console.error('❌ Failed to set audio mode:', error);
    }
  }

  async toggleSpeakerMode(): Promise<boolean> {
    const newMode = !this.state.speakerMode;
    await this.setSpeakerMode(newMode);
    return newMode;
  }

  // Stop speaking (with barge-in support for WebSocket mode)
  async stopSpeaking(): Promise<void> {
    try {
      console.log('🔇 Stopping speech...');

      // Send interrupt to server if WebSocket connected
      if (this.state.wsConnected) {
        this.wsSend({ type: 'interrupt' });
        this.wsAudioChunks = []; // Discard pending audio
      }

      this.state.isSpeaking = false;
      this.notifyStateChange();

      await Speech.stop();

      if (this.state.player) {
        try {
          this.state.player.pause();
          this.state.player.remove();
          this.state.player = undefined;
        } catch (playerError) {
          console.warn('⚠️ Player cleanup error:', playerError);
        }
      }

      console.log('✅ Speech stopped');
    } catch (error) {
      console.error('❌ Failed to stop speech:', error);
    }
  }

  // Callbacks
  onTranscript(callback: (transcript: string) => void): void {
    this.onTranscriptCallback = callback;
  }

  onStateChange(callback: (state: any) => void): void {
    this.onConversationStateChanged = callback;
  }

  /** Register callback for real-time transcripts from Deepgram (WebSocket mode) */
  onInterimTranscript(callback: (text: string, isFinal: boolean) => void): void {
    this.onInterimTranscriptCallback = callback;
  }

  /** Register callback for AI response text (WebSocket mode - for chat display) */
  onResponseText(callback: (text: string, userTranscript: string) => void): void {
    this.onResponseTextCallback = callback;
  }

  // Notify state change
  private notifyStateChange(): void {
    this.onConversationStateChanged?.({
      isListening: this.state.isListening,
      isSpeaking: this.state.isSpeaking,
      isTranscribing: this.state.isTranscribing,
      isProcessing: this.state.isProcessing,
      conversationMode: this.state.conversationMode,
      isInitialized: this.state.isInitialized,
      speakerMode: this.state.speakerMode,
      sttAvailable: this.state.sttAvailable,
      ttsAvailable: this.state.ttsAvailable,
      wsConnected: this.state.wsConnected,
      initializationError: this.state.initializationError
    });
  }

  // Clean text for speech
  private cleanTextForSpeech(text: string): string {
    return text
      .replace(/\*[^*]*\*/g, '')
      .replace(/\([^)]*\)/g, '')
      .replace(/\[[^\]]*\]/g, '')
      .replace(/[""]/g, '"')
      .replace(/📞|🔊|🎤|⚡|🔥|💙|🛡️|🚗|🏨|⛽|📍|🚨/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // Check if speaking
  async isSpeaking(): Promise<boolean> {
    try {
      const systemSpeaking = await Speech.isSpeakingAsync();
      return systemSpeaking || this.state.isSpeaking;
    } catch (error) {
      return this.state.isSpeaking;
    }
  }

  // Get conversation state
  getConversationState(): any {
    return {
      isListening: this.state.isListening,
      isSpeaking: this.state.isSpeaking,
      isTranscribing: this.state.isTranscribing,
      isProcessing: this.state.isProcessing,
      conversationMode: this.state.conversationMode,
      isInitialized: this.state.isInitialized,
      isRecording: this.state.isRecording,
      speakerMode: this.state.speakerMode,
      sttAvailable: this.state.sttAvailable,
      ttsAvailable: this.state.ttsAvailable,
      wsConnected: this.state.wsConnected,
      initializationError: this.state.initializationError
    };
  }

  // Legacy compatibility
  async startRecording(): Promise<boolean> {
    return await this.startListening();
  }

  async stopRecording(): Promise<string | null> {
    await this.stopListening();
    return null;
  }

  // Volume controls
  setVolumeBoost(boost: number): void {
    this.conversationSettings.volumeBoost = Math.max(1.0, Math.min(boost, 3.0));
    console.log(`🔊 Volume boost set to ${this.conversationSettings.volumeBoost}x`);
  }

  getVolumeBoost(): number {
    return this.conversationSettings.volumeBoost;
  }

  setVoiceSpeed(speed: number): void {
    this.config.voiceSpeed = speed;
    console.log('⚡ Voice speed set to:', speed);
  }

  // Configure base URL (for testing different substrates)
  setBaseUrl(url: string): void {
    this.config.baseUrl = url;
    this.config.ttsEndpoint = `${url}/tts`;
    this.config.sttEndpoint = `${url}/stt`;
    console.log('🔊 Voice endpoints updated:', { tts: this.config.ttsEndpoint, stt: this.config.sttEndpoint });
  }

  getState(): VoiceState {
    return { ...this.state };
  }

  // Cleanup
  async cleanup(): Promise<void> {
    try {
      await this.stopConversationMode();
      this.disconnectWebSocket();

      if (this.state.isRecording && this.state.recorder) {
        await this.state.recorder.stop();
      }

      if (this.state.player) {
        this.state.player.remove();
      }

      this.state.isRecording = false;
      this.state.isSpeaking = false;
      this.state.isListening = false;
      this.state.isTranscribing = false;
      this.state.isProcessing = false;
      this.state.conversationMode = false;
      this.state.wsConnected = false;
      this.state.recorder = undefined;
      this.state.player = undefined;

      console.log('🧹 Voice engine cleaned up');
    } catch (error) {
      console.error('❌ Failed to cleanup voice engine:', error);
    }
  }
}

// Export singleton instance
export const voiceEngine = new SubstrateVoiceEngine();
export default SubstrateVoiceEngine;
