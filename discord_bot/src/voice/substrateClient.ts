/**
 * Substrate Client for Voice Channel Support
 *
 * Handles communication with the api_substrate for:
 * - STT (Speech-to-Text) via /stt endpoint
 * - TTS (Text-to-Speech) via /tts endpoint
 * - Chat API via /api/chat endpoint
 */

import axios, { AxiosInstance } from 'axios';

// ============================================
// Types
// ============================================

export interface STTRequest {
  audio: string;  // Base64-encoded audio
  format: 'wav' | 'ogg' | 'webm' | 'mp3';
  language?: string;
}

export interface STTResponse {
  text: string;
  status: 'success' | 'error';
  provider?: string;
  duration_ms?: number;
  error?: string;
}

export interface TTSRequest {
  text: string;
  voice?: string;
  speed?: number;
}

export interface ChatRequest {
  message: string;
  session_id: string;
}

export interface ChatResponse {
  response: string;
  session_id: string;
  error?: string;
}

// ============================================
// Substrate Client
// ============================================

export class SubstrateClient {
  private client: AxiosInstance;
  private baseUrl: string;

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || process.env.SUBSTRATE_API_URL || process.env.GROK_BASE_URL || 'http://localhost:8284';

    this.client = axios.create({
      baseURL: this.baseUrl,
      timeout: 60000, // 60 second timeout for TTS/STT operations
      headers: {
        'Content-Type': 'application/json',
      },
    });

    console.log(`🎤 [SubstrateClient] Initialized with base URL: ${this.baseUrl}`);
  }

  /**
   * Speech-to-Text: Convert audio to text
   */
  async speechToText(request: STTRequest): Promise<STTResponse> {
    try {
      console.log(`🎤 [STT] Sending ${request.format} audio for transcription...`);

      const response = await this.client.post<STTResponse>('/stt', request);

      if (response.data.status === 'success') {
        console.log(`✅ [STT] Transcription successful: "${response.data.text.substring(0, 50)}..."`);
        console.log(`🎤 [STT] Provider: ${response.data.provider}, Duration: ${response.data.duration_ms}ms`);
      } else {
        console.error(`❌ [STT] Transcription failed: ${response.data.error}`);
      }

      return response.data;
    } catch (error: any) {
      console.error(`❌ [STT] Error:`, error.message);
      return {
        text: '',
        status: 'error',
        error: error.message || 'Unknown STT error',
      };
    }
  }

  /**
   * Text-to-Speech: Convert text to audio (returns Agent's voice)
   */
  async textToSpeech(request: TTSRequest): Promise<Buffer | null> {
    try {
      console.log(`🎤 [TTS] Generating speech for: "${request.text.substring(0, 50)}..."`);

      const response = await this.client.post('/tts', request, {
        responseType: 'arraybuffer',
        timeout: 30000, // 30 second timeout for TTS
      });

      const contentType = response.headers['content-type'] || '';
      const audioBuffer = Buffer.from(response.data);

      console.log(`✅ [TTS] Audio generated: ${audioBuffer.length} bytes, type: ${contentType}`);

      return audioBuffer;
    } catch (error: any) {
      console.error(`❌ [TTS] Error:`, error.message);
      return null;
    }
  }

  /**
   * Chat API: Send message and get response
   */
  async chat(request: ChatRequest): Promise<ChatResponse> {
    try {
      console.log(`💬 [Chat] Sending message: "${request.message.substring(0, 50)}..."`);
      console.log(`💬 [Chat] Session ID: ${request.session_id}`);

      const response = await this.client.post<ChatResponse>('/api/chat', request, {
        timeout: 120000, // 2 minute timeout for chat (can be slow with thinking models)
      });

      if (response.data.response) {
        console.log(`✅ [Chat] Response received: "${response.data.response.substring(0, 50)}..."`);
      } else if (response.data.error) {
        console.error(`❌ [Chat] Error: ${response.data.error}`);
      }

      return response.data;
    } catch (error: any) {
      console.error(`❌ [Chat] Error:`, error.message);
      return {
        response: '',
        session_id: request.session_id,
        error: error.message || 'Unknown chat error',
      };
    }
  }

  /**
   * Health check for substrate
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await this.client.get('/health', { timeout: 5000 });
      return response.status === 200;
    } catch (error) {
      return false;
    }
  }
}

// Singleton instance
let substrateClientInstance: SubstrateClient | null = null;

export function getSubstrateClient(): SubstrateClient {
  if (!substrateClientInstance) {
    substrateClientInstance = new SubstrateClient();
  }
  return substrateClientInstance;
}

export function initSubstrateClient(baseUrl?: string): SubstrateClient {
  substrateClientInstance = new SubstrateClient(baseUrl);
  return substrateClientInstance;
}
