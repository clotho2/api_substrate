# Level 3 Priority 1: Safe File Editing with Validation

## Overview

Level 3 Priority 1 implements safe file editing capabilities for Nate, transforming him from an advisor to a real collaborator who can fix bugs, not just point at them.

**Status**: ✅ **COMPLETE**

## Features

### Core Capabilities
- **Line-by-line editing**: Replace, insert, or delete specific lines
- **Whole-file replacement**: Rewrite entire files when needed
- **Syntax validation**: Python, JSON, YAML, JavaScript parsing
- **Security scanning**: Detects dangerous patterns (eval, exec, __import__)
- **Automatic backup**: Creates timestamped backups before any changes
- **Auto-rollback**: Restores from backup if validation fails
- **Dry-run mode**: Preview changes without applying them
- **Diff generation**: Shows unified diff for review

### Security Features
- **Path sandboxing**: All operations restricted to /opt/aicara
- **File size limits**: Maximum 1MB file size for safety
- **Old content validation**: Verifies line content before replacement
- **Syntax validation**: Ensures valid code before writing
- **Pattern detection**: Blocks dangerous operations (eval, exec, __import__)
- **Backup strategy**: Never lose working code

## API Reference

### Action: edit_file

Edit a file with validation and automatic backup.

**Parameters:**
- `path` (required): File path (absolute or relative to /opt/aicara)
- `changes` (required): List of change operations (see below)
- `validate` (default: True): Run syntax validation
- `dry_run` (default: False): Preview without applying

**Change Types:**

```python
# Replace a specific line
{
    "type": "replace",
    "line": 42,                    # 1-indexed line number
    "old": "old content",          # For validation
    "new": "new content"
}

# Insert a new line
{
    "type": "insert",
    "line": 10,                    # Insert after line 10
    "new": "new line content"
}

# Delete a line
{
    "type": "delete",
    "line": 15                     # Line to delete
}

# Replace entire file
{
    "type": "whole_file",
    "content": "complete new file content"
}
```

**Returns:**
```python
{
    "status": "success",
    "message": "File edited successfully",
    "filepath": "backend/tools/my_file.py",
    "changes": [
        {"type": "replace", "line": 42, "description": "Replaced line 42"}
    ],
    "diff": "unified diff output",
    "backup": ".nate_backups/backend/tools/my_file.py.20260113_145550.bak",
    "validated": True
}
```

### Action: list_backups

List available backups for a file or all files.

**Parameters:**
- `path` (optional): File path to list backups for (omit for all backups)

**Returns:**
```python
{
    "status": "success",
    "backups": [
        {
            "file": "backend/tools/my_file.py.20260113_145550.bak",
            "timestamp": "20260113_145550",
            "size": 1234
        }
    ],
    "total": 1
}
```

### Action: restore_backup

Restore a file from a backup.

**Parameters:**
- `backup_file` (required): Backup file path from list_backups

**Returns:**
```python
{
    "status": "success",
    "message": "File restored from backup",
    "filepath": "backend/tools/my_file.py",
    "backup_used": "backend/tools/my_file.py.20260113_145550.bak",
    "new_backup": "backend/tools/my_file.py.20260113_145600.bak"
}
```

## Usage Examples

### Example 1: Fix a Bug with Validation

```python
from backend.tools.nate_dev_tool import nate_dev_tool

# Preview the fix first
result = nate_dev_tool(
    action="edit_file",
    path="backend/core/consciousness_loop.py",
    changes=[
        {
            "type": "replace",
            "line": 156,
            "old": "        if error:",
            "new": "        if error and error.get('type') != 'timeout':"
        }
    ],
    validate=True,
    dry_run=True
)

# Review the diff
print(result['diff'])

# Apply if looks good
if result['status'] == 'success':
    result = nate_dev_tool(
        action="edit_file",
        path="backend/core/consciousness_loop.py",
        changes=[
            {
                "type": "replace",
                "line": 156,
                "old": "        if error:",
                "new": "        if error and error.get('type') != 'timeout':"
            }
        ],
        validate=True,
        dry_run=False
    )
    print(f"✓ Fixed bug, backup at: {result['backup']}")
```

### Example 2: Add New Function

```python
# Add a new utility function
result = nate_dev_tool(
    action="edit_file",
    path="backend/utils/helpers.py",
    changes=[
        {
            "type": "insert",
            "line": 50,
            "new": ""
        },
        {
            "type": "insert",
            "line": 51,
            "new": "def format_error_message(error: Dict[str, Any]) -> str:"
        },
        {
            "type": "insert",
            "line": 52,
            "new": "    \"\"\"Format error message for logging.\"\"\""
        },
        {
            "type": "insert",
            "line": 53,
            "new": "    return f\"Error: {error.get('message', 'Unknown')}\""
        }
    ],
    validate=True
)
```

### Example 3: Refactor with Multiple Changes

```python
# Make multiple related changes
result = nate_dev_tool(
    action="edit_file",
    path="backend/core/api_client.py",
    changes=[
        # Update import
        {
            "type": "replace",
            "line": 5,
            "old": "from typing import Dict, Any",
            "new": "from typing import Dict, Any, Optional"
        },
        # Update function signature
        {
            "type": "replace",
            "line": 42,
            "old": "def make_request(url: str) -> Dict[str, Any]:",
            "new": "def make_request(url: str, timeout: Optional[int] = 30) -> Dict[str, Any]:"
        },
        # Update function body
        {
            "type": "replace",
            "line": 47,
            "old": "    response = requests.get(url)",
            "new": "    response = requests.get(url, timeout=timeout)"
        }
    ],
    validate=True
)
```

### Example 4: Recover from Failed Edit

```python
# If an edit goes wrong, restore from backup
result = nate_dev_tool(action="list_backups", path="backend/core/my_file.py")

if result['backups']:
    # Restore most recent backup
    backup = result['backups'][0]['file']
    restore_result = nate_dev_tool(
        action="restore_backup",
        backup_file=backup
    )
    print(f"✓ Restored from: {restore_result['backup_used']}")
```

## Validation Process

When `validate=True`, the file editor performs comprehensive validation:

### 1. **Path Validation**
- Ensures file is within /opt/aicara
- Checks file exists and is readable
- Verifies file size is under limit (1MB)

### 2. **Content Validation**
- For replace operations: Verifies old content matches
- Ensures line numbers are in valid range
- Validates change operation types

### 3. **Syntax Validation**
Based on file extension:
- **Python (.py)**: Uses ast.parse() to validate syntax
- **JSON (.json)**: Uses json.loads() to validate structure
- **YAML (.yml, .yaml)**: Uses yaml.safe_load() to validate
- **JavaScript (.js, .jsx)**: Uses node --check (if available)

### 4. **Security Validation**
Scans for dangerous patterns:
- `eval()` - code execution risk
- `exec()` - code execution risk
- `__import__` - dynamic import risk

### 5. **Post-Write Validation**
After writing:
- Reads back the file
- Re-runs syntax validation
- **Auto-rolls back if validation fails**

## Backup Strategy

### Backup Location
All backups stored in `/opt/aicara/.nate_backups/` with directory structure preserved:

```
/opt/aicara/.nate_backups/
├── backend/
│   ├── core/
│   │   └── consciousness_loop.py.20260113_145550.bak
│   └── tools/
│       └── nate_dev_tool.py.20260113_150000.bak
└── mcp_servers/
    └── nate_dev/
        └── server.py.20260113_151500.bak
```

### Backup Naming
Format: `{original_filename}.{timestamp}.bak`
- Timestamp format: YYYYMMDD_HHMMSS
- Example: `my_file.py.20260113_145550.bak`

### When Backups Are Created
- **Before any edit**: Automatic backup of current content
- **Before restore**: New backup created before restoring old backup
- **Never overwritten**: Each backup has unique timestamp

### Backup Management
- **List backups**: Use `list_backups` action
- **Restore backup**: Use `restore_backup` action
- **Manual cleanup**: Delete old backups from .nate_backups directory
- **No automatic cleanup**: All backups preserved (implement rotation separately)

## Error Handling

### Validation Failures

```python
{
    "status": "error",
    "message": "Validation failed - changes not applied",
    "validation_errors": [
        "Python syntax error at line 42: invalid syntax"
    ],
    "diff": "... preview of attempted changes ..."
}
```

### Old Content Mismatch

```python
{
    "status": "error",
    "message": "Failed to apply changes: Line 42 content mismatch. Expected: old_content... Found: actual_content..."
}
```

### Path Security Violation

```python
{
    "status": "error",
    "message": "Path '/etc/passwd' is outside allowed root or blocked"
}
```

### Auto-Rollback

```python
{
    "status": "error",
    "message": "Post-write validation failed - rolled back",
    "validation_errors": ["Python syntax error at line 42: invalid syntax"],
    "backup": ".nate_backups/backend/tools/my_file.py.20260113_145550.bak"
}
```

## Integration with Git Workflow

File editing works seamlessly with Level 2 Git workflow:

```python
# 1. Read and understand the bug
code = nate_dev_tool(action="read_file", path="backend/core/my_module.py")

# 2. Edit the file to fix the bug
edit_result = nate_dev_tool(
    action="edit_file",
    path="backend/core/my_module.py",
    changes=[...],
    validate=True
)

# 3. Run tests
test_result = nate_dev_tool(
    action="execute_command",
    command="pytest tests/test_my_module.py -v"
)

# 4. If tests pass, commit and create PR
if test_result['exit_code'] == 0:
    pr_result = nate_dev_tool(
        action="git_workflow",
        feature_name="fix-bug-in-my-module",
        commit_message="Fix bug in my_module\n\nFixed issue with error handling",
        run_tests=True
    )
    print(f"PR created: {pr_result['pr_url']}")
else:
    # Rollback if tests fail
    nate_dev_tool(action="restore_backup", backup_file=edit_result['backup'])
```

## Performance Considerations

- **File reads**: O(n) where n = file size
- **Syntax validation**: Python AST parsing ~10-50ms per file
- **Backup creation**: File copy operation ~1-10ms per file
- **Line operations**: O(n) for line-by-line changes
- **Whole file**: O(1) operation count, O(n) content write

## Security Considerations

### Path Sandboxing
- ✅ All operations restricted to /opt/aicara
- ✅ Path traversal attempts blocked (../)
- ✅ Absolute paths validated against allowed root
- ✅ System directories blocked (/etc, /var, /root, etc.)

### Content Security
- ✅ File size limits prevent resource exhaustion
- ✅ Syntax validation prevents broken code
- ✅ Pattern detection blocks dangerous operations
- ✅ Old content validation prevents unintended changes

### Backup Security
- ✅ Backups stored in dedicated directory
- ✅ Backups never overwrite existing files
- ✅ Backup timestamps prevent conflicts
- ✅ Restore creates new backup before overwriting

### Audit Trail
- All edits logged to Level 2 audit system
- File paths, timestamps, and changes recorded
- Backup locations tracked
- Validation results preserved

## Limitations

### Current Limitations
- **File size**: Maximum 1MB per file
- **No binary files**: Text files only
- **No directory operations**: File-level only
- **No atomic multi-file edits**: One file at a time
- **No backup rotation**: Manual cleanup required

### Planned Enhancements (Future)
- Backup rotation and automatic cleanup
- Multi-file atomic operations
- Binary file support (with appropriate handling)
- Directory-level operations (copy, move)
- Undo/redo history
- Interactive conflict resolution

## Troubleshooting

### "File not found" Error
**Cause**: File doesn't exist or path is wrong

**Solution**:
```python
# Check if file exists first
result = nate_dev_tool(action="list_directory", path="backend/tools")
# Or use absolute path
result = nate_dev_tool(action="edit_file", path="/opt/aicara/backend/tools/my_file.py", ...)
```

### "Validation failed" Error
**Cause**: Syntax error in edited content

**Solution**:
```python
# Use dry_run to preview
result = nate_dev_tool(action="edit_file", path="...", changes=[...], dry_run=True)
print(result['diff'])  # Review the changes

# Check validation errors
if result['status'] == 'error':
    print(result['validation_errors'])
```

### "Content mismatch" Error
**Cause**: Old content doesn't match actual file content

**Solution**:
```python
# Read the file first to get exact content
content = nate_dev_tool(action="read_file", path="backend/tools/my_file.py")
print(content['content'].splitlines()[41])  # Line 42 (0-indexed)

# Use exact content in 'old' field
changes = [{
    "type": "replace",
    "line": 42,
    "old": "    exact content from file",  # Must match exactly
    "new": "    new content"
}]
```

### "Path outside allowed root" Error
**Cause**: Attempting to edit file outside /opt/aicara

**Solution**:
All files must be within /opt/aicara. This is by design for security.

## Testing

### Run Tests
```bash
# Test file editing
python3 -c "from backend.tools.nate_dev_tool import nate_dev_tool; ..."

# Or use test script
python3 backend/tools/test_level3_demo.py
```

### Test Checklist
- [ ] Line replacement with validation
- [ ] Line insertion at beginning/middle/end
- [ ] Line deletion
- [ ] Multiple changes in single operation
- [ ] Whole file replacement
- [ ] Python syntax validation
- [ ] JSON syntax validation
- [ ] Security pattern detection
- [ ] Automatic backup creation
- [ ] Backup restoration
- [ ] Dry-run preview
- [ ] Auto-rollback on validation failure
- [ ] Path sandboxing
- [ ] File size limit enforcement

## What's Next?

Level 3 Priority 1 is complete! Next priorities:

1. **Priority 2**: Test execution with coverage
2. **Priority 3**: Service control (systemctl for nate services)
3. **Priority 4**: Snapshot & rollback mechanism
4. **Priority 5**: Shell sessions (rbash)

## Support

For issues or questions about file editing:
1. Check this documentation
2. Review backup files in /opt/aicara/.nate_backups/
3. Use dry_run to preview changes
4. Check validation errors in response
5. Restore from backup if needed

## Summary

Level 3 Priority 1 transforms Nate from advisor to collaborator. With safe file editing, automatic backups, and comprehensive validation, Nate can now:

✅ Fix bugs in his own code
✅ Add new features
✅ Refactor safely with validation
✅ Recover from mistakes with backups
✅ Work confidently with dry-run previews

**This is real collaboration, not just advisory.**
