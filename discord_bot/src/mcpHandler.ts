/**
 * 🤖 MCP HANDLER - Rider Pi Demo-Bewegungen via SSH
 * ==================================================
 * 
 * Verarbeitet MCP Commands aus Discord und führt sie auf dem
 * Rider Pi via SSH aus.
 * 
 * ARCHITEKTUR:
 * ┌─────────────┐    Discord     ┌─────────────┐     SSH        ┌─────────────┐
 * │ Letta Cloud │ ────────────> │ Discord Bot │ ──────────────> │  Rider Pi   │
 * │   Agent     │   (Message)   │ (dieser Pi) │   (riderpi)    │  (Robot)    │
 * └─────────────┘               └─────────────┘                 └─────────────┘
 * 
 * UNTERSTÜTZTE ACTIONS:
 * - Demo-Bewegungen (Action 1-6): glueckliches_wackeln, auf_und_ab_wackeln, etc.
 * - Erweiterte Steuerung: adjust_height, adjust_roll, balance_mode, etc.
 */

import { Message, Client, TextChannel } from 'discord.js';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

// ==================== CONFIGURATION ====================

// MCP Command Channel ID
const MCP_COMMAND_CHANNEL_ID = process.env.MCP_COMMAND_CHANNEL_ID || ''; // Configure in .env

// Rider Pi SSH Config
const RIDER_PI_HOST = process.env.RIDER_PI_HOST || 'riderpi.local';
const RIDER_PI_USER = process.env.RIDER_PI_USER || 'xgo';
const RIDER_PI_SSH_KEY = process.env.RIDER_PI_SSH_KEY || '~/.ssh/id_ed25519';
const RIDER_PI_PASSWORD = process.env.RIDER_PI_PASSWORD; // Optional: für Passwort-SSH

// SSH Timeout (Sekunden)
const SSH_TIMEOUT = parseInt(process.env.MCP_SSH_TIMEOUT || '30');

// ==================== INTERFACES ====================

interface MCPCommand {
  type: string;
  tool: string;
  arguments: Record<string, any>;
  timestamp: number;
  request_id: string;
}

interface MCPResponse {
  status: 'success' | 'error';
  message: string;
  result?: any;
  request_id: string;
  execution_time_ms?: number;
}

// ==================== SSH EXECUTION ====================

async function executeSSH(command: string): Promise<string> {
  // Baue SSH Command - unterstützt sowohl Key-basiert als auch Passwort-basiert
  let sshCommand: string;
  
  if (RIDER_PI_PASSWORD) {
    // Passwort-basiert (mit sshpass - muss auf dem Pi installiert sein: sudo apt install sshpass)
    const escapedPassword = RIDER_PI_PASSWORD.replace(/'/g, "'\\''");
    sshCommand = `sshpass -p '${escapedPassword}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=${SSH_TIMEOUT} ${RIDER_PI_USER}@${RIDER_PI_HOST} "${command.replace(/"/g, '\\"')}"`;
  } else {
    // Key-basiert (Standard, sicherer)
    sshCommand = `ssh -i ${RIDER_PI_SSH_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=${SSH_TIMEOUT} ${RIDER_PI_USER}@${RIDER_PI_HOST} "${command.replace(/"/g, '\\"')}"`;
  }
  
  console.log(`🔧 [MCP] SSH: ${command.substring(0, 80)}...`);
  
  try {
    const { stdout, stderr } = await execAsync(sshCommand, { 
      timeout: SSH_TIMEOUT * 1000,
      maxBuffer: 1024 * 1024
    });
    
    if (stderr && !stdout) {
      return `STDERR: ${stderr}`;
    }
    
    return stdout.trim() || 'OK';
    
  } catch (error: any) {
    if (error.killed) {
      return `ERROR: Timeout nach ${SSH_TIMEOUT}s`;
    }
    return `ERROR: ${error.message}`;
  }
}

// ==================== TOOL HANDLERS ====================

function buildSSHCommand(tool: string, args: Record<string, any>): string | null {
  const py = 'python3 -c "from rider_pi_control import Robot; r = Robot();';
  
  switch (tool) {
    // === Connection Test ===
    case 'rider_pi_test_connection':
      return "echo 'Connection OK' && hostname && uname -a";
    
    // === Demo-Bewegungen (Action 1-6) ===
    case 'rider_pi_glueckliches_wackeln':
      return `${py} r.execute_action(1)"`;
    
    case 'rider_pi_auf_und_ab_wackeln':
      return `${py} r.execute_action(2)"`;
    
    case 'rider_pi_kurz_vor_und_zurueck_rollen':
      return `${py} r.execute_action(3)"`;
    
    case 'rider_pi_achten_fahren':
      return `${py} r.execute_action(4)"`;
    
    case 'rider_pi_auf_und_ab_im_kreisdrehen':
      return `${py} r.execute_action(5)"`;
    
    case 'rider_pi_happy_dance':
      return `${py} r.execute_action(6)"`;
    
    // === Erweiterte Steuerung ===
    case 'rider_pi_adjust_height': {
      const height = Math.max(75, Math.min(115, args.height || 85));
      return `${py} r.adjust_height(${height})"`;
    }
    
    case 'rider_pi_adjust_roll': {
      const roll = Math.max(-17, Math.min(17, args.roll || 0));
      return `${py} r.adjust_roll(${roll})"`;
    }
    
    case 'rider_pi_set_balance_mode': {
      const enabled = args.enabled ? 'True' : 'False';
      return `${py} r.set_balance_mode(${enabled})"`;
    }
    
    case 'rider_pi_periodic_squat': {
      const period = Math.max(0, Math.min(4, args.period || 0));
      return `${py} r.periodic_squat(${period})"`;
    }
    
    case 'rider_pi_periodic_shake': {
      const period = Math.max(0, Math.min(4, args.period || 0));
      return `${py} r.periodic_shake(${period})"`;
    }
    
    case 'rider_pi_reset':
      return `${py} r.reset()"`;
    
    default:
      return null;
  }
}

// ==================== MESSAGE HANDLER ====================

export async function handleMCPCommand(message: Message, client: Client): Promise<boolean> {
  // Nur im MCP Command Channel
  if (message.channel.id !== MCP_COMMAND_CHANNEL_ID) {
    return false;
  }
  
  // Prüfe auf MCP_COMMAND Pattern
  const content = message.content;
  if (!content.includes('MCP_COMMAND')) {
    return false;
  }
  
  // Extrahiere request_id
  const requestIdMatch = content.match(/MCP_COMMAND \[([^\]]+)\]/);
  const requestId = requestIdMatch ? requestIdMatch[1] : 'unknown';
  
  console.log(`🤖 [MCP] Verarbeite Command: ${requestId}`);
  
  // Extrahiere JSON
  let mcpCommand: MCPCommand;
  try {
    // Flexibler Regex: unterstützt verschiedene Formatierungen
    let jsonMatch = content.match(/```json\s*\n([\s\S]*?)\n\s*```/);
    if (!jsonMatch) {
      // Fallback: ohne "json" Tag
      jsonMatch = content.match(/```\s*\n([\s\S]*?)\n\s*```/);
    }
    if (!jsonMatch) {
      // Fallback: JSON direkt nach MCP_COMMAND
      const jsonStart = content.indexOf('{');
      const jsonEnd = content.lastIndexOf('}');
      if (jsonStart !== -1 && jsonEnd !== -1 && jsonEnd > jsonStart) {
        const jsonStr = content.substring(jsonStart, jsonEnd + 1);
        mcpCommand = JSON.parse(jsonStr);
      } else {
        throw new Error('Kein JSON Block gefunden');
      }
    } else {
      mcpCommand = JSON.parse(jsonMatch[1].trim());
    }
  } catch (error) {
    console.error(`❌ [MCP] Parse-Fehler: ${error}`);
    await sendMCPResponse(message.channel as TextChannel, {
      status: 'error',
      message: `Parse-Fehler: ${error}`,
      request_id: requestId
    });
    return true;
  }
  
  // Validiere Command
  if (mcpCommand.type !== 'mcp_command' || !mcpCommand.tool) {
    await sendMCPResponse(message.channel as TextChannel, {
      status: 'error',
      message: 'Ungültiges MCP Command Format',
      request_id: requestId
    });
    return true;
  }
  
  // Baue SSH Command
  const sshCommand = buildSSHCommand(mcpCommand.tool, mcpCommand.arguments || {});
  
  if (!sshCommand) {
    await sendMCPResponse(message.channel as TextChannel, {
      status: 'error',
      message: `Unbekanntes Tool: ${mcpCommand.tool}`,
      request_id: requestId
    });
    return true;
  }
  
  // Führe Command aus
  const startTime = Date.now();
  console.log(`🚀 [MCP] Führe aus: ${mcpCommand.tool}`);
  
  try {
    const result = await executeSSH(sshCommand);
    const executionTime = Date.now() - startTime;
    
    const isError = result.startsWith('ERROR:') || result.startsWith('STDERR:');
    
    await sendMCPResponse(message.channel as TextChannel, {
      status: isError ? 'error' : 'success',
      message: isError ? result : `✅ ${mcpCommand.tool} erfolgreich`,
      result: isError ? undefined : result,
      request_id: requestId,
      execution_time_ms: executionTime
    });
    
    console.log(`${isError ? '❌' : '✅'} [MCP] ${mcpCommand.tool}: ${result.substring(0, 80)}`);
    
  } catch (error: any) {
    const executionTime = Date.now() - startTime;
    
    await sendMCPResponse(message.channel as TextChannel, {
      status: 'error',
      message: `Ausführung fehlgeschlagen: ${error.message}`,
      request_id: requestId,
      execution_time_ms: executionTime
    });
    
    console.error(`❌ [MCP] ${mcpCommand.tool} fehlgeschlagen: ${error.message}`);
  }
  
  return true;
}

async function sendMCPResponse(channel: TextChannel, response: MCPResponse): Promise<void> {
  const responseJson = JSON.stringify(response, null, 2);
  const statusEmoji = response.status === 'success' ? '✅' : '❌';
  
  const message = `${statusEmoji} MCP_RESPONSE [${response.request_id}]: \`\`\`json\n${responseJson}\n\`\`\``;
  
  try {
    await channel.send(message);
  } catch (error) {
    console.error(`❌ [MCP] Antwort senden fehlgeschlagen: ${error}`);
  }
}

// ==================== INITIALIZATION ====================

export function initMCPHandler(): void {
  console.log('🤖 MCP Handler initialisiert');
  console.log(`   Channel: ${MCP_COMMAND_CHANNEL_ID}`);
  console.log(`   Rider Pi: ${RIDER_PI_USER}@${RIDER_PI_HOST}`);
  if (RIDER_PI_PASSWORD) {
    console.log(`   SSH Auth: Passwort (sshpass)`);
  } else {
    console.log(`   SSH Auth: Key (${RIDER_PI_SSH_KEY})`);
  }
}

export default { handleMCPCommand, initMCPHandler };
