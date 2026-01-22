#!/usr/bin/env python3
"""
Agent Self-Development MCP Server - Level 1 (Read-Only Diagnostics)

This MCP server gives the agent the ability to inspect and understand its own codebase,
logs, and system health. Level 1 is READ-ONLY - no modifications allowed.

Tools available:
- read_source_file: Read any source file in the codebase
- search_code: Search for patterns in the codebase (grep-like)
- read_logs: Read system logs with filtering
- check_health: Get system health and status info
- list_directory: List files in a directory
- get_config: Read current configuration

Security:
- All operations are read-only
- Protected files (secrets, .env) are redacted
- Path traversal is blocked
- Only operates within /opt/substrate (all services)
"""

import os
import sys
import json
import re
import subprocess
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

# MCP imports - using the stdio server pattern
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("WARNING: MCP library not available. Install with: pip install mcp", file=sys.stderr)

# Configuration
SUBSTRATE_ROOT = Path(__file__).parent.parent.parent.resolve()
BACKEND_ROOT = SUBSTRATE_ROOT / "backend"
LOGS_DIR = SUBSTRATE_ROOT / "logs"

# Security boundary - allow access to all services in /opt/substrate
ALLOWED_ROOT = Path("/opt/substrate").resolve()

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

def is_protected_file(filepath: str) -> bool:
    """Check if a file contains sensitive data that should be redacted."""
    filepath_lower = filepath.lower()
    for pattern in PROTECTED_PATTERNS:
        if re.search(pattern, filepath_lower):
            return True
    return False

def is_blocked_file(filepath: str) -> bool:
    """Check if a file should not be readable at all."""
    for blocked in BLOCKED_FILES:
        if blocked in filepath:
            return True
    return False

def sanitize_path(requested_path: str) -> Optional[Path]:
    """
    Sanitize and validate a requested path.
    Returns None if the path is invalid or outside allowed directories.
    """
    try:
        # Resolve the path
        if requested_path.startswith('/'):
            full_path = Path(requested_path).resolve()
        else:
            full_path = (SUBSTRATE_ROOT / requested_path).resolve()

        # Check if path is within allowed directories (/opt/substrate)
        try:
            full_path.relative_to(ALLOWED_ROOT)
        except ValueError:
            return None

        # Check for blocked files
        if is_blocked_file(str(full_path)):
            return None

        return full_path
    except Exception:
        return None

def redact_sensitive_content(content: str, filepath: str) -> str:
    """Redact sensitive information from file content."""
    if not is_protected_file(filepath):
        return content

    # Redact patterns that look like secrets
    patterns = [
        (r'(api[_-]?key\s*[=:]\s*)["\']?[\w-]+["\']?', r'\1[REDACTED]'),
        (r'(password\s*[=:]\s*)["\']?[^\s"\']+["\']?', r'\1[REDACTED]'),
        (r'(token\s*[=:]\s*)["\']?[\w.-]+["\']?', r'\1[REDACTED]'),
        (r'(secret\s*[=:]\s*)["\']?[^\s"\']+["\']?', r'\1[REDACTED]'),
        (r'(DISCORD_[A-Z_]+\s*=\s*)[^\s\n]+', r'\1[REDACTED]'),
        (r'(OPENROUTER_[A-Z_]+\s*=\s*)[^\s\n]+', r'\1[REDACTED]'),
        (r'(VENICE_[A-Z_]+\s*=\s*)[^\s\n]+', r'\1[REDACTED]'),
        (r'(POSTGRES_[A-Z_]+\s*=\s*)[^\s\n]+', r'\1[REDACTED]'),
    ]

    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)

    return content


# ============================================
# MCP TOOLS - Level 1 (Read-Only)
# ============================================

async def read_source_file(path: str, start_line: int = 1, end_line: int = -1) -> Dict[str, Any]:
    """
    Read a source file from the agent's codebase.

    Args:
        path: Relative path from substrate root, or absolute path within substrate
        start_line: Starting line number (1-indexed, default: 1)
        end_line: Ending line number (-1 for end of file)

    Returns:
        Dict with file content, line count, and metadata
    """
    safe_path = sanitize_path(path)
    if safe_path is None:
        return {
            "status": "error",
            "message": f"Path '{path}' is outside allowed directories or blocked"
        }

    if not safe_path.exists():
        return {
            "status": "error",
            "message": f"File not found: {path}"
        }

    if safe_path.is_dir():
        return {
            "status": "error",
            "message": f"Path is a directory, not a file: {path}"
        }

    try:
        content = safe_path.read_text(encoding='utf-8', errors='replace')
        lines = content.splitlines()
        total_lines = len(lines)

        # Handle line range
        start_idx = max(0, start_line - 1)
        end_idx = total_lines if end_line == -1 else min(end_line, total_lines)

        selected_lines = lines[start_idx:end_idx]
        selected_content = '\n'.join(selected_lines)

        # Redact if needed
        selected_content = redact_sensitive_content(selected_content, str(safe_path))

        return {
            "status": "success",
            "path": str(safe_path.relative_to(ALLOWED_ROOT)),
            "content": selected_content,
            "total_lines": total_lines,
            "lines_shown": f"{start_line}-{end_idx}",
            "is_protected": is_protected_file(str(safe_path))
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error reading file: {str(e)}"
        }


async def search_code(
    pattern: str,
    path: str = "backend",
    file_pattern: str = "*.py",
    max_results: int = 50,
    context_lines: int = 2
) -> Dict[str, Any]:
    """
    Search for a pattern in the codebase (grep-like functionality).

    Args:
        pattern: Regex pattern to search for
        path: Directory to search in (relative to substrate root)
        file_pattern: Glob pattern for files to search (default: *.py)
        max_results: Maximum number of matches to return
        context_lines: Number of context lines before/after match

    Returns:
        Dict with search results
    """
    search_path = sanitize_path(path)
    if search_path is None:
        return {
            "status": "error",
            "message": f"Invalid search path: {path}"
        }

    if not search_path.exists():
        return {
            "status": "error",
            "message": f"Path not found: {path}"
        }

    results = []
    files_searched = 0

    try:
        compiled_pattern = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {
            "status": "error",
            "message": f"Invalid regex pattern: {str(e)}"
        }

    try:
        for filepath in search_path.rglob(file_pattern):
            if filepath.is_file() and not is_blocked_file(str(filepath)):
                files_searched += 1
                try:
                    content = filepath.read_text(encoding='utf-8', errors='replace')
                    lines = content.splitlines()

                    for i, line in enumerate(lines):
                        if compiled_pattern.search(line):
                            # Get context
                            start = max(0, i - context_lines)
                            end = min(len(lines), i + context_lines + 1)
                            context = '\n'.join(lines[start:end])

                            # Redact if protected
                            if is_protected_file(str(filepath)):
                                context = redact_sensitive_content(context, str(filepath))

                            results.append({
                                "file": str(filepath.relative_to(ALLOWED_ROOT)),
                                "line_number": i + 1,
                                "match": line.strip()[:200],  # Truncate long lines
                                "context": context
                            })

                            if len(results) >= max_results:
                                break
                except Exception:
                    continue  # Skip files that can't be read

            if len(results) >= max_results:
                break

        return {
            "status": "success",
            "pattern": pattern,
            "path": path,
            "file_pattern": file_pattern,
            "files_searched": files_searched,
            "matches_found": len(results),
            "results": results,
            "truncated": len(results) >= max_results
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Search error: {str(e)}"
        }


async def read_logs(
    log_type: str = "backend",
    lines: int = 100,
    filter_pattern: str = None,
    since_minutes: int = None
) -> Dict[str, Any]:
    """
    Read system logs.

    Args:
        log_type: Type of log (backend, discord, telegram, system)
        lines: Number of lines to return (from end)
        filter_pattern: Optional regex to filter log lines
        since_minutes: Only show logs from last N minutes

    Returns:
        Dict with log content
    """
    # Try journalctl for systemd logs first
    service_map = {
        "backend": "substrate-agent",
        "discord": "substrate-agent",  # Discord is part of backend
        "telegram": "substrate-telegram",
        "system": None  # System logs
    }

    service = service_map.get(log_type)

    try:
        if service:
            cmd = ["journalctl", "-u", service, "-n", str(lines), "--no-pager"]
            if since_minutes:
                cmd.extend(["--since", f"{since_minutes} minutes ago"])
        else:
            cmd = ["journalctl", "-n", str(lines), "--no-pager"]
            if since_minutes:
                cmd.extend(["--since", f"{since_minutes} minutes ago"])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        log_content = result.stdout

        # Apply filter if specified
        if filter_pattern and log_content:
            try:
                compiled = re.compile(filter_pattern, re.IGNORECASE)
                log_content = '\n'.join(
                    line for line in log_content.splitlines()
                    if compiled.search(line)
                )
            except re.error:
                pass  # Invalid regex, skip filtering

        # Redact sensitive info from logs
        log_content = redact_sensitive_content(log_content, "logs")

        return {
            "status": "success",
            "log_type": log_type,
            "service": service or "system",
            "lines_requested": lines,
            "filter": filter_pattern,
            "content": log_content,
            "line_count": len(log_content.splitlines())
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Log read timed out"}
    except FileNotFoundError:
        # journalctl not available, try file-based logs
        return {"status": "error", "message": "journalctl not available and no log files found"}
    except Exception as e:
        return {"status": "error", "message": f"Error reading logs: {str(e)}"}


async def check_health() -> Dict[str, Any]:
    """
    Get system health and status information.

    Returns:
        Dict with health metrics including:
        - Service status
        - Memory usage
        - Recent errors
        - Uptime
        - Active sessions
    """
    health = {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "services": {},
        "system": {},
        "codebase": {}
    }

    # Check service status
    services = ["substrate-agent", "substrate-telegram"]
    for service in services:
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
        # Memory
        result = subprocess.run(
            ["free", "-h"], capture_output=True, text=True, timeout=5
        )
        health["system"]["memory"] = result.stdout

        # Disk
        result = subprocess.run(
            ["df", "-h", str(SUBSTRATE_ROOT)],
            capture_output=True, text=True, timeout=5
        )
        health["system"]["disk"] = result.stdout

        # Uptime
        result = subprocess.run(
            ["uptime"], capture_output=True, text=True, timeout=5
        )
        health["system"]["uptime"] = result.stdout.strip()
    except Exception as e:
        health["system"]["error"] = str(e)

    # Codebase stats
    try:
        py_files = list(BACKEND_ROOT.rglob("*.py"))
        health["codebase"]["python_files"] = len(py_files)
        health["codebase"]["total_lines"] = sum(
            len(f.read_text(errors='replace').splitlines())
            for f in py_files if f.is_file()
        )
        health["codebase"]["root"] = str(SUBSTRATE_ROOT)
    except Exception as e:
        health["codebase"]["error"] = str(e)

    # Recent errors from logs (last 10 minutes)
    try:
        result = subprocess.run(
            ["journalctl", "-u", "substrate-agent", "--since", "10 minutes ago",
             "-p", "err", "--no-pager", "-n", "20"],
            capture_output=True, text=True, timeout=10
        )
        errors = result.stdout.strip()
        health["recent_errors"] = errors if errors else "No recent errors"
    except Exception:
        health["recent_errors"] = "Could not fetch error logs"

    return health


async def list_directory(path: str = "backend", pattern: str = None) -> Dict[str, Any]:
    """
    List files in a directory.

    Args:
        path: Directory path relative to substrate root
        pattern: Optional glob pattern to filter files

    Returns:
        Dict with directory listing
    """
    dir_path = sanitize_path(path)
    if dir_path is None:
        return {"status": "error", "message": f"Invalid path: {path}"}

    if not dir_path.exists():
        return {"status": "error", "message": f"Directory not found: {path}"}

    if not dir_path.is_dir():
        return {"status": "error", "message": f"Path is not a directory: {path}"}

    try:
        if pattern:
            files = list(dir_path.glob(pattern))
        else:
            files = list(dir_path.iterdir())

        entries = []
        for f in sorted(files):
            if is_blocked_file(str(f)):
                continue
            entry = {
                "name": f.name,
                "type": "directory" if f.is_dir() else "file",
                "path": str(f.relative_to(ALLOWED_ROOT))
            }
            if f.is_file():
                entry["size"] = f.stat().st_size
                entry["modified"] = datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            entries.append(entry)

        return {
            "status": "success",
            "path": str(dir_path.relative_to(ALLOWED_ROOT)),
            "entries": entries,
            "count": len(entries)
        }
    except Exception as e:
        return {"status": "error", "message": f"Error listing directory: {str(e)}"}


async def get_config(config_type: str = "all") -> Dict[str, Any]:
    """
    Get current configuration information.

    Args:
        config_type: Type of config to get (all, model, memory, tools)

    Returns:
        Dict with configuration information (sensitive values redacted)
    """
    config = {"status": "success", "config_type": config_type}

    # Read .env.example to show what config options exist
    env_example = SUBSTRATE_ROOT / ".env.example"
    if env_example.exists():
        content = env_example.read_text()
        config["available_options"] = content

    # Check which services are configured
    backend_env = BACKEND_ROOT / ".env"
    if backend_env.exists():
        env_content = backend_env.read_text()
        config["configured_keys"] = [
            line.split('=')[0] for line in env_content.splitlines()
            if line and not line.startswith('#') and '=' in line
        ]

    # Get model configuration from code
    config_file = BACKEND_ROOT / "core" / "config.py"
    if config_file.exists():
        config["config_file"] = str(config_file.relative_to(ALLOWED_ROOT))

    return config


# ============================================
# MCP SERVER SETUP
# ============================================

def create_server():
    """Create and configure the MCP server."""
    if not MCP_AVAILABLE:
        print("ERROR: MCP library not available", file=sys.stderr)
        sys.exit(1)

    server = Server("agent-dev")

    # Register tools
    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="read_source_file",
                description="Read a source file from the agent's codebase. Use this to examine code, understand how features work, or investigate bugs.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to substrate root (e.g., 'backend/core/consciousness_loop.py')"
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "Starting line number (1-indexed)",
                            "default": 1
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "Ending line number (-1 for end of file)",
                            "default": -1
                        }
                    },
                    "required": ["path"]
                }
            ),
            Tool(
                name="search_code",
                description="Search for patterns in the codebase (grep-like). Use this to find where functions are defined, trace code paths, or find usages.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Regex pattern to search for"
                        },
                        "path": {
                            "type": "string",
                            "description": "Directory to search in",
                            "default": "backend"
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": "Glob pattern for files (e.g., '*.py')",
                            "default": "*.py"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum results to return",
                            "default": 50
                        },
                        "context_lines": {
                            "type": "integer",
                            "description": "Context lines before/after match",
                            "default": 2
                        }
                    },
                    "required": ["pattern"]
                }
            ),
            Tool(
                name="read_logs",
                description="Read system logs to diagnose issues. Use this to see errors, trace execution flow, or understand what happened.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "log_type": {
                            "type": "string",
                            "description": "Type of log: backend, discord, telegram, system",
                            "enum": ["backend", "discord", "telegram", "system"],
                            "default": "backend"
                        },
                        "lines": {
                            "type": "integer",
                            "description": "Number of lines to return",
                            "default": 100
                        },
                        "filter_pattern": {
                            "type": "string",
                            "description": "Regex to filter log lines"
                        },
                        "since_minutes": {
                            "type": "integer",
                            "description": "Only show logs from last N minutes"
                        }
                    }
                }
            ),
            Tool(
                name="check_health",
                description="Get system health and status. Use this to check if services are running, see resource usage, or find recent errors.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="list_directory",
                description="List files in a directory. Use this to explore the codebase structure.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path",
                            "default": "backend"
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern to filter"
                        }
                    }
                }
            ),
            Tool(
                name="get_config",
                description="Get current configuration information (sensitive values redacted).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "config_type": {
                            "type": "string",
                            "description": "Type of config to get",
                            "enum": ["all", "model", "memory", "tools"],
                            "default": "all"
                        }
                    }
                }
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Handle tool calls."""
        handlers = {
            "read_source_file": read_source_file,
            "search_code": search_code,
            "read_logs": read_logs,
            "check_health": check_health,
            "list_directory": list_directory,
            "get_config": get_config
        }

        handler = handlers.get(name)
        if not handler:
            return [TextContent(type="text", text=json.dumps({
                "status": "error",
                "message": f"Unknown tool: {name}"
            }))]

        result = await handler(**arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    return server


async def main():
    """Run the MCP server."""
    server = create_server()
    print(f"🔧 Agent Dev MCP Server starting...", file=sys.stderr)
    print(f"   Substrate root: {SUBSTRATE_ROOT}", file=sys.stderr)
    print(f"   Allowed access: {ALLOWED_ROOT}", file=sys.stderr)
    print(f"   Level: 1 (Read-Only)", file=sys.stderr)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
