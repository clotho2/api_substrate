#!/usr/bin/env python3
"""
Nate File Editor - Level 3

Safe file editing with validation, backup, and auto-rollback.
This allows Nate to fix bugs and make improvements, not just point at them.

Features:
- Syntax validation (Python, JSON, YAML, JS, etc.)
- Automatic backup before changes
- Auto-rollback on validation failure
- Diff preview before applying
- Line-by-line or whole-file edits
"""

import os
import re
import json
import yaml
import shutil
import subprocess
import ast
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime


# Configuration
_current_file = Path(__file__).resolve()
SUBSTRATE_ROOT = _current_file.parent.parent.parent  # backend/tools -> backend -> substrate
ALLOWED_ROOT = Path("/opt/aicara")
BACKUP_DIR = Path("/opt/aicara/.nate_backups")
MAX_FILE_SIZE = 1_000_000  # 1MB max for safety


class FileEditor:
    """Safe file editor with validation and rollback."""

    def __init__(self):
        """Initialize file editor."""
        # Ensure backup directory exists
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    def edit_file(
        self,
        filepath: str,
        changes: List[Dict[str, Any]],
        validate: bool = True,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Edit a file with validation and backup.

        Args:
            filepath: Path to file (within /opt/aicara)
            changes: List of change dicts with:
                - type: "replace", "insert", "delete", "whole_file"
                - line: Line number (1-indexed) for replace/insert/delete
                - old: Old content (for replace validation)
                - new: New content
                - content: Full file content (for whole_file)
            validate: Run syntax validation
            dry_run: Preview changes without applying

        Returns:
            Dict with results
        """
        # Validate filepath
        file_path = self._validate_path(filepath)
        if not file_path:
            return {
                "status": "error",
                "message": f"Path '{filepath}' is outside allowed root or blocked"
            }

        if not file_path.exists():
            return {
                "status": "error",
                "message": f"File not found: {filepath}"
            }

        if not file_path.is_file():
            return {
                "status": "error",
                "message": f"Path is not a file: {filepath}"
            }

        # Check file size
        if file_path.stat().st_size > MAX_FILE_SIZE:
            return {
                "status": "error",
                "message": f"File too large (max {MAX_FILE_SIZE} bytes)"
            }

        # Read current content
        try:
            current_content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to read file: {str(e)}"
            }

        # Apply changes
        try:
            new_content, change_summary = self._apply_changes(
                current_content,
                changes,
                file_path.name
            )
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to apply changes: {str(e)}"
            }

        # Generate diff
        diff = self._generate_diff(current_content, new_content, filepath)

        # If dry run, return preview
        if dry_run:
            return {
                "status": "success",
                "message": "Dry run - changes not applied",
                "filepath": self._get_display_path(file_path),
                "changes": change_summary,
                "diff": diff,
                "dry_run": True
            }

        # Validate syntax if requested
        if validate:
            validation_result = self._validate_syntax(new_content, file_path.suffix, file_path)
            if not validation_result["valid"]:
                return {
                    "status": "error",
                    "message": "Validation failed - changes not applied",
                    "validation_errors": validation_result["errors"],
                    "diff": diff
                }

        # Create backup
        backup_path = self._create_backup(file_path, current_content)

        # Write new content
        try:
            file_path.write_text(new_content, encoding='utf-8')
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to write file: {str(e)}",
                "backup": str(backup_path)
            }

        # Validate the written file
        if validate:
            try:
                written_content = file_path.read_text(encoding='utf-8')
                validation_result = self._validate_syntax(written_content, file_path.suffix, file_path)

                if not validation_result["valid"]:
                    # Auto-rollback
                    self._restore_backup(file_path, backup_path)
                    return {
                        "status": "error",
                        "message": "Post-write validation failed - rolled back",
                        "validation_errors": validation_result["errors"],
                        "backup": str(backup_path)
                    }
            except Exception as e:
                # Auto-rollback
                self._restore_backup(file_path, backup_path)
                return {
                    "status": "error",
                    "message": f"Post-write validation error - rolled back: {str(e)}",
                    "backup": str(backup_path)
                }

        return {
            "status": "success",
            "message": "File edited successfully",
            "filepath": self._get_display_path(file_path),
            "changes": change_summary,
            "diff": diff,
            "backup": str(backup_path.relative_to(BACKUP_DIR)),
            "validated": validate
        }

    def _validate_path(self, filepath: str) -> Optional[Path]:
        """Validate path is within allowed roots."""
        try:
            # Resolve path (prepend SUBSTRATE_ROOT for relative paths like nate_dev_tool)
            if filepath.startswith('/'):
                full_path = Path(filepath).resolve()
            else:
                full_path = (SUBSTRATE_ROOT / filepath).resolve()

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

            return full_path
        except Exception:
            return None

    def _get_display_path(self, full_path: Path) -> str:
        """Get display path relative to appropriate root."""
        try:
            return str(full_path.relative_to(SUBSTRATE_ROOT))
        except ValueError:
            try:
                return str(full_path.relative_to(ALLOWED_ROOT))
            except ValueError:
                return str(full_path)

    def _apply_changes(
        self,
        content: str,
        changes: List[Dict[str, Any]],
        filename: str
    ) -> Tuple[str, List[Dict[str, str]]]:
        """Apply list of changes to content."""
        lines = content.splitlines(keepends=True)
        change_summary = []

        for change in changes:
            # Support both "type" and "action" as the operation key
            change_type = change.get("type") or change.get("action")

            if not change_type:
                raise ValueError("Each change must have either 'type' or 'action' key specifying the operation")

            if change_type == "whole_file":
                # Replace entire file
                new_content = change.get("content", "")
                change_summary.append({
                    "type": "whole_file",
                    "description": f"Replaced entire file ({len(lines)} → {len(new_content.splitlines())} lines)"
                })
                return new_content, change_summary

            elif change_type == "replace":
                # Replace specific line
                line_num = change.get("line", 0)
                # Support multiple parameter names for flexibility (check existence, not truthiness)
                if "old" in change:
                    old_text = change["old"]
                elif "old_content" in change:
                    old_text = change["old_content"]
                else:
                    old_text = ""

                if "new" in change:
                    new_text = change["new"]
                elif "new_content" in change:
                    new_text = change["new_content"]
                elif "content" in change:
                    new_text = change["content"]
                else:
                    raise ValueError(f"Replace operation requires 'new', 'new_content', or 'content' parameter")

                if line_num < 1 or line_num > len(lines):
                    raise ValueError(f"Line {line_num} out of range (1-{len(lines)})")

                # Validate old content matches
                current_line = lines[line_num - 1].rstrip('\n\r')
                if old_text and old_text.strip() != current_line.strip():
                    raise ValueError(
                        f"Line {line_num} content mismatch. "
                        f"Expected: {old_text[:50]}... "
                        f"Found: {current_line[:50]}..."
                    )

                # Preserve line ending style
                line_ending = '\n'
                if lines[line_num - 1].endswith('\r\n'):
                    line_ending = '\r\n'

                lines[line_num - 1] = new_text + line_ending
                change_summary.append({
                    "type": "replace",
                    "line": line_num,
                    "description": f"Replaced line {line_num}"
                })

            elif change_type == "insert":
                # Insert new line
                line_num = change.get("line", 0)
                # Support multiple parameter names for flexibility (check existence, not truthiness)
                if "new" in change:
                    new_text = change["new"]
                elif "new_content" in change:
                    new_text = change["new_content"]
                elif "content" in change:
                    new_text = change["content"]
                else:
                    raise ValueError(f"Insert operation requires 'new', 'new_content', or 'content' parameter")

                if line_num < 0 or line_num > len(lines):
                    raise ValueError(f"Line {line_num} out of range (0-{len(lines)})")

                # If inserting at end and last line has no newline, add one first
                if line_num == len(lines) and lines and not lines[-1].endswith(('\n', '\r\n')):
                    lines[-1] += '\n'

                lines.insert(line_num, new_text + '\n')
                change_summary.append({
                    "type": "insert",
                    "line": line_num,
                    "description": f"Inserted line at {line_num}"
                })

            elif change_type == "delete":
                # Delete line
                line_num = change.get("line", 0)

                if line_num < 1 or line_num > len(lines):
                    raise ValueError(f"Line {line_num} out of range (1-{len(lines)})")

                deleted_content = lines[line_num - 1][:50]
                del lines[line_num - 1]
                change_summary.append({
                    "type": "delete",
                    "line": line_num,
                    "description": f"Deleted line {line_num}: {deleted_content}..."
                })

            else:
                raise ValueError(f"Unknown change type: {change_type}")

        return ''.join(lines), change_summary

    def _validate_syntax(self, content: str, file_extension: str, filepath: Optional[Path] = None) -> Dict[str, Any]:
        """Validate syntax based on file type."""
        errors = []

        # Files that are allowed to contain security patterns (security tools themselves)
        security_tool_files = [
            'file_editor.py',
            'command_executor.py',
            'test_executor.py',
            'nate_dev_tool.py'
        ]
        is_security_tool = filepath and any(filepath.name == f for f in security_tool_files)

        if file_extension in ['.py', '.pyw']:
            # Python syntax validation
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"Python syntax error at line {e.lineno}: {e.msg}")

        elif file_extension in ['.json']:
            # JSON validation
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                errors.append(f"JSON error at line {e.lineno}: {e.msg}")

        elif file_extension in ['.yaml', '.yml']:
            # YAML validation
            try:
                yaml.safe_load(content)
            except yaml.YAMLError as e:
                errors.append(f"YAML error: {str(e)}")

        elif file_extension in ['.js', '.jsx']:
            # JavaScript validation (if node available)
            try:
                import tempfile
                # node --check requires a file, so write to temp file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name

                try:
                    result = subprocess.run(
                        ['node', '--check', tmp_path],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode != 0:
                        errors.append(f"JavaScript syntax error: {result.stderr}")
                finally:
                    # Clean up temp file
                    Path(tmp_path).unlink(missing_ok=True)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                # Node not available, skip JS validation
                pass

        # Additional validation: check for common dangerous patterns
        # Skip this check for security tool files (they contain these patterns legitimately)
        if not is_security_tool:
            dangerous_patterns = [
                (r'eval\s*\(', "Contains eval() - security risk"),
                (r'exec\s*\(', "Contains exec() - security risk"),
                (r'__import__', "Contains __import__ - security risk"),
            ]

            for pattern, message in dangerous_patterns:
                if re.search(pattern, content):
                    errors.append(f"Security warning: {message}")

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }

    def _generate_diff(self, old_content: str, new_content: str, filepath: str) -> str:
        """Generate unified diff."""
        import difflib
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filepath}",
            tofile=f"b/{filepath}",
            lineterm=''
        )

        return ''.join(diff)

    def _create_backup(self, file_path: Path, content: str) -> Path:
        """Create backup of file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Get relative path from appropriate root
        try:
            relative_path = file_path.relative_to(SUBSTRATE_ROOT)
        except ValueError:
            try:
                relative_path = file_path.relative_to(ALLOWED_ROOT)
            except ValueError:
                # Fallback: use just the filename
                relative_path = Path(file_path.name)

        # Create subdirectories in backup dir
        backup_file_dir = BACKUP_DIR / relative_path.parent
        backup_file_dir.mkdir(parents=True, exist_ok=True)

        backup_path = backup_file_dir / f"{relative_path.name}.{timestamp}.bak"
        backup_path.write_text(content, encoding='utf-8')

        return backup_path

    def _restore_backup(self, file_path: Path, backup_path: Path):
        """Restore file from backup."""
        try:
            content = backup_path.read_text(encoding='utf-8')
            file_path.write_text(content, encoding='utf-8')
        except Exception as e:
            raise RuntimeError(f"Failed to restore backup: {str(e)}")

    def list_backups(self, filepath: Optional[str] = None) -> Dict[str, Any]:
        """List available backups."""
        try:
            backups = []

            if filepath:
                # List backups for specific file
                file_path = self._validate_path(filepath)
                if not file_path:
                    return {"status": "error", "message": "Invalid filepath"}

                # Get relative path from appropriate root (same logic as _create_backup)
                try:
                    relative_path = file_path.relative_to(SUBSTRATE_ROOT)
                except ValueError:
                    try:
                        relative_path = file_path.relative_to(ALLOWED_ROOT)
                    except ValueError:
                        relative_path = Path(file_path.name)

                backup_dir = BACKUP_DIR / relative_path.parent

                if backup_dir.exists():
                    pattern = f"{relative_path.name}.*.bak"
                    for backup in sorted(backup_dir.glob(pattern), reverse=True):
                        backups.append({
                            "file": str(backup.relative_to(BACKUP_DIR)),
                            "timestamp": backup.stem.split('.')[-1],
                            "size": backup.stat().st_size
                        })
            else:
                # List all backups
                for backup in sorted(BACKUP_DIR.rglob("*.bak"), reverse=True):
                    backups.append({
                        "file": str(backup.relative_to(BACKUP_DIR)),
                        "timestamp": backup.stem.split('.')[-1],
                        "size": backup.stat().st_size
                    })

            return {
                "status": "success",
                "backups": backups[:50],  # Limit to 50 most recent
                "total": len(backups)
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to list backups: {str(e)}"
            }

    def restore_from_backup(self, backup_file: str) -> Dict[str, Any]:
        """Restore a file from backup."""
        try:
            # Validate and resolve backup path to prevent traversal
            backup_path = (BACKUP_DIR / backup_file).resolve()

            # Ensure backup path is within BACKUP_DIR
            try:
                backup_path.relative_to(BACKUP_DIR)
            except ValueError:
                return {"status": "error", "message": "Invalid backup path - outside backup directory"}

            if not backup_path.exists():
                return {"status": "error", "message": "Backup not found"}

            # Determine original file path
            # Remove .timestamp.bak suffix
            original_relative = backup_path.relative_to(BACKUP_DIR)
            parts = original_relative.stem.rsplit('.', 1)
            original_name = parts[0] if len(parts) > 1 else original_relative.stem

            # Try to reconstruct the original path - check both roots
            # Try SUBSTRATE_ROOT first (most common)
            original_path = SUBSTRATE_ROOT / original_relative.parent / original_name
            if not original_path.exists():
                # Try ALLOWED_ROOT as fallback
                original_path = ALLOWED_ROOT / original_relative.parent / original_name

            # Create new backup of current file (before restoring)
            new_backup = None
            if original_path.exists():
                current_content = original_path.read_text(encoding='utf-8')
                new_backup = self._create_backup(original_path, current_content)

            # Restore from backup
            backup_content = backup_path.read_text(encoding='utf-8')
            original_path.write_text(backup_content, encoding='utf-8')

            return {
                "status": "success",
                "message": "File restored from backup",
                "filepath": self._get_display_path(original_path),
                "backup_used": backup_file,
                "new_backup": str(new_backup.relative_to(BACKUP_DIR)) if new_backup else None
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to restore backup: {str(e)}"
            }
