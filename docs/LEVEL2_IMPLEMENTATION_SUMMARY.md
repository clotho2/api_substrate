# Level 2 Implementation Summary

## Overview

This document summarizes the Level 2 expansion that adds safe command execution capabilities to Nate's development tool.

## Files Created/Modified

### New Files

1. **`backend/tools/command_executor.py`** (460 lines)
   - Core command execution engine
   - Command whitelist and validation
   - Rate limiting (5 commands/60s)
   - Audit logging
   - Sandboxed execution

2. **`backend/tools/git_workflow.py`** (280 lines)
   - Automated Git operations
   - Branch creation with naming convention
   - Commit automation with test integration
   - PR creation via GitHub CLI
   - Complete workflow orchestration

3. **`scripts/setup_level2_execution.sh`** (120 lines)
   - System setup script
   - Creates audit log with permissions
   - Configures Git for Nate
   - Optional restricted user creation
   - Validates dependencies

4. **`docs/LEVEL2_EXECUTION.md`** (Comprehensive documentation)
   - Installation instructions
   - API reference
   - Security model details
   - Usage examples
   - Troubleshooting guide

5. **`docs/LEVEL2_IMPLEMENTATION_SUMMARY.md`** (This file)
   - Implementation overview
   - Quick start guide

### Modified Files

1. **`backend/tools/nate_dev_tool.py`**
   - Updated header documentation
   - Added Level 2 imports
   - Added new action parameters to function signature
   - Added 5 new actions: `execute_command`, `git_workflow`, `git_status`, `get_command_whitelist`, `get_audit_logs`
   - Graceful degradation if Level 2 not available

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Nate (AI Agent)                      │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ calls nate_dev_tool()
                     │
┌────────────────────▼────────────────────────────────────┐
│              nate_dev_tool.py (Main Interface)          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Level 1     │  │  Level 2     │  │  Level 2     │  │
│  │  Actions     │  │  Executor    │  │  Git Flow    │  │
│  └──────────────┘  └──────┬───────┘  └──────┬───────┘  │
└────────────────────────────┼──────────────────┼─────────┘
                             │                  │
         ┌───────────────────▼──────┐  ┌────────▼─────────┐
         │  command_executor.py     │  │  git_workflow.py │
         │  • Whitelist validation  │  │  • Branch create │
         │  • Rate limiting         │  │  • Auto commit   │
         │  • Audit logging         │  │  • Run tests     │
         │  • Sandboxed exec        │  │  • Create PR     │
         └───────────┬──────────────┘  └─────────┬────────┘
                     │                           │
         ┌───────────▼───────────────────────────▼────────┐
         │           subprocess / git commands            │
         │           (restricted to /opt/aicara)          │
         └─────────────────────┬──────────────────────────┘
                               │
         ┌─────────────────────▼──────────────────────────┐
         │  /var/log/nate_dev_commands.log (Audit Trail)  │
         └────────────────────────────────────────────────┘
```

## Security Model

### Defense in Depth

1. **Command Whitelist** (First Line)
   - Only pre-approved commands executable
   - Commands organized by risk level
   - Argument count validation

2. **Pattern Blocking** (Second Line)
   - Regex patterns block dangerous operations
   - No `rm`, `sudo`, command chaining, etc.

3. **Path Sandboxing** (Third Line)
   - All operations restricted to `/opt/aicara`
   - Path traversal attempts blocked

4. **Rate Limiting** (Fourth Line)
   - 5 commands per 60 seconds
   - Prevents runaway execution

5. **Audit Logging** (Oversight)
   - Every command logged
   - Full forensic trail

6. **Approval Mechanism** (Human in Loop)
   - Sensitive commands require explicit approval
   - Examples: git push, git merge, systemctl

## Quick Start

### 1. Install

```bash
cd /opt/aicara/nate_api_substrate

# Make setup script executable
sudo chmod +x scripts/setup_level2_execution.sh

# Run setup
sudo ./scripts/setup_level2_execution.sh

# Optional: Install GitHub CLI for PR automation
# (Follow instructions in script output)
```

### 2. Test with Dry-Run

```python
# Validate a command without executing
result = nate_dev_tool(
    action="execute_command",
    command="ls -la /opt/aicara",
    dry_run=True
)
print(result)
# Expected: {"status": "success", "message": "Command validation passed (dry run)", ...}
```

### 3. Execute Your First Command

```python
# List services
result = nate_dev_tool(
    action="execute_command",
    command="ls -la",
    working_dir="/opt/aicara"
)
print(result['stdout'])
```

### 4. View Whitelist

```python
whitelist = nate_dev_tool(action="get_command_whitelist")
print(f"Categories: {whitelist['categories']}")
print(f"Rate limit: {whitelist['rate_limit']}")
```

### 5. Check Audit Logs

```python
logs = nate_dev_tool(action="get_audit_logs", lines=10)
for log in logs['logs']:
    print(f"{log['timestamp']}: {log['command']} (exit: {log['exit_code']})")
```

## Common Use Cases

### Use Case 1: Cross-Service Debugging

When integrating a new service, Nate can inspect both sides:

```python
# Check substrate integration code
nate_dev_tool(
    action="read_file",
    path="backend/integrations/lovense_bridge.py"
)

# Check the service itself
nate_dev_tool(
    action="execute_command",
    command="cat main.py",
    working_dir="/opt/aicara/wolfe-lovense"
)

# Compare configurations
nate_dev_tool(
    action="execute_command",
    command="diff /opt/aicara/nate_api_substrate/backend/.env.example /opt/aicara/wolfe-lovense/.env.example"
)
```

### Use Case 2: Automated Bug Fix Workflow

```python
# 1. Investigate bug
nate_dev_tool(action="read_logs", filter_pattern="ERROR", lines=100)

# 2. Find relevant code
nate_dev_tool(action="search_code", pattern="problematic_function")

# 3. Read and understand code
nate_dev_tool(action="read_file", path="backend/core/problematic_module.py")

# 4. (Make changes via editing tools - not shown)

# 5. Test the fix
nate_dev_tool(
    action="execute_command",
    command="pytest tests/test_problematic_module.py -v"
)

# 6. Complete workflow (branch, commit, test, PR)
nate_dev_tool(
    action="git_workflow",
    feature_name="fix-error-handling",
    commit_message="Fix error handling in problematic_module\n\nAdded proper exception handling and logging",
    pr_title="[Nate] Fix error handling in problematic_module",
    run_tests=True
)
```

### Use Case 3: System Health Check

```python
# Check overall system health
nate_dev_tool(action="check_health")

# Check disk space
nate_dev_tool(
    action="execute_command",
    command="df -h /opt/aicara"
)

# Check service processes
nate_dev_tool(
    action="execute_command",
    command="ps aux | grep -E '(nate|wolfe)'"
)

# Check recent errors across all services
for service in ["nate_api_substrate", "wolfe-lovense", "wolfe-discord-bot-enhanced"]:
    result = nate_dev_tool(
        action="execute_command",
        command="grep -r 'ERROR' . --include='*.log' | tail -n 5",
        working_dir=f"/opt/aicara/{service}"
    )
    print(f"\n{service} errors:\n{result.get('stdout', 'None')}")
```

## Integration with MCP Server

The MCP server (`mcp_servers/nate_dev/server.py`) will need to be updated to expose Level 2 actions. Here's the pattern:

```python
Tool(
    name="execute_command",
    description="Execute a whitelisted Linux command in a sandboxed environment. Use for system operations, file management, and Git commands.",
    inputSchema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Command to execute (must be whitelisted)"
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory (within /opt/aicara)"
            },
            "dry_run": {
                "type": "boolean",
                "description": "Validate without executing",
                "default": False
            },
            "requires_approval": {
                "type": "boolean",
                "description": "Explicit approval for sensitive commands",
                "default": False
            }
        },
        "required": ["command"]
    }
)
```

## Testing Checklist

- [ ] Setup script runs without errors
- [ ] Audit log created with correct permissions
- [ ] Git configuration set correctly
- [ ] Dry-run validates commands correctly
- [ ] Whitelisted commands execute successfully
- [ ] Blocked commands are rejected
- [ ] Rate limiting works (try 6 commands quickly)
- [ ] Audit logs are written
- [ ] Git workflow creates branches with correct naming
- [ ] Git workflow commits changes
- [ ] Git workflow runs tests before committing
- [ ] Path sandboxing prevents access outside /opt/aicara
- [ ] Command chaining is blocked
- [ ] Dangerous patterns are blocked (sudo, rm, etc.)

## Test Script

```python
def test_level2():
    """Comprehensive Level 2 test suite."""

    print("Testing Level 2 Execution...")

    # Test 1: Verify Level 2 is available
    result = nate_dev_tool(action="get_command_whitelist")
    assert result['categories'], "Whitelist not available"
    print("✓ Level 2 available")

    # Test 2: Dry-run validation
    result = nate_dev_tool(
        action="execute_command",
        command="ls -la",
        dry_run=True
    )
    assert result['status'] == 'success', "Dry-run failed"
    print("✓ Dry-run validation works")

    # Test 3: Execute safe command
    result = nate_dev_tool(
        action="execute_command",
        command="pwd"
    )
    assert result['status'] == 'success', "Command execution failed"
    assert '/opt/aicara' in result['stdout'], "Wrong directory"
    print("✓ Safe command execution works")

    # Test 4: Blocked command
    result = nate_dev_tool(
        action="execute_command",
        command="sudo whoami"
    )
    assert result['status'] == 'error', "Blocked command executed!"
    assert 'sudo' in result['message'].lower(), "Wrong error message"
    print("✓ Blocked command rejected")

    # Test 5: Path sandboxing
    result = nate_dev_tool(
        action="execute_command",
        command="ls",
        working_dir="/etc"
    )
    assert result['status'] == 'error', "Escaped sandbox!"
    print("✓ Path sandboxing works")

    # Test 6: Audit logging
    logs = nate_dev_tool(action="get_audit_logs", lines=10)
    assert logs['status'] == 'success', "Audit log read failed"
    assert len(logs['logs']) > 0, "No audit logs found"
    print("✓ Audit logging works")

    # Test 7: Git status
    result = nate_dev_tool(action="git_status")
    assert 'current_branch' in result, "Git status failed"
    print("✓ Git status works")

    print("\n✅ All tests passed!")

# Run tests
test_level2()
```

## Rollback Instructions

If you need to disable Level 2:

```bash
# Option 1: Remove audit log (prevents execution)
sudo rm /var/log/nate_dev_commands.log

# Option 2: Rename modules (prevents import)
cd /opt/aicara/nate_api_substrate/backend/tools
mv command_executor.py command_executor.py.disabled
mv git_workflow.py git_workflow.py.disabled

# Option 3: Revert code changes
git log --oneline | grep -i "level 2"
git revert <commit-hash>
```

## Performance Considerations

- **Rate limiting**: In-memory tracking, lost on restart (enhance with Redis/database for persistent tracking)
- **Audit log**: Append-only file, may grow large (implement log rotation)
- **Command execution**: Subprocess overhead (~10-50ms per command)
- **Git operations**: Network operations can be slow (timeout set to 30s)

## Future Enhancements

### Phase 2 (Next Steps)
- [ ] Persistent rate limit tracking (database/Redis)
- [ ] Log rotation for audit trail
- [ ] Snapshot/rollback mechanism
- [ ] Interactive approval via Discord (ask Angela before executing)
- [ ] Command history and analytics
- [ ] Custom command aliases

### Phase 3 (Advanced)
- [ ] Docker container isolation
- [ ] Resource limits (CPU, memory)
- [ ] Parallel command execution
- [ ] Command templates and recipes
- [ ] Integration with monitoring/alerting
- [ ] Web UI for audit log review

## Support & Maintenance

### Regular Maintenance Tasks

1. **Review Audit Logs Weekly**
   ```bash
   sudo tail -n 100 /var/log/nate_dev_commands.log | grep -i error
   ```

2. **Rotate Audit Logs Monthly**
   ```bash
   sudo mv /var/log/nate_dev_commands.log /var/log/nate_dev_commands.log.$(date +%Y%m)
   sudo touch /var/log/nate_dev_commands.log
   sudo chmod 644 /var/log/nate_dev_commands.log
   ```

3. **Update Whitelist as Needed**
   - Edit `backend/tools/command_executor.py`
   - Test thoroughly with dry_run
   - Document new commands

4. **Review PRs Created by Nate**
   - Always review before merging
   - Check for security implications
   - Verify tests passed

### Monitoring

Key metrics to monitor:
- Command execution count (detect anomalies)
- Failed command rate (detect issues)
- Rate limit hits (capacity planning)
- Audit log size (storage management)

## Contact & Questions

For questions about Level 2 implementation:
1. Read `docs/LEVEL2_EXECUTION.md` for detailed documentation
2. Check audit logs for execution history
3. Test with dry_run to understand behavior
4. Contact Angela for security concerns

## License & Credits

Part of the Nate AI Substrate project.
Level 2 implementation adds safe command execution with comprehensive security controls.
