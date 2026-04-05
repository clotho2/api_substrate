import axios from 'axios';
import * as fs from 'fs/promises';
import * as path from 'path';
import * as crypto from 'crypto';

export interface ElevenLabsRequest {
  text: string;
  voiceId?: string;
  modelId?: string;
  stability?: number;
  similarityBoost?: number;
  style?: number;
  useSpeakerBoost?: boolean;
}

export interface ElevenLabsResult {
  success: boolean;
  audioBuffer?: Buffer;
  error?: string;
  duration?: number;
}

/**
 * ElevenLabs Text-to-Speech Service
 * Supports Eleven v3 (alpha) model with Audio Tags support
 * 
 * Audio Tags Format (for v3 model):
 * - [whispering] - whispering tone
 * - [laughs] - laughing
 * - [sighs] - sighing
 * - [excited] - excited tone
 * - [sarcastic] - sarcastic tone
 * - [strong X accent] - accent (e.g., [strong French accent])
 * - [applause] - sound effects
 * 
 * Example: "[excited] Hey! [whispering] I have a secret for you."
 */
export class ElevenLabsService {
  private apiKey: string;
  private defaultVoiceId: string;
  private defaultModelId: string = 'eleven_v3'; // Eleven v3 (alpha) - supports Audio Tags!
  private baseUrl: string = 'https://api.elevenlabs.io/v1';
  private tempDir: string;

  constructor(apiKey: string, voiceId: string, tempDir?: string) {
    if (!apiKey || !voiceId) {
      throw new Error('ElevenLabs API key and Voice ID are required');
    }
    this.apiKey = apiKey;
    this.defaultVoiceId = voiceId;
    this.tempDir = tempDir || path.join(process.cwd(), 'temp_audio');
  }

  /**
   * Initialize the service (create temp directory)
   */
  async initialize(): Promise<void> {
    try {
      await fs.mkdir(this.tempDir, { recursive: true });
      console.log('✅ ElevenLabs Service initialized');
    } catch (error) {
      console.error('❌ Failed to initialize ElevenLabs service:', error);
      throw error;
    }
  }

  /**
   * Generate speech from text using ElevenLabs API
   * Supports Audio Tags for v3 model (e.g., [excited], [whispering])
   */
  async generateSpeech(request: ElevenLabsRequest): Promise<ElevenLabsResult> {
    const startTime = Date.now();
    
    try {
      // Validate input
      if (!request.text || typeof request.text !== 'string' || request.text.trim().length === 0) {
        return {
          success: false,
          error: 'Text is required and must be non-empty',
          duration: Date.now() - startTime
        };
      }

      // Security: Limit text length (ElevenLabs v3 has 3000 char limit, but we'll be conservative)
      if (request.text.length > 3000) {
        return {
          success: false,
          error: `Text too long (${request.text.length} chars). Maximum is 3000 characters.`,
          duration: Date.now() - startTime
        };
      }

      const voiceId = request.voiceId || this.defaultVoiceId;
      const modelId = request.modelId || this.defaultModelId;
      
      // Build API request
      const url = `${this.baseUrl}/text-to-speech/${voiceId}`;
      
      const requestBody: any = {
        text: request.text.trim(),
        model_id: modelId,
      };

      // Add voice settings (optional, but recommended)
      if (request.stability !== undefined || request.similarityBoost !== undefined || 
          request.style !== undefined || request.useSpeakerBoost !== undefined) {
        requestBody.voice_settings = {};
        
        if (request.stability !== undefined) {
          requestBody.voice_settings.stability = Math.max(0, Math.min(1, request.stability));
        }
        if (request.similarityBoost !== undefined) {
          requestBody.voice_settings.similarity_boost = Math.max(0, Math.min(1, request.similarityBoost));
        }
        if (request.style !== undefined) {
          requestBody.voice_settings.style = Math.max(0, Math.min(1, request.style));
        }
        if (request.useSpeakerBoost !== undefined) {
          requestBody.voice_settings.use_speaker_boost = request.useSpeakerBoost;
        }
      } else {
        // Default settings (recommended by ElevenLabs)
        requestBody.voice_settings = {
          stability: 0.5,
          similarity_boost: 0.75,
          style: 0.0,
          use_speaker_boost: false
        };
      }

      // Make API request
      const response = await axios.post(url, requestBody, {
        headers: {
          'xi-api-key': this.apiKey,
          'Content-Type': 'application/json'
        },
        responseType: 'arraybuffer', // Get binary audio data
        timeout: 300000 // 🎤 5 Minuten timeout für Voice Messages (ElevenLabs + Verarbeitung braucht länger!)
      });

      if (response.status !== 200) {
        return {
          success: false,
          error: `API returned status ${response.status}`,
          duration: Date.now() - startTime
        };
      }

      // Convert to Buffer
      const audioBuffer = Buffer.from(response.data, 'binary');
      
      // Security: Validate audio buffer size (max 25MB for Discord)
      if (audioBuffer.length > 25 * 1024 * 1024) {
        return {
          success: false,
          error: `Audio file too large (${(audioBuffer.length / 1024 / 1024).toFixed(2)}MB). Maximum is 25MB.`,
          duration: Date.now() - startTime
        };
      }

      return {
        success: true,
        audioBuffer,
        duration: Date.now() - startTime
      };

    } catch (error: any) {
      let errorMessage = 'Unknown error';
      
      if (axios.isAxiosError(error)) {
        if (error.response) {
          // API returned error response
          const status = error.response.status;
          const data = error.response.data;
          
          if (typeof data === 'string') {
            errorMessage = `API Error ${status}: ${data}`;
          } else if (data && typeof data === 'object' && 'detail' in data) {
            errorMessage = `API Error ${status}: ${(data as any).detail?.message || JSON.stringify(data)}`;
          } else {
            errorMessage = `API Error ${status}: ${JSON.stringify(data)}`;
          }
        } else if (error.request) {
          errorMessage = 'No response from ElevenLabs API (network error)';
        } else {
          errorMessage = `Request setup error: ${error.message}`;
        }
      } else if (error instanceof Error) {
        errorMessage = error.message;
      } else {
        errorMessage = String(error);
      }

      return {
        success: false,
        error: errorMessage,
        duration: Date.now() - startTime
      };
    }
  }

  /**
   * Clean up temporary files (optional cleanup method)
   */
  async cleanup(): Promise<void> {
    try {
      // Could implement cleanup of old temp files here if needed
      // For now, we're using in-memory buffers, so no cleanup needed
    } catch (error) {
      console.error('Error during cleanup:', error);
    }
  }
}

