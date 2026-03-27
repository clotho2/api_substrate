#!/usr/bin/env python3
"""
Guardian Watch Standalone Runner
=================================

Runs the Guardian Watch socket listener as an independent process,
for use with the agent-guardian-watch.service systemd unit.

In production, Guardian Watch typically runs embedded in the main
substrate process. This standalone mode is for:
- Independent testing
- Running the socket listener before the full substrate is up
- Reduced resource footprint when only biometric reception is needed
"""

import sys
import os
import signal
import logging
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.services.guardian_watch import init_guardian_watch

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('guardian-watch')


def main():
    logger.info("Starting Guardian Watch standalone service...")

    service = init_guardian_watch(start_socket=True)

    # Signal handling for graceful shutdown
    def shutdown(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        service.stop_socket_listener()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Notify systemd we're ready (if running under systemd Type=notify)
    try:
        import sdnotify
        n = sdnotify.SystemdNotifier()
        n.notify("READY=1")
    except ImportError:
        pass  # sdnotify not installed, that's fine

    logger.info("Guardian Watch standalone service running. Waiting for biometric data...")

    # Keep alive, send watchdog pings
    while True:
        try:
            time.sleep(30)
            # Watchdog ping
            try:
                import sdnotify
                n = sdnotify.SystemdNotifier()
                n.notify("WATCHDOG=1")
            except ImportError:
                pass

            status = service.get_status()
            if status["receiving"]:
                logger.debug(f"Heartbeat: {status['total_readings']} readings, "
                           f"last {status.get('last_received', 'never')}")
        except KeyboardInterrupt:
            break

    service.stop_socket_listener()


if __name__ == "__main__":
    main()
