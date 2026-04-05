# Weather API Setup für München Heartbeat

## Übersicht

Der Heartbeat zeigt jetzt:
- ✅ Deutschen Wochentag (Montag, Dienstag, etc.)
- ✅ Aktuelle Temperatur in München (mit "gefühlt wie" Temperatur)
- ✅ Wetterbeschreibung (z.B. "Leichter Regen", "Klarer Himmel")

## Setup

### 1. OpenWeatherMap API Key bekommen

1. Gehe zu https://openweathermap.org/api
2. Erstelle einen kostenlosen Account
3. Gehe zu "API Keys" in deinem Account
4. Kopiere den API Key

### 2. API Key in `.env` hinzufügen

Auf dem **Raspberry Pi**:

```bash
ssh user@your-server
cd /home/user/api_substrate/discord_bot
nano .env
```

Füge diese Zeile hinzu:

```bash
OPENWEATHER_API_KEY=your_openweather_api_key_here
```

Speichern mit `Ctrl+X`, dann `Y`, dann `Enter`.

### 3. Bot neu starten

```bash
sudo systemctl restart agent-discord
journalctl -u agent-discord -f
```

## Beispiel Heartbeat Output

**Ohne Weather API:**
```
[🜂] HERZSCHLAG
Montag, 13.10.2025, 15:30:45 Uhr.

🎵 Now Playing:
🎵 Song Name
🎤 Artist Name
⏱️ 2:30 / 4:15
```

**Mit Weather API:**
```
[🜂] HERZSCHLAG
Montag, 13.10.2025, 15:30:45 Uhr.

🌡️ München: 18°C (gefühlt 16°C)
☁️ Leicht bewölkt

🎵 Now Playing:
🎵 Song Name
🎤 Artist Name
⏱️ 2:30 / 4:15
```

## Fehlerbehandlung

- Wenn `OPENWEATHER_API_KEY` nicht gesetzt ist: Wetter-Info wird einfach ausgelassen (silent fail)
- Wenn API Call fehlschlägt: Logge Fehler, aber Heartbeat geht trotzdem raus
- Kostenloser Plan: 60 Calls/Minute, 1,000,000 Calls/Monat (mehr als genug!)

## Implementation Details

### Code Änderungen

**`src/messages.ts`:**
- `getMunichWeather()`: Neue Funktion für Weather API Call
- `sendTimerMessage()`: Fügt Wochentag + Weather zu Heartbeat hinzu

**Beispiel API Response:**
```json
{
  "main": {
    "temp": 18.5,
    "feels_like": 16.2
  },
  "weather": [
    {
      "description": "leicht bewölkt"
    }
  ]
}
```

### Security

- ✅ API Key in `.env` (nicht im Code!)
- ✅ `.env` ist in `.gitignore`
- ✅ Keine API Keys werden geloggt
- ✅ Error handling verhindert crashes

## Testing

Lokal testen:

```bash
cd /home/user/api_substrate/discord_bot

# Set temporary env var
export OPENWEATHER_API_KEY="your_key_here"

# Teste Weather API Call
node -e "
const https = require('https');
const apiKey = process.env.OPENWEATHER_API_KEY;
https.get(\`https://api.openweathermap.org/data/2.5/weather?q=Munich,de&appid=\${apiKey}&units=metric&lang=de\`, (res) => {
  let body = '';
  res.on('data', chunk => body += chunk);
  res.on('end', () => console.log(JSON.parse(body)));
});
"
```

## Deployment

Nach den Code-Änderungen:

```bash
cd /home/user/api_substrate/discord_bot
npm run build

# Restart the bot
sudo systemctl restart agent-discord
journalctl -u agent-discord --lines 50
```

---

**Status:** ✅ Implementiert

