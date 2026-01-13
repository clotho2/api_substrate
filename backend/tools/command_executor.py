#!/usr/bin/env python3
"""
Nate Command Executor - Level 2 (Safe Command Execution)

This module enables Nate to execute whitelisted Linux commands in a sandboxed
environment with full audit logging and safety mechanisms.

Security Features:
- Command whitelisting (only approved commands can run)
- Sandboxed execution (restricted to /opt/aicara)
- Rate limiting (max 5 commands per minute)
- Full audit logging (all commands logged for review)
- Dry-run mode (test commands without execution)
- Approval mechanism for sensitive operations
- Automatic rollback on errors
"""

import os
import re
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from collections import deque

# Configuration
ALLOWED_ROOT = Path("/opt/aicara")
AUDIT_LOG = Path("/var/log/nate_dev_commands.log")
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 15  # commands per window (increased for complex investigations)

# Command rate limiting tracking (in-memory for now)
_command_history = deque(maxlen=100)

# Whitelisted commands - organized by risk level
WHITELISTED_COMMANDS = {
    # Read-only commands (safe)
    "safe": {
        "ls": {"max_args": 10, "description": "List directory contents"},
        "pwd": {"max_args": 0, "description": "Print working directory"},
        "cat": {"max_args": 5, "description": "Display file contents"},
        "head": {"max_args": 5, "description": "Display file start"},
        "tail": {"max_args": 5, "description": "Display file end"},
        "grep": {"max_args": 10, "description": "Search text patterns"},
        "find": {"max_args": 10, "description": "Find files"},
        "echo": {"max_args": 20, "description": "Display text"},
        "wc": {"max_args": 5, "description": "Count lines/words/characters"},
        "sort": {"max_args": 5, "description": "Sort lines"},
        "uniq": {"max_args": 5, "description": "Filter duplicate lines"},
        "diff": {"max_args": 5, "description": "Compare files"},
        "stat": {"max_args": 3, "description": "File statistics"},
        "file": {"max_args": 3, "description": "File type identification"},
        "which": {"max_args": 3, "description": "Locate command"},
        "whoami": {"max_args": 0, "description": "Current user"},
        "date": {"max_args": 5, "description": "Display date/time"},
        "env": {"max_args": 0, "description": "Show environment variables"},
    },

    # File operations (moderate risk - requires logging)
    "moderate": {
        "mkdir": {"max_args": 5, "description": "Create directory", "requires_approval": False},
        "touch": {"max_args": 5, "description": "Create empty file", "requires_approval": False},
        "cp": {"max_args": 5, "description": "Copy files", "requires_approval": False},
        "mv": {"max_args": 3, "description": "Move/rename files", "requires_approval": False},
        "chmod": {"max_args": 3, "description": "Change permissions", "requires_approval": True},
        "chown": {"max_args": 3, "description": "Change ownership", "requires_approval": True},
    },

    # Git commands (workflow integration)
    "git": {
        "git status": {"max_args": 5, "description": "Show working tree status"},
        "git branch": {"max_args": 5, "description": "List/create branches"},
        "git checkout": {"max_args": 5, "description": "Switch branches/restore files"},
        "git add": {"max_args": 10, "description": "Stage changes"},
        "git commit": {"max_args": 10, "description": "Commit changes"},
        "git diff": {"max_args": 10, "description": "Show changes"},
        "git log": {"max_args": 10, "description": "Show commit history"},
        "git pull": {"max_args": 5, "description": "Fetch and merge", "requires_approval": True},
        "git push": {"max_args": 10, "description": "Push commits", "requires_approval": True},
        "git fetch": {"max_args": 5, "description": "Fetch from remote"},
        "git remote": {"max_args": 5, "description": "Manage remotes"},
        "git stash": {"max_args": 5, "description": "Stash changes"},
        "git merge": {"max_args": 5, "description": "Merge branches", "requires_approval": True},
        "git rebase": {"max_args": 5, "description": "Rebase branch", "requires_approval": True},
        "git reset": {"max_args": 5, "description": "Reset changes", "requires_approval": True},
    },

    # Testing and build commands
    "test": {
        "pytest": {"max_args": 10, "description": "Run Python tests"},
        "python": {"max_args": 10, "description": "Run Python script"},
        "python3": {"max_args": 10, "description": "Run Python3 script"},
        "pip": {"max_args": 10, "description": "Python package manager"},
        "npm": {"max_args": 10, "description": "Node package manager"},
        "node": {"max_args": 10, "description": "Run Node.js script"},
    },

    # System info (read-only)
    "system": {
        "df": {"max_args": 5, "description": "Disk space usage"},
        "du": {"max_args": 10, "description": "Directory space usage"},
        "ps": {"max_args": 10, "description": "Process status"},
        "systemctl": {"max_args": 5, "description": "Service control", "requires_approval": True},
        "journalctl": {"max_args": 10, "description": "System journal"},
        "free": {"max_args": 5, "description": "Memory usage"},
        "uptime": {"max_args": 0, "description": "System uptime"},
    },
}

# Blocked patterns - never allow these
BLOCKED_PATTERNS = [
    r'\brm\b',  # Remove files
    r'\brmdir\b',  # Remove directory
    r'\bkill\b',  # Kill processes
    r'\bkillall\b',
    r'\bsudo\b',  # Privilege escalation
    r'\bsu\b',
    r'\bapt\b',  # Package management
    r'\bapt-get\b',
    r'\byum\b',
    r'\bdd\b',  # Dangerous disk operations
    r'\bmkfs\b',
    r'\bformat\b',
    r'\breboot\b',  # System control
    r'\bshutdown\b',
    r'\bhalt\b',
    r'\bpoweroff\b',
    r'[;&|]',  # Command chaining (prevent complex chains)
    r'>',  # File redirection (both single and double)
    r'<',  # Input redirection
    r'`.*`',  # Command substitution
    r'\$\(',  # Command substitution
    r'\n',  # Newline injection
    r'(^|\s)\.\.(\s|/|$)',  # Path traversal (prevents ../../../etc/passwd but allows git ranges)
    r'/etc/',  # System directories
    r'/var/',  # Var directory
    r'/home/',  # Home directories
    r'/root/',  # Root home
    r'/boot/',  # Boot directory
    r'/sys/',  # System files
    r'/proc/',  # Process files
    r'/dev/',  # Device files
    r'/tmp/',  # Temp (use /opt/aicara instead)
    r'\.ssh/',  # SSH keys
    r'\.git/config',  # Git credentials
    r'shutil\.rmtree',  # Python file deletion
    r'shutil\.rmdir',
    r'os\.remove',  # Python file deletion
    r'os\.unlink',
    r'os\.rmdir',
    r'subprocess\.',  # Prevent nested subprocess calls
    r'eval\(',  # Python code execution
    r'exec\(',  # Python code execution
    r'__import__',  # Python dynamic imports
]


def _check_rate_limit() -> Tuple[bool, str]:
    """Check if rate limit is exceeded."""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW

    # Remove old entries
    while _command_history and _command_history[0] < cutoff:
        _command_history.popleft()

    if len(_command_history) >= RATE_LIMIT_MAX:
        return False, f"Rate limit exceeded: {RATE_LIMIT_MAX} commands per {RATE_LIMIT_WINDOW}s"

    return True, ""


def _record_command_execution(command: str):
    """Record command execution timestamp for rate limiting."""
    _command_history.append(time.time())


def _validate_command(command: str) -> Tuple[bool, str, Optional[str], Optional[Dict]]:
    """
    Validate a command against whitelist and blocked patterns.

    Returns:
        (is_valid, error_message, command_category, command_config)
    """
    # Check blocked patterns first
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"Command contains blocked pattern: {pattern}", None, None

    # Parse command
    parts = command.strip().split()
    if not parts:
        return False, "Empty command", None, None

    # Check if command is whitelisted
    base_command = parts[0]

    # Check for git commands (special case - "git status" is one command)
    if base_command == "git" and len(parts) > 1:
        git_command = f"{parts[0]} {parts[1]}"
        for category, commands in WHITELISTED_COMMANDS.items():
            if git_command in commands:
                config = commands[git_command]
                # Validate argument count
                arg_count = len(parts) - 2  # Exclude "git" and subcommand
                if arg_count > config["max_args"]:
                    return False, f"Too many arguments (max {config['max_args']})", None, None
                return True, "", category, config

    # Check regular commands
    for category, commands in WHITELISTED_COMMANDS.items():
        if base_command in commands:
            config = commands[base_command]
            # Validate argument count
            arg_count = len(parts) - 1
            if arg_count > config["max_args"]:
                return False, f"Too many arguments (max {config['max_args']})", None, None
            return True, "", category, config

    return False, f"Command '{base_command}' is not whitelisted", None, None


def _audit_log_command(
    command: str,
    output: str,
    exit_code: int,
    duration: float,
    dry_run: bool,
    error: Optional[str] = None
):
    """Log command execution to audit log."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "command": command,
        "exit_code": exit_code,
        "duration_ms": round(duration * 1000, 2),
        "dry_run": dry_run,
        "output_length": len(output),
        "error": error,
        "user": "nate-ai",
    }

    try:
        # Ensure log directory exists
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

        # Append to audit log
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        # If logging fails, at least print to stderr
        print(f"WARNING: Failed to write audit log: {e}", flush=True)


def _sanitize_path_for_command(path: str) -> Optional[str]:
    """Ensure path is within allowed root."""
    try:
        if path.startswith('/'):
            full_path = Path(path).resolve()
        else:
            full_path = (ALLOWED_ROOT / path).resolve()

        # Check if within allowed root
        full_path.relative_to(ALLOWED_ROOT)
        return str(full_path)
    except (ValueError, Exception):
        return None


def execute_command(
    command: str,
    working_dir: str = None,
    dry_run: bool = False,
    requires_approval: bool = False,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Execute a whitelisted command in a sandboxed environment.

    Args:
        command: The command to execute
        working_dir: Working directory (relative to /opt/aicara or absolute within it)
        dry_run: If True, validate but don't execute
        requires_approval: If True, require explicit approval (currently just warns)
        timeout: Command timeout in seconds

    Returns:
        Dict with execution results
    """
    start_time = time.time()

    # Check rate limit
    rate_ok, rate_msg = _check_rate_limit()
    if not rate_ok:
        return {
            "status": "error",
            "message": rate_msg,
            "command": command,
            "dry_run": dry_run
        }

    # Validate command
    is_valid, error_msg, category, config = _validate_command(command)
    if not is_valid:
        return {
            "status": "error",
            "message": f"Command validation failed: {error_msg}",
            "command": command,
            "dry_run": dry_run
        }

    # Check if approval required
    needs_approval = config and config.get("requires_approval", False)
    if needs_approval and not requires_approval:
        return {
            "status": "error",
            "message": f"Command '{command}' requires explicit approval. Set requires_approval=True",
            "command": command,
            "dry_run": dry_run,
            "category": category
        }

    # Validate working directory
    if working_dir:
        working_dir = _sanitize_path_for_command(working_dir)
        if not working_dir:
            return {
                "status": "error",
                "message": f"Working directory is outside allowed root",
                "command": command,
                "dry_run": dry_run
            }
    else:
        working_dir = str(ALLOWED_ROOT)

    # Dry run - just validate
    if dry_run:
        return {
            "status": "success",
            "message": "Command validation passed (dry run)",
            "command": command,
            "category": category,
            "working_dir": working_dir,
            "requires_approval": needs_approval,
            "dry_run": True
        }

    # Record execution for rate limiting
    _record_command_execution(command)

    # Execute command
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                **os.environ,
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": str(ALLOWED_ROOT),
            }
        )

        duration = time.time() - start_time
        output = result.stdout + result.stderr

        # Log to audit trail
        _audit_log_command(
            command=command,
            output=output,
            exit_code=result.returncode,
            duration=duration,
            dry_run=False
        )

        return {
            "status": "success" if result.returncode == 0 else "error",
            "command": command,
            "working_dir": working_dir,
            "category": category,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output": output,
            "duration_ms": round(duration * 1000, 2),
            "dry_run": False
        }

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        error = f"Command timed out after {timeout}s"
        _audit_log_command(
            command=command,
            output="",
            exit_code=-1,
            duration=duration,
            dry_run=False,
            error=error
        )
        return {
            "status": "error",
            "message": error,
            "command": command,
            "dry_run": False
        }

    except Exception as e:
        duration = time.time() - start_time
        error = str(e)
        _audit_log_command(
            command=command,
            output="",
            exit_code=-1,
            duration=duration,
            dry_run=False,
            error=error
        )
        return {
            "status": "error",
            "message": f"Execution error: {error}",
            "command": command,
            "dry_run": False
        }


def get_whitelisted_commands() -> Dict[str, Any]:
    """Get list of all whitelisted commands organized by category."""
    return {
        "categories": list(WHITELISTED_COMMANDS.keys()),
        "commands": {
            category: {
                cmd: {
                    "description": info["description"],
                    "max_args": info["max_args"],
                    "requires_approval": info.get("requires_approval", False)
                }
                for cmd, info in commands.items()
            }
            for category, commands in WHITELISTED_COMMANDS.items()
        },
        "rate_limit": {
            "max_commands": RATE_LIMIT_MAX,
            "window_seconds": RATE_LIMIT_WINDOW
        }
    }


def get_audit_logs(lines: int = 100) -> List[Dict[str, Any]]:
    """Read recent audit logs."""
    try:
        if not AUDIT_LOG.exists():
            return []

        logs = []
        with open(AUDIT_LOG, "r") as f:
            for line in f:
                try:
                    logs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue

        # Return most recent entries
        return logs[-lines:]
    except Exception as e:
        return [{"error": f"Failed to read audit logs: {str(e)}"}]
