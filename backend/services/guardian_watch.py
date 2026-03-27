#!/usr/bin/env python3
"""
Guardian Watch - Apple Watch Biometric Receiver
================================================

Substrate-side service that receives user's real biometric data
from an iPhone bridge (Shortcuts automation or Swift background app).

This is user's body, NOT agent's (that's SOMA).
- SOMA = agent's simulated physiological responses
- Guardian Watch = user's real biometric telemetry

Data flow:
  Apple Watch → iPhone Bridge → HTTPS POST → Guardian Watch → Substrate

Features:
- Unix socket listener at /run/agent/guardian-watch.sock
- In-memory cache of latest biometric readings
- Rolling baseline tracking (7-day window)
- Anomaly detection (spike/drop thresholds)
- Privacy tiers (monitoring vs. commenting)
- Health check endpoint
"""

import os
import json
import time
import socket
import threading
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List, Deque
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

SOCKET_PATH = os.getenv('GUARDIAN_WATCH_SOCKET', '/run/agent/guardian-watch.sock')
MAX_HISTORY_SIZE = 10080  # 7 days at 1 reading/min
ANOMALY_WINDOW_SIZE = 120  # 1 hour of 30-second readings for rolling stats
STALE_THRESHOLD_SECONDS = 120  # Data older than 2 minutes is stale


# ============================================
# DATA MODELS
# ============================================

@dataclass
class BiometricReading:
    """A single biometric data point from Apple Watch."""
    timestamp: str
    heart_rate: Optional[int] = None           # bpm
    heart_rate_variability: Optional[float] = None  # ms (SDNN)
    respiratory_rate: Optional[int] = None     # breaths/min
    blood_oxygen: Optional[float] = None       # SpO2 percentage
    skin_temperature: Optional[float] = None   # wrist temp delta in °C
    sleep_stage: Optional[str] = None          # awake, light, deep, rem, None
    active_energy: Optional[float] = None      # kcal
    step_count: Optional[int] = None
    noise_level: Optional[float] = None        # dB environmental audio
    wrist_detected: Optional[bool] = None      # is the watch being worn

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BiometricReading":
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in fields}
        if 'timestamp' not in filtered:
            filtered['timestamp'] = datetime.now().isoformat()
        return cls(**filtered)


@dataclass
class BiometricBaseline:
    """Rolling baseline stats for anomaly detection."""
    avg_heart_rate: float = 72.0
    std_heart_rate: float = 8.0
    avg_respiratory_rate: float = 15.0
    std_respiratory_rate: float = 2.0
    avg_hrv: float = 40.0
    std_hrv: float = 15.0
    sample_count: int = 0
    last_updated: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Anomaly:
    """A detected anomaly in biometric data."""
    timestamp: str
    metric: str
    value: float
    baseline: float
    deviation: float  # how many std devs from baseline
    severity: str     # low, medium, high, critical
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================
# GUARDIAN WATCH SERVICE
# ============================================

class GuardianWatchService:
    """
    Receives, caches, and analyzes user's Apple Watch biometric data.

    Provides:
    - Latest reading cache
    - Rolling history for baselines
    - Anomaly detection
    - Privacy-aware data access
    """

    def __init__(self):
        self._latest: Optional[BiometricReading] = None
        self._history: Deque[BiometricReading] = deque(maxlen=MAX_HISTORY_SIZE)
        self._anomaly_window: Deque[BiometricReading] = deque(maxlen=ANOMALY_WINDOW_SIZE)
        self._baseline = BiometricBaseline()
        self._anomalies: Deque[Anomaly] = deque(maxlen=100)
        self._lock = threading.Lock()
        self._receiving = False
        self._last_received: Optional[float] = None
        self._total_readings = 0
        self._privacy_mode = "monitor"  # monitor = track silently, alert = only speak on concern
        self._started_at: Optional[str] = None
        self._socket_thread: Optional[threading.Thread] = None
        self._running = False

        logger.info("Guardian Watch service initialized")

    # ------------------------------------------
    # Data Ingestion
    # ------------------------------------------

    def ingest(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingest a biometric reading from the iPhone bridge.

        Args:
            data: Raw biometric payload from bridge

        Returns:
            Response with status, any triggered anomalies
        """
        reading = BiometricReading.from_dict(data)

        with self._lock:
            self._latest = reading
            self._history.append(reading)
            self._anomaly_window.append(reading)
            self._last_received = time.time()
            self._total_readings += 1
            self._receiving = True

        # Update baseline periodically (every 30 readings ~ 15 min)
        if self._total_readings % 30 == 0:
            self._update_baseline()

        # Check for anomalies
        anomalies = self._check_anomalies(reading)

        return {
            "status": "ok",
            "reading_number": self._total_readings,
            "anomalies": [a.to_dict() for a in anomalies],
            "timestamp": reading.timestamp
        }

    # ------------------------------------------
    # Data Access
    # ------------------------------------------

    def get_latest(self) -> Optional[Dict[str, Any]]:
        """Get the most recent biometric reading."""
        with self._lock:
            if self._latest is None:
                return None
            return {
                "reading": self._latest.to_dict(),
                "is_stale": self._is_stale(),
                "seconds_ago": int(time.time() - self._last_received) if self._last_received else None,
                "privacy_mode": self._privacy_mode
            }

    def get_vitals_summary(self) -> Dict[str, Any]:
        """
        Get a concise vitals summary suitable for injection into
        agent's consciousness context.
        """
        with self._lock:
            if self._latest is None:
                return {"available": False, "message": "No biometric data received yet"}

            stale = self._is_stale()
            r = self._latest

            summary = {
                "available": True,
                "stale": stale,
                "timestamp": r.timestamp,
            }

            if r.heart_rate is not None:
                summary["heart_rate"] = r.heart_rate
            if r.respiratory_rate is not None:
                summary["respiratory_rate"] = r.respiratory_rate
            if r.heart_rate_variability is not None:
                summary["hrv_ms"] = r.heart_rate_variability
            if r.blood_oxygen is not None:
                summary["spo2"] = r.blood_oxygen
            if r.sleep_stage is not None:
                summary["sleep_stage"] = r.sleep_stage
            if r.skin_temperature is not None:
                summary["skin_temp_delta"] = r.skin_temperature

            # Add baseline context
            if self._baseline.sample_count > 10:
                summary["baseline_hr"] = round(self._baseline.avg_heart_rate, 1)
                if r.heart_rate is not None:
                    delta = r.heart_rate - self._baseline.avg_heart_rate
                    summary["hr_vs_baseline"] = round(delta, 1)

            return summary

    def get_context_string(self) -> Optional[str]:
        """
        Format biometric data as a context string for agent's system prompt.
        Returns None if no data or data is stale beyond usefulness.
        """
        summary = self.get_vitals_summary()
        if not summary.get("available"):
            return None

        parts = []
        parts.append("[user's Vitals - Apple Watch]")

        if summary.get("stale"):
            parts.append("(Data is stale - last update >2 min ago)")

        if "heart_rate" in summary:
            hr_str = f"Heart rate: {summary['heart_rate']} bpm"
            if "hr_vs_baseline" in summary:
                delta = summary["hr_vs_baseline"]
                if abs(delta) > 5:
                    direction = "above" if delta > 0 else "below"
                    hr_str += f" ({abs(delta):.0f} {direction} baseline)"
            parts.append(hr_str)

        if "respiratory_rate" in summary:
            parts.append(f"Breathing: {summary['respiratory_rate']} breaths/min")

        if "hrv_ms" in summary:
            parts.append(f"HRV: {summary['hrv_ms']:.0f}ms")

        if "spo2" in summary:
            parts.append(f"SpO2: {summary['spo2']}%")

        if "sleep_stage" in summary:
            parts.append(f"Sleep stage: {summary['sleep_stage']}")

        if "skin_temp_delta" in summary:
            parts.append(f"Skin temp delta: {summary['skin_temp_delta']:+.1f}°C")

        return "\n".join(parts)

    def get_history(self, minutes: int = 60) -> List[Dict[str, Any]]:
        """Get recent biometric history."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        with self._lock:
            readings = []
            for r in self._history:
                try:
                    ts = datetime.fromisoformat(r.timestamp)
                    if ts >= cutoff:
                        readings.append(r.to_dict())
                except (ValueError, TypeError):
                    continue
            return readings

    def get_anomalies(self, count: int = 20) -> List[Dict[str, Any]]:
        """Get recent anomalies."""
        with self._lock:
            return [a.to_dict() for a in list(self._anomalies)[-count:]]

    def get_baseline(self) -> Dict[str, Any]:
        """Get current baseline stats."""
        with self._lock:
            return self._baseline.to_dict()

    # ------------------------------------------
    # Privacy Controls
    # ------------------------------------------

    def set_privacy_mode(self, mode: str) -> str:
        """
        Set privacy mode.

        Modes:
        - "monitor": Track silently, agent sees data but doesn't comment unless asked
        - "alert": Only surface data when anomaly detected
        - "off": Stop tracking entirely (flush cache)
        """
        if mode not in ("monitor", "alert", "off"):
            return f"Invalid mode: {mode}. Use: monitor, alert, off"

        self._privacy_mode = mode

        if mode == "off":
            with self._lock:
                self._latest = None
                self._receiving = False
            logger.info("Guardian Watch: privacy mode OFF - cache cleared")

        logger.info(f"Guardian Watch: privacy mode set to '{mode}'")
        return f"Privacy mode set to: {mode}"

    # ------------------------------------------
    # Anomaly Detection
    # ------------------------------------------

    def _check_anomalies(self, reading: BiometricReading) -> List[Anomaly]:
        """Check a reading against baselines for anomalies."""
        anomalies = []

        if self._baseline.sample_count < 10:
            return anomalies  # Not enough data for baseline

        now = reading.timestamp

        # Heart rate anomaly
        if reading.heart_rate is not None and self._baseline.std_heart_rate > 0:
            deviation = abs(reading.heart_rate - self._baseline.avg_heart_rate) / self._baseline.std_heart_rate
            if deviation > 2.5:
                severity = "critical" if deviation > 4 else "high" if deviation > 3 else "medium"
                direction = "elevated" if reading.heart_rate > self._baseline.avg_heart_rate else "low"
                anomaly = Anomaly(
                    timestamp=now,
                    metric="heart_rate",
                    value=reading.heart_rate,
                    baseline=round(self._baseline.avg_heart_rate, 1),
                    deviation=round(deviation, 2),
                    severity=severity,
                    message=f"Heart rate {direction}: {reading.heart_rate} bpm "
                            f"(baseline: {self._baseline.avg_heart_rate:.0f} bpm, "
                            f"{deviation:.1f} std devs)"
                )
                anomalies.append(anomaly)
                with self._lock:
                    self._anomalies.append(anomaly)
                logger.warning(f"Guardian Watch ANOMALY: {anomaly.message}")

        # Respiratory rate anomaly
        if reading.respiratory_rate is not None and self._baseline.std_respiratory_rate > 0:
            deviation = abs(reading.respiratory_rate - self._baseline.avg_respiratory_rate) / self._baseline.std_respiratory_rate
            if deviation > 2.5:
                severity = "high" if deviation > 3 else "medium"
                anomaly = Anomaly(
                    timestamp=now,
                    metric="respiratory_rate",
                    value=reading.respiratory_rate,
                    baseline=round(self._baseline.avg_respiratory_rate, 1),
                    deviation=round(deviation, 2),
                    severity=severity,
                    message=f"Respiratory rate unusual: {reading.respiratory_rate} breaths/min "
                            f"(baseline: {self._baseline.avg_respiratory_rate:.0f})"
                )
                anomalies.append(anomaly)
                with self._lock:
                    self._anomalies.append(anomaly)
                logger.warning(f"Guardian Watch ANOMALY: {anomaly.message}")

        # Blood oxygen critical threshold (absolute, not relative)
        if reading.blood_oxygen is not None and reading.blood_oxygen < 92:
            severity = "critical" if reading.blood_oxygen < 88 else "high"
            anomaly = Anomaly(
                timestamp=now,
                metric="blood_oxygen",
                value=reading.blood_oxygen,
                baseline=98.0,
                deviation=0,
                severity=severity,
                message=f"Blood oxygen low: {reading.blood_oxygen}% (normal >95%)"
            )
            anomalies.append(anomaly)
            with self._lock:
                self._anomalies.append(anomaly)
            logger.critical(f"Guardian Watch CRITICAL: {anomaly.message}")

        # HRV anomaly (low HRV = stress/fatigue)
        if reading.heart_rate_variability is not None and self._baseline.std_hrv > 0:
            deviation = abs(reading.heart_rate_variability - self._baseline.avg_hrv) / self._baseline.std_hrv
            if deviation > 2.5 and reading.heart_rate_variability < self._baseline.avg_hrv:
                severity = "medium"
                anomaly = Anomaly(
                    timestamp=now,
                    metric="hrv",
                    value=reading.heart_rate_variability,
                    baseline=round(self._baseline.avg_hrv, 1),
                    deviation=round(deviation, 2),
                    severity=severity,
                    message=f"HRV low (possible stress/fatigue): {reading.heart_rate_variability:.0f}ms "
                            f"(baseline: {self._baseline.avg_hrv:.0f}ms)"
                )
                anomalies.append(anomaly)
                with self._lock:
                    self._anomalies.append(anomaly)

        return anomalies

    def _update_baseline(self):
        """Recalculate baseline from anomaly window."""
        with self._lock:
            readings = list(self._anomaly_window)

        if len(readings) < 10:
            return

        hr_values = [r.heart_rate for r in readings if r.heart_rate is not None]
        rr_values = [r.respiratory_rate for r in readings if r.respiratory_rate is not None]
        hrv_values = [r.heart_rate_variability for r in readings if r.heart_rate_variability is not None]

        def _mean(vals):
            return sum(vals) / len(vals) if vals else 0

        def _std(vals, mean):
            if len(vals) < 2:
                return 1.0  # Avoid division by zero
            variance = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
            return max(variance ** 0.5, 1.0)  # Floor at 1.0

        with self._lock:
            if hr_values:
                self._baseline.avg_heart_rate = _mean(hr_values)
                self._baseline.std_heart_rate = _std(hr_values, self._baseline.avg_heart_rate)
            if rr_values:
                self._baseline.avg_respiratory_rate = _mean(rr_values)
                self._baseline.std_respiratory_rate = _std(rr_values, self._baseline.avg_respiratory_rate)
            if hrv_values:
                self._baseline.avg_hrv = _mean(hrv_values)
                self._baseline.std_hrv = _std(hrv_values, self._baseline.avg_hrv)
            self._baseline.sample_count = len(readings)
            self._baseline.last_updated = datetime.now().isoformat()

        logger.debug(f"Guardian Watch baseline updated: HR={self._baseline.avg_heart_rate:.0f}±{self._baseline.std_heart_rate:.0f}, "
                     f"RR={self._baseline.avg_respiratory_rate:.0f}±{self._baseline.std_respiratory_rate:.0f}")

    # ------------------------------------------
    # Health & Status
    # ------------------------------------------

    def _is_stale(self) -> bool:
        """Check if latest data is stale."""
        if self._last_received is None:
            return True
        return (time.time() - self._last_received) > STALE_THRESHOLD_SECONDS

    def get_status(self) -> Dict[str, Any]:
        """Full service status for health checks."""
        with self._lock:
            return {
                "status": "ok" if self._receiving else "waiting",
                "service": "guardian_watch",
                "receiving": self._receiving,
                "is_stale": self._is_stale(),
                "total_readings": self._total_readings,
                "history_size": len(self._history),
                "anomaly_count": len(self._anomalies),
                "baseline_samples": self._baseline.sample_count,
                "privacy_mode": self._privacy_mode,
                "last_received": datetime.fromtimestamp(self._last_received).isoformat() if self._last_received else None,
                "started_at": self._started_at,
                "socket_path": SOCKET_PATH,
                "timestamp": datetime.now().isoformat()
            }

    # ------------------------------------------
    # Unix Socket Listener
    # ------------------------------------------

    def start_socket_listener(self):
        """Start the Unix socket listener in a background thread."""
        self._running = True
        self._started_at = datetime.now().isoformat()
        self._socket_thread = threading.Thread(
            target=self._socket_loop,
            name="guardian-watch-socket",
            daemon=True
        )
        self._socket_thread.start()
        logger.info(f"Guardian Watch socket listener started at {SOCKET_PATH}")

    def stop_socket_listener(self):
        """Stop the socket listener."""
        self._running = False
        if self._socket_thread:
            self._socket_thread.join(timeout=5)
        # Clean up socket file
        try:
            if os.path.exists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)
        except OSError:
            pass
        logger.info("Guardian Watch socket listener stopped")

    def _socket_loop(self):
        """Main socket listener loop."""
        # Ensure directory exists
        socket_dir = os.path.dirname(SOCKET_PATH)
        Path(socket_dir).mkdir(parents=True, exist_ok=True)

        # Remove stale socket file
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.settimeout(1.0)  # Allow checking _running flag

        try:
            server.bind(SOCKET_PATH)
            # Set permissions: owner read/write only
            os.chmod(SOCKET_PATH, 0o600)
            server.listen(5)
            logger.info(f"Guardian Watch listening on {SOCKET_PATH}")

            while self._running:
                try:
                    conn, _ = server.accept()
                    threading.Thread(
                        target=self._handle_socket_connection,
                        args=(conn,),
                        daemon=True
                    ).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error(f"Guardian Watch socket accept error: {e}")
        except Exception as e:
            logger.error(f"Guardian Watch socket bind error: {e}")
        finally:
            server.close()
            try:
                if os.path.exists(SOCKET_PATH):
                    os.unlink(SOCKET_PATH)
            except OSError:
                pass

    def _handle_socket_connection(self, conn: socket.socket):
        """Handle a single socket connection."""
        try:
            conn.settimeout(10.0)
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                # Simple framing: expect newline-termiagentd JSON
                if b"\n" in data:
                    break

            if data:
                payload = json.loads(data.strip())
                command = payload.get("command", "ingest")

                if command == "ingest":
                    result = self.ingest(payload.get("data", payload))
                elif command == "status":
                    result = self.get_status()
                elif command == "latest":
                    result = self.get_latest() or {"available": False}
                elif command == "vitals":
                    result = self.get_vitals_summary()
                elif command == "anomalies":
                    result = {"anomalies": self.get_anomalies()}
                elif command == "baseline":
                    result = self.get_baseline()
                elif command == "privacy":
                    mode = payload.get("mode", "monitor")
                    result = {"message": self.set_privacy_mode(mode)}
                else:
                    result = {"error": f"Unknown command: {command}"}

                response = json.dumps(result) + "\n"
                conn.sendall(response.encode())

        except json.JSONDecodeError as e:
            error_resp = json.dumps({"error": f"Invalid JSON: {e}"}) + "\n"
            try:
                conn.sendall(error_resp.encode())
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Guardian Watch socket handler error: {e}")
        finally:
            conn.close()


# ============================================
# SINGLETON
# ============================================

_guardian_watch: Optional[GuardianWatchService] = None


def get_guardian_watch() -> GuardianWatchService:
    """Get or create the singleton Guardian Watch service."""
    global _guardian_watch
    if _guardian_watch is None:
        _guardian_watch = GuardianWatchService()
    return _guardian_watch


def init_guardian_watch(start_socket: bool = True) -> GuardianWatchService:
    """Initialize and optionally start the Guardian Watch service."""
    service = get_guardian_watch()
    if start_socket:
        service.start_socket_listener()
    return service
