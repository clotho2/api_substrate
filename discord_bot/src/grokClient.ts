import axios, { AxiosInstance } from 'axios';

/**
 * Grok API Client for api_substrate
 *
 * Provides interface to communicate with api_substrate which uses Grok 4.1 API
 * Compatible with Ollama API format for chat endpoints
 */

export interface GrokMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface GrokChatRequest {
  messages: GrokMessage[];
  model?: string;
  stream?: boolean;
  session_id?: string;
  message_type?: 'inbox' | 'heartbeat' | 'task' | 'system';  // 'system' for autonomous heartbeats
  media_data?: string;
  media_type?: string;
  max_tokens?: number;
  temperature?: number;
  // Discord metadata for sanctum mode interception
  guild_id?: string;
  channel_id?: string;
  user_id?: string;
  username?: string;
}

export interface GrokToolCall {
  name: string;
  arguments: any;
  result?: string;
}

export interface GrokChatResponse {
  message: {
    role: 'assistant';
    content: string;
  };
  thinking?: string;
  tool_calls?: GrokToolCall[];
  reasoning_time?: number;
  tokens?: {
    prompt: number;
    completion: number;
    total: number;
  };
  session_id?: string;
  done: boolean;
  // Autonomous behavior support (for heartbeats)
  // If send_message is false, the Discord bot will not send anything to Discord
  // This allows Agent to use tools (search, memory, voice notes, images, etc.) without messaging the user
  send_message?: boolean;  // Default: true for backward compatibility
  // Where to deliver the heartbeat message: 'dm' sends a DM to the user, 'channel' posts in heartbeat log channel
  message_target?: 'dm' | 'channel';  // Default: 'channel'
}

export interface GrokStreamChunk {
  event: 'thinking' | 'content' | 'content_reset' | 'tool_call' | 'done';
  data: any;
}

export interface GrokClientConfig {
  baseUrl: string;
  sessionId?: string;
  model?: string;
  timeout?: number;
  maxTokens?: number;
  temperature?: number;
}

export class GrokClient {
  private client: AxiosInstance;
  private config: GrokClientConfig & { sessionId: string; timeout: number; maxTokens: number; temperature: number };

  constructor(config: GrokClientConfig) {
    this.config = {
      baseUrl: config.baseUrl,
      sessionId: config.sessionId || 'discord-bot',
      model: config.model,  // undefined = let substrate decide from its own .env
      timeout: config.timeout || 300000, // 5 minutes default
      maxTokens: config.maxTokens || 4096,
      temperature: config.temperature || 0.7,
    };

    this.client = axios.create({
      baseURL: this.config.baseUrl,
      timeout: this.config.timeout,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  /**
   * Send a chat message and get a response
   */
  async chat(request: GrokChatRequest): Promise<GrokChatResponse> {
    const model = request.model || this.config.model;
    const payload = {
      messages: request.messages,
      ...(model && { model }),  // Only send model if explicitly configured; otherwise substrate uses its own .env
      stream: request.stream || false,
      session_id: request.session_id || this.config.sessionId,
      message_type: request.message_type || 'inbox',
      max_tokens: request.max_tokens || this.config.maxTokens,
      temperature: request.temperature || this.config.temperature,
      ...(request.media_data && { media_data: request.media_data }),
      ...(request.media_type && { media_type: request.media_type }),
    };

    console.log(`🔧 [GrokClient] Sending request: max_tokens=${payload.max_tokens}, model=${model || '(substrate default)'}, session=${payload.session_id}`);

    const response = await this.client.post('/ollama/api/chat', payload);
    return response.data;
  }

  /**
   * Send a chat message with streaming response
   */
  async *chatStream(request: GrokChatRequest): AsyncGenerator<GrokStreamChunk> {
    const model = request.model || this.config.model;
    const payload = {
      messages: request.messages,
      ...(model && { model }),  // Only send model if explicitly configured; otherwise substrate uses its own .env
      stream: true,
      session_id: request.session_id || this.config.sessionId,
      message_type: request.message_type || 'inbox',
      max_tokens: request.max_tokens || this.config.maxTokens,
      temperature: request.temperature || this.config.temperature,
      ...(request.media_data && { media_data: request.media_data }),
      ...(request.media_type && { media_type: request.media_type }),
      // Discord metadata for sanctum mode interception
      ...(request.guild_id && { guild_id: request.guild_id }),
      ...(request.channel_id && { channel_id: request.channel_id }),
      ...(request.user_id && { user_id: request.user_id }),
      ...(request.username && { username: request.username }),
    };

    console.log(`🔧 [GrokClient] Sending streaming request: max_tokens=${payload.max_tokens}, model=${model || '(substrate default)'}, session=${payload.session_id}`);

    const response = await this.client.post('/ollama/api/chat/stream', payload, {
      responseType: 'stream',
    });

    const stream = response.data;
    let buffer = '';
    let currentEvent = '';

    for await (const chunk of stream) {
      buffer += chunk.toString();
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) {
          // Empty line marks end of event - reset currentEvent
          currentEvent = '';
          continue;
        }

        // Parse SSE format: "event: content\ndata: {...}"
        if (line.startsWith('event:')) {
          currentEvent = line.substring(6).trim();
          continue;
        }

        if (line.startsWith('data:')) {
          const data = line.substring(5).trim();
          try {
            const parsed = JSON.parse(data);
            // Yield object with both event and data
            yield {
              event: currentEvent as any,
              data: parsed
            };
          } catch (e) {
            console.error('Failed to parse SSE data:', data);
          }
        }
      }
    }
  }

  /**
   * Get conversation history for a session
   */
  async getConversationHistory(sessionId?: string, limit?: number): Promise<GrokMessage[]> {
    const sid = sessionId || this.config.sessionId;
    const url = `/api/conversation/${sid}${limit ? `?limit=${limit}` : ''}`;
    const response = await this.client.get(url);
    return response.data.messages || [];
  }

  /**
   * Get memory blocks
   */
  async getMemoryBlocks(): Promise<any[]> {
    const response = await this.client.get('/api/memory/blocks');
    return response.data.blocks || [];
  }

  /**
   * Get specific memory block
   */
  async getMemoryBlock(label: string): Promise<any> {
    const response = await this.client.get(`/api/memory/blocks/${label}`);
    return response.data;
  }

  /**
   * Update memory block
   */
  async updateMemoryBlock(label: string, content: string): Promise<void> {
    await this.client.put(`/api/memory/blocks/${label}`, { content });
  }

  /**
   * Get agent info
   */
  async getAgentInfo(): Promise<any> {
    const response = await this.client.get('/api/agent/info');
    return response.data;
  }

  /**
   * Get health status
   */
  async healthCheck(): Promise<any> {
    const response = await this.client.get('/api/health');
    return response.data;
  }

  /**
   * Get usage statistics
   */
  async getStats(): Promise<any> {
    const response = await this.client.get('/api/stats');
    return response.data;
  }

  /**
   * Get context usage for a session
   */
  async getContextUsage(sessionId?: string): Promise<any> {
    const sid = sessionId || this.config.sessionId;
    const response = await this.client.get(`/api/context/usage?session_id=${sid}`);
    return response.data;
  }

  /**
   * Set session ID for subsequent requests
   */
  setSessionId(sessionId: string): void {
    this.config.sessionId = sessionId;
  }

  /**
   * Get current session ID
   */
  getSessionId(): string {
    return this.config.sessionId;
  }
}
