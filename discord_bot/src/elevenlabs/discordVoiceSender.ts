import { Message, TextChannel, DMChannel, AttachmentBuilder } from 'discord.js';
import { ElevenLabsService, ElevenLabsRequest } from './elevenlabsService';

export interface SendVoiceMessageOptions {
  text: string;
  target: Message | TextChannel | DMChannel;
  voiceId?: string;
  modelId?: string;
  stability?: number;
  similarityBoost?: number;
  style?: number;
  useSpeakerBoost?: boolean;
  replyToMessageId?: string;
}

export interface SendVoiceMessageResult {
  success: boolean;
  messageId?: string;
  error?: string;
  audioSize?: number;
  duration?: number;
}

/**
 * Send voice message to Discord using ElevenLabs TTS
 * 
 * This function:
 * 1. Generates audio from text using ElevenLabs API
 * 2. Sends the audio file as a Discord attachment
 * 3. Supports replying to messages
 * 
 * Security:
 * - Validates text length (max 3000 chars)
 * - Validates audio file size (max 25MB for Discord)
 * - Sanitizes input text
 */
export class DiscordVoiceSender {
  private elevenLabsService: ElevenLabsService;

  constructor(elevenLabsService: ElevenLabsService) {
    this.elevenLabsService = elevenLabsService;
  }

  /**
   * Send voice message to Discord
   */
  async sendVoiceMessage(options: SendVoiceMessageOptions): Promise<SendVoiceMessageResult> {
    const startTime = Date.now();

    try {
      // Security: Validate text input
      if (!options.text || typeof options.text !== 'string') {
        return {
          success: false,
          error: 'Text is required and must be a string',
          duration: Date.now() - startTime
        };
      }

      // Security: Sanitize text (remove null bytes, limit length)
      let sanitizedText = options.text.replace(/\0/g, '').trim();
      
      if (sanitizedText.length === 0) {
        return {
          success: false,
          error: 'Text cannot be empty after sanitization',
          duration: Date.now() - startTime
        };
      }

      if (sanitizedText.length > 3000) {
        return {
          success: false,
          error: `Text too long (${sanitizedText.length} chars). Maximum is 3000 characters.`,
          duration: Date.now() - startTime
        };
      }

      // Generate audio using ElevenLabs
      const ttsRequest: ElevenLabsRequest = {
        text: sanitizedText,
        voiceId: options.voiceId,
        modelId: options.modelId,
        stability: options.stability,
        similarityBoost: options.similarityBoost,
        style: options.style,
        useSpeakerBoost: options.useSpeakerBoost
      };

      console.log(`🎤 Generating voice message (${sanitizedText.length} chars)...`);
      const ttsResult = await this.elevenLabsService.generateSpeech(ttsRequest);

      if (!ttsResult.success || !ttsResult.audioBuffer) {
        return {
          success: false,
          error: ttsResult.error || 'Failed to generate audio',
          duration: Date.now() - startTime
        };
      }

      // Security: Validate audio buffer size (Discord limit is 25MB)
      if (ttsResult.audioBuffer.length > 25 * 1024 * 1024) {
        return {
          success: false,
          error: `Audio file too large (${(ttsResult.audioBuffer.length / 1024 / 1024).toFixed(2)}MB). Maximum is 25MB.`,
          duration: Date.now() - startTime
        };
      }

      // Create Discord attachment
      const attachment = new AttachmentBuilder(ttsResult.audioBuffer, {
        name: 'voice_message.mp3',
        description: `Voice message: ${sanitizedText.substring(0, 100)}${sanitizedText.length > 100 ? '...' : ''}`
      });

      // Send to Discord
      let sentMessage;
      
      if (options.target instanceof Message) {
        // Reply to a message
        if (options.replyToMessageId) {
          sentMessage = await options.target.reply({
            files: [attachment]
          });
        } else {
          // Send in same channel
          sentMessage = await (options.target.channel as any).send({
            files: [attachment]
          });
        }
      } else {
        // Send to channel or DM
        sentMessage = await options.target.send({
          files: [attachment]
        });
      }

      console.log(`✅ Voice message sent successfully (${(ttsResult.audioBuffer.length / 1024).toFixed(2)}KB)`);

      return {
        success: true,
        messageId: sentMessage.id,
        audioSize: ttsResult.audioBuffer.length,
        duration: Date.now() - startTime
      };

    } catch (error: any) {
      let errorMessage = 'Unknown error';
      
      if (error instanceof Error) {
        errorMessage = error.message;
      } else {
        errorMessage = String(error);
      }

      console.error('❌ Error sending voice message:', errorMessage);

      return {
        success: false,
        error: errorMessage,
        duration: Date.now() - startTime
      };
    }
  }
}

