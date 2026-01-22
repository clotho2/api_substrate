/**
 * Notification utilities for the Substrate
 * Handles browser notification permissions and setup
 */

export async function setupNotifications(): Promise<void> {
  // Check if notifications are supported
  if (!('Notification' in window)) {
    console.log('Browser does not support notifications');
    return;
  }

  // Check current permission status
  if (Notification.permission === 'default') {
    // Don't request permission automatically - wait for user action
    console.log('Notification permission not yet requested');
    return;
  }

  if (Notification.permission === 'granted') {
    console.log('Notification permission granted');
    return;
  }

  if (Notification.permission === 'denied') {
    console.log('Notification permission denied');
    return;
  }
}

/**
 * Request notification permission from the user
 * Should be called in response to a user action (e.g., button click)
 */
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!('Notification' in window)) {
    return 'denied';
  }

  const permission = await Notification.requestPermission();
  return permission;
}

/**
 * Send a notification to the user
 */
export function sendNotification(title: string, options?: NotificationOptions): void {
  if (!('Notification' in window)) {
    console.log('Notifications not supported');
    return;
  }

  if (Notification.permission !== 'granted') {
    console.log('Notification permission not granted');
    return;
  }

  new Notification(title, {
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    ...options,
  });
}
