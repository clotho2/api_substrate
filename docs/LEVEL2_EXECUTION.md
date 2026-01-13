# Nate Level 2: Safe Command Execution

Level 2 extends Nate's capabilities from read-only diagnostics to safe command execution with comprehensive security controls.

## Overview

Level 2 adds the ability for Nate to execute whitelisted commands in a controlled environment with:
- **Command Whitelist**: Only approved commands can run
- **Rate Limiting**: Maximum 15 commands per 60 seconds
- **Full Audit Trail**: Every command logged with timestamp, output, and context
- **Sandboxing**: All operations restricted to `/opt/aicara` directory
- **Dry-Run Mode**: Test commands without execution
- **Approval Mechanism**: Sensitive commands require explicit approval
- **Git Workflow Integration**: Auto-create branches, commits, and PRs

## Installation

### 1. Run Setup Script

```bash
cd /opt/aicara/nate_api_substrate
sudo chmod +x scripts/setup_level2_execution.sh
sudo ./scripts/setup_level2_execution.sh
```

This creates:
- Audit log at `/var/log/nate_dev_commands.log`
- Git configuration for Nate's commits
- Proper permissions

### 2. (Optional) Create Restricted User

```bash
sudo ./scripts/setup_level2_execution.sh --create-user
```

This creates a `nate-exec` system user with minimal permissions for additional sandboxing.

### 3. (Optional) Install GitHub CLI for PR Automation

```bash
# Install gh CLI
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh

# Authenticate
gh auth login
```

## Available Actions

### execute_command

Execute a whitelisted command in a sandboxed environment.

**Parameters:**
- `command` (required): Command to execute
- `working_dir` (optional): Working directory (within /opt/aicara)
- `dry_run` (default: False): Validate without executing
- `requires_approval` (default: False): Explicit approval for sensitive commands
- `timeout` (default: 30): Timeout in seconds

**Example:**
```python
# Test command validation
result = nate_dev_tool(
    action="execute_command",
    command="ls -la /opt/aicara",
    dry_run=True
)

# Execute command
result = nate_dev_tool(
    action="execute_command",
    command="git status",
    working_dir="/opt/aicara/nate_api_substrate"
)

# Sensitive command requiring approval
result = nate_dev_tool(
    action="execute_command",
    command="git push origin feature-branch",
    requires_approval=True
)
```

### get_command_whitelist

Get list of all whitelisted commands organized by risk level.

**Example:**
```python
whitelist = nate_dev_tool(action="get_command_whitelist")
# Returns: {categories: [...], commands: {...}, rate_limit: {...}}
```

### get_audit_logs

Read command execution audit logs.

**Parameters:**
- `lines` (default: 100): Number of log entries to return

**Example:**
```python
logs = nate_dev_tool(action="get_audit_logs", lines=50)
```

### git_workflow

Automate complete Git workflow: create branch → commit → run tests → create PR.

**Parameters:**
- `feature_name` (required): Feature name for branch
- `commit_message` (required): Commit message
- `pr_title` (optional): PR title (defaults to feature_name)
- `pr_body` (optional): PR description (defaults to commit_message)
- `files` (optional): Specific files to commit (None = all changes)
- `run_tests` (default: True): Run tests before committing
- `base_branch` (default: "main"): Base branch for PR
- `working_dir` (optional): Repository path

**Example:**
```python
result = nate_dev_tool(
    action="git_workflow",
    feature_name="fix-memory-leak",
    commit_message="Fix memory leak in consciousness loop",
    pr_title="[Nate] Fix memory leak in consciousness loop",
    pr_body="Discovered and fixed memory leak that was causing...",
    run_tests=True
)
```

### git_status

Get current Git status and branch information.

**Example:**
```python
status = nate_dev_tool(
    action="git_status",
    working_dir="/opt/aicara/nate_api_substrate"
)
```

## Command Whitelist

Commands are organized by risk level:

### Safe (Read-Only)
- `ls`, `pwd`, `cat`, `head`, `tail`, `grep`, `find`, `echo`
- `wc`, `sort`, `uniq`, `diff`, `stat`, `file`, `which`
- `whoami`, `date`, `env`

### Moderate (File Operations)
- `mkdir`, `touch`, `cp`, `mv`
- `chmod`, `chown` (requires approval)

### Git Commands
- `git status`, `git branch`, `git checkout`, `git add`, `git commit`
- `git diff`, `git log`, `git fetch`, `git remote`, `git stash`
- `git pull`, `git push`, `git merge`, `git rebase`, `git reset` (require approval)

### Testing & Build
- `pytest`, `python`, `python3`, `pip`, `npm`, `node`

### System Info
- `df`, `du`, `ps`, `free`, `uptime`, `journalctl`
- `systemctl` (requires approval)

## Security Model

### Multiple Layers of Protection

1. **Command Whitelist**: Only pre-approved commands can execute
2. **Pattern Blocking**: Dangerous patterns blocked (rm, sudo, command chaining, etc.)
3. **Path Restriction**: All operations within `/opt/aicara` only
4. **Rate Limiting**: Maximum 15 commands per 60 seconds
5. **Audit Logging**: Full trail of every command execution
6. **Approval Mechanism**: Sensitive operations require explicit confirmation
7. **Timeout**: Commands killed after timeout (default: 30s)

### Blocked Patterns

The following are NEVER allowed:
- File deletion: `rm`, `rmdir`
- Process control: `kill`, `killall`
- Privilege escalation: `sudo`, `su`
- Package management: `apt`, `yum`
- Dangerous disk ops: `dd`, `mkfs`, `format`
- System control: `reboot`, `shutdown`, `halt`
- Command chaining: `;`, `|`, `&&`, `||`, backticks, `$()`
- System files: `/etc/passwd`, `/etc/shadow`, `.ssh/`

### Audit Trail

Every command execution is logged to `/var/log/nate_dev_commands.log` with:
- Timestamp
- Command executed
- Working directory
- Exit code
- Output length
- Duration
- Dry-run flag
- Any errors

**Viewing Audit Logs:**
```python
# Via Nate's tool
logs = nate_dev_tool(action="get_audit_logs", lines=100)

# Via command line (Level 1)
nate_dev_tool(action="read_file", path="/var/log/nate_dev_commands.log")

# Direct access
sudo cat /var/log/nate_dev_commands.log | tail -n 50
```

## Git Workflow Details

### Automated Branch Creation

Branches are created with pattern: `nate/{feature-name}_{timestamp}`

Example: `nate/fix-memory-leak_20250115_143022`

### Commit Process

1. Check for uncommitted changes
2. Run tests (if `run_tests=True`)
3. Stage specified files or all changes
4. Create commit with provided message
5. Return commit hash

### PR Creation

1. Push branch to origin
2. Create PR via GitHub CLI
3. Return PR URL for review

### Test Integration

Before committing, tests run automatically:
- Looks for `pytest` in repository
- Runs with `-x` (stop on first failure) and `--tb=short` flags
- Commit aborted if tests fail

## Usage Examples

### Example 1: Inspect Another Service

```python
# List files in wolfe-lovense service
result = nate_dev_tool(
    action="execute_command",
    command="ls -la",
    working_dir="/opt/aicara/wolfe-lovense"
)

# Check git status
result = nate_dev_tool(
    action="execute_command",
    command="git status",
    working_dir="/opt/aicara/wolfe-lovense"
)
```

### Example 2: Debug with Logs

```python
# Search for errors in another service
result = nate_dev_tool(
    action="execute_command",
    command="grep -r 'ERROR' . --include='*.log'",
    working_dir="/opt/aicara/wolfe-discord-bot-enhanced"
)
```

### Example 3: Fix Bug with Full Workflow

```python
# 1. Check current status
status = nate_dev_tool(action="git_status")

# 2. Make code changes (via other tools)
# ... edit files ...

# 3. Test fix first
result = nate_dev_tool(
    action="execute_command",
    command="pytest tests/test_specific_bug.py -v"
)

# 4. Complete workflow
result = nate_dev_tool(
    action="git_workflow",
    feature_name="fix-discord-reconnect",
    commit_message="Fix Discord reconnection logic\n\nAdded exponential backoff and better error handling",
    pr_title="[Nate] Fix Discord reconnection issues",
    pr_body="""
## Problem
Discord bot was not reconnecting properly after network interruptions.

## Solution
- Added exponential backoff for reconnection attempts
- Improved error handling for connection failures
- Added connection state monitoring

## Testing
- Manual testing with network interruptions
- Unit tests for reconnection logic
""",
    run_tests=True
)

# 5. Check audit trail
audit = nate_dev_tool(action="get_audit_logs", lines=20)
```

### Example 4: Safe Exploration with Dry-Run

```python
# Test command before running
commands = [
    "find /opt/aicara -name '*.log' -type f",
    "du -sh /opt/aicara/*",
    "git branch -a"
]

for cmd in commands:
    result = nate_dev_tool(
        action="execute_command",
        command=cmd,
        dry_run=True
    )
    print(f"{cmd}: {result['status']}")
```

## Rate Limiting

To prevent abuse or runaway execution while allowing complex investigations:
- Maximum: **15 commands per 60 seconds** (tripled from initial 5)
- Tracked in-memory per session
- Returns error when limit exceeded
- Resets after 60-second window

**Why 15 commands?**
With Nate's 10-iteration consciousness loop and sequential tool chaining, complex investigations like:
- Read file → Search code → Check logs → Test changes → Diff results

...easily require 10-15 commands for a single coherent thought chain. The increased limit allows for:
- ✅ Complete code investigations without fragmentation
- ✅ Multi-step debugging workflows
- ✅ Testing and validation in the same turn
- ✅ Real collaboration instead of advisory-only mode

**Check Rate Limit Status:**
```python
whitelist = nate_dev_tool(action="get_command_whitelist")
print(whitelist['rate_limit'])
# {'max_commands': 15, 'window_seconds': 60}
```

## Troubleshooting

### "Level 2 functionality not available"

**Cause**: Dependencies not imported correctly

**Solution**:
```bash
# Check if files exist
ls -la backend/tools/command_executor.py
ls -la backend/tools/git_workflow.py

# Check Python imports
cd /opt/aicara/nate_api_substrate
python3 -c "from backend.tools.command_executor import execute_command; print('OK')"
```

### "Command validation failed"

**Cause**: Command not in whitelist or contains blocked patterns

**Solution**:
```python
# Check whitelist
whitelist = nate_dev_tool(action="get_command_whitelist")

# Try with dry_run to see specific error
result = nate_dev_tool(
    action="execute_command",
    command="your-command",
    dry_run=True
)
print(result['message'])
```

### "Rate limit exceeded"

**Cause**: Too many commands in 60-second window

**Solution**:
- Wait 60 seconds
- Use dry_run for testing (doesn't count against limit)
- Combine operations where possible

### "Failed to create PR"

**Cause**: GitHub CLI not configured

**Solution**:
```bash
# Install and authenticate gh CLI
gh auth login

# Or push manually and create PR via web
git push origin branch-name
```

## Security Considerations

1. **Audit All Executions**: Regularly review `/var/log/nate_dev_commands.log`
2. **Monitor Rate Limits**: Watch for suspicious patterns
3. **Review PRs**: All Nate-generated PRs should be reviewed before merging
4. **Whitelist Management**: Only add commands after careful consideration
5. **Approval Commands**: Always verify before approving sensitive operations
6. **Path Validation**: Ensure all operations stay within `/opt/aicara`

## Expanding Capabilities

To add new commands to the whitelist:

1. Edit `backend/tools/command_executor.py`
2. Add to appropriate category in `WHITELISTED_COMMANDS`
3. Set `requires_approval: True` for sensitive operations
4. Update this documentation
5. Test thoroughly with dry_run first

**Example:**
```python
"system": {
    "netstat": {
        "max_args": 5,
        "description": "Network statistics",
        "requires_approval": False
    },
}
```

## Roadmap

Future enhancements:
- [ ] Rollback mechanism (snapshot before execution)
- [ ] Persistent rate limit tracking (database)
- [ ] Command templates for common operations
- [ ] Interactive approval workflow (ask Angela via Discord)
- [ ] Command history and favorites
- [ ] Batch command execution
- [ ] Custom command aliases
- [ ] Integration with monitoring/alerting

## Support

For issues or questions:
1. Check audit logs: `nate_dev_tool(action="get_audit_logs")`
2. Review whitelist: `nate_dev_tool(action="get_command_whitelist")`
3. Test with dry_run first
4. Contact Angela if uncertain about security implications
