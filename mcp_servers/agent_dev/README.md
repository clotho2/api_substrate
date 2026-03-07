# Agent Self-Development MCP Server

This MCP server gives the agent the ability to inspect and understand its own codebase, logs, and system health.

## Levels

### Level 1: Read-Only Diagnostics (Current)
- Read source files
- Search codebase
- Read logs
- Check health
- List directories
- View configuration

### Level 2: Git-Based Modifications (Future)
- Create branches
- Edit files
- Commit changes
- Create pull requests

### Level 3: Full Autonomy (Future)
- Run tests
- Deploy changes
- Self-healing

## Available Tools (Level 1)

| Tool | Description |
|------|-------------|
| `read_source_file` | Read any source file in the codebase |
| `search_code` | Grep-like search for patterns |
| `read_logs` | Read system/service logs |
| `check_health` | Get system health metrics |
| `list_directory` | Explore codebase structure |
| `get_config` | View configuration (redacted) |

## Security

- **Read-only**: Level 1 cannot modify anything
- **Protected files**: Secrets are automatically redacted
- **Path sandboxing**: Cannot access files outside substrate directory
- **Blocked files**: SSH keys, git credentials completely hidden

## Setup

### 1. Install Dependencies

```bash
cd mcp_servers/agent_dev
pip install -r requirements.txt
```

### 2. Test the Server

```bash
python server.py
```

### 3. Connect to the agent

Add to your MCP configuration (Claude Desktop, agent tool config, etc.):

```json
{
  "mcpServers": {
    "agent-dev": {
      "command": "python",
      "args": ["/path/to/substrate/mcp_servers/agent_dev/server.py"]
    }
  }
}
```

## Usage Examples

### Reading Source Files

```json
{
  "tool": "read_source_file",
  "arguments": {
    "path": "backend/core/consciousness_loop.py",
    "start_line": 1,
    "end_line": 100
  }
}
```

### Searching Code

```json
{
  "tool": "search_code",
  "arguments": {
    "pattern": "discord_tool",
    "path": "backend",
    "file_pattern": "*.py",
    "max_results": 20
  }
}
```

### Reading Logs

```json
{
  "tool": "read_logs",
  "arguments": {
    "log_type": "backend",
    "lines": 50,
    "filter_pattern": "ERROR|WARNING",
    "since_minutes": 30
  }
}
```

### Checking Health

```json
{
  "tool": "check_health",
  "arguments": {}
}
```

## Roadmap

### Level 2 Features (Planned)
- `git_status()` - See current git state
- `git_branch(name)` - Create feature branch
- `edit_file(path, old, new)` - Make code changes
- `git_commit(message)` - Commit changes
- `git_create_pr(title, body)` - Open PR for review
- `run_tests()` - Validate changes

### Level 3 Features (Future)
- `deploy(branch)` - Deploy to staging/prod
- `rollback(version)` - Revert changes
- `self_heal(issue)` - Automatic bug fixes

## Architecture

```
┌─────────────────────────────────────────┐
│          Agent Consciousness             │
│                                         │
│  "I notice an error in my logs..."      │
│                                         │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│         MCP Tool Call                    │
│                                         │
│  read_logs(log_type="backend",          │
│            filter_pattern="ERROR")       │
│                                         │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│       Agent Dev MCP Server               │
│                                         │
│  ✅ Validate request                    │
│  ✅ Check permissions                   │
│  ✅ Execute (read-only)                 │
│  ✅ Redact sensitive data               │
│  ✅ Return results                      │
│                                         │
└─────────────────────────────────────────┘
```
