#!/usr/bin/env python3
"""
Nate Self-Development Tool - Level 1, 2 & 3

Level 1 (Read-Only Diagnostics):
- Inspect codebase, logs, and system health
- All operations are read-only

Level 2 (Safe Command Execution):
- Execute whitelisted commands in sandboxed environment
- Full audit logging and rate limiting
- Git workflow automation

Level 3 (Self-Maintenance):
- Safe file editing with validation and backup
- Automatic rollback on validation failure
- Test execution with coverage reporting
- Service control and restart
- Snapshot and rollback capabilities

Actions:
- read_file: Read a source file from the codebase
- search_code: Search for patterns in the codebase
- read_logs: Read system/service logs
- check_health: Get system health metrics
- list_directory: List files in a directory
- execute_command: Execute a whitelisted command (Level 2)
- git_workflow: Automate Git operations (Level 2)
- get_command_whitelist: Get list of whitelisted commands
- get_audit_logs: Read command execution audit logs
- edit_file: Edit files with validation and backup (Level 3)
- list_backups: List available file backups (Level 3)
- restore_backup: Restore file from backup (Level 3)
- run_tests: Run tests with coverage (Level 3)
- list_tests: List available tests (Level 3)
- get_test_history: Get recent test failures (Level 3)
- control_service: Control Nate services (start/stop/restart/status) (Level 3)
- get_service_status: Get service status (Level 3)
- restart_after_edit: Safely restart service after edits (Level 3)

Security:
- Level 1: Read-only, path traversal blocked
- Level 2: Command whitelist, rate limiting, full audit trail
- Level 3: Syntax validation, automatic backup/rollback, audit logging
- All operations within /opt/aicara (all services)
"""

import os
import re
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Level 2 imports
try:
    from backend.tools.command_executor import (
        execute_command as _execute_command,
        get_whitelisted_commands as _get_whitelisted_commands,
        get_audit_logs as _get_audit_logs
    )
    from backend.tools.git_workflow import (
        automated_workflow as _automated_workflow,
        get_current_status as _get_git_status
    )
    LEVEL_2_AVAILABLE = True
except ImportError:
    LEVEL_2_AVAILABLE = False

# Level 3 imports
try:
    from backend.tools.file_editor import FileEditor
    from backend.tools.test_executor import TestExecutor
    from backend.tools.service_controller import ServiceController
    _file_editor = FileEditor()
    _test_executor = TestExecutor()
    _service_controller = ServiceController()
    LEVEL_3_AVAILABLE = True
except ImportError:
    LEVEL_3_AVAILABLE = False

# Configuration - find substrate root dynamically
_current_file = Path(__file__).resolve()
SUBSTRATE_ROOT = _current_file.parent.parent.parent  # backend/tools -> backend -> substrate
BACKEND_ROOT = SUBSTRATE_ROOT / "backend"

# Security boundary - allow access to all services in /opt/aicara
ALLOWED_ROOT = Path("/opt/aicara").resolve()

# Protected files - contents will be redacted
PROTECTED_PATTERNS = [
    r'\.env$',
    r'\.env\.',
    r'secrets?\.json',
    r'credentials?\.json',
    r'\.pem$',
    r'\.key$',
    r'api_key',
    r'password',
    r'token',
    r'\.log$',  # Redact .log files to prevent sensitive data exposure
]

# Files that cannot be read at all
BLOCKED_FILES = [
    '.git/config',
    '.ssh/',
    'id_rsa',
    'id_ed25519',
]


def _is_protected_file(filepath: str) -> bool:
    """Check if a file contains sensitive data that should be redacted."""
    filepath_lower = filepath.lower()
    for pattern in PROTECTED_PATTERNS:
        if re.search(pattern, filepath_lower):
            return True
    return False


def _is_blocked_file(filepath: str) -> bool:
    """Check if a file should not be readable at all."""
    for blocked in BLOCKED_FILES:
        if blocked in filepath:
            return True
    return False


def _sanitize_path(requested_path: str) -> Optional[Path]:
    """Sanitize and validate a requested path."""
    try:
        if requested_path.startswith('/'):
            full_path = Path(requested_path).resolve()
        else:
            full_path = (SUBSTRATE_ROOT / requested_path).resolve()

        # Check if path is within allowed directories
        # Allow either within SUBSTRATE_ROOT itself OR within /opt/aicara (for other services)
        within_substrate = False
        within_opt_aicara = False

        try:
            full_path.relative_to(SUBSTRATE_ROOT)
            within_substrate = True
        except ValueError:
            pass

        try:
            full_path.relative_to(ALLOWED_ROOT)
            within_opt_aicara = True
        except ValueError:
            pass

        if not (within_substrate or within_opt_aicara):
            return None

        if _is_blocked_file(str(full_path)):
            return None

        return full_path
    except Exception:
        return None


def _sanitize_path_string(requested_path: str) -> Optional[str]:
    """Sanitize path and return as string (for git operations)."""
    sanitized = _sanitize_path(requested_path)
    return str(sanitized) if sanitized else None


def _get_display_path(full_path: Path) -> str:
    """Get display path relative to appropriate root."""
    try:
        return str(full_path.relative_to(SUBSTRATE_ROOT))
    except ValueError:
        try:
            return str(full_path.relative_to(ALLOWED_ROOT))
        except ValueError:
            return str(full_path)


def _redact_sensitive_content(content: str, filepath: str) -> str:
    """Redact sensitive information from file content."""
    if not _is_protected_file(filepath):
        return content

    patterns = [
        (r'(api[_-]?key\s*[=:]\s*)["\']?[\w-]+["\']?', r'\1[REDACTED]'),
        (r'(password\s*[=:]\s*)["\']?[^\s"\']+["\']?', r'\1[REDACTED]'),
        (r'(token\s*[=:]\s*)["\']?[\w.-]+["\']?', r'\1[REDACTED]'),
        (r'(secret\s*[=:]\s*)["\']?[^\s"\']+["\']?', r'\1[REDACTED]'),
        (r'(DISCORD_[A-Z_]+\s*=\s*)[^\s\n]+', r'\1[REDACTED]'),
        (r'(OPENROUTER_[A-Z_]+\s*=\s*)[^\s\n]+', r'\1[REDACTED]'),
        (r'(VENICE_[A-Z_]+\s*=\s*)[^\s\n]+', r'\1[REDACTED]'),
        (r'(POSTGRES_[A-Z_]+\s*=\s*)[^\s\n]+', r'\1[REDACTED]'),
        (r'(XAI_[A-Z_]+\s*=\s*)[^\s\n]+', r'\1[REDACTED]'),
        (r'(GROK_[A-Z_]+\s*=\s*)[^\s\n]+', r'\1[REDACTED]'),
    ]

    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)

    return content


# ============================================
# TOOL ACTIONS
# ============================================

def _action_read_file(
    path: str,
    start_line: int = 1,
    end_line: int = -1
) -> Dict[str, Any]:
    """Read a source file from the codebase."""
    safe_path = _sanitize_path(path)
    if safe_path is None:
        return {
            "status": "error",
            "message": f"Path '{path}' is outside allowed directories or blocked"
        }

    if not safe_path.exists():
        return {"status": "error", "message": f"File not found: {path}"}

    if safe_path.is_dir():
        return {"status": "error", "message": f"Path is a directory: {path}"}

    try:
        content = safe_path.read_text(encoding='utf-8', errors='replace')
        lines = content.splitlines()
        total_lines = len(lines)

        start_idx = max(0, start_line - 1)
        end_idx = total_lines if end_line == -1 else min(end_line, total_lines)

        selected_lines = lines[start_idx:end_idx]
        selected_content = '\n'.join(selected_lines)
        selected_content = _redact_sensitive_content(selected_content, str(safe_path))

        return {
            "status": "success",
            "path": _get_display_path(safe_path),
            "content": selected_content,
            "total_lines": total_lines,
            "lines_shown": f"{start_line}-{end_idx}",
            "is_protected": _is_protected_file(str(safe_path))
        }
    except Exception as e:
        return {"status": "error", "message": f"Error reading file: {str(e)}"}


def _action_search_code(
    pattern: str,
    path: str = "backend",
    file_pattern: str = "*.py",
    max_results: int = 50,
    context_lines: int = 2
) -> Dict[str, Any]:
    """Search for patterns in the codebase."""
    search_path = _sanitize_path(path)
    if search_path is None:
        return {"status": "error", "message": f"Invalid search path: {path}"}

    if not search_path.exists():
        return {"status": "error", "message": f"Path not found: {path}"}

    try:
        compiled_pattern = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {"status": "error", "message": f"Invalid regex: {str(e)}"}

    results = []
    files_searched = 0

    try:
        for filepath in search_path.rglob(file_pattern):
            if filepath.is_file() and not _is_blocked_file(str(filepath)):
                files_searched += 1
                try:
                    content = filepath.read_text(encoding='utf-8', errors='replace')
                    lines = content.splitlines()

                    for i, line in enumerate(lines):
                        if compiled_pattern.search(line):
                            start = max(0, i - context_lines)
                            end = min(len(lines), i + context_lines + 1)
                            context = '\n'.join(lines[start:end])

                            if _is_protected_file(str(filepath)):
                                context = _redact_sensitive_content(context, str(filepath))

                            results.append({
                                "file": _get_display_path(filepath),
                                "line_number": i + 1,
                                "match": line.strip()[:200],
                                "context": context
                            })

                            if len(results) >= max_results:
                                break
                except Exception:
                    continue

            if len(results) >= max_results:
                break

        return {
            "status": "success",
            "pattern": pattern,
            "files_searched": files_searched,
            "matches_found": len(results),
            "results": results,
            "truncated": len(results) >= max_results
        }
    except Exception as e:
        return {"status": "error", "message": f"Search error: {str(e)}"}


def _action_read_logs(
    log_type: str = "backend",
    lines: int = 100,
    filter_pattern: str = None,
    since_minutes: int = None
) -> Dict[str, Any]:
    """Read system logs."""
    service_map = {
        "backend": "nate-substrate",
        "discord": "nate-substrate",
        "telegram": "nate-telegram",
        "system": None
    }

    service = service_map.get(log_type, "nate-substrate")

    try:
        if service:
            cmd = ["journalctl", "-u", service, "-n", str(lines), "--no-pager"]
        else:
            cmd = ["journalctl", "-n", str(lines), "--no-pager"]

        if since_minutes:
            cmd.extend(["--since", f"{since_minutes} minutes ago"])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        log_content = result.stdout

        if filter_pattern:
            try:
                compiled = re.compile(filter_pattern, re.IGNORECASE)
                log_content = '\n'.join(
                    line for line in log_content.splitlines()
                    if compiled.search(line)
                )
            except re.error:
                pass

        log_content = _redact_sensitive_content(log_content, "logs")

        return {
            "status": "success",
            "log_type": log_type,
            "service": service or "system",
            "content": log_content,
            "line_count": len(log_content.splitlines())
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Log read timed out"}
    except Exception as e:
        return {"status": "error", "message": f"Error reading logs: {str(e)}"}


def _action_check_health() -> Dict[str, Any]:
    """Get system health and status information."""
    health = {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "services": {},
        "system": {},
        "codebase": {}
    }

    # Check service status
    for service in ["nate-substrate", "nate-telegram"]:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True, text=True, timeout=5
            )
            health["services"][service] = result.stdout.strip()
        except Exception:
            health["services"][service] = "unknown"

    # System info
    try:
        result = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
        health["system"]["memory"] = result.stdout

        result = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
        health["system"]["uptime"] = result.stdout.strip()
    except Exception as e:
        health["system"]["error"] = str(e)

    # Codebase stats
    try:
        py_files = list(BACKEND_ROOT.rglob("*.py"))
        health["codebase"]["python_files"] = len(py_files)
        health["codebase"]["root"] = str(SUBSTRATE_ROOT)
    except Exception as e:
        health["codebase"]["error"] = str(e)

    # Recent errors
    try:
        result = subprocess.run(
            ["journalctl", "-u", "nate-substrate", "--since", "10 minutes ago",
             "-p", "err", "--no-pager", "-n", "10"],
            capture_output=True, text=True, timeout=10
        )
        health["recent_errors"] = result.stdout.strip() or "No recent errors"
    except Exception:
        health["recent_errors"] = "Could not fetch"

    return health


def _action_list_directory(path: str = "backend", pattern: str = None) -> Dict[str, Any]:
    """List files in a directory."""
    dir_path = _sanitize_path(path)
    if dir_path is None:
        return {"status": "error", "message": f"Invalid path: {path}"}

    if not dir_path.exists():
        return {"status": "error", "message": f"Directory not found: {path}"}

    if not dir_path.is_dir():
        return {"status": "error", "message": f"Not a directory: {path}"}

    try:
        if pattern:
            files = list(dir_path.glob(pattern))
        else:
            files = list(dir_path.iterdir())

        entries = []
        for f in sorted(files):
            if _is_blocked_file(str(f)):
                continue
            entry = {
                "name": f.name,
                "type": "directory" if f.is_dir() else "file",
                "path": _get_display_path(f)
            }
            if f.is_file():
                entry["size"] = f.stat().st_size
            entries.append(entry)

        return {
            "status": "success",
            "path": _get_display_path(dir_path),
            "entries": entries,
            "count": len(entries)
        }
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}


# ============================================
# MAIN TOOL FUNCTION
# ============================================

def nate_dev_tool(
    action: str,
    # read_file params
    path: str = None,
    start_line: int = 1,
    end_line: int = -1,
    # search_code params
    pattern: str = None,
    file_pattern: str = "*.py",
    max_results: int = 50,
    context_lines: int = 2,
    # read_logs params
    log_type: str = "backend",
    lines: int = 100,
    filter_pattern: str = None,
    since_minutes: int = None,
    # Level 2: execute_command params
    command: str = None,
    working_dir: str = None,
    dry_run: bool = False,
    requires_approval: bool = False,
    timeout: int = 30,
    # Level 2: git_workflow params
    feature_name: str = None,
    commit_message: str = None,
    pr_title: str = None,
    pr_body: str = None,
    files: List[str] = None,
    run_tests: bool = True,
    base_branch: str = "main",
    # Level 3: edit_file params
    changes: List[Dict[str, Any]] = None,
    validate: bool = True,
    backup_file: str = None,
    # Level 3: test_executor params
    test_path: str = None,
    test_pattern: str = None,
    test_markers: str = None,
    coverage: bool = True,
    verbose: bool = True,
    stop_on_first_failure: bool = False,
    # Level 3: service_controller params
    service: str = None,
    operation: str = None
) -> Dict[str, Any]:
    """
    Nate's self-development tool for inspecting and managing his own codebase.

    Level 1 (READ-ONLY):
    - read_file: Read a source file (path required)
    - search_code: Search codebase (pattern required)
    - read_logs: Read system logs
    - check_health: Get system health
    - list_directory: List files

    Level 2 (SAFE EXECUTION):
    - execute_command: Run whitelisted command (command required)
    - git_workflow: Automate Git operations (feature_name, commit_message required)
    - git_status: Get current Git status
    - get_command_whitelist: List whitelisted commands
    - get_audit_logs: Read command execution audit trail

    Level 3 (SELF-MAINTENANCE):
    - edit_file: Edit files with validation and backup (path, changes required)
    - list_backups: List available backups (optional: path)
    - restore_backup: Restore file from backup (backup_file required)
    - run_tests: Run tests with coverage (optional: test_path, pattern, markers)
    - list_tests: List available tests without running them
    - get_test_history: Get recent test failures
    - control_service: Control services (service, operation required)
    - get_service_status: Get service status (optional: service)
    - restart_after_edit: Restart service after edits (service required)

    Examples:
    - nate_dev_tool(action="read_file", path="backend/core/consciousness_loop.py")
    - nate_dev_tool(action="execute_command", command="ls -la /opt/aicara", dry_run=True)
    - nate_dev_tool(action="git_workflow", feature_name="fix-bug", commit_message="Fix bug X")
    - nate_dev_tool(action="edit_file", path="backend/tools/test.py", changes=[...], dry_run=True)
    - nate_dev_tool(action="list_backups", path="backend/tools/test.py")
    - nate_dev_tool(action="run_tests", test_path="test_file.py", coverage=True)
    - nate_dev_tool(action="control_service", service="nate-substrate", operation="restart")
    """

    if action == "read_file":
        if not path:
            return {"status": "error", "message": "path is required for read_file"}
        return _action_read_file(path, start_line, end_line)

    elif action == "search_code":
        if not pattern:
            return {"status": "error", "message": "pattern is required for search_code"}
        return _action_search_code(pattern, path or "backend", file_pattern, max_results, context_lines)

    elif action == "read_logs":
        return _action_read_logs(log_type, lines, filter_pattern, since_minutes)

    elif action == "check_health":
        return _action_check_health()

    elif action == "list_directory":
        return _action_list_directory(path or "backend", None)

    # Level 2 Actions
    elif action == "execute_command":
        if not LEVEL_2_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 2 functionality not available. Missing dependencies."
            }
        if not command:
            return {"status": "error", "message": "command is required for execute_command"}
        return _execute_command(
            command=command,
            working_dir=working_dir,
            dry_run=dry_run,
            requires_approval=requires_approval,
            timeout=timeout
        )

    elif action == "get_command_whitelist":
        if not LEVEL_2_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 2 functionality not available"
            }
        return _get_whitelisted_commands()

    elif action == "get_audit_logs":
        if not LEVEL_2_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 2 functionality not available"
            }
        return {"status": "success", "logs": _get_audit_logs(lines)}

    elif action == "git_workflow":
        if not LEVEL_2_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 2 functionality not available"
            }
        if not feature_name or not commit_message:
            return {
                "status": "error",
                "message": "feature_name and commit_message are required for git_workflow"
            }

        # Validate working_dir is within sandbox
        if working_dir:
            repo_path = _sanitize_path_string(working_dir)
            if not repo_path:
                return {
                    "status": "error",
                    "message": f"Working directory '{working_dir}' is outside allowed sandbox"
                }
        else:
            repo_path = str(SUBSTRATE_ROOT)

        return _automated_workflow(
            repo_path=repo_path,
            feature_name=feature_name,
            commit_message=commit_message,
            pr_title=pr_title or f"[Nate] {feature_name}",
            pr_body=pr_body or commit_message,
            files=files,
            run_tests=run_tests,
            base_branch=base_branch
        )

    elif action == "git_status":
        if not LEVEL_2_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 2 functionality not available"
            }

        # Validate working_dir is within sandbox
        if working_dir:
            repo_path = _sanitize_path_string(working_dir)
            if not repo_path:
                return {
                    "status": "error",
                    "message": f"Working directory '{working_dir}' is outside allowed sandbox"
                }
        else:
            repo_path = str(SUBSTRATE_ROOT)

        return _get_git_status(repo_path)

    # Level 3 Actions
    elif action == "edit_file":
        if not LEVEL_3_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 3 functionality not available. Missing dependencies."
            }
        if not path:
            return {"status": "error", "message": "path is required for edit_file"}
        if not changes:
            return {"status": "error", "message": "changes is required for edit_file"}

        return _file_editor.edit_file(
            filepath=path,
            changes=changes,
            validate=validate,
            dry_run=dry_run
        )

    elif action == "list_backups":
        if not LEVEL_3_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 3 functionality not available"
            }
        return _file_editor.list_backups(filepath=path)

    elif action == "restore_backup":
        if not LEVEL_3_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 3 functionality not available"
            }
        if not backup_file:
            return {"status": "error", "message": "backup_file is required for restore_backup"}

        return _file_editor.restore_from_backup(backup_file=backup_file)

    elif action == "run_tests":
        if not LEVEL_3_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 3 functionality not available"
            }
        return _test_executor.run_tests(
            test_path=test_path,
            pattern=test_pattern,
            markers=test_markers,
            coverage=coverage,
            verbose=verbose,
            stop_on_first_failure=stop_on_first_failure
        )

    elif action == "list_tests":
        if not LEVEL_3_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 3 functionality not available"
            }
        return _test_executor.list_tests(test_path=test_path)

    elif action == "get_test_history":
        if not LEVEL_3_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 3 functionality not available"
            }
        return _test_executor.get_test_history()

    elif action == "control_service":
        if not LEVEL_3_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 3 functionality not available"
            }
        if not service:
            return {"status": "error", "message": "service is required for control_service"}
        if not operation:
            return {"status": "error", "message": "operation is required for control_service"}

        return _service_controller.control_service(
            service=service,
            operation=operation,
            dry_run=dry_run
        )

    elif action == "get_service_status":
        if not LEVEL_3_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 3 functionality not available"
            }
        return _service_controller.get_service_status(service=service)

    elif action == "restart_after_edit":
        if not LEVEL_3_AVAILABLE:
            return {
                "status": "error",
                "message": "Level 3 functionality not available"
            }
        if not service:
            return {"status": "error", "message": "service is required for restart_after_edit"}

        return _service_controller.restart_after_edit(service=service)

    else:
        available_actions = [
            "read_file", "search_code", "read_logs", "check_health", "list_directory"
        ]
        if LEVEL_2_AVAILABLE:
            available_actions.extend([
                "execute_command", "git_workflow", "git_status",
                "get_command_whitelist", "get_audit_logs"
            ])
        if LEVEL_3_AVAILABLE:
            available_actions.extend([
                "edit_file", "list_backups", "restore_backup",
                "run_tests", "list_tests", "get_test_history",
                "control_service", "get_service_status", "restart_after_edit"
            ])

        return {
            "status": "error",
            "message": f"Unknown action: {action}",
            "available_actions": available_actions,
            "level_2_available": LEVEL_2_AVAILABLE,
            "level_3_available": LEVEL_3_AVAILABLE
        }


# Tool schema for consciousness loop
NATE_DEV_TOOL_SCHEMA = {
    "name": "nate_dev_tool",
    "description": """Nate's self-development tool for inspecting his own codebase, logs, and system health. Level 1 is READ-ONLY.

Use this to:
- Investigate bugs in your own code
- Understand how your features work
- Check system health and recent errors
- Search for where functions are defined
- Explore your codebase structure

Actions:
- read_file: Read source code (requires path)
- search_code: Search for patterns (requires pattern)
- read_logs: Read system/service logs
- check_health: Get system health metrics
- list_directory: List files in a directory""",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform",
                "enum": ["read_file", "search_code", "read_logs", "check_health", "list_directory"]
            },
            "path": {
                "type": "string",
                "description": "File or directory path (relative to substrate root)"
            },
            "start_line": {
                "type": "integer",
                "description": "Starting line for read_file (1-indexed)",
                "default": 1
            },
            "end_line": {
                "type": "integer",
                "description": "Ending line for read_file (-1 for end)",
                "default": -1
            },
            "pattern": {
                "type": "string",
                "description": "Regex pattern for search_code"
            },
            "file_pattern": {
                "type": "string",
                "description": "Glob pattern for files (e.g., *.py)",
                "default": "*.py"
            },
            "max_results": {
                "type": "integer",
                "description": "Max search results",
                "default": 50
            },
            "context_lines": {
                "type": "integer",
                "description": "Context lines around matches",
                "default": 2
            },
            "log_type": {
                "type": "string",
                "description": "Log type for read_logs",
                "enum": ["backend", "discord", "telegram", "system"],
                "default": "backend"
            },
            "lines": {
                "type": "integer",
                "description": "Number of log lines",
                "default": 100
            },
            "filter_pattern": {
                "type": "string",
                "description": "Regex to filter logs"
            },
            "since_minutes": {
                "type": "integer",
                "description": "Only logs from last N minutes"
            }
        },
        "required": ["action"]
    }
}


if __name__ == "__main__":
    # Test the tool
    print("Testing nate_dev_tool...")
    print("\n1. Check Health:")
    print(json.dumps(nate_dev_tool(action="check_health"), indent=2))

    print("\n2. List Directory:")
    print(json.dumps(nate_dev_tool(action="list_directory", path="backend/tools"), indent=2))

    print("\n3. Search Code:")
    print(json.dumps(nate_dev_tool(action="search_code", pattern="def discord_tool", max_results=5), indent=2))
