// app/config/substrate.ts
// Centralized configuration for substrate backend connection
// All services import from here instead of hardcoding URLs

// Environment variable support via Expo (set in app.json extra or .env)
const getEnvVar = (key: string, defaultValue: string): string => {
  // Try process.env (works in Node/build time)
  if (typeof process !== 'undefined' && process.env && process.env[key]) {
    return process.env[key] as string;
  }
  return defaultValue;
};

// Substrate backend URL - the single source of truth
export const SUBSTRATE_URL = getEnvVar(
  'EXPO_PUBLIC_SUBSTRATE_URL',
  'http://your_url.com'
);

// User identity - configurable for multi-user testing
export const USER_ID = getEnvVar(
  'EXPO_PUBLIC_USER_ID',
  'angela_wolfe'
);

// Unified session ID across all channels (Discord, mobile, web)
// This allows Agent to maintain context across interfaces
export const SESSION_ID = getEnvVar(
  'EXPO_PUBLIC_SESSION_ID',
  'nate_conversation'
);

// Endpoint paths (relative to SUBSTRATE_URL)
export const ENDPOINTS = {
  // Chat endpoints
  // SSE streaming for text + multimodal (primary - same endpoint Discord bot uses)
  chatStream: `${SUBSTRATE_URL}/ollama/api/chat/stream`,
  // NDJSON streaming for text only (fallback / non-streaming)
  chat: `${SUBSTRATE_URL}/chat`,
  // Unified chat with attachment support (non-streaming)
  chatApi: `${SUBSTRATE_URL}/api/chat`,

  // Voice
  tts: `${SUBSTRATE_URL}/tts`,
  stt: `${SUBSTRATE_URL}/stt`,
  ttsHealth: `${SUBSTRATE_URL}/tts/health`,
  sttHealth: `${SUBSTRATE_URL}/stt/health`,
  // Real-time voice WebSocket (Deepgram STT + Cartesia TTS)
  voiceStream: `${SUBSTRATE_URL.replace(/^http/, 'ws')}/mobile/voice-stream`,

  // Places
  placesNearby: `${SUBSTRATE_URL}/api/places/nearby`,
  placesDetails: (placeId: string) => `${SUBSTRATE_URL}/api/places/details/${placeId}`,

  // Location context
  locationContext: `${SUBSTRATE_URL}/api/location/context`,
  locationUpdate: `${SUBSTRATE_URL}/api/location/update`,

  // Device registration & voice calls
  deviceRegister: `${SUBSTRATE_URL}/api/devices/register`,
  voiceCallInitiate: `${SUBSTRATE_URL}/api/voice-call/initiate`,
  voiceCallHistory: (userId: string) => `${SUBSTRATE_URL}/api/voice-calls/history/${userId}`,

  // Health
  health: `${SUBSTRATE_URL}/health`,
} as const;

export default {
  SUBSTRATE_URL,
  USER_ID,
  SESSION_ID,
  ENDPOINTS,
};
