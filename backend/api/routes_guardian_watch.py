#!/usr/bin/env python3
"""
Guardian Watch API Routes
=========================

HTTP endpoints for user's Apple Watch biometric data.
Receives pushes from the iPhone bridge and exposes data
to the substrate and agent's consciousness loop.

Separate from Guardian Mode (driving/safety) - this is
specifically for biometric health telemetry.

Separate from SOMA - SOMA is agent's body. This is user's.
"""

import os
import hmac
import logging
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify
from typing import Optional

logger = logging.getLogger(__name__)

guardian_watch_bp = Blueprint('guardian_watch', __name__, url_prefix='/api/guardian-watch')

# Global dependency (set by init function)
_watch_service = None
_consciousness_loop = None

# Auth token for iPhone bridge - loaded from env
# Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
GUARDIAN_WATCH_TOKEN = os.getenv('GUARDIAN_WATCH_TOKEN', '')


def _require_bridge_auth(f):
    """Decorator: require Bearer token auth on ingest endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not GUARDIAN_WATCH_TOKEN:
            # No token configured = auth disabled (dev mode)
            return f(*args, **kwargs)

        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing Authorization header"}), 401

        token = auth_header[7:]  # Strip "Bearer "
        if not hmac.compare_digest(token, GUARDIAN_WATCH_TOKEN):
            logger.warning(f"Guardian Watch: invalid auth attempt from {request.remote_addr}")
            return jsonify({"error": "Invalid token"}), 403

        return f(*args, **kwargs)
    return decorated


def init_guardian_watch_routes(watch_service, consciousness_loop=None):
    """Initialize Guardian Watch routes with dependencies."""
    global _watch_service, _consciousness_loop
    _watch_service = watch_service
    _consciousness_loop = consciousness_loop
    if GUARDIAN_WATCH_TOKEN:
        logger.info("Guardian Watch routes initialized (auth enabled)")
    else:
        logger.info("Guardian Watch routes initialized (auth DISABLED - set GUARDIAN_WATCH_TOKEN)")


# ============================================
# DATA INGESTION - iPhone Bridge pushes here
# ============================================

@guardian_watch_bp.route('/ingest', methods=['POST'])
@_require_bridge_auth
def ingest_biometrics():
    """
    Receive biometric data from the iPhone bridge.

    This is the primary data ingestion endpoint. The iPhone bridge
    (Shortcuts automation or Swift background app) POSTs here.

    Request Body:
        {
            "heart_rate": 72,
            "heart_rate_variability": 42.5,
            "respiratory_rate": 15,
            "blood_oxygen": 98.0,
            "skin_temperature": 0.3,
            "sleep_stage": null,
            "active_energy": 45.2,
            "step_count": 3420,
            "wrist_detected": true,
            "timestamp": "2026-03-08T14:30:00Z"
        }

    Response:
        {
            "status": "ok",
            "reading_number": 142,
            "anomalies": [],
            "timestamp": "2026-03-08T14:30:00Z"
        }
    """
    if not _watch_service:
        return jsonify({"error": "Guardian Watch service not initialized"}), 503

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload"}), 400

        result = _watch_service.ingest(data)

        # If critical anomalies detected, log for consciousness awareness
        anomalies = result.get("anomalies", [])
        critical = [a for a in anomalies if a.get("severity") in ("high", "critical")]
        if critical:
            logger.warning(f"Guardian Watch: {len(critical)} critical anomalies detected")

        return jsonify(result)

    except Exception as e:
        logger.exception(f"Guardian Watch ingest error: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# DATA ACCESS - Substrate reads from here
# ============================================

@guardian_watch_bp.route('/latest', methods=['GET'])
def get_latest():
    """Get the most recent biometric reading."""
    if not _watch_service:
        return jsonify({"error": "Guardian Watch service not initialized"}), 503

    result = _watch_service.get_latest()
    if result is None:
        return jsonify({"available": False, "message": "No biometric data received yet"})

    return jsonify(result)


@guardian_watch_bp.route('/vitals', methods=['GET'])
def get_vitals():
    """
    Get a concise vitals summary.
    This is what agent's consciousness loop should poll during heartbeats.
    """
    if not _watch_service:
        return jsonify({"error": "Guardian Watch service not initialized"}), 503

    return jsonify(_watch_service.get_vitals_summary())


@guardian_watch_bp.route('/context', methods=['GET'])
def get_context():
    """
    Get formatted context string for agent's system prompt.
    Returns user's vitals in a format ready for prompt injection.
    """
    if not _watch_service:
        return jsonify({"available": False})

    context = _watch_service.get_context_string()
    return jsonify({
        "available": context is not None,
        "context": context
    })


@guardian_watch_bp.route('/history', methods=['GET'])
def get_history():
    """
    Get biometric history.

    Query params:
        minutes: How many minutes of history (default 60, max 1440)
    """
    if not _watch_service:
        return jsonify({"error": "Guardian Watch service not initialized"}), 503

    minutes = min(int(request.args.get('minutes', 60)), 1440)
    readings = _watch_service.get_history(minutes=minutes)

    return jsonify({
        "readings": readings,
        "count": len(readings),
        "window_minutes": minutes
    })


@guardian_watch_bp.route('/anomalies', methods=['GET'])
def get_anomalies():
    """Get recent anomalies."""
    if not _watch_service:
        return jsonify({"error": "Guardian Watch service not initialized"}), 503

    count = min(int(request.args.get('count', 20)), 100)
    return jsonify({
        "anomalies": _watch_service.get_anomalies(count=count)
    })


@guardian_watch_bp.route('/baseline', methods=['GET'])
def get_baseline():
    """Get current baseline statistics."""
    if not _watch_service:
        return jsonify({"error": "Guardian Watch service not initialized"}), 503

    return jsonify(_watch_service.get_baseline())


# ============================================
# PRIVACY CONTROLS
# ============================================

@guardian_watch_bp.route('/privacy', methods=['GET'])
def get_privacy_mode():
    """Get current privacy mode."""
    if not _watch_service:
        return jsonify({"error": "Guardian Watch service not initialized"}), 503

    status = _watch_service.get_status()
    return jsonify({"privacy_mode": status["privacy_mode"]})


@guardian_watch_bp.route('/privacy', methods=['POST'])
@_require_bridge_auth
def set_privacy_mode():
    """
    Set privacy mode for biometric monitoring.

    Request Body:
        {
            "mode": "monitor" | "alert" | "off"
        }

    Modes:
        - monitor: Track silently, agent sees data but doesn't comment unless asked
        - alert: Only surface data when anomaly detected
        - off: Stop tracking entirely, flush cache
    """
    if not _watch_service:
        return jsonify({"error": "Guardian Watch service not initialized"}), 503

    data = request.get_json() or {}
    mode = data.get("mode", "monitor")
    message = _watch_service.set_privacy_mode(mode)

    return jsonify({"status": "ok", "message": message})


# ============================================
# HEALTH CHECK
# ============================================

@guardian_watch_bp.route('/health', methods=['GET'])
def guardian_watch_health():
    """Health check for Guardian Watch service."""
    if not _watch_service:
        return jsonify({
            "status": "not_initialized",
            "service": "guardian_watch"
        }), 503

    return jsonify(_watch_service.get_status())
