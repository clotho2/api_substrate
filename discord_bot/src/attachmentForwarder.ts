import { Client, Events } from "discord.js";
import { GrokClient } from "./grokClient";
import axios from "axios";

// ===== CHUNKING UTILITIES (for long Grok responses) =====
function chunkText(text: string, limit: number): string[] {
  const chunks: string[] = [];
  let i = 0;
  while (i < text.length) {
    let end = Math.min(i + limit, text.length);
    let slice = text.slice(i, end);
    if (end < text.length) {
      const lastNewline = slice.lastIndexOf('\n');
      if (lastNewline > Math.floor(limit * 0.6)) {
        end = i + lastNewline + 1;
        slice = text.slice(i, end);
      }
    }
    chunks.push(slice);
    i = end;
  }
  return chunks;
}

async function sendChunkSeries(
  msg: any,
  chunks: string[],
  preferReply: boolean = true
): Promise<void> {
  if (!chunks.length) return;
  try {
    // Send first chunk as reply if preferred
    if (preferReply && typeof msg.reply === 'function') {
      await msg.reply(chunks[0]);
    } else if (typeof msg.channel?.send === 'function') {
      await msg.channel.send(chunks[0]);
    } else {
      await msg.send(chunks[0]);
    }
    
    // Send remaining chunks to channel with delay
    for (let i = 1; i < chunks.length; i++) {
      await new Promise((r) => setTimeout(r, 200));
      if (typeof msg.channel?.send === 'function') {
        await msg.channel.send(chunks[i]);
      } else {
        await msg.send(chunks[i]);
      }
    }
  } catch (err) {
    console.error("❌ Error sending chunked message:", err);
  }
}

// ===== SECURITY & PERFORMANCE CONFIGS =====
const ALLOWED_IMAGE_DOMAINS = [
  'cdn.discordapp.com',
  'media.discordapp.net',
  'images.discordapp.net'
];
const MAX_IMAGES_PER_MESSAGE = 10; // Discord's limit
const MAX_IMAGE_DOWNLOAD_SIZE = 25 * 1024 * 1024; // 25MB
const REQUEST_TIMEOUT = 90000; // 90s (increased for large base64 uploads to Grok)
const SAFE_TARGET_BYTES = 4 * 1024 * 1024; // 4MB safe target
const MAX_BYTES = 5 * 1024 * 1024; // 5MB absolute limit

// Note: Using 2000px dimension limit for multi-image requests (safe default)
const MAX_DIMENSION = 2000; // px - safe dimension limit for multimodal requests

// Rate limiting map: userId -> timestamp
const processingUsers = new Map<string, number>();

// sharp is optional; load dynamically to avoid native install issues where unavailable
async function loadSharp(): Promise<any | null> {
  try {
    const mod: any = await import('sharp');
    return mod?.default ?? mod;
  } catch (err) {
    console.warn('[Sharp] Failed to load sharp module:', err instanceof Error ? err.message : err);
    return null;
  }
}

function createSharpPipeline(sharpMod: any, input: Buffer): any | null {
  try {
    return sharpMod ? sharpMod(input) : null;
  } catch (err) {
    console.error('[Sharp] Failed to create pipeline:', err instanceof Error ? err.message : err);
    return null;
  }
}

// Security: Validate Discord CDN URLs to prevent SSRF attacks
function validateImageUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    // Only allow HTTPS
    if (parsed.protocol !== 'https:') {
      console.warn(`[Security] Rejected non-HTTPS URL: ${url}`);
      return false;
    }
    // Check if domain is in allowed list
    const isAllowed = ALLOWED_IMAGE_DOMAINS.some(domain => parsed.hostname === domain || parsed.hostname.endsWith('.' + domain));
    if (!isAllowed) {
      console.warn(`[Security] Rejected URL from untrusted domain: ${parsed.hostname}`);
    }
    return isAllowed;
  } catch (err) {
    console.error('[Security] Invalid URL format:', url, err instanceof Error ? err.message : err);
    return false;
  }
}

function extractAssistantText(ns: any): string {
  try {
    let out = '';
    const arr = (ns && (ns.messages || ns.data)) || [];
    if (Array.isArray(arr)) {
      for (const m of arr) {
        const type = (m && (m.messageType || m.message_type || m.role));
        if (type === 'assistant_message' || type === 'assistant') {
          const c = m.content;
          if (Array.isArray(c)) {
            for (const p of c) {
              if (p && p.type === 'text' && typeof p.text === 'string') {
                out += p.text;
              }
            }
          } else if (c && typeof c === 'object' && typeof c.text === 'string') {
            out += c.text;
          } else if (typeof c === 'string') {
            out += c;
          }
        }
      }
    }
    if (!out && typeof ns?.content === 'string') return ns.content;
    return out;
  } catch { return ''; }
}

/**
 * Registers a listener that forwards image attachments to Grok API (via api_substrate)
 * and replies with the agent response in the same thread.
 */
export function registerAttachmentForwarder(client: Client) {
  console.log('📦 AttachmentForwarder loaded (with typing + compression + multi-image + security)');
  
  client.on(Events.MessageCreate, async (msg) => {
    // Ignore bot messages
    if (msg.author.bot) return;

    // No attachments? skip
    if (!msg.attachments?.size) return;

    // Collect and validate image URLs
    const urls: string[] = [];
    let rejectedUrls = 0;
    
    // Also collect non-image attachments (PDFs, text files, etc.)
    const nonImageAttachments: Array<{url: string, name: string, type: string, size: number}> = [];
    
    for (const [, att] of msg.attachments) {
      const ct = (att as any).contentType || (att as any).content_type || '';
      const url = (att as any).url || (att as any).proxyURL;
      const name = (att as any).name || 'unknown';
      const size = (att as any).size || 0;
      
      if (ct && typeof ct === 'string' && ct.startsWith('image/') && url) {
        // Image attachments (existing logic)
        const urlStr = String(url);
        // Security: validate URL before processing
        if (validateImageUrl(urlStr)) {
          urls.push(urlStr);
        } else {
          console.warn(`[Security] Skipped invalid image URL from user ${msg.author.id}`);
          rejectedUrls++;
        }
      } else if (url && ct) {
        // Non-image attachments (PDFs, text files, etc.)
        const urlStr = String(url);
        if (validateImageUrl(urlStr)) {  // Same security check
          nonImageAttachments.push({
            url: urlStr,
            name: String(name),
            type: ct,
            size: Number(size)
          });
          console.log(`📎 [Non-image attachment] ${name} (${ct}, ${Math.round(size/1024)}KB)`);
        }
      }
    }
    
    // 🔥 FIX (Nov 7, 2025): Non-image attachments are now handled by the file chunking system
    // The main message handler will process them automatically - no need to forward here!
    if (urls.length === 0 && nonImageAttachments.length > 0) {
      console.log(`📎 Found ${nonImageAttachments.length} non-image attachment(s) - letting main handler process them`);
      return; // Let the main message handler deal with non-image attachments
    }
    
    if (urls.length === 0) {
      // Inform user if images were rejected
      if (rejectedUrls > 0) {
        try {
          await msg.reply("❌ Invalid image sources (only Discord CDN links allowed for security).");
        } catch (err) {
          console.error('[Discord] Failed to send rejection message:', err instanceof Error ? err.message : err);
        }
      }
      return;
    }
    
    // Discord limit check (max 10 images per message)
    if (urls.length > MAX_IMAGES_PER_MESSAGE) {
      console.warn(`[Limit] User ${msg.author.id} sent ${urls.length} images, limiting to ${MAX_IMAGES_PER_MESSAGE}`);
      try {
        await msg.reply(`⚠️ Too many images (${urls.length}). Processing only the first ${MAX_IMAGES_PER_MESSAGE} images.`);
      } catch (err) {
        console.error('[Discord] Failed to send limit message:', err instanceof Error ? err.message : err);
      }
      urls.splice(MAX_IMAGES_PER_MESSAGE); // Keep only first 10
    }

    // Rate limiting: prevent user from spamming concurrent requests
    const userId = msg.author.id;
    const lastProcessing = processingUsers.get(userId);
    const now = Date.now();
    if (lastProcessing && (now - lastProcessing) < 3000) {
      console.warn(`[RateLimit] User ${userId} is sending images too quickly, ignoring`);
      try {
        await msg.react('⏳');
      } catch (err) {
        console.error('[Discord] Failed to react:', err instanceof Error ? err.message : err);
      }
      return;
    }
    processingUsers.set(userId, now);

    let typingInterval: NodeJS.Timeout | null = null;
    let longerTimeout: NodeJS.Timeout | null = null; // For "taking longer" message
    let processingReply: any = null; // Store reply for editing
    
    try {
      // Show typing while processing
      try {
        await (msg.channel as any).sendTyping();
        
        // 🔔 Send immediate processing message
        const processingMsg = urls.length === 1 
          ? "🖼️ Verarbeite dein Bild..." 
          : `🖼️ Verarbeite deine ${urls.length} Bilder...`;
        processingReply = await msg.reply(processingMsg);
        
        // 🕐 Set up "taking longer" message after 60 seconds
        longerTimeout = setTimeout(async () => {
          try {
            if (processingReply) {
              await processingReply.edit(processingMsg + "\n⏱️ Dauert noch etwas länger, hab Geduld...");
            }
          } catch (err) {
            console.warn('[AttachmentForwarder] Could not edit processing message:', err);
          }
        }, 60000); // After 60 seconds
      } catch (err) {
        console.error('[Discord] Failed to send typing indicator:', err instanceof Error ? err.message : err);
      }
      
      typingInterval = setInterval(() => {
        (msg.channel as any).sendTyping().catch((err: Error) => {
          console.error('[Discord] Typing interval error:', err.message);
        });
      }, 8000);

      const userText = (msg.content || '').trim();
      // Build context info (username, channel, timestamp)
      const userName = msg.author.username || 'Unknown';
      const channelInfo = msg.guild 
        ? `#${(msg.channel as any).name || 'unknown-channel'} (channel_id=${msg.channel.id})`
        : 'DM';
      const TIMEZONE = process.env.TIMEZONE || 'America/New_York';
      const LOCALE = process.env.LOCALE || 'en-US';
      const now = new Date();
      const weekday = new Intl.DateTimeFormat(LOCALE, {
        timeZone: TIMEZONE,
        weekday: 'short'
      }).format(now);
      const timeOnly = new Intl.DateTimeFormat(LOCALE, {
        timeZone: TIMEZONE,
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      }).format(now);
      const timestamp = `${weekday}, ${timeOnly}`;
      
      const reply = await forwardImagesToGrok(urls, userId, userName, channelInfo, timestamp, userText, processingReply, msg);
      
      if (reply && reply.trim()) {
        // CHUNKING: Split long responses to avoid Discord's 2000 char limit
        const DISCORD_LIMIT = 1900; // Keep some margin under 2000
        if (reply.length > DISCORD_LIMIT) {
          console.log(`📦 Reply is ${reply.length} chars, chunking into multiple messages...`);
          const chunks = chunkText(reply, DISCORD_LIMIT);
          console.log(`📦 Sending ${chunks.length} chunks to Discord`);
          await sendChunkSeries(msg, chunks, true);
        } else {
          await msg.reply(reply);
        }
      } else {
        console.warn('[Grok] Empty reply received, not sending message');
      }
    } catch (err) {
      console.error("[AttachmentForwarder] Image processing failed:", err instanceof Error ? err.message : err, err);
      
      // Provide helpful error message based on error type
      let userMessage = "❌ Couldn't process image(s).";
      const errMsg = err instanceof Error ? err.message : String(err);
      
      if (errMsg.includes('GROK_BASE_URL') || errMsg.includes('GROK_SESSION_ID')) {
        userMessage += " (Bot configuration error - please contact admin)";
      } else if (errMsg.includes('timeout') || errMsg.includes('ETIMEDOUT')) {
        userMessage += " (Network timeout - please try again later)";
      } else if (errMsg.includes('ECONNREFUSED') || errMsg.includes('network')) {
        userMessage += " (Connection error - Grok API unreachable)";
      } else if (errMsg.includes('401') || errMsg.includes('403')) {
        userMessage += " (API authentication failed - please contact admin)";
      } else if (errMsg.includes('429')) {
        userMessage += " (Too many requests - please wait 1-2 minutes)";
      } else if (errMsg.includes('5MB') || errMsg.includes('too large')) {
        userMessage += " (Images too large - please use smaller images)";
      } else {
        userMessage += " Please try again later.";
      }
      
      try {
        await msg.reply(userMessage);
      } catch (replyErr) {
        console.error('[Discord] Failed to send error reply:', replyErr instanceof Error ? replyErr.message : replyErr);
      }
    } finally {
      // CRITICAL: Always clear the typing interval to prevent memory leaks
      if (typingInterval) {
        clearInterval(typingInterval);
        typingInterval = null;
      }
      
      // Clear "taking longer" timeout if it exists
      if (longerTimeout) {
        clearTimeout(longerTimeout);
      }
      
      // Clean up rate limit after a delay
      setTimeout(() => processingUsers.delete(userId), 10000);
    }
  });
}

// Helper: Download and validate image with proper error handling
async function downloadImage(url: string, index: number, total: number): Promise<{ buffer: Buffer; mediaType: string } | null> {
  try {
    const res = await axios.get(url, { 
      responseType: 'arraybuffer', 
      timeout: REQUEST_TIMEOUT, 
      maxContentLength: MAX_IMAGE_DOWNLOAD_SIZE,
      validateStatus: (status) => status === 200
    });
    
    const mediaType = (res.headers['content-type'] as string) || 'image/jpeg';
    const buffer = Buffer.from(res.data);
    
    console.log(`📥 [${index + 1}/${total}] Downloaded: ${Math.round(buffer.length / 1024)}KB, type=${mediaType}`);
    return { buffer, mediaType };
  } catch (err) {
    console.error(`[Download] Failed to download image ${index + 1}/${total}:`, err instanceof Error ? err.message : err);
    return null;
  }
}

// Helper: Compress image buffer with adaptive strategy + dimension checking
async function compressImage(buffer: Buffer, mediaType: string, index: number, total: number, forceDimensionCheck: boolean = false): Promise<{ buffer: Buffer; mediaType: string } | null> {
  const sharpMod = await loadSharp();
  if (!sharpMod) {
    console.warn(`⚠️ [${index + 1}/${total}] sharp not available; cannot compress`);
    return null;
  }

  // CRITICAL: Get image metadata to check dimensions
  let metadata;
  try {
    metadata = await createSharpPipeline(sharpMod, buffer)?.metadata();
  } catch (err) {
    console.error(`❌ [${index + 1}/${total}] Failed to read image metadata:`, err instanceof Error ? err.message : err);
    return null;
  }

  const originalWidth = metadata?.width || 0;
  const originalHeight = metadata?.height || 0;
  const exceedsDimensions = originalWidth > MAX_DIMENSION || originalHeight > MAX_DIMENSION;

  console.log(`📐 [${index + 1}/${total}] Original: ${originalWidth}x${originalHeight}px, ${Math.round(buffer.length / 1024)}KB`);

  // If dimensions are fine AND size is fine, skip compression
  if (!exceedsDimensions && buffer.length <= SAFE_TARGET_BYTES && !forceDimensionCheck) {
    console.log(`✅ [${index + 1}/${total}] No compression needed`);
    return { buffer, mediaType };
  }

  let buf = buffer;
  // Start with safe dimensions
  let width = Math.min(MAX_DIMENSION, originalWidth);
  let quality = 70;
  let fmt: 'webp' | 'jpeg' = 'webp';
  let attempts = 0;
  const maxAttempts = 10;
  let needsResize = exceedsDimensions; // Track if we still need dimension fixes

  // Compress if size OR dimensions exceed limits
  while ((buf.length > SAFE_TARGET_BYTES || needsResize) && attempts < maxAttempts) {
    const pipeline = createSharpPipeline(sharpMod, buf)?.rotate().resize({ width, withoutEnlargement: true });
    if (!pipeline) {
      console.warn(`⚠️ [${index + 1}/${total}] Failed to create pipeline at attempt ${attempts + 1}`);
      return null;
    }

    try {
      const out = fmt === 'webp'
        ? await pipeline.webp({ quality }).toBuffer()
        : await pipeline.jpeg({ quality, mozjpeg: true }).toBuffer();
      
      console.log(`🗜️ [${index + 1}/${total}] Attempt ${attempts + 1}: ${fmt} ${width}px q${quality} → ${Math.round(out.length / 1024)}KB`);
      
      buf = out;
      mediaType = fmt === 'webp' ? 'image/webp' : 'image/jpeg';
      
      // After first resize, dimensions are fixed
      if (needsResize && width <= MAX_DIMENSION) {
        needsResize = false;
        console.log(`✅ [${index + 1}/${total}] Dimensions now within safe limit (${width}px)`);
      }

      if (buf.length > SAFE_TARGET_BYTES) {
        // Adaptive compression strategy
        if (quality > 40) {
          quality = Math.max(35, quality - 10);
        } else if (width > 640) {
          width = Math.max(640, Math.floor(width * 0.8));
        } else if (fmt === 'webp') {
          // Switch to JPEG if WEBP isn't helping
          fmt = 'jpeg';
          quality = 55;
          width = Math.min(width, 1024);
        } else {
          quality = Math.max(30, quality - 5);
          width = Math.max(480, Math.floor(width * 0.85));
        }
      }
      attempts++;
    } catch (err) {
      console.error(`[Compress] Compression failed at attempt ${attempts + 1}:`, err instanceof Error ? err.message : err);
      return null;
    }
  }

  if (buf.length > SAFE_TARGET_BYTES) {
    console.warn(`⚠️ [${index + 1}/${total}] Still ${Math.round(buf.length / 1024)}KB after ${attempts} attempts`);
    return null;
  }

  console.log(`✅ [${index + 1}/${total}] Compressed to ${Math.round(buf.length / 1024)}KB (${mediaType})`);
  return { buffer: buf, mediaType };
}

async function forwardImagesToGrok(
  urls: string[],
  userId: string,
  userName: string,
  channelInfo: string,
  timestamp: string,
  userText?: string,
  statusMessage: any = null,
  discordMessage: any = null // Direct access to Discord message for real-time sending
): Promise<string> {
  const baseUrl = process.env.GROK_BASE_URL || 'http://localhost:8284';
  const sessionId = process.env.GROK_SESSION_ID || 'discord-bot';
  const model = process.env.GROK_MODEL;  // Use same model as text messages

  const grokClient = new GrokClient({
    baseUrl,
    sessionId,
    model,  // Pass model from env var (ensures consistency with text messages)
    timeout: REQUEST_TIMEOUT  // 90s timeout for image uploads
  });

  // 🔧 Direct base64 upload (URL upload had reliability issues)
  console.log(`📦 Processing ${urls.length} image(s) via base64 upload, hasText=${!!(userText && userText.trim())}`);
  
  try {
    const base64Images: any[] = [];
    let skippedCount = 0;
    let compressedCount = 0;

    // Process images sequentially to avoid memory spikes
    for (let i = 0; i < urls.length; i++) {
        const url = urls[i];
        
        // Download image
        const downloaded = await downloadImage(url, i, urls.length);
        if (!downloaded) {
          skippedCount++;
          continue;
        }

      let { buffer, mediaType } = downloaded;

      // CRITICAL: ALWAYS check dimensions (2000px safe limit) even for single images
      const isMultiImage = urls.length > 1;
      // Force dimension check for ALL images (not just multi-image)
      const needsCompression = buffer.length > SAFE_TARGET_BYTES || true; // Always check!
        
        if (needsCompression) {
          if (buffer.length > SAFE_TARGET_BYTES) {
            console.log(`🗜️ [${i + 1}/${urls.length}] Image exceeds safe size limit, compressing...`);
          } else {
            console.log(`📐 [${i + 1}/${urls.length}] Checking dimensions for multi-image request...`);
          }
          
          // Update status message with compression info
          if (statusMessage) {
            try {
              const baseMsg = urls.length === 1 
                ? "🖼️ Verarbeite dein Bild..." 
                : `🖼️ Verarbeite deine ${urls.length} Bilder...`;
              await statusMessage.edit(`${baseMsg}\n🗜️ Komprimiere Bild ${i + 1}/${urls.length}...`);
            } catch (err) {
              console.warn('[Status] Could not update compression status:', err instanceof Error ? err.message : err);
            }
          }
          
          const compressed = await compressImage(buffer, mediaType, i, urls.length, isMultiImage);
          
          if (!compressed) {
            console.warn(`⚠️ [${i + 1}/${urls.length}] Compression/resize failed, skipping image`);
            skippedCount++;
            continue;
          }

          buffer = compressed.buffer;
          mediaType = compressed.mediaType;
          if (compressed.buffer.length !== downloaded.buffer.length || isMultiImage) {
            compressedCount++;
          }
        }

        // Convert to base64 and add to payload
        const base64Data = buffer.toString('base64');
        base64Images.push({ 
          type: 'image', 
          source: { type: 'base64', mediaType, data: base64Data } 
        });

        // CRITICAL: Clear buffer reference to free memory immediately
        buffer = null as any;
      }

      console.log(`📊 Base64 processing complete: ${base64Images.length} images, ${compressedCount} compressed, ${skippedCount} skipped`);
      console.log(`🔍 [DEBUG] About to check statusMessage update...`);

      // Update status with final processing info
      if (statusMessage && compressedCount > 0) {
        console.log(`🔍 [DEBUG] Updating status message...`);
        try {
          const baseMsg = urls.length === 1 
            ? "🖼️ Verarbeite dein Bild..." 
            : `🖼️ Verarbeite deine ${urls.length} Bilder...`;
          const compressMsg = compressedCount === 1
            ? "✅ 1 Bild komprimiert"
            : `✅ ${compressedCount} Bilder komprimiert`;
          await statusMessage.edit(`${baseMsg}\n${compressMsg}\n📤 Sende an Grok...`);
          console.log(`🔍 [DEBUG] Status message updated successfully`);
        } catch (err) {
          console.warn('[Status] Could not update final status:', err instanceof Error ? err.message : err);
        }
      }

      console.log(`🔍 [DEBUG] Checking if base64Images.length === 0... (length=${base64Images.length})`);
      if (base64Images.length === 0) {
        // Provide specific reason why all images failed
        if (skippedCount === urls.length) {
          const sharpAvailable = await loadSharp();
          if (!sharpAvailable) {
            return "❌ All images too large (>4MB) and compression unavailable.\n💡 Tip: Please resize images first or ask admin to install 'sharp'.";
          } else {
            return "❌ All images failed compression (possibly corrupt files).\n💡 Tip: Please try different or smaller images (<2MB).";
          }
        } else {
          return "❌ All images failed to download (network issue).\n💡 Tip: Please try again later.";
        }
      }

      console.log(`🔍 [DEBUG] Building payload for ${base64Images.length} image(s)...`);

      // Build context message with user and channel info
      const contextPrefix = `[${userName} (id=${userId}, time=${timestamp}) sent ${base64Images.length} image(s) in ${channelInfo}]`;
      const textContent = userText && userText.trim()
        ? `${contextPrefix} ${userText}`
        : `${contextPrefix} Describe the image(s).`;

      // ✅ Build request payload using OpenAI/Grok multimodal format
      // Format: content as array with text and image_url objects
      // This format is supported by api_substrate for multimodal messages
      const contentArray: any[] = [
        { type: 'text', text: textContent }
      ];

      // Add each image as an image_url object with data URI
      for (const img of base64Images) {
        const mediaType = img.source.mediaType || 'image/jpeg';
        const base64Data = img.source.data;
        contentArray.push({
          type: 'image_url',
          image_url: {
            url: `data:${mediaType};base64,${base64Data}`
          }
        });
      }

      const payload: any = {
        messages: [
          {
            role: 'user',
            content: contentArray  // OpenAI/Grok multimodal format
          }
        ]
      };

      console.log(`🔍 [DEBUG] Payload built, sending to api_substrate with streaming...`);

      // 📊 CREDIT TRACKING: Log image attachment call
      console.log(`
╔══════════════════════════════════════
║ 📤 GROK CALL (IMAGE ATTACHMENT)
║ Time: ${timestamp}
║ Reason: image_attachment
║ Images: ${base64Images.length}
║ User: ${userName}
╚══════════════════════════════════════`);

      // ✅ Call Grok API with STREAMING for real-time responses
      let text2 = '';
      let hasSentContent = false;
      let contentWasReset = false;
      let doneResponse: string | null = null;

      try {
        for await (const chunk of grokClient.chatStream({
          messages: payload.messages,
          session_id: sessionId,
        })) {
          console.log(`📦 [STREAM CHUNK] Event: ${chunk.event}`);

          // Handle different chunk types
          if (chunk.event === 'thinking' && chunk.data) {
            const content = typeof chunk.data === 'string' ? chunk.data : chunk.data.content || '';
            console.log(`💭 [THINKING] ${content.substring(0, 100)}...`);
          } else if (chunk.event === 'content' && chunk.data) {
            const content = typeof chunk.data === 'string' ? chunk.data : chunk.data.content || '';
            console.log(`💬 [CONTENT] ${content.substring(0, 100)}...`);
            text2 += content;

            // Send content immediately to Discord
            if (discordMessage && content.trim()) {
              await discordMessage.channel.send(content);
              hasSentContent = true;
            }
          } else if (chunk.event === 'content_reset') {
            // Backend discovered streamed content was <tool_call> XML, not real content
            const reason = chunk.data?.reason || 'unknown';
            console.log(`🔄 [CONTENT RESET] Clearing ${text2.length} chars of accumulated content (reason: ${reason})`);
            if (hasSentContent) {
              console.warn(`🔄 ⚠️ Content was already streamed to Discord before reset - will send corrected response from done event`);
              contentWasReset = true;
            }
            text2 = '';
          } else if (chunk.event === 'tool_call' && chunk.data) {
            const toolName = chunk.data.name || 'unknown';
            const toolArgs = chunk.data.arguments || {};
            console.log(`🔧 [TOOL CALL] ${toolName}(${JSON.stringify(toolArgs).substring(0, 100)}...)`);

            // Send tool call info to Discord
            if (discordMessage) {
              const toolMessage = `**🔧 Tool: ${toolName}**`;
              await discordMessage.channel.send(toolMessage);
            }
          } else if (chunk.event === 'done') {
            console.log(`✅ [STREAM DONE] Total content: ${text2.length} chars`);

            // Use done.response as authoritative final response (backend fix ensures it's populated)
            if (chunk.data?.response && typeof chunk.data.response === 'string' && chunk.data.response.trim()) {
              const finalResponse = chunk.data.response;
              doneResponse = finalResponse;
              console.log(`📋 [DONE] Authoritative response available (${finalResponse.length} chars)`);
              // Override accumulated content with authoritative response
              if (finalResponse !== text2) {
                console.log(`📋 [DONE] Using done.response over accumulated content (${text2.length} chars)`);
                text2 = finalResponse;
              }
            }

            // Log token usage if available
            if (chunk.data && chunk.data.tokens) {
              const tokens = chunk.data.tokens;
              console.log(`📊 Tokens: ${tokens.prompt} prompt + ${tokens.completion} completion = ${tokens.total} total`);
            }
            // Also check for usage at top level (new done event format)
            if (chunk.data?.usage) {
              const u = chunk.data.usage;
              console.log(`📊 Usage: ${u.prompt_tokens || 0} prompt + ${u.completion_tokens || 0} completion = ${u.total_tokens || 0} total`);
            }
          }
        }
      } catch (streamError: any) {
        console.error('❌ Error processing stream:', streamError);
        const errMsg = streamError instanceof Error ? streamError.message : String(streamError);

        // Socket termination errors - return partial text if we got any
        if (/termiagentd|other side closed|socket.*closed|UND_ERR_SOCKET/i.test(errMsg)) {
          console.log(`🔌 Stream termiagentd early - returning collected text (${text2.length} chars)`);
        } else {
          console.log(`⚠️ Stream error - attempting to return partial text (${text2.length} chars)`);

          // If stream error AND no text collected AND nothing sent, inform user!
          if (text2.length === 0 && !hasSentContent) {
            console.error(`❌ Stream error with no response collected - informing user`);
            throw new Error('Stream failed with no response collected');
          }
        }
      }

      // If content was reset after being streamed to Discord, send the corrected response
      if (contentWasReset && doneResponse && discordMessage) {
        console.log(`🔄 [CONTENT RESET RECOVERY] Sending corrected response (${doneResponse.length} chars) after content reset`);
        try {
          // Chunk for Discord's 2000-char limit
          const chunks = doneResponse.match(/[\s\S]{1,1990}/g) || [];
          for (const c of chunks) {
            await discordMessage.channel.send(c);
          }
        } catch (sendErr) {
          console.error(`❌ Failed to send corrected response after content reset:`, sendErr);
        }
        return "";
      }

      // If we already sent content via streaming, return empty to avoid duplicate
      if (hasSentContent) {
        console.log(`✅ [STREAM END] Content already sent via real-time streaming - suppressing duplicate`);
        return "";
      }

      return text2;

    } catch (e: any) {
      const detail = (e?.body?.detail || e?.response?.data || e?.message || '').toString();
      const statusCode = e?.statusCode || e?.response?.status || 0;
      console.error('[Grok] Image upload failed:', e instanceof Error ? e.message : e);

      // Provide specific error messages based on failure type
      if (/exceeds\s*5\s*MB/i.test(detail) || /payload.*large/i.test(detail)) {
        return "❌ Image(s) still too large even after compression (>5MB).\n💡 Tip: Please use smaller images (<2MB recommended).";
      } else if (/401|403|unauthorized/i.test(detail)) {
        return "❌ API authentication failed.\n💡 Please contact admin (API key issue).";
      } else if (/429|rate.?limit/i.test(detail)) {
        return "❌ Too many API requests.\n💡 Please wait 1-2 minutes and try again.";
      } else if (/timeout|ETIMEDOUT/i.test(detail)) {
        return "❌ API timeout - processing took too long.\n💡 Please use smaller images or try later.";
      } else if (/network|ECONNREFUSED|ENOTFOUND/i.test(detail)) {
        return "❌ Grok API unreachable.\n💡 Please try again later or contact admin.";
      } else if (statusCode === 502 || statusCode === 503 || /bad gateway|service unavailable/i.test(detail)) {
        return "❌ Grok server having issues (502/503 error).\n💡 Their backend is overloaded - please try again in 1-2 minutes.";
      }

      return `❌ Error processing image: ${detail}`;
    }
}
