# 🤖 MCP Handler Environment Variables Setup

**For the Discord Bot Server**

## 📋 Required Environment Variables

Füge diese Variablen zur `.env` Datei auf dem **Discord Bot Pi** hinzu:

```bash
# Rider Pi SSH Configuration
RIDER_PI_HOST=your_pi_ip_address          # IP address or hostname of your Pi
RIDER_PI_USER=xgo                    # SSH Benutzername auf dem Rider Pi
RIDER_PI_PASSWORD=yahboom            # SSH Passwort (optional, wenn kein SSH Key)
RIDER_PI_SSH_KEY=~/.ssh/id_ed25519   # SSH Key Pfad (optional, wenn Passwort verwendet wird)

# MCP Command Channel
MCP_COMMAND_CHANNEL_ID=your_channel_id_here

# SSH Timeout (optional, Standard: 30 Sekunden)
MCP_SSH_TIMEOUT=30
```

## 🔐 SSH Authentication Methods

Der MCP Handler unterstützt **zwei Methoden**:

### Methode 1: SSH Key (Empfohlen - Sicherer)

```bash
# In .env:
RIDER_PI_HOST=your_pi_ip_address
RIDER_PI_USER=your_username
RIDER_PI_SSH_KEY=~/.ssh/id_ed25519
# RIDER_PI_PASSWORD NICHT setzen
```

**Voraussetzung:** SSH Key muss auf dem Discord Bot Pi vorhanden sein und zum Rider Pi kopiert sein.

### Methode 2: Passwort (Einfacher Setup)

```bash
# In .env:
RIDER_PI_HOST=your_robot_ip_address
RIDER_PI_USER=xgo
RIDER_PI_PASSWORD=yahboom
# RIDER_PI_SSH_KEY kann weggelassen werden
```

**Voraussetzung:** `sshpass` muss auf dem Discord Bot Pi installiert sein:
```bash
sudo apt install sshpass
```

## 🚀 Setup auf Discord Bot Pi

### Schritt 1: .env Datei bearbeiten

```bash
# SSH to your server
ssh user@your-server
cd ~/your-bot-directory
nano .env
```

### Schritt 2: Variablen hinzufügen

Füge am Ende der `.env` Datei hinzu:

```bash
# MCP Handler - Rider Pi Configuration
RIDER_PI_HOST=your_pi_hostname_or_ip
RIDER_PI_USER=your_username
RIDER_PI_PASSWORD=your_password
MCP_COMMAND_CHANNEL_ID=your_channel_id_here
```

### Schritt 3: sshpass installieren (nur bei Passwort-Methode)

```bash
sudo apt update
sudo apt install -y sshpass
```

### Schritt 4: Bot neu starten

```bash
pm2 restart discord-bot
pm2 logs discord-bot --lines 30
```

## ✅ Verification

Nach dem Neustart sollte in den Logs erscheinen:

```
🤖 MCP Handler initialisiert
   Channel: your_mcp_command_channel_id
   Rider Pi: username@your_pi_ip
   SSH Auth: Passwort (sshpass)
```

## 🔍 Troubleshooting

### Problem: "sshpass: command not found"
**Lösung:** `sudo apt install sshpass` auf dem Discord Bot Pi

### Problem: "Permission denied (publickey,password)"
**Lösung:** 
- Prüfe ob Passwort korrekt ist
- Prüfe ob User `xgo` auf dem Rider Pi existiert
- Test manually: `sshpass -p 'your_password' ssh username@your_pi_ip "echo 'OK'"`

### Problem: "Connection timeout"
**Lösung:**
- Check if Rider Pi is reachable: `ping your_pi_ip`
- Check if SSH port 22 is open: `telnet your_pi_ip 22`
- Erhöhe Timeout: `MCP_SSH_TIMEOUT=60`

## 🔒 Security Note

**Passwort in .env ist weniger sicher als SSH Keys!**

Für Produktion empfohlen:
1. SSH Key generieren auf Discord Bot Pi
2. Copy key to Rider Pi: `ssh-copy-id -i ~/.ssh/id_ed25519 username@your_pi_ip`
3. `RIDER_PI_PASSWORD` aus `.env` entfernen
4. Nur `RIDER_PI_SSH_KEY` verwenden

