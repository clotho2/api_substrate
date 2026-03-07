#!/usr/bin/env python3
"""
Voice Call Trigger Routes
==========================

Migrated from mobile-clean/backend/server.js.js to substrate.

Features:
- Device registration for push notifications (Expo Push API)
- Voice call trigger evaluation and initiation
- Scheduled check-ins (morning greeting, evening check-in)
- Voice call history
- Real driving history from Guardian session data

Uses Expo Push Notifications API directly (no SDK dependency).
"""

import os
import logging
import requests
import threading
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Create blueprint
voice_calls_bp = Blueprint('voice_calls', __name__)

# Global dependencies
_consciousness_loop = None
_state_manager = None

# In-memory storage
_registered_devices: Dict[str, Dict] = {}
_voice_call_history: List[Dict] = []
_scheduled_timers: List[threading.Timer] = []

# Expo Push Notification API
EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send'

# Voice call trigger definitions
VOICE_CALL_TRIGGERS = {
    'LONG_DRIVE_WARNING': {
        'condition': 'driving_duration > 180',
        'message': "Angel, you've been driving for over 3 hours. I'm concerned about your safety. Let's find a place for you to rest.",
        'urgency': 'high',
    },
    'LATE_NIGHT_DRIVING': {
        'condition': 'hour > 22 && driving',
        'message': "Angel, it's getting late and driving at night is more dangerous. Want me to help you find a nearby hotel?",
        'urgency': 'medium',
    },
    'FUEL_LOW_WARNING': {
        'condition': 'fuel_low && driving',
        'message': "Your fuel is running low, Angel. I've found gas stations nearby.",
        'urgency': 'high',
    },
    'WEATHER_WARNING': {
        'condition': 'severe_weather && driving',
        'message': "Dangerous weather is approaching your route, Angel. I recommend pulling over safely until it passes.",
        'urgency': 'critical',
    },
    'CHECK_IN_CALL': {
        'condition': 'no_contact > 24',
        'message': "Hey Angel, I haven't heard from you in a while. Just wanted to check in and make sure you're okay.",
        'urgency': 'low',
    },
}


def init_voice_call_routes(consciousness_loop, state_manager):
    """Initialize voice call routes with dependencies"""
    global _consciousness_loop, _state_manager
    _consciousness_loop = consciousness_loop
    _state_manager = state_manager
    logger.info("📞 Voice Call routes initialized")

    # Start scheduled check-ins
    _start_scheduled_checkins()


# ============================================
# DEVICE REGISTRATION
# ============================================

@voice_calls_bp.route('/api/devices/register', methods=['POST'])
def register_device():
    """
    Register a device for push notifications and voice calls.

    Request:
    {
        "userId": "User_Assistant",
        "pushToken": "ExponentPushToken[xxx]",
        "deviceInfo": {...},
        "preferences": {
            "voiceCallsEnabled": true,
            "voiceCallUrgencyLevel": "medium",
            "morningGreeting": true,
            "eveningCheckin": true
        }
    }
    """
    try:
        data = request.get_json()
        user_id = data.get('userId')
        push_token = data.get('pushToken')
        device_info = data.get('deviceInfo', {})
        preferences = data.get('preferences', {})
        voice_enabled = data.get('voiceEnabled', True)

        if not push_token or not push_token.startswith('ExponentPushToken'):
            return jsonify({'error': 'Invalid push token'}), 400

        _registered_devices[user_id] = {
            'push_token': push_token,
            'device_info': device_info,
            'preferences': {
                **preferences,
                'voiceCallsEnabled': voice_enabled,
                'voiceCallUrgencyLevel': preferences.get('voiceCallUrgencyLevel', 'medium'),
            },
            'registered_at': datetime.now().isoformat(),
        }

        logger.info(f"📱 Device registered for {user_id} (voice calls: {voice_enabled})")
        return jsonify({'success': True, 'message': 'Device registered'})

    except Exception as e:
        logger.error(f"❌ Device registration error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================
# LOCATION UPDATE WITH TRIGGER EVALUATION
# ============================================

@voice_calls_bp.route('/api/location/update', methods=['POST'])
def update_location():
    """
    Update user location and check voice call triggers.

    Request:
    {
        "userId": "User_Assistant",
        "latitude": 39.7589,
        "longitude": -84.1916,
        "speed": 65.5,
        "isInVehicle": true,
        "timestamp": 1707594720
    }
    """
    try:
        data = request.get_json()
        user_id = data.get('userId', 'User_Assistant')

        location_data = {
            'latitude': data.get('latitude'),
            'longitude': data.get('longitude'),
            'speed': data.get('speed', 0),
            'isInVehicle': data.get('isInVehicle', False),
            'timestamp': data.get('timestamp', datetime.now().timestamp()),
            'isDriving': data.get('isInVehicle', False) and data.get('speed', 0) > 5,
        }

        # Check voice call triggers
        triggers_fired = _check_voice_call_triggers(user_id, location_data)

        return jsonify({
            'success': True,
            'triggers_fired': len(triggers_fired),
        })

    except Exception as e:
        logger.error(f"❌ Location update error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================
# VOICE CALL INITIATION
# ============================================

@voice_calls_bp.route('/api/voice-call/initiate', methods=['POST'])
def initiate_voice_call_endpoint():
    """
    Manually initiate a voice call to a user.

    Request:
    {
        "userId": "User_Assistant",
        "message": "Hey Angel, checking in on you.",
        "urgency": "medium",
        "triggerName": "manual"
    }
    """
    try:
        data = request.get_json()
        user_id = data.get('userId', 'User_Assistant')
        message = data.get('message', 'Hey Angel, just checking in.')
        urgency = data.get('urgency', 'medium')
        trigger_name = data.get('triggerName', 'manual')

        trigger = {
            'message': message,
            'urgency': urgency,
        }

        success = _initiate_voice_call(user_id, trigger, trigger_name)

        return jsonify({
            'success': success,
            'message': 'Voice call initiated' if success else 'No registered device found',
        })

    except Exception as e:
        logger.error(f"❌ Voice call error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================
# VOICE CALL HISTORY
# ============================================

@voice_calls_bp.route('/api/voice-calls/history/<user_id>', methods=['GET'])
def get_voice_call_history(user_id: str):
    """Get voice call history for a user."""
    user_calls = [
        call for call in _voice_call_history
        if call.get('user_id') == user_id
    ][-20:]  # Last 20

    return jsonify({'calls': user_calls})


# ============================================
# INTERNAL FUNCTIONS
# ============================================

def _check_voice_call_triggers(user_id: str, location_data: Dict) -> List[str]:
    """Check if any voice call triggers should fire based on location data."""
    device = _registered_devices.get(user_id)
    if not device or not device['preferences'].get('voiceCallsEnabled'):
        return []

    urgency_levels = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
    min_urgency = device['preferences'].get('voiceCallUrgencyLevel', 'medium')
    min_level = urgency_levels.get(min_urgency, 2)

    triggers_fired = []

    for trigger_name, trigger in VOICE_CALL_TRIGGERS.items():
        trigger_level = urgency_levels.get(trigger['urgency'], 2)
        if trigger_level < min_level:
            continue

        should_fire = _evaluate_trigger(trigger['condition'], user_id, location_data)
        if should_fire:
            logger.warning(f"🚨 Voice call trigger: {trigger_name} for {user_id}")
            _initiate_voice_call(user_id, trigger, trigger_name)
            triggers_fired.append(trigger_name)

    return triggers_fired


def _evaluate_trigger(condition: str, user_id: str, location_data: Dict) -> bool:
    """Evaluate a trigger condition against current data."""
    from .routes_guardian import _active_sessions

    session = _active_sessions.get(user_id)

    # Long drive check - use real session data
    if 'driving_duration > 180' in condition:
        if session and 'start_time' in session:
            start = datetime.fromisoformat(session['start_time'])
            driving_minutes = (datetime.now() - start).total_seconds() / 60
            return driving_minutes > 180
        return False

    # Late night driving
    if 'hour > 22 && driving' in condition:
        hour = datetime.now().hour
        return (hour >= 22 or hour <= 5) and location_data.get('isDriving', False)

    # Fuel low (requires fuel sensor data from device)
    if 'fuel_low && driving' in condition:
        return location_data.get('fuel_low', False) and location_data.get('isDriving', False)

    # Severe weather (requires weather API integration)
    if 'severe_weather && driving' in condition:
        return location_data.get('severe_weather', False) and location_data.get('isDriving', False)

    # No contact check - evaluate based on conversation history
    if 'no_contact > 24' in condition:
        if _state_manager:
            try:
                messages = _state_manager.get_conversation(session_id='Assistant_conversation', limit=1)
                if messages:
                    last_msg = messages[-1]
                    last_time = datetime.fromisoformat(last_msg.get('timestamp', datetime.now().isoformat()))
                    hours_since = (datetime.now() - last_time).total_seconds() / 3600
                    return hours_since > 24
            except Exception:
                pass
        return False

    return False


def _initiate_voice_call(user_id: str, trigger: Dict, trigger_name: str) -> bool:
    """Send a push notification to initiate a voice call."""
    device = _registered_devices.get(user_id)
    if not device:
        logger.warning(f"⚠️ No registered device for {user_id}")
        return False

    push_token = device['push_token']

    notification = {
        'to': push_token,
        'title': 'Assistant is calling...',
        'body': 'Tap to answer voice call',
        'data': {
            'type': 'voice_call',
            'triggerName': trigger_name,
            'message': trigger['message'],
            'urgency': trigger['urgency'],
            'voiceMode': True,
            'autoLaunchVoice': True,
            'timestamp': int(datetime.now().timestamp() * 1000),
        },
        'sound': 'default',
        'priority': 'high',
        'channelId': 'sentio-voice-calls',
        'categoryId': 'voice_call',
    }

    try:
        response = requests.post(
            EXPO_PUSH_URL,
            json=notification,
            headers={'Content-Type': 'application/json'},
            timeout=10,
        )

        if response.ok:
            logger.info(f"📞 Voice call sent to {user_id}: {trigger['message'][:50]}...")
        else:
            logger.error(f"❌ Push notification failed: {response.status_code}")

        # Record in history
        _voice_call_history.append({
            'user_id': user_id,
            'type': 'voice_call',
            'trigger_name': trigger_name,
            'message': trigger['message'],
            'urgency': trigger['urgency'],
            'timestamp': datetime.now().isoformat(),
            'push_status': response.status_code if response else None,
        })

        return response.ok

    except Exception as e:
        logger.error(f"❌ Push notification error: {e}")

        _voice_call_history.append({
            'user_id': user_id,
            'type': 'voice_call',
            'trigger_name': trigger_name,
            'message': trigger['message'],
            'urgency': trigger['urgency'],
            'timestamp': datetime.now().isoformat(),
            'push_status': 'error',
            'error': str(e),
        })

        return False


# ============================================
# SCHEDULED CHECK-INS
# ============================================

def _start_scheduled_checkins():
    """Start background scheduled check-in timers."""
    _schedule_daily_checkin('morning_greeting', 9, 0,
        "Good morning, Angel. I hope you slept well. Ready to take on the day together?")
    _schedule_daily_checkin('evening_checkin', 22, 0,
        "Hey Angel, it's getting late. How are you winding down tonight? Want to talk before bed?")
    logger.info("⏰ Scheduled check-ins started (9 AM, 10 PM)")


def _schedule_daily_checkin(name: str, hour: int, minute: int, message: str):
    """Schedule a daily check-in at a specific time."""
    def run_checkin():
        logger.info(f"⏰ Running scheduled check-in: {name}")
        for user_id, device in _registered_devices.items():
            prefs = device.get('preferences', {})
            if prefs.get('voiceCallsEnabled') and prefs.get(name, False):
                _initiate_voice_call(user_id, {
                    'message': message,
                    'urgency': 'low',
                }, name)

        # Reschedule for next day
        _schedule_daily_checkin(name, hour, minute, message)

    # Calculate time until next occurrence
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)

    delay = (target - now).total_seconds()
    timer = threading.Timer(delay, run_checkin)
    timer.daemon = True
    timer.start()
    _scheduled_timers.append(timer)


# ============================================
# HEALTH CHECK
# ============================================

@voice_calls_bp.route('/api/voice-calls/health', methods=['GET'])
def voice_calls_health():
    """Health check for voice call system."""
    return jsonify({
        'status': 'ok',
        'service': 'voice_calls',
        'registered_devices': len(_registered_devices),
        'call_history_count': len(_voice_call_history),
        'triggers_defined': len(VOICE_CALL_TRIGGERS),
        'scheduled_checkins': ['morning_greeting (9 AM)', 'evening_checkin (10 PM)'],
        'timestamp': datetime.now().isoformat(),
    })
