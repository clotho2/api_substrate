# Systemd Service Setup Guide

This guide covers deploying the Discord bot as a systemd service. The service file `agent-discord.service` is in the substrate repo root.

## Prerequisites

- Linux server with systemd
- Node.js 18+ installed
- Bot dependencies installed (`cd discord_bot && npm install`)
- Bot built (`npm run build`)
- `.env` file configured (`cp .env.example .env`)
- Substrate service (`agent-substrate`) running

## Installation

### 1. Copy Service File

```bash
sudo cp /home/user/api_substrate/agent-discord.service /etc/systemd/system/
```

### 2. Enable and Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable agent-discord
sudo systemctl start agent-discord
```

## Management Commands

```bash
# Check status
sudo systemctl status agent-discord

# View logs (real-time)
sudo journalctl -u agent-discord -f

# View recent logs
sudo journalctl -u agent-discord -n 100

# View logs from today
sudo journalctl -u agent-discord --since today

# Restart
sudo systemctl restart agent-discord

# Stop
sudo systemctl stop agent-discord

# Disable auto-start
sudo systemctl disable agent-discord
```

## Troubleshooting

### Service Won't Start

1. **Check service status:**
   ```bash
   sudo systemctl status agent-discord
   ```

2. **Check logs for errors:**
   ```bash
   sudo journalctl -u agent-discord -n 50
   ```

3. **Verify file paths:**
   ```bash
   cat /etc/systemd/system/agent-discord.service
   ```

4. **Test manually:**
   ```bash
   cd /home/user/api_substrate/discord_bot
   npm start
   ```

### Common Issues

**"Failed to load environment file"**
- Ensure `.env` exists in `discord_bot/` directory
- Path in `EnvironmentFile=` must be absolute

**"Cannot find module"**
- Run `npm install` and `npm run build` in the `discord_bot/` directory

**Bot starts but crashes**
- Check if substrate is running: `curl http://localhost:8284/api/health`
- Check logs: `sudo journalctl -u agent-discord -n 100`

## Security Notes

The service file includes security hardening:
- `NoNewPrivileges=true` - Prevents privilege escalation
- `PrivateTmp=true` - Isolates /tmp directory
- `MemoryMax` / `CPUQuota` - Resource limits (commented out by default, adjust as needed)

Protect your `.env` file:
```bash
chmod 600 /home/user/api_substrate/discord_bot/.env
```

## Updating

```bash
sudo systemctl stop agent-discord
cd /home/user/api_substrate
git pull
cd discord_bot
npm install
npm run build
sudo systemctl start agent-discord
```
