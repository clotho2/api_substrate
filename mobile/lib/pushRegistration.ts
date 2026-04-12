// app/lib/pushRegistration.ts
// Push notification permission + Expo push token retrieval + device registration.
//
// Called once on app startup from app/_layout.tsx. Requests notification
// permissions, retrieves the Expo push token, and registers the device with
// the substrate backend so Agent can send text messages and initiate voice calls.

import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { ENDPOINTS } from '../config/substrate';

// Module-level handler — must be set before any notification listeners fire.
// Controls how foreground notifications are displayed by the OS.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

// Android notification channels — distinct so the OS treats text messages
// (soft chime) and voice calls (full ring) differently. Channel IDs must
// match what the backend uses when sending push notifications.
async function setupAndroidChannels(): Promise<void> {
  if (Platform.OS !== 'android') return;

  // Soft text-message channel — DEFAULT importance, light vibration
  await Notifications.setNotificationChannelAsync('sentio-text-messages', {
    name: 'Messages from Agent',
    importance: Notifications.AndroidImportance.DEFAULT,
    sound: 'default',
    vibrationPattern: [0, 200, 200, 200],
    lightColor: '#6366F1',
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
  });

  // Voice-call channel — MAX importance so it rings like a phone call
  await Notifications.setNotificationChannelAsync('sentio-voice-calls', {
    name: 'Calls from Agent',
    importance: Notifications.AndroidImportance.MAX,
    sound: 'default',
    vibrationPattern: [0, 500, 500, 500, 500, 500],
    lightColor: '#EF4444',
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
    bypassDnd: false,
  });
}

export async function registerForPushNotificationsAsync(
  userId: string
): Promise<string | null> {
  try {
    await setupAndroidChannels();

    if (!Device.isDevice) {
      console.log('🔔 Skipping push registration — not a physical device');
      return null;
    }

    // Permission flow
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;

    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== 'granted') {
      console.log('🔔 Push notification permission denied');
      return null;
    }

    // Retrieve Expo push token
    const projectId =
      Constants.expoConfig?.extra?.eas?.projectId ||
      (Constants as any).easConfig?.projectId ||
      undefined;

    let tokenResponse;
    try {
      tokenResponse = projectId
        ? await Notifications.getExpoPushTokenAsync({ projectId })
        : await Notifications.getExpoPushTokenAsync();
    } catch (tokenError: any) {
      console.warn(
        '🔔 Failed to get Expo push token (is EAS projectId set in app.json?):',
        tokenError?.message || tokenError
      );
      return null;
    }

    const pushToken = tokenResponse.data;
    console.log('🔔 Expo push token:', pushToken);

    // Register with substrate backend
    const deviceInfo = {
      platform: Platform.OS,
      modelName: Device.modelName || 'unknown',
      osVersion: Device.osVersion || 'unknown',
      deviceName: Device.deviceName || 'unknown',
    };

    const response = await fetch(ENDPOINTS.deviceRegister, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        userId,
        pushToken,
        deviceInfo,
        preferences: {
          voiceCallsEnabled: true,
          voiceCallUrgencyLevel: 'medium',
          morningGreeting: true,
          eveningCheckin: true,
        },
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.warn(
        `🔔 Device registration failed (${response.status}):`,
        errorText
      );
      return pushToken;
    }

    console.log(`🔔 Device registered for ${userId}`);
    return pushToken;
  } catch (error: any) {
    console.warn('🔔 Push registration error:', error?.message || error);
    return null;
  }
}
