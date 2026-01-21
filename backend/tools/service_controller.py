#!/usr/bin/env python3
"""
Nate Service Controller - Level 3 Priority 3

Safe service control for Nate's self-maintenance.
This allows Nate to restart services after making changes.

Features:
- Control only Nate's services (nate-substrate, nate-telegram)
- Start, stop, restart, and check status
- Full audit logging
- Safety checks before operations
"""

import subprocess
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path


# Configuration
ALLOWED_SERVICES = [
    "nate-substrate",
    "nate-telegram"
]

AUDIT_LOG = Path("/var/log/nate_service_control.log")


class ServiceController:
    """Safe service controller for Nate's services only."""

    def __init__(self):
        """Initialize service controller."""
        # Ensure audit log exists with proper permissions
        if not AUDIT_LOG.exists():
            try:
                AUDIT_LOG.touch(mode=0o644)
            except Exception:
                pass  # Will log to stdout if file creation fails

    def control_service(
        self,
        service: str,
        operation: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Control a service (start/stop/restart/status).

        Args:
            service: Service name (must be in ALLOWED_SERVICES)
            operation: Operation to perform (start/stop/restart/status)
            dry_run: Preview the operation without executing

        Returns:
            Dict with status and operation details
        """
        # Validate service
        if service not in ALLOWED_SERVICES:
            return {
                "status": "error",
                "message": f"Service '{service}' not allowed. Allowed services: {', '.join(ALLOWED_SERVICES)}"
            }

        # Validate operation
        valid_operations = ["start", "stop", "restart", "status"]
        if operation not in valid_operations:
            return {
                "status": "error",
                "message": f"Invalid operation '{operation}'. Valid operations: {', '.join(valid_operations)}"
            }

        # Build systemctl command
        cmd = ["systemctl", operation, service]

        # Log the operation
        self._audit_log({
            "timestamp": datetime.now().isoformat(),
            "service": service,
            "operation": operation,
            "dry_run": dry_run,
            "command": " ".join(cmd)
        })

        if dry_run:
            return {
                "status": "success",
                "message": f"Dry run - would execute: {' '.join(cmd)}",
                "service": service,
                "operation": operation,
                "dry_run": True
            }

        # Execute the command
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            # For status operation, parse the output
            if operation == "status":
                return self._parse_status(service, result)

            # For other operations, check if successful
            if result.returncode == 0:
                return {
                    "status": "success",
                    "message": f"Service {service} {operation} completed successfully",
                    "service": service,
                    "operation": operation,
                    "output": result.stdout
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to {operation} service {service}",
                    "service": service,
                    "operation": operation,
                    "error": result.stderr,
                    "exit_code": result.returncode
                }

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": f"Operation timed out after 30 seconds",
                "service": service,
                "operation": operation
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to execute operation: {str(e)}",
                "service": service,
                "operation": operation
            }

    def get_service_status(self, service: Optional[str] = None) -> Dict[str, Any]:
        """
        Get status of one or all Nate services.

        Args:
            service: Specific service name, or None for all services

        Returns:
            Dict with service status information
        """
        if service:
            # Validate service
            if service not in ALLOWED_SERVICES:
                return {
                    "status": "error",
                    "message": f"Service '{service}' not allowed"
                }

            return self.control_service(service, "status")
        else:
            # Get status of all services
            statuses = {}
            for svc in ALLOWED_SERVICES:
                result = self.control_service(svc, "status")
                statuses[svc] = {
                    "active": result.get("active", False),
                    "running": result.get("running", False),
                    "status_text": result.get("status_text", "unknown")
                }

            return {
                "status": "success",
                "services": statuses
            }

    def restart_after_edit(
        self,
        service: str,
        wait_seconds: int = 2
    ) -> Dict[str, Any]:
        """
        Safely restart a service after code edits.

        Args:
            service: Service to restart
            wait_seconds: Seconds to wait before restart (default: 2)

        Returns:
            Dict with restart status
        """
        import time

        # Validate service
        if service not in ALLOWED_SERVICES:
            return {
                "status": "error",
                "message": f"Service '{service}' not allowed"
            }

        # Get status before restart
        before_status = self.control_service(service, "status")

        # Wait a moment (for file system sync, etc.)
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        # Restart the service
        restart_result = self.control_service(service, "restart")

        if restart_result["status"] != "success":
            return restart_result

        # Wait a moment for service to start
        time.sleep(1)

        # Get status after restart
        after_status = self.control_service(service, "status")

        return {
            "status": "success",
            "message": f"Service {service} restarted successfully",
            "service": service,
            "before": {
                "active": before_status.get("active", False),
                "running": before_status.get("running", False)
            },
            "after": {
                "active": after_status.get("active", False),
                "running": after_status.get("running", False)
            }
        }

    def _parse_status(self, service: str, result: subprocess.CompletedProcess) -> Dict[str, Any]:
        """Parse systemctl status output."""
        output = result.stdout + result.stderr

        # Check if service is active
        active = "active (running)" in output.lower()
        running = "running" in output.lower()
        failed = "failed" in output.lower()
        inactive = "inactive" in output.lower()

        # Determine status text
        if active and running:
            status_text = "active (running)"
        elif failed:
            status_text = "failed"
        elif inactive:
            status_text = "inactive"
        else:
            status_text = "unknown"

        return {
            "status": "success",
            "service": service,
            "active": active,
            "running": running,
            "failed": failed,
            "inactive": inactive,
            "status_text": status_text,
            "output": output,
            "exit_code": result.returncode
        }

    def _audit_log(self, entry: Dict[str, Any]):
        """Log service control operation to audit log."""
        try:
            with open(AUDIT_LOG, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception:
            # If audit log fails, at least log to stdout
            print(f"AUDIT: {json.dumps(entry)}")

    def get_audit_logs(self, lines: int = 50) -> Dict[str, Any]:
        """Get recent service control audit logs."""
        try:
            if not AUDIT_LOG.exists():
                return {
                    "status": "success",
                    "logs": [],
                    "message": "No audit log found"
                }

            with open(AUDIT_LOG, 'r') as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:]

            logs = []
            for line in recent_lines:
                try:
                    logs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue

            return {
                "status": "success",
                "logs": logs,
                "total": len(logs)
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to read audit logs: {str(e)}"
            }
