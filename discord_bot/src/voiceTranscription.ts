/**
 * Voice Transcription Service - OpenAI Whisper Integration
 *
 * Transcribes Discord voice messages (.ogg, .webm, .mp3) using OpenAI Whisper API
 */

import axios from 'axios';
import FormData from 'form-data';

export interface TranscriptionRequest {
  audioUrl: string;
  fileName: string;
  language?: string; // Optional: 'en', 'de', 'es', etc. Auto-detect if not provided
}

export interface TranscriptionResult {
  success: boolean;
  text?: string;
  error?: string;
  duration?: number;
  language?: string;
}

/**
 * Voice Transcription Service using OpenAI Whisper API
 */
export class VoiceTranscriptionService {
  private apiKey: string;
  private model: string = 'whisper-1';
  private baseUrl: string = 'https://api.openai.com/v1';
  private maxFileSizeMB: number = 25; // OpenAI limit

  constructor(apiKey: string) {
    if (!apiKey) {
      throw new Error('OpenAI API key is required for voice transcription');
    }
    this.apiKey = apiKey;
  }

  /**
   * Transcribe audio from URL using OpenAI Whisper API
   */
  async transcribeAudio(request: TranscriptionRequest): Promise<TranscriptionResult> {
    const startTime = Date.now();

    try {
      console.log(`🎤 Transcribing audio: ${request.fileName} from ${request.audioUrl.substring(0, 50)}...`);

      // Step 1: Download audio file
      const audioResponse = await axios.get(request.audioUrl, {
        responseType: 'arraybuffer',
        timeout: 30000, // 30 second timeout for download
        maxContentLength: this.maxFileSizeMB * 1024 * 1024,
      });

      const audioBuffer = Buffer.from(audioResponse.data);
      const fileSizeMB = audioBuffer.length / (1024 * 1024);

      console.log(`📥 Downloaded audio: ${fileSizeMB.toFixed(2)}MB`);

      // Security: Validate file size
      if (fileSizeMB > this.maxFileSizeMB) {
        return {
          success: false,
          error: `Audio file too large (${fileSizeMB.toFixed(2)}MB). Maximum is ${this.maxFileSizeMB}MB.`,
          duration: Date.now() - startTime
        };
      }

      // Step 2: Prepare form data for Whisper API
      const formData = new FormData();
      formData.append('file', audioBuffer, {
        filename: request.fileName,
        contentType: this.getContentType(request.fileName)
      });
      formData.append('model', this.model);

      // Optional: Specify language for better accuracy
      if (request.language) {
        formData.append('language', request.language);
      }

      // Step 3: Call OpenAI Whisper API
      console.log(`🔄 Sending to OpenAI Whisper API...`);
      const transcriptionResponse = await axios.post(
        `${this.baseUrl}/audio/transcriptions`,
        formData,
        {
          headers: {
            'Authorization': `Bearer ${this.apiKey}`,
            ...formData.getHeaders()
          },
          timeout: 60000, // 60 second timeout for transcription
        }
      );

      if (transcriptionResponse.status !== 200) {
        return {
          success: false,
          error: `Whisper API returned status ${transcriptionResponse.status}`,
          duration: Date.now() - startTime
        };
      }

      const transcriptionText = transcriptionResponse.data.text || '';
      const detectedLanguage = transcriptionResponse.data.language;

      console.log(`✅ Transcription complete: "${transcriptionText.substring(0, 100)}${transcriptionText.length > 100 ? '...' : ''}"`);

      return {
        success: true,
        text: transcriptionText.trim(),
        language: detectedLanguage,
        duration: Date.now() - startTime
      };

    } catch (error: any) {
      let errorMessage = 'Unknown error';

      if (axios.isAxiosError(error)) {
        if (error.response) {
          // API returned error response
          const status = error.response.status;
          const data = error.response.data;

          if (status === 401) {
            errorMessage = 'Invalid OpenAI API key';
          } else if (status === 413) {
            errorMessage = 'Audio file too large for OpenAI API';
          } else if (typeof data === 'string') {
            errorMessage = `API Error ${status}: ${data}`;
          } else if (data && typeof data === 'object' && 'error' in data) {
            errorMessage = `API Error ${status}: ${(data as any).error?.message || JSON.stringify(data)}`;
          } else {
            errorMessage = `API Error ${status}: ${JSON.stringify(data)}`;
          }
        } else if (error.request) {
          errorMessage = 'No response from OpenAI API (network error)';
        } else if (error.code === 'ECONNABORTED') {
          errorMessage = 'Request timeout - audio file may be too long';
        } else {
          errorMessage = `Request setup error: ${error.message}`;
        }
      } else if (error instanceof Error) {
        errorMessage = error.message;
      } else {
        errorMessage = String(error);
      }

      console.error(`❌ Transcription failed: ${errorMessage}`);

      return {
        success: false,
        error: errorMessage,
        duration: Date.now() - startTime
      };
    }
  }

  /**
   * Get content type for audio file based on extension
   */
  private getContentType(fileName: string): string {
    const ext = fileName.toLowerCase().split('.').pop();

    switch (ext) {
      case 'ogg':
        return 'audio/ogg';
      case 'webm':
        return 'audio/webm';
      case 'mp3':
        return 'audio/mpeg';
      case 'mp4':
      case 'm4a':
        return 'audio/mp4';
      case 'wav':
        return 'audio/wav';
      case 'flac':
        return 'audio/flac';
      default:
        return 'audio/ogg'; // Default to ogg (Discord's default format)
    }
  }

  /**
   * Check if a file is a supported audio format
   */
  static isSupportedAudioFile(fileName: string): boolean {
    const ext = fileName.toLowerCase().split('.').pop();
    const supportedFormats = ['ogg', 'webm', 'mp3', 'mp4', 'm4a', 'wav', 'flac'];
    return supportedFormats.includes(ext || '');
  }
}
