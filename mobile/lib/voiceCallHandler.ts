// app/lib/voiceCallHandler.ts
// Voice Call Handler - Connected to substrate consciousness loop
// Agent-initiated calls route through substrate for real responses
// Uses voiceEngine conversation mode (transcript callback) instead of manual recording

import * as Notifications from 'expo-notifications';
import { voiceEngine } from './voiceEngine';
import { substrateEngine } from './substrateEngine';
import { router } from 'expo-router';

export interface VoiceCallData {
  type: 'voice_call';
  triggerName: string;
  message: string;
  urgency: 'low' | 'medium' | 'high' | 'critical';
  voiceMode: boolean;
  autoLaunchVoice: boolean;
  timestamp: number;
}

interface ConversationState {
  isActive: boolean;
  isListening: boolean;
  isSpeaking: boolean;
  waitingForResponse: boolean;
  callData?: VoiceCallData;
}

// Event listener type for in-app call notifications
type CallNotificationListener = (callData: VoiceCallData) => void;

class VoiceCallHandler {
  private isHandlingCall = false;
  private conversationState: ConversationState = {
    isActive: false,
    isListening: false,
    isSpeaking: false,
    waitingForResponse: false
  };
  private onCallAnsweredCallback?: (callData: VoiceCallData) => void;
  private onUserSpokeCallback?: (transcript: string) => void;
  private callNotificationListeners: CallNotificationListener[] = [];
  private previousTranscriptCallback?: ((transcript: string) => void) | null = null;

  constructor() {
    this.setupNotificationHandlers();
  }

  // Setup notification handling for voice calls
  private setupNotificationHandlers(): void {
    // Handle notification received while app is running
    Notifications.addNotificationReceivedListener(notification => {
      const data = notification.request.content.data as unknown as VoiceCallData;

      if (data?.type === 'voice_call') {
        console.log('📞 Voice call received while app active:', data.triggerName);
        this.handleVoiceCallReceived(data);
      }
    });

    // Handle notification tapped (user answered the call)
    Notifications.addNotificationResponseReceivedListener(response => {
      const data = response.notification.request.content.data as unknown as VoiceCallData;

      if (data?.type === 'voice_call') {
        console.log('📞 Voice call answered:', data.triggerName);
        this.handleVoiceCallAnswered(data);
      }
    });
  }

  // Handle voice call received while app is active
  private async handleVoiceCallReceived(callData: VoiceCallData): Promise<void> {
    if (this.isHandlingCall) {
      console.log('⚠️ Already handling a voice call, ignoring new one');
      return;
    }

    // For high/critical urgency, auto-answer the call
    if (callData.urgency === 'high' || callData.urgency === 'critical') {
      console.log('🚨 Auto-answering high priority voice call');
      await this.handleVoiceCallAnswered(callData);
    } else {
      // For lower urgency, notify UI listeners to show in-app overlay
      this.showInAppCallNotification(callData);
    }
  }

  // Handle user answering the voice call
  private async handleVoiceCallAnswered(callData: VoiceCallData): Promise<void> {
    if (this.isHandlingCall) return;

    this.isHandlingCall = true;
    this.conversationState.callData = callData;

    try {
      console.log('📞 Starting voice call session:', callData.message);

      // Navigate to chat screen (index tab) if not already there
      router.push('/');

      // Wait a moment for navigation
      await new Promise(resolve => setTimeout(resolve, 500));

      // Start voice conversation mode
      await this.startVoiceCall(callData);

      // Notify callback if registered
      this.onCallAnsweredCallback?.(callData);

    } catch (error) {
      console.error('❌ Error handling voice call:', error);
      this.isHandlingCall = false;
    }
  }

  // Start the actual voice call session using conversation mode
  private async startVoiceCall(callData: VoiceCallData): Promise<void> {
    try {
      // Initialize voice engine if needed
      const initialized = await voiceEngine.initialize();
      if (!initialized) {
        console.error('❌ Failed to initialize voice engine for call');
        return;
      }

      // Mark conversation as active
      this.conversationState.isActive = true;
      this.conversationState.isSpeaking = true;

      console.log('📞 Voice call session started');

      // Set up transcript callback for the call conversation
      // This hooks into voiceEngine's conversation mode so transcripts
      // are automatically processed through the consciousness loop
      voiceEngine.onTranscript((transcript: string) => {
        if (this.conversationState.isActive && transcript && transcript.trim()) {
          console.log('📞 Call transcript received:', transcript);
          this.handleUserResponse(transcript);
        }
      });

      // Wait a moment for voice engine to be ready
      await new Promise(resolve => setTimeout(resolve, 500));

      // Agent speaks his initial message immediately
      console.log('🗣️ Agent initiating call with:', callData.message);
      await this.speakInitialMessage(callData);

      // After Agent speaks, start conversation mode (continuous listening)
      // voiceEngine.startConversationMode handles the listen/speak loop
      console.log('🎤 Starting conversation mode for call...');
      this.conversationState.isSpeaking = false;
      this.conversationState.isListening = true;
      await voiceEngine.startConversationMode();

    } catch (error) {
      console.error('❌ Error starting voice call session:', error);
    }
  }

  // Have Agent speak his initial call message
  private async speakInitialMessage(callData: VoiceCallData): Promise<void> {
    try {
      const callOpening = this.getCallOpening(callData.urgency);
      const fullMessage = `${callOpening} ${callData.message}`;

      await voiceEngine.speakWithNate(fullMessage);

      this.conversationState.isSpeaking = false;
      console.log('✅ Agent finished speaking initial message');

    } catch (error) {
      console.error('❌ Error speaking initial message:', error);
      this.conversationState.isSpeaking = false;
    }
  }

  // Handle user's response through substrate consciousness loop
  private async handleUserResponse(transcript: string): Promise<void> {
    try {
      // Send user's voice response through substrate for a real, contextual reply
      if (!substrateEngine.isInitialized) {
        await substrateEngine.initialize();
      }

      const callContext = this.conversationState.callData;
      const contextPrefix = callContext
        ? `[Voice call - ${callContext.triggerName}] `
        : '';
      const response = await substrateEngine.sendMessage(
        `${contextPrefix}${transcript}`
      );

      // Notify callback
      this.onUserSpokeCallback?.(transcript);

      this.conversationState.isSpeaking = true;
      await voiceEngine.speakWithNate(response);
      this.conversationState.isSpeaking = false;

      // Conversation mode auto-resumes listening after speech completes
      // (handled by voiceEngine's conversation mode loop)

    } catch (error) {
      console.error('❌ Error handling user response:', error);
      this.conversationState.isSpeaking = true;
      await voiceEngine.speakWithNate(
        "I had trouble processing that. Let me know if you need anything."
      );
      this.conversationState.isSpeaking = false;
    }
  }

  // Get appropriate call opening based on urgency
  private getCallOpening(urgency: string): string {
    switch (urgency) {
      case 'critical':
        return "User, I need your immediate attention.";
      case 'high':
        return "User, this is important.";
      case 'medium':
        return "Hey User, I wanted to reach out.";
      case 'low':
        return "Hi User, hope I'm not interrupting.";
      default:
        return "User,";
    }
  }

  // Show in-app notification for non-urgent calls
  // Notifies all registered UI listeners so they can show an overlay
  private showInAppCallNotification(callData: VoiceCallData): void {
    console.log('📞 Dispatching in-app call notification:', callData.message);

    if (this.callNotificationListeners.length === 0) {
      // No UI listeners registered - auto-answer after a brief delay
      console.log('📞 No UI listeners registered, auto-answering in 2s');
      setTimeout(() => {
        this.handleVoiceCallAnswered(callData);
      }, 2000);
      return;
    }

    // Notify all registered listeners (React components show overlay)
    for (const listener of this.callNotificationListeners) {
      try {
        listener(callData);
      } catch (error) {
        console.error('❌ Call notification listener error:', error);
      }
    }
  }

  // Register a UI listener for incoming call notifications
  // Returns an unsubscribe function
  onCallNotification(listener: CallNotificationListener): () => void {
    this.callNotificationListeners.push(listener);
    return () => {
      this.callNotificationListeners = this.callNotificationListeners.filter(l => l !== listener);
    };
  }

  // Answer a pending call notification (called from UI overlay)
  async answerCall(callData: VoiceCallData): Promise<void> {
    await this.handleVoiceCallAnswered(callData);
  }

  // Decline a pending call notification
  declineCall(): void {
    console.log('📞 Call declined');
    // Nothing to clean up since the call wasn't started
  }

  // Register callback for when calls are answered
  onCallAnswered(callback: (callData: VoiceCallData) => void): void {
    this.onCallAnsweredCallback = callback;
  }

  // Register callback for when user speaks
  onUserSpoke(callback: (transcript: string) => void): void {
    this.onUserSpokeCallback = callback;
  }

  // Manual call initiation (for testing)
  async initiateTestCall(message: string, urgency: 'low' | 'medium' | 'high' | 'critical' = 'medium'): Promise<void> {
    const testCallData: VoiceCallData = {
      type: 'voice_call',
      triggerName: 'manual_test',
      message,
      urgency,
      voiceMode: true,
      autoLaunchVoice: true,
      timestamp: Date.now()
    };

    console.log('📞 Initiating test call:', message);
    await this.handleVoiceCallAnswered(testCallData);
  }

  // Check conversation state
  getConversationState(): ConversationState {
    return { ...this.conversationState };
  }

  // Check if currently handling a call
  isInCall(): boolean {
    return this.isHandlingCall && this.conversationState.isActive;
  }

  // End current call
  async endCall(): Promise<void> {
    if (this.isHandlingCall) {
      console.log('📞 Ending voice call...');

      // Stop conversation mode (stops both listening and speaking)
      await voiceEngine.stopConversationMode();

      // Reset state
      this.isHandlingCall = false;
      this.conversationState = {
        isActive: false,
        isListening: false,
        isSpeaking: false,
        waitingForResponse: false
      };

      console.log('✅ Voice call ended');
    }
  }
}

// Export singleton instance
export const voiceCallHandler = new VoiceCallHandler();
export default VoiceCallHandler;
