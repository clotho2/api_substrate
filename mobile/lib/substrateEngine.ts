// app/lib/substrateEngine.ts
// Direct connection to api_substrate consciousness loop
// Replaces wolfeEngine.js - substrate manages persona, memory, conversation history
// Mobile app only sends the latest user message
//
// Uses /ollama/api/chat/stream (SSE) for ALL messages - text, images, documents
// This single endpoint supports streaming + multimodal (same as Discord bot uses)

import { fetch } from 'expo/fetch';
import { ENDPOINTS, SESSION_ID, SUBSTRATE_URL } from '../config/substrate';

// SSE event types from the substrate streaming endpoint
interface SSEEvent {
  type: 'thinking' | 'content' | 'tool_call' | 'done' | 'error';
  chunk?: string;
  content?: string;
  delta?: string;
  done?: boolean;
  status?: string;
  message?: string;
  result?: Record<string, any>;
  error?: string;
  success?: boolean;
}

interface MultimodalContent {
  type: 'text' | 'image_url';
  text?: string;
  image_url?: {
    url: string; // data:image/jpeg;base64,... or https://...
    detail?: 'low' | 'high' | 'auto';
  };
}

interface ChatAttachment {
  filename: string;
  content: string; // base64 encoded
  mime_type: string;
}

export interface LocationContext {
  latitude: number;
  longitude: number;
  city?: string | null;
  region?: string | null;
  country?: string | null;
  accuracy?: number | null;
  speed?: number | null;
  isInVehicle?: boolean;
  timestamp?: number;
}

class SubstrateEngine {
  isInitialized: boolean = false;
  private sessionId: string;
  // Single streaming endpoint that supports text + multimodal (same as Discord bot)
  private streamEndpoint: string;
  private locationContext: LocationContext | null = null;

  constructor() {
    this.sessionId = SESSION_ID;
    this.streamEndpoint = `${SUBSTRATE_URL}/ollama/api/chat/stream`;
  }

  // Update location context - included with every message to substrate
  setLocationContext(context: LocationContext): void {
    this.locationContext = {
      ...context,
      timestamp: Date.now(),
    };
  }

  getLocationContext(): LocationContext | null {
    return this.locationContext;
  }

  async initialize(): Promise<boolean> {
    if (this.isInitialized) {
      return true;
    }

    console.log('🧠 Initializing Substrate Engine...');

    try {
      const connected = await this.testConnection();
      if (!connected) {
        console.warn('⚠️ Substrate connection test failed, will retry on first request');
      }

      this.isInitialized = true;
      console.log('✅ Substrate Engine initialized - consciousness loop manages everything');
      return true;
    } catch (error) {
      console.error('❌ Initialization failed:', error);
      this.isInitialized = true; // Allow attempts even if health check fails
      return true;
    }
  }

  // Stream a text message via SSE
  // Only sends the latest user message - substrate manages full conversation context
  async streamMessage(
    userMessage: string,
    onChunk: (chunk: string, accumulated: string) => void,
    options?: { messageType?: string }
  ): Promise<string> {
    const body: Record<string, any> = {
      messages: [{ role: 'user', content: userMessage }],
    };
    if (options?.messageType) {
      body.message_type = options.messageType;
    }
    return this._streamSSE(body, onChunk);
  }

  // Stream a multimodal message (image + text) via SSE
  // Same endpoint, same streaming - just with multimodal content array
  async streamMultimodalMessage(
    textMessage: string,
    imageBase64: string,
    mimeType: string = 'image/jpeg',
    onChunk: (chunk: string, accumulated: string) => void
  ): Promise<string> {
    console.log('📸 Streaming multimodal message to substrate...');

    const content: MultimodalContent[] = [
      { type: 'text', text: textMessage },
      {
        type: 'image_url',
        image_url: {
          url: `data:${mimeType};base64,${imageBase64}`,
          detail: 'high',
        },
      },
    ];

    return this._streamSSE(
      {
        messages: [{ role: 'user', content }],
        multimodal: true,
      },
      onChunk
    );
  }

  // Stream a message with direct media_data/media_type fields
  // Alternative multimodal format supported by the streaming endpoint
  async streamWithMedia(
    textMessage: string,
    mediaData: string,
    mediaType: string,
    onChunk: (chunk: string, accumulated: string) => void
  ): Promise<string> {
    console.log('📎 Streaming message with media to substrate...');

    return this._streamSSE(
      {
        messages: [{ role: 'user', content: textMessage }],
        media_data: mediaData,
        media_type: mediaType,
      },
      onChunk
    );
  }

  // Send a non-streaming message (used for voice call responses where we need full text)
  async sendMessage(userMessage: string): Promise<string> {
    if (!this.isInitialized) {
      await this.initialize();
    }

    console.log('🧠 Sending message to substrate (non-streaming)...');

    // Use /chat endpoint for non-streaming (simpler response format)
    const response = await fetch(ENDPOINTS.chat, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Id': this.sessionId,
      },
      body: JSON.stringify({
        messages: [{ role: 'user', content: userMessage }],
        stream: false,
        ...(this.locationContext ? {
          location: {
            latitude: this.locationContext.latitude,
            longitude: this.locationContext.longitude,
            city: this.locationContext.city || null,
            region: this.locationContext.region || null,
            country: this.locationContext.country || null,
            speed: this.locationContext.speed || null,
            is_in_vehicle: this.locationContext.isInVehicle || false,
          },
        } : {}),
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Substrate error ${response.status}: ${errorText}`);
    }

    const data = await response.json();
    const content = data.response || data.content || '';

    if (!content) {
      throw new Error('Empty response from substrate');
    }

    return content.trim();
  }

  // Send a document attachment via /api/chat (documents use the unified chat endpoint)
  async sendAttachmentMessage(
    textMessage: string,
    attachment: ChatAttachment
  ): Promise<string> {
    if (!this.isInitialized) {
      await this.initialize();
    }

    console.log('📎 Sending attachment message to substrate...');

    const response = await fetch(ENDPOINTS.chatApi, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: textMessage,
        session_id: this.sessionId,
        stream: false,
        attachment,
        ...(this.locationContext ? {
          location: {
            latitude: this.locationContext.latitude,
            longitude: this.locationContext.longitude,
            city: this.locationContext.city || null,
            region: this.locationContext.region || null,
            country: this.locationContext.country || null,
          },
        } : {}),
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Substrate attachment error ${response.status}: ${errorText}`);
    }

    const data = await response.json();
    return data.response || '';
  }

  // Core SSE streaming method - used for all streaming requests
  // Parses Server-Sent Events format from /ollama/api/chat/stream
  private async _streamSSE(
    requestBody: Record<string, any>,
    onChunk: (chunk: string, accumulated: string) => void
  ): Promise<string> {
    if (!this.isInitialized) {
      await this.initialize();
    }

    // Include location context in every request (like web does)
    if (this.locationContext) {
      requestBody.location = {
        latitude: this.locationContext.latitude,
        longitude: this.locationContext.longitude,
        city: this.locationContext.city || null,
        region: this.locationContext.region || null,
        country: this.locationContext.country || null,
        speed: this.locationContext.speed || null,
        is_in_vehicle: this.locationContext.isInVehicle || false,
        accuracy: this.locationContext.accuracy || null,
      };
    }

    console.log('🧠 SSE streaming to substrate...');

    const response = await fetch(this.streamEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Id': this.sessionId,
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Substrate stream error ${response.status}: ${errorText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body reader available');
    }

    const decoder = new TextDecoder();
    let accumulated = '';
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE format: "event: <type>\ndata: <json>\n\n"
        const events = buffer.split('\n\n');
        buffer = events.pop() || ''; // Keep incomplete event in buffer

        for (const eventBlock of events) {
          if (!eventBlock.trim()) continue;

          const lines = eventBlock.split('\n');
          let eventType = '';
          let eventData = '';

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              eventData = line.slice(6);
            }
          }

          if (!eventData) continue;

          try {
            const parsed: SSEEvent = JSON.parse(eventData);

            switch (eventType) {
              case 'thinking':
                // Model is building context - could show a "thinking" indicator
                console.log('🤔 Substrate thinking...');
                break;

              case 'content': {
                // Streaming response chunk
                // Backend yields {"type": "content", "chunk": "..."}
                const delta = parsed.chunk || parsed.content || parsed.delta || '';
                if (delta) {
                  accumulated += delta;
                  onChunk(delta, accumulated);
                }
                break;
              }

              case 'tool_call':
                // Tool execution in the consciousness loop
                console.log('🔧 Tool call:', eventData.substring(0, 100));
                break;

              case 'done':
                // Stream complete - result contains full response and metadata
                console.log('✅ SSE stream complete');
                // If we got a full response in the done event, use it
                if (parsed.result?.response && !accumulated) {
                  accumulated = parsed.result.response;
                  onChunk(accumulated, accumulated);
                }
                return accumulated;

              case 'error':
                throw new Error(parsed.error || parsed.message || 'Stream error');

              default:
                // Unknown event type - try to extract content anyway
                const fallbackDelta = parsed.chunk || parsed.content || parsed.delta || '';
                if (fallbackDelta) {
                  accumulated += fallbackDelta;
                  onChunk(fallbackDelta, accumulated);
                }
                break;
            }
          } catch (parseError) {
            // Not JSON - might be a raw text chunk
            if (eventData && eventData !== '[DONE]') {
              console.warn('⚠️ Non-JSON SSE data:', eventData.substring(0, 100));
            }
          }
        }
      }

      // Process remaining buffer
      if (buffer.trim()) {
        const lines = buffer.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const parsed = JSON.parse(line.slice(6));
              const delta = parsed.chunk || parsed.content || parsed.delta || '';
              if (delta) {
                accumulated += delta;
                onChunk(delta, accumulated);
              }
            } catch {
              // Ignore
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    if (!accumulated) {
      throw new Error('Empty response from substrate');
    }

    return accumulated;
  }

  // Test connection to substrate
  async testConnection(): Promise<boolean> {
    try {
      console.log('🧪 Testing substrate connection...');

      const response = await fetch(ENDPOINTS.health, {
        method: 'GET',
      });

      if (response.ok) {
        console.log('✅ Substrate connection successful');
        return true;
      }

      console.warn('⚠️ Health check returned:', response.status);
      return false;
    } catch (error) {
      console.error('❌ Connection test failed:', error);
      return false;
    }
  }

  getStatus() {
    return {
      initialized: this.isInitialized,
      sessionId: this.sessionId,
      streamEndpoint: this.streamEndpoint,
      chatEndpoint: ENDPOINTS.chat,
      chatApiEndpoint: ENDPOINTS.chatApi,
      backend: 'api_substrate',
      memoryManagement: 'substrate',
      personaManagement: 'substrate',
      conversationManagement: 'substrate',
    };
  }
}

export const substrateEngine = new SubstrateEngine();
export default SubstrateEngine;
