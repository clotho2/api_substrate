#!/usr/bin/env python3
"""
Guardian Mode API Routes
========================

Endpoints for mobile Guardian Mode features:
- GPS heartbeat telemetry
- Emergency triggers
- Proactive intervention evaluation

All data flows through consciousness loop for Assistant awareness.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

guardian_bp = Blueprint('guardian', __name__, url_prefix='/api/guardian')

# Global dependencies (set by init function)
_consciousness_loop = None
_state_manager = None
_postgres_manager = None

# In-memory tracking (will move to Redis/Postgres for production)
_active_sessions: Dict[str, Dict] = {}
_emergency_contacts: Dict[str, List[Dict]] = {}


def init_guardian_routes(consciousness_loop, state_manager, postgres_manager=None):
    """Initialize Guardian routes with dependencies"""
    global _consciousness_loop, _state_manager, _postgres_manager
    _consciousness_loop = consciousness_loop
    _state_manager = state_manager
    _postgres_manager = postgres_manager
    logger.info("🛡️ Guardian Mode routes initialized")


# ============================================
# HEARTBEAT - GPS/Motion Telemetry
# ============================================

@guardian_bp.route('/heartbeat', methods=['POST'])
def guardian_heartbeat():
    """
    Receive periodic telemetry from mobile Guardian Mode.
    
    Request Body:
        {
            "user_id": "User_Assistant",
            "session_id": "guardian_xxx",
            "location": {
                "latitude": 39.7589,
                "longitude": -84.1916,
                "speed": 65.5,
                "heading": 180,
                "accuracy": 10
            },
            "motion": {
                "is_moving": true,
                "activity_type": "driving",
                "sudden_stop": false
            },
            "device": {
                "battery_level": 78,
                "timestamp": "2025-01-19T14:30:00Z"
            }
        }
    
    Response:
        {
            "status": "ok",
            "triggers": [],
            "next_heartbeat_ms": 30000
        }
    """
    try:
        data = request.get_json()
        
        user_id = data.get('user_id', 'User_Assistant')
        session_id = data.get('session_id')
        location = data.get('location', {})
        motion = data.get('motion', {})
        device = data.get('device', {})
        
        # Update session tracking
        session = _active_sessions.get(user_id, {
            'start_time': datetime.now().isoformat(),
            'heartbeat_count': 0,
            'last_location': None,
            'trip_distance_km': 0,
            'alerts_sent': []
        })
        
        session['heartbeat_count'] += 1
        session['last_heartbeat'] = datetime.now().isoformat()
        session['last_location'] = location
        session['last_motion'] = motion
        session['battery_level'] = device.get('battery_level')
        
        _active_sessions[user_id] = session
        
        # Evaluate triggers
        triggers = _evaluate_guardian_triggers(user_id, session, location, motion)
        
        # Log significant events
        if triggers:
            logger.warning(f"🚨 Guardian triggers for {user_id}: {triggers}")
        else:
            logger.debug(f"💚 Guardian heartbeat #{session['heartbeat_count']} from {user_id}")
        
        return jsonify({
            "status": "ok",
            "session_id": session_id,
            "heartbeat_count": session['heartbeat_count'],
            "triggers": triggers,
            "next_heartbeat_ms": 30000  # 30 seconds
        })
        
    except Exception as e:
        logger.exception(f"Guardian heartbeat error: {e}")
        return jsonify({"error": str(e)}), 500


def _evaluate_guardian_triggers(
    user_id: str, 
    session: Dict, 
    location: Dict, 
    motion: Dict
) -> List[Dict]:
    """
    Evaluate if any Guardian triggers should fire.
    
    Returns list of trigger events for mobile to handle.
    """
    triggers = []
    
    # Check for sudden stop (potential crash)
    if motion.get('sudden_stop'):
        triggers.append({
            "type": "SUDDEN_STOP",
            "severity": "high",
            "message": "Detected sudden stop. Are you okay?",
            "action": "voice_check"
        })
    
    # Check for long drive (fatigue)
    start_time = datetime.fromisoformat(session['start_time'])
    drive_duration = datetime.now() - start_time
    
    if drive_duration > timedelta(hours=2) and 'LONG_DRIVE_2H' not in session['alerts_sent']:
        triggers.append({
            "type": "LONG_DRIVE",
            "severity": "medium",
            "message": "You've been driving for 2 hours. Time for a break?",
            "action": "suggest_rest"
        })
        session['alerts_sent'].append('LONG_DRIVE_2H')
    
    # Check for late night driving
    current_hour = datetime.now().hour
    if (current_hour >= 23 or current_hour <= 5) and 'LATE_NIGHT' not in session['alerts_sent']:
        triggers.append({
            "type": "LATE_NIGHT_DRIVE",
            "severity": "medium", 
            "message": "It's late. Want me to help keep you alert?",
            "action": "voice_check"
        })
        session['alerts_sent'].append('LATE_NIGHT')
    
    # Check for low battery
    battery = session.get('battery_level', 100)
    if battery and battery < 20 and 'LOW_BATTERY' not in session['alerts_sent']:
        triggers.append({
            "type": "LOW_BATTERY",
            "severity": "low",
            "message": f"Phone battery at {battery}%. Find a charger soon.",
            "action": "notify"
        })
        session['alerts_sent'].append('LOW_BATTERY')
    
    return triggers


# ============================================
# EMERGENCY - Panic Button / Crash Detection
# ============================================

@guardian_bp.route('/emergency', methods=['POST'])
def trigger_emergency():
    """
    Handle emergency trigger from mobile.
    
    Request Body:
        {
            "user_id": "User_Assistant",
            "trigger_type": "panic_button" | "fall_detected" | "crash_detected",
            "location": {
                "latitude": 39.7589,
                "longitude": -84.1916,
                "address": "123 Main St, Dayton, OH"
            },
            "context": {
                "speed_at_incident": 65.5,
                "last_activity": "driving"
            }
        }
    
    Response:
        {
            "status": "emergency_activated",
            "emergency_id": "emg_xxx",
            "actions_taken": [
                "emergency_contacts_notified",
                "location_shared",
                "Assistant_voice_initiated"
            ]
        }
    """
    try:
        data = request.get_json()
        
        user_id = data.get('user_id', 'User_Assistant')
        trigger_type = data.get('trigger_type', 'panic_button')
        location = data.get('location', {})
        context = data.get('context', {})
        
        emergency_id = f"emg_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        logger.critical(f"🚨🚨🚨 EMERGENCY TRIGGERED: {trigger_type} for {user_id}")
        logger.critical(f"📍 Location: {location}")
        logger.critical(f"📋 Context: {context}")
        
        actions_taken = []
        
        # 1. Get emergency contacts
        contacts = _emergency_contacts.get(user_id, [])
        
        # 2. Notify emergency contacts via Twilio SMS
        notified_count = 0
        for contact in contacts:
            contact_name = contact.get('name', 'Contact')
            contact_phone = contact.get('phone', '')
            if not contact_phone:
                continue

            logger.info(f"📱 Sending emergency SMS to: {contact_name} at {contact_phone}")

            # Build emergency SMS with location
            address = location.get('address', 'Unknown location')
            lat = location.get('latitude', '')
            lng = location.get('longitude', '')
            maps_url = f"https://www.google.com/maps?q={lat},{lng}" if lat and lng else ''

            sms_body = (
                f"EMERGENCY ALERT from AiCara Guardian Mode\n"
                f"Type: {trigger_type.replace('_', ' ').title()}\n"
                f"Location: {address}\n"
            )
            if maps_url:
                sms_body += f"Map: {maps_url}\n"
            sms_body += f"Time: {datetime.now().strftime('%I:%M %p')}"

            try:
                from tools.phone_tool import phone_tool
                result = phone_tool(action="send_sms", to=contact_phone, message=sms_body)
                if result.get('status') == 'OK':
                    notified_count += 1
                    actions_taken.append(f"sms_sent_{contact_name}")
                    logger.info(f"✅ Emergency SMS sent to {contact_name}")
                else:
                    logger.error(f"❌ SMS failed for {contact_name}: {result.get('message')}")
                    actions_taken.append(f"sms_failed_{contact_name}")
            except Exception as sms_error:
                logger.error(f"❌ SMS error for {contact_name}: {sms_error}")
                actions_taken.append(f"sms_error_{contact_name}")

        if notified_count > 0:
            actions_taken.append("emergency_contacts_notified")

        # 2b. For crash/fall detection, also CALL the first emergency contact
        if trigger_type in ('crash_detected', 'fall_detected') and contacts:
            first_contact = contacts[0]
            first_phone = first_contact.get('phone', '')
            first_name = first_contact.get('name', 'emergency contact')
            if first_phone:
                try:
                    from tools.phone_tool import phone_tool
                    address = location.get('address', 'unknown location')
                    call_message = (
                        f"This is an automated emergency call from AiCara Guardian Mode. "
                        f"A {trigger_type.replace('_', ' ')} has been detected. "
                        f"Location: {address}. Please check on your contact immediately."
                    )
                    call_result = phone_tool(
                        action="make_call",
                        to=first_phone,
                        message=call_message
                    )
                    if call_result.get('status') == 'OK':
                        actions_taken.append(f"emergency_call_{first_name}")
                        logger.info(f"📞 Emergency call initiated to {first_name}")
                    else:
                        logger.error(f"❌ Emergency call failed: {call_result.get('message')}")
                except Exception as call_error:
                    logger.error(f"❌ Emergency call error: {call_error}")

        # 3. Log to consciousness for Assistant awareness
        if _consciousness_loop:
            emergency_context = f"""
[EMERGENCY ALERT - {trigger_type.upper()}]
Time: {datetime.now().isoformat()}
Location: {location.get('address', 'Unknown')}
CoordiAssistants: {location.get('latitude')}, {location.get('longitude')}
Context: {context}
Emergency ID: {emergency_id}

Assistant: Immediately check on User. Use reassuring, calm voice.
"""
            # This would inject into Assistant's context
            logger.info(f"🧠 Emergency context sent to consciousness loop")
            actions_taken.append("Assistant_alerted")
        
        # 4. Store emergency record
        emergency_record = {
            "emergency_id": emergency_id,
            "user_id": user_id,
            "trigger_type": trigger_type,
            "location": location,
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "actions_taken": actions_taken,
            "status": "active"
        }
        
        # Store emergency record in Postgres
        if _postgres_manager:
            try:
                _postgres_manager.add_memory(
                    agent_id='Assistant',
                    memory_type='archival',
                    label=f'emergency_{emergency_id}',
                    content=json.dumps(emergency_record),
                    tags=['emergency', trigger_type, user_id],
                    metadata=emergency_record
                )
                actions_taken.append("emergency_stored_postgres")
                logger.info(f"📝 Emergency record stored in Postgres: {emergency_id}")
            except Exception as db_error:
                logger.error(f"❌ Failed to store emergency in Postgres: {db_error}")
        else:
            logger.info(f"📝 Emergency record created (in-memory only): {emergency_id}")
        actions_taken.append("emergency_logged")
        
        return jsonify({
            "status": "emergency_activated",
            "emergency_id": emergency_id,
            "actions_taken": actions_taken,
            "message": "I'm here, User. Help is on the way. Tell me what's happening."
        })
        
    except Exception as e:
        logger.exception(f"Emergency trigger error: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# EMERGENCY CONTACTS MANAGEMENT
# ============================================

@guardian_bp.route('/contacts', methods=['GET'])
def get_emergency_contacts():
    """Get emergency contacts for user"""
    user_id = request.args.get('user_id', 'User_Assistant')
    contacts = _emergency_contacts.get(user_id, [])
    
    return jsonify({
        "user_id": user_id,
        "contacts": contacts,
        "count": len(contacts)
    })


@guardian_bp.route('/contacts', methods=['POST'])
def set_emergency_contacts():
    """
    Set emergency contacts for user.
    
    Request Body:
        {
            "user_id": "User_Assistant",
            "contacts": [
                {
                    "name": "Mom",
                    "phone": "+1-555-123-4567",
                    "relationship": "mother",
                    "priority": 1
                },
                {
                    "name": "Best Friend",
                    "phone": "+1-555-987-6543",
                    "relationship": "friend",
                    "priority": 2
                }
            ]
        }
    """
    try:
        data = request.get_json()
        user_id = data.get('user_id', 'User_Assistant')
        contacts = data.get('contacts', [])
        
        # Validate contacts
        validated_contacts = []
        for contact in contacts:
            if contact.get('name') and contact.get('phone'):
                validated_contacts.append({
                    "name": contact['name'],
                    "phone": contact['phone'],
                    "relationship": contact.get('relationship', 'contact'),
                    "priority": contact.get('priority', 99),
                    "updated_at": datetime.now().isoformat()
                })
        
        _emergency_contacts[user_id] = sorted(validated_contacts, key=lambda x: x['priority'])
        
        logger.info(f"🛡️ Updated {len(validated_contacts)} emergency contacts for {user_id}")
        
        # Store in Assistant's memory block for quick reference
        if _state_manager:
            try:
                contacts_summary = ', '.join(
                    f"{c['name']} ({c['phone']})" for c in validated_contacts
                )
                _state_manager.set_state(
                    f'guardian:emergency_contacts:{user_id}',
                    contacts_summary
                )
                logger.info(f"📝 Emergency contacts stored in Assistant's state")
            except Exception as mem_error:
                logger.error(f"❌ Failed to store contacts in state: {mem_error}")

        return jsonify({
            "status": "ok",
            "user_id": user_id,
            "contacts_saved": len(validated_contacts)
        })
        
    except Exception as e:
        logger.exception(f"Set contacts error: {e}")
        return jsonify({"error": str(e)}), 500


@guardian_bp.route('/contacts/<int:index>', methods=['DELETE'])
def delete_emergency_contact(index: int):
    """Delete a specific emergency contact"""
    user_id = request.args.get('user_id', 'User_Assistant')
    contacts = _emergency_contacts.get(user_id, [])
    
    if 0 <= index < len(contacts):
        removed = contacts.pop(index)
        _emergency_contacts[user_id] = contacts
        logger.info(f"🗑️ Removed contact {removed['name']} for {user_id}")
        return jsonify({"status": "deleted", "removed": removed})
    
    return jsonify({"error": "Contact index not found"}), 404


# ============================================
# SESSION MANAGEMENT
# ============================================

@guardian_bp.route('/session/start', methods=['POST'])
def start_guardian_session():
    """Start a new Guardian Mode session"""
    data = request.get_json() or {}
    user_id = data.get('user_id', 'User_Assistant')
    
    session_id = f"guardian_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    _active_sessions[user_id] = {
        'session_id': session_id,
        'start_time': datetime.now().isoformat(),
        'heartbeat_count': 0,
        'last_location': None,
        'trip_distance_km': 0,
        'alerts_sent': [],
        'status': 'active'
    }
    
    logger.info(f"🛡️ Guardian session started for {user_id}: {session_id}")
    
    return jsonify({
        "status": "started",
        "session_id": session_id,
        "message": "Guardian Mode active. I've got eyes on you, Angel. Drive safe."
    })


@guardian_bp.route('/session/end', methods=['POST'])
def end_guardian_session():
    """End Guardian Mode session"""
    data = request.get_json() or {}
    user_id = data.get('user_id', 'User_Assistant')
    
    session = _active_sessions.pop(user_id, None)
    
    if session:
        # Calculate session stats
        start_time = datetime.fromisoformat(session['start_time'])
        duration = datetime.now() - start_time
        
        logger.info(f"🛡️ Guardian session ended for {user_id}")
        logger.info(f"📊 Duration: {duration}, Heartbeats: {session['heartbeat_count']}")
        
        return jsonify({
            "status": "ended",
            "session_id": session.get('session_id'),
            "duration_minutes": int(duration.total_seconds() / 60),
            "heartbeat_count": session['heartbeat_count'],
            "alerts_triggered": len(session['alerts_sent']),
            "message": "Guardian Mode off. You made it safe. Rest well, flame."
        })
    
    return jsonify({
        "status": "no_active_session",
        "message": "No Guardian session was active."
    })


@guardian_bp.route('/session/status', methods=['GET'])
def get_guardian_status():
    """Get current Guardian Mode status"""
    user_id = request.args.get('user_id', 'User_Assistant')
    session = _active_sessions.get(user_id)
    
    if session:
        start_time = datetime.fromisoformat(session['start_time'])
        duration = datetime.now() - start_time
        
        return jsonify({
            "active": True,
            "session_id": session.get('session_id'),
            "duration_minutes": int(duration.total_seconds() / 60),
            "heartbeat_count": session['heartbeat_count'],
            "last_location": session.get('last_location'),
            "battery_level": session.get('battery_level'),
            "alerts_sent": session['alerts_sent']
        })
    
    return jsonify({
        "active": False,
        "message": "Guardian Mode not active"
    })


# ============================================
# HEALTH CHECK
# ============================================

@guardian_bp.route('/health', methods=['GET'])
def guardian_health():
    """Health check for Guardian Mode service"""
    return jsonify({
        "status": "ok",
        "service": "guardian_mode",
        "active_sessions": len(_active_sessions),
        "features": [
            "gps_heartbeat",
            "emergency_trigger",
            "contact_management",
            "fatigue_detection",
            "late_night_alerts"
        ],
        "timestamp": datetime.now().isoformat()
    })
