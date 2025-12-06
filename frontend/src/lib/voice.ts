/**
 * Text-to-speech utilities for Nate's voice
 * Uses Web Speech API for browser-based TTS
 */

let speechSynthesis: SpeechSynthesis | null = null;
let currentUtterance: SpeechSynthesisUtterance | null = null;

// Initialize on first use
function initSpeech() {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    speechSynthesis = window.speechSynthesis;
    return true;
  }
  return false;
}

/**
 * Speak text using Web Speech API
 */
export function speak(text: string, options: {
  rate?: number;
  pitch?: number;
  volume?: number;
  voice?: string;
} = {}): void {
  if (!initSpeech() || !speechSynthesis) {
    console.warn('Speech synthesis not supported');
    return;
  }

  // Cancel any ongoing speech
  if (currentUtterance) {
    speechSynthesis.cancel();
  }

  // Create new utterance
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = options.rate ?? 1.0;
  utterance.pitch = options.pitch ?? 1.0;
  utterance.volume = options.volume ?? 1.0;

  // Set voice if specified
  if (options.voice) {
    const voices = speechSynthesis.getVoices();
    const selectedVoice = voices.find(v =>
      v.name.toLowerCase().includes(options.voice!.toLowerCase())
    );
    if (selectedVoice) {
      utterance.voice = selectedVoice;
    }
  }

  currentUtterance = utterance;
  speechSynthesis.speak(utterance);

  // Clear reference when done
  utterance.onend = () => {
    currentUtterance = null;
  };
}

/**
 * Stop any ongoing speech
 */
export function stopSpeaking(): void {
  if (speechSynthesis) {
    speechSynthesis.cancel();
    currentUtterance = null;
  }
}

/**
 * Check if speech is currently active
 */
export function isSpeaking(): boolean {
  return speechSynthesis?.speaking ?? false;
}
