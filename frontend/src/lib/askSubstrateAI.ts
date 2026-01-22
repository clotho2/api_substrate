/**
 * API client for the Substrate
 * Handles non-streaming chat requests to the backend
 */

export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  thinking?: string;
  toolCalls?: any[];
  reasoningTime?: number;
  message_type?: string;
}

export interface ChatResponse {
  role: 'assistant';
  content: string;
  thinking?: string;
  toolCalls?: any[];
  reasoningTime?: number;
}

/**
 * Send messages to the substrate and get a response
 * Uses non-streaming endpoint for reliable message persistence
 */
export async function askSubstrateAI(
  messages: Message[],
  sessionId: string = 'default',
  model?: string
): Promise<ChatResponse> {
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8284';

  try {
    const response = await fetch(`${API_URL}/ollama/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Id': sessionId,
      },
      body: JSON.stringify({
        messages,
        model,
        session_id: sessionId,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.error || `HTTP ${response.status}`);
    }

    const data = await response.json();

    return {
      role: 'assistant',
      content: data.message?.content || data.content || '',
      thinking: data.thinking,
      toolCalls: data.tool_calls,
      reasoningTime: data.reasoning_time,
    };
  } catch (error) {
    console.error('Error calling substrate AI:', error);
    throw error;
  }
}
