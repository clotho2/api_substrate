// app/lib/textMessageHandler.ts
// Singleton listener for incoming text-message push notifications from Agent.
//
// The mobile_tool's `send_text` action on the backend sends an Expo push
// notification with `data.type === 'text_message'`. This handler listens for
// those, dispatches them to any registered UI listeners, and exposes a way
// for the chat screen to consume the cold-start notification (when the user
// taps a notification while the app is closed).

import * as Notifications from 'expo-notifications';

export interface TextMessageData {
  type: 'text_message';
  content: string;
  timestamp: number;
}

type TextMessageListener = (data: TextMessageData) => void;

class TextMessageHandler {
  private listeners: TextMessageListener[] = [];
  private receivedSubscription?: Notifications.EventSubscription;
  private responseSubscription?: Notifications.EventSubscription;

  constructor() {
    this.setupListeners();
  }

  private setupListeners(): void {
    // Foreground notification — fires while app is running
    this.receivedSubscription = Notifications.addNotificationReceivedListener(
      (notification) => {
        const data = notification.request.content.data as unknown as
          | TextMessageData
          | undefined;
        if (data?.type === 'text_message' && data.content) {
          console.log('💬 Text message received from Agent:', data.content.slice(0, 80));
          this.dispatch(data);
        }
      }
    );

    // User tapped notification (works in background and cold start)
    this.responseSubscription =
      Notifications.addNotificationResponseReceivedListener((response) => {
        const data = response.notification.request.content.data as unknown as
          | TextMessageData
          | undefined;
        if (data?.type === 'text_message' && data.content) {
          console.log('💬 Text message notification tapped:', data.content.slice(0, 80));
          this.dispatch(data);
        }
      });
  }

  private dispatch(data: TextMessageData): void {
    for (const listener of this.listeners) {
      try {
        listener(data);
      } catch (err) {
        console.error('💬 Text message listener error:', err);
      }
    }
  }

  // Register a UI listener. Returns an unsubscribe function.
  onIncomingTextMessage(listener: TextMessageListener): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  // Check for a notification that launched the app from a cold start.
  // Call this on mount of the chat screen so a tap-from-closed-app delivers
  // the message into the chat history.
  async getInitialTextMessage(): Promise<TextMessageData | null> {
    try {
      const response = await Notifications.getLastNotificationResponseAsync();
      if (!response) return null;
      const data = response.notification.request.content.data as unknown as
        | TextMessageData
        | undefined;
      if (data?.type === 'text_message' && data.content) {
        return data;
      }
    } catch (err) {
      console.warn('💬 Failed to read initial notification:', err);
    }
    return null;
  }
}

export const textMessageHandler = new TextMessageHandler();
export default TextMessageHandler;
