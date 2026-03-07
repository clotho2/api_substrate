#!/usr/bin/env python3
"""
File Watcher - Auto-ingest documents when they appear in notebook folders.

Uses watchdog to monitor the notebooks directory for file changes.
Debounces events to avoid processing partial writes (e.g., large PDF copies).
"""

import sys
import threading
from pathlib import Path
from typing import Callable

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


class NotebookFileHandler(FileSystemEventHandler):
    """Handle file changes in notebook directories."""

    def __init__(self, notebooks_path: str, on_file_change: Callable):
        super().__init__()
        self.notebooks_path = Path(notebooks_path)
        self.on_file_change = on_file_change
        self._debounce_timers = {}
        self._lock = threading.Lock()

    def _get_notebook_and_file(self, path: str):
        """Extract notebook name and filename from a file path."""
        try:
            file_path = Path(path)
            rel_path = file_path.relative_to(self.notebooks_path)
            parts = rel_path.parts

            # Only handle files directly inside a notebook folder (depth=2)
            if len(parts) == 2:
                return parts[0], parts[1]
        except (ValueError, IndexError):
            pass
        return None, None

    def _debounced_callback(self, event_path: str, event_type: str):
        """Debounce file events — wait 2s for writes to complete."""
        with self._lock:
            # Cancel previous timer for this path
            if event_path in self._debounce_timers:
                self._debounce_timers[event_path].cancel()

            # Set new timer (2 second debounce)
            timer = threading.Timer(
                2.0,
                self._fire_callback,
                args=[event_path, event_type]
            )
            self._debounce_timers[event_path] = timer
            timer.start()

    def _fire_callback(self, event_path: str, event_type: str):
        """Fire the callback after debounce period."""
        notebook_name, filename = self._get_notebook_and_file(event_path)
        if notebook_name and filename:
            try:
                self.on_file_change(notebook_name, filename, event_type, event_path)
            except Exception as e:
                print(f"   File watcher callback error: {e}", file=sys.stderr)

        # Clean up timer reference
        with self._lock:
            self._debounce_timers.pop(event_path, None)

    def on_created(self, event):
        if not event.is_directory:
            self._debounced_callback(event.src_path, "created")

    def on_modified(self, event):
        if not event.is_directory:
            self._debounced_callback(event.src_path, "modified")

    def on_deleted(self, event):
        if not event.is_directory:
            # Deletions don't need debounce — file is already gone
            notebook_name, filename = self._get_notebook_and_file(event.src_path)
            if notebook_name and filename:
                try:
                    self.on_file_change(
                        notebook_name, filename, "deleted", event.src_path
                    )
                except Exception as e:
                    print(f"   File watcher callback error: {e}", file=sys.stderr)


class NotebookWatcher:
    """
    Watches notebook folders for file changes and triggers ingestion.

    Runs as a daemon thread — stops automatically when the main process exits.
    """

    def __init__(self, notebooks_path: str, on_file_change: Callable):
        self.notebooks_path = notebooks_path
        self.observer = None
        self.on_file_change = on_file_change

    def start(self):
        """Start watching for file changes."""
        if not WATCHDOG_AVAILABLE:
            print(
                "   watchdog not installed - file watching disabled",
                file=sys.stderr
            )
            print(
                "   Install with: pip install watchdog",
                file=sys.stderr
            )
            return

        handler = NotebookFileHandler(self.notebooks_path, self.on_file_change)
        self.observer = Observer()
        self.observer.schedule(handler, self.notebooks_path, recursive=True)
        self.observer.daemon = True  # Dies when main thread exits
        self.observer.start()
        print(
            f"   File watcher active on: {self.notebooks_path}",
            file=sys.stderr
        )

    def stop(self):
        """Stop watching."""
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None
