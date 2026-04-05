/**
 * 🎥 YouTube Transcript Integration
 * 
 * Automatically fetches and attaches YouTube video transcripts to messages
 * before sending to Letta. Smart chunking for long videos.
 * 
 * Created: October 26, 2025
 * Updated: October 26, 2025 - Switched to youtubei.js for better reliability
 */

import { Innertube } from 'youtubei.js';

// Initialize YouTube client (reuse instance)
let youtubeClient: Innertube | null = null;

async function getYouTubeClient(): Promise<Innertube> {
  if (!youtubeClient) {
    console.log('🔧 Initializing YouTube client...');
    youtubeClient = await Innertube.create();
    console.log('✅ YouTube client initialized');
  }
  return youtubeClient;
}

// Cache for long video transcripts
const transcriptCache: Map<string, {
  full: string;
  chunks: ChunkInfo[];
  metadata: TranscriptMetadata;
  timestamp: number;
}> = new Map();

interface ChunkInfo {
  text: string;
  startTime: string;  // e.g., "0:00"
  endTime: string;    // e.g., "10:45"
  index: number;      // Chunk number (1-based)
}

interface TranscriptMetadata {
  videoId: string;
  title: string;
  language: string;
  length: number;
  estimatedDuration: string;
}

// Configuration
const THRESHOLD = 10000; // When to switch from full to preview (chars)
const PREVIEW_SIZE = 3000; // Beginning/end size for previews
const CHUNK_SIZE = 8000; // Size of on-demand chunks
const CACHE_TTL = 3600000; // 1 hour cache (milliseconds)

/**
 * Extract YouTube video ID from URL
 */
function extractVideoId(url: string): string | null {
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/v\/([a-zA-Z0-9_-]{11})/
  ];

  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match) return match[1];
  }
  return null;
}

/**
 * Fetch transcript from YouTube using youtubei.js (with timestamps)
 */
async function fetchTranscript(videoId: string): Promise<{ 
  text: string; 
  language: string; 
  title: string;
  segments: Array<{ text: string; startMs: number; }>;
} | null> {
  try {
    console.log(`📺 Fetching transcript for video: ${videoId}`);
    
    const yt = await getYouTubeClient();
    
    // Get video info
    const info = await yt.getInfo(videoId);
    
    if (!info) {
      console.log(`⚠️ Could not get video info for: ${videoId}`);
      return null;
    }
    
    const title = info.basic_info?.title || `Video ${videoId}`;
    console.log(`📺 Video title: "${title}"`);
    
    // Try to get transcript
    const transcriptData = await info.getTranscript();
    
    if (!transcriptData) {
      console.log(`⚠️ No transcript available for video: ${videoId}`);
      return null;
    }
    
    // Get transcript content
    const transcript = transcriptData.transcript;
    
    if (!transcript?.content?.body?.initial_segments) {
      console.log(`⚠️ Transcript data structure unexpected for: ${videoId}`);
      return null;
    }
    
    // Extract text and timestamps from segments
    const rawSegments = transcript.content.body.initial_segments;
    const segments = rawSegments
      .map((segment: any) => ({
        text: segment.snippet?.text?.toString() || '',
        startMs: segment.start_ms || segment.startMs || 0
      }))
      .filter((seg: any) => seg.text.length > 0);
    
    const text = segments.map((s: any) => s.text).join(' ');
    
    if (!text || text.length === 0) {
      console.log(`⚠️ Transcript is empty for: ${videoId}`);
      return null;
    }
    
    // Get language (if available)
    const language = (transcript as any).language || 'English';
    
    console.log(`✅ Transcript fetched: ${videoId} - "${title}" (${text.length} chars, ${segments.length} segments, ${language})`);
    
    return { text, language, title, segments };
    
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    const errorName = error instanceof Error ? error.name : 'Unknown';
    
    // 🔥 FIX: Ignore ParsingErrors from youtubei.js - they're warnings, not critical
    // These happen when YouTube changes their API structure, but transcripts often still work
    if (errorMessage.includes('ParsingError') || errorMessage.includes('Type mismatch')) {
      console.log(`⚠️ YouTube API parsing warning (non-critical) for ${videoId} - transcript may still work`);
      // Try to continue anyway - sometimes transcripts work despite parsing errors
      // But we'll return null to be safe, as the transcript data might be incomplete
      return null;
    }
    
    console.error(`❌ Error fetching transcript for ${videoId}:`);
    console.error(`   Type: ${errorName}`);
    console.error(`   Message: ${errorMessage}`);
    
    // Check for specific error types
    if (errorMessage.includes('Transcript is disabled')) {
      console.log(`   → Transcript is disabled for this video`);
    } else if (errorMessage.includes('Could not find') || errorMessage.includes('not available')) {
      console.log(`   → No transcript available for this video`);
    } else {
      console.error(`   Full error:`, error);
    }
    
    return null;
  }
}

/**
 * Format milliseconds to timestamp (e.g., "1:23:45" or "10:30")
 */
function formatTimestamp(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  }
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

/**
 * Create chunks from long transcript with timestamps
 */
function createChunksWithTimestamps(
  segments: Array<{ text: string; startMs: number }>, 
  chunkSize: number
): ChunkInfo[] {
  const chunks: ChunkInfo[] = [];
  let currentChunk = '';
  let chunkStartMs = segments[0]?.startMs || 0;
  let chunkIndex = 1;
  
  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i];
    const segmentText = segment.text + ' ';
    
    // 🔥 FIX: Handle segments that are themselves larger than chunkSize
    // If the segment itself is too large, we need to split it
    if (segmentText.length > chunkSize) {
      console.log(`⚠️ Large segment detected (${segmentText.length} chars > ${chunkSize}): splitting into multiple chunks`);
      
      // First, finalize current chunk if it has content
      if (currentChunk.length > 0) {
        chunks.push({
          text: currentChunk.trim(),
          startTime: formatTimestamp(chunkStartMs),
          endTime: formatTimestamp(segment.startMs),
          index: chunkIndex++
        });
        currentChunk = '';
      }
      
      // Split the large segment into multiple chunks
      let segmentStartMs = segment.startMs;
      let remainingText = segment.text;
      let subChunkCount = 0;
      
      while (remainingText.length > 0) {
        // Take up to chunkSize characters
        const chunkText = remainingText.slice(0, chunkSize);
        remainingText = remainingText.slice(chunkSize);
        
        // Estimate end time based on proportion of text processed
        const textProportion = chunkText.length / segment.text.length;
        const segmentDuration = i < segments.length - 1 
          ? (segments[i + 1].startMs - segment.startMs)
          : 5000; // Default 5 seconds if last segment
        const chunkEndMs = segmentStartMs + Math.round(segmentDuration * textProportion);
        
        chunks.push({
          text: chunkText.trim(),
          startTime: formatTimestamp(segmentStartMs),
          endTime: formatTimestamp(chunkEndMs),
          index: chunkIndex++
        });
        
        segmentStartMs = chunkEndMs;
        subChunkCount++;
      }
      
      console.log(`✅ Split large segment into ${subChunkCount} chunks`);
      
      // Update chunkStartMs for next segment
      chunkStartMs = segment.startMs + (i < segments.length - 1 
        ? (segments[i + 1].startMs - segment.startMs)
        : 5000);
      continue;
    }
    
    // Normal case: If adding this segment would exceed chunk size, finalize current chunk
    if (currentChunk.length + segmentText.length > chunkSize && currentChunk.length > 0) {
      chunks.push({
        text: currentChunk.trim(),
        startTime: formatTimestamp(chunkStartMs),
        endTime: formatTimestamp(segment.startMs),
        index: chunkIndex++
      });
      
      currentChunk = segmentText;
      chunkStartMs = segment.startMs;
    } else {
      currentChunk += segmentText;
    }
  }
  
  // Add final chunk
  if (currentChunk.length > 0) {
    const lastSegment = segments[segments.length - 1];
    chunks.push({
      text: currentChunk.trim(),
      startTime: formatTimestamp(chunkStartMs),
      endTime: formatTimestamp(lastSegment.startMs + 5000), // Estimate end time
      index: chunkIndex
    });
  }
  
  return chunks;
}

/**
 * Estimate video duration from transcript length
 */
function estimateDuration(length: number): string {
  const estimatedMinutes = Math.round(length / 1200); // ~1200 chars per minute
  if (estimatedMinutes < 2) return '~1 min';
  if (estimatedMinutes < 60) return `~${estimatedMinutes} min`;
  const hours = Math.floor(estimatedMinutes / 60);
  const minutes = estimatedMinutes % 60;
  return `~${hours}h ${minutes}min`;
}

/**
 * Process transcript intelligently (full or preview with timestamps)
 */
async function processTranscript(
  videoId: string, 
  fullText: string, 
  language: string, 
  title: string,
  segments: Array<{ text: string; startMs: number }>
): Promise<string> {
  const metadata: TranscriptMetadata = {
    videoId,
    title,
    language,
    length: fullText.length,
    estimatedDuration: estimateDuration(fullText.length)
  };

  // Short video: Return full transcript (no metadata box, just title)
  if (fullText.length <= THRESHOLD) {
    console.log(`✅ Transcript processed: ${videoId} (full)`);
    
    return `

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 VIDEO TRANSCRIPT (by Discord Bot)
"${title}"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${fullText}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
  }

  // Long video: Cache full transcript with timestamps and return preview
  const chunks = createChunksWithTimestamps(segments, CHUNK_SIZE);
  
  transcriptCache.set(videoId, {
    full: fullText,
    chunks,
    metadata,
    timestamp: Date.now()
  });

  console.log(`✅ Transcript processed: ${videoId} (preview, ${chunks.length} chunks cached with timestamps)`);

  // Create chunk overview with timestamps and brief preview
  const chunkOverview = chunks.map(chunk => {
    const preview = chunk.text.slice(0, 100).replace(/\n/g, ' ');
    return `  📍 Chunk ${chunk.index}: ${chunk.startTime} - ${chunk.endTime} | "${preview}..."`;
  }).join('\n');

  const beginning = fullText.slice(0, PREVIEW_SIZE);
  const ending = fullText.slice(-PREVIEW_SIZE);
  const middleLength = fullText.length - (PREVIEW_SIZE * 2);

  return `

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 VIDEO TRANSCRIPT PREVIEW (by Discord Bot)
"${title}"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 BEGINNING (${formatTimestamp(segments[0].startMs)}):
${beginning}

... [MIDDLE SECTION: ${middleLength.toLocaleString()} chars] ...

📖 ENDING:
${ending}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 CHUNK OVERVIEW (${chunks.length} chunks available)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${chunkOverview}

💡 Commands for you:
- "show me chunk X of ${videoId}" → Get specific chunk (e.g., "show me chunk 2 of ${videoId}")
- "show me info for ${videoId}" → Get video metadata
- "minute 15" or "15:30" or "at 15:30" → Get chunk containing that timestamp
- You can reference timestamps (e.g., "what happens at 10:30?", "show me minute 15")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
}

/**
 * Main function: Preprocess YouTube links in message content
 * Returns both processed content and status info for user feedback
 */
export async function preprocessYouTubeLinks(content: string, sendTyping?: () => Promise<void>): Promise<{
  content: string;
  videosProcessed: number;
  videosFailed: number;
}> {
  // Find all YouTube URLs in the message
  const youtubeRegex = /https?:\/\/(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/g;
  const matches = [...content.matchAll(youtubeRegex)];

  if (matches.length === 0) {
    return { content, videosProcessed: 0, videosFailed: 0 }; // No YouTube links found
  }

  console.log(`📺 Found ${matches.length} YouTube link(s) - fetching transcripts...`);

  let processedContent = content;
  let videosProcessed = 0;
  let videosFailed = 0;

  // Process each YouTube link
  for (const match of matches) {
    const videoId = extractVideoId(match[0]);
    
    if (!videoId) {
      videosFailed++;
      continue;
    }

    console.log(`🎥 Processing video: ${videoId}`);
    
    // Send typing indicator to show activity
    if (sendTyping) {
      await sendTyping();
    }

    const transcriptData = await fetchTranscript(videoId);
    
    if (!transcriptData) {
      console.log(`⚠️ Skipping video ${videoId} (no transcript available)`);
      videosFailed++;
      continue;
    }

    const transcriptText = await processTranscript(
      videoId, 
      transcriptData.text, 
      transcriptData.language, 
      transcriptData.title,
      transcriptData.segments
    );
    
    // Append transcript to message content
    processedContent += transcriptText;
    videosProcessed++;
    
    console.log(`✅ Video ${videoId} processed successfully`);
  }

  console.log(`📺 YouTube processing complete: ${videosProcessed} successful, ${videosFailed} failed`);

  return { content: processedContent, videosProcessed, videosFailed };
}

/**
 * Parse timestamp string to milliseconds
 * Supports: "15:30", "1:15:30", "15", "15 min", "15 minutes", "15:30:45"
 * Also parses formatted timestamps from chunks: "0:00", "10:45", "1:23:45"
 */
function parseTimestampToMs(timestampStr: string): number | null {
  if (!timestampStr) return null;
  
  // Remove common words
  const cleaned = timestampStr.toLowerCase()
    .replace(/minute|min|m\b/g, '')
    .replace(/second|sec|s\b/g, '')
    .replace(/hour|h\b/g, '')
    .trim();
  
  // Pattern 1: "15:30" or "1:15:30" (MM:SS or HH:MM:SS)
  // Also handles "0:00", "10:45" from chunk timestamps
  const timePattern = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/;
  const timeMatch = cleaned.match(timePattern);
  if (timeMatch) {
    if (timeMatch[3]) {
      // HH:MM:SS format
      const hours = parseInt(timeMatch[1], 10);
      const minutes = parseInt(timeMatch[2], 10);
      const seconds = parseInt(timeMatch[3], 10);
      return (hours * 3600 + minutes * 60 + seconds) * 1000;
    } else {
      // MM:SS format (could be minutes:seconds or hours:minutes)
      const first = parseInt(timeMatch[1], 10);
      const second = parseInt(timeMatch[2], 10);
      // If first number > 59, assume HH:MM format
      if (first > 59) {
        return (first * 3600 + second * 60) * 1000;
      }
      // Otherwise assume MM:SS format
      return (first * 60 + second) * 1000;
    }
  }
  
  // Pattern 2: Just a number (assume minutes)
  const numberPattern = /^(\d+)$/;
  const numberMatch = cleaned.match(numberPattern);
  if (numberMatch) {
    const minutes = parseInt(numberMatch[1], 10);
    return minutes * 60 * 1000;
  }
  
  return null;
}

/**
 * Find chunk that contains a specific timestamp
 */
function findChunkByTimestamp(chunks: ChunkInfo[], targetMs: number): ChunkInfo | null {
  for (const chunk of chunks) {
    // Parse chunk times to milliseconds for comparison
    const startMs = parseTimestampToMs(chunk.startTime);
    const endMs = parseTimestampToMs(chunk.endTime);
    
    if (startMs !== null && endMs !== null) {
      // Check if target time is within this chunk's range
      if (targetMs >= startMs && targetMs <= endMs) {
        return chunk;
      }
    }
  }
  return null;
}

/**
 * Handle chunk requests from Letta/the bot
 * Detects patterns like: "show me chunk 2 of VIDEO_ID" or "show me info for VIDEO_ID"
 * Also supports time-based requests: "minute 15", "15:30", "what happens at 15:30"
 */
export function handleChunkRequest(content: string): string | null {
  // Check for info request first
  const infoPattern = /(?:show me )?info (?:for |of )?([a-zA-Z0-9_-]{11})/i;
  const infoMatch = content.match(infoPattern);
  
  if (infoMatch) {
    const videoId = infoMatch[1];
    const cached = transcriptCache.get(videoId);
    
    if (!cached) {
      console.log(`❌ Video ${videoId} not found in cache`);
      return `❌ Video ${videoId} not found in cache. Please share the video link first.`;
    }
    
    // 🔥 FIX: Check if cache has expired
    const now = Date.now();
    if (now - cached.timestamp > CACHE_TTL) {
      console.log(`❌ Video ${videoId} cache expired (age: ${Math.round((now - cached.timestamp) / 1000 / 60)} minutes)`);
      transcriptCache.delete(videoId); // Clean up expired entry
      return `❌ Transcript cache expired (older than 1 hour). Please share the video link again to refresh the cache.`;
    }
    
    console.log(`📊 Sending info for ${videoId}`);
    
    // Create chunk overview with timestamps
    const chunkList = cached.chunks.map(chunk => 
      `  📍 Chunk ${chunk.index}: ${chunk.startTime} - ${chunk.endTime}`
    ).join('\n');
    
    return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 VIDEO INFO (by Discord Bot)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Title: "${cached.metadata.title}"
Video ID: ${cached.metadata.videoId}
Language: ${cached.metadata.language}
Duration: ${cached.metadata.estimatedDuration}
Total Length: ${cached.metadata.length.toLocaleString()} chars

📚 AVAILABLE CHUNKS (${cached.chunks.length}):
${chunkList}

💡 Request chunks with: "show me chunk X of ${videoId}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
  }
  
  // 🕐 TIME-BASED REQUEST: Check for timestamp patterns first
  // Patterns: "minute 15", "15:30", "at 15:30", "15 min", "what happens at 15:30", etc.
  // 🔥 FIX: Only match if there's context suggesting it's a YouTube request, not just any time
  console.log(`🕐 Checking for time-based patterns in: "${content}"`);
  
  // First check if there's YouTube-related context
  const hasYouTubeContext = /(?:video|youtube|transcript|chunk|minute|at\s+\d|what happens|show me|zeig mir)/i.test(content);
  
  let timeMatch: RegExpMatchArray | null = null;
  let timestampStr: string | null = null;
  
  // If no YouTube context and no cached videos, skip time-based matching
  if (!hasYouTubeContext && transcriptCache.size === 0) {
    console.log(`🕐 No YouTube context and no cached videos - skipping time-based pattern matching`);
  } else {
    const timePatterns = [
      /(?:minute|min|at|ab|bei)\s+(\d+)/i,  // "minute 15", "at 15", "bei 15"
      /(?:at|ab|bei|what happens at|show me|zeig mir)\s+(\d{1,2}:\d{2}(?::\d{2})?)/i,  // "at 15:30", "what happens at 15:30"
      /(\d{1,2}:\d{2}(?::\d{2})?)(?!\s*(?:Uhr|uhr|o'clock|am|pm|AM|PM|\d))/i,  // "15:30" but NOT "12:15 Uhr" or "12:15 2025"
      /(\d+)\s*(?:min|minute|m)\b/i,  // "15 min" or "15 minutes"
    ];
    
    for (let i = 0; i < timePatterns.length; i++) {
      const pattern = timePatterns[i];
      const match = content.match(pattern);
      console.log(`🕐 Pattern ${i + 1} test: ${match ? 'MATCHED' : 'no match'}`);
      if (match) {
        timeMatch = match;
        timestampStr = match[1];
        console.log(`🕐 Time pattern matched: "${match[0]}" -> timestamp: "${timestampStr}"`);
        break;
      }
    }
  }
  
  // If we found a timestamp, try to find the chunk
  if (timestampStr) {
    const targetMs = parseTimestampToMs(timestampStr);
    console.log(`🕐 Parsed timestamp "${timestampStr}" to ${targetMs}ms (${targetMs ? formatTimestamp(targetMs) : 'null'})`);
    if (targetMs !== null) {
      console.log(`🕐 Time-based request detected: "${timestampStr}" (${formatTimestamp(targetMs)})`);
      
      // Try to find video ID in message, or use most recent
      const videoIdPattern = /([a-zA-Z0-9_-]{11})/;
      const videoIdMatch = content.match(videoIdPattern);
      let videoId = videoIdMatch ? videoIdMatch[1] : null;
      
      // If no video ID specified, try to find the most recent one in cache
      if (!videoId) {
        console.log(`📖 No video ID specified for time-based request, looking for most recent cached video...`);
        const now = Date.now();
        const recentVideos = Array.from(transcriptCache.entries())
          .filter(([id, data]) => {
            const age = now - data.timestamp;
            return age <= CACHE_TTL;
          })
          .sort((a, b) => b[1].timestamp - a[1].timestamp);
        
        if (recentVideos.length === 0) {
          console.log(`❌ No cached videos found for time-based request`);
          return `❌ No cached video transcript found. Please share a YouTube video link first.`;
        }
        
        videoId = recentVideos[0][0];
        const videoAge = Math.round((Date.now() - recentVideos[0][1].timestamp) / 1000 / 60);
        console.log(`📖 ✅ Using most recent video for time-based request: ${videoId} (age: ${videoAge} minutes)`);
      }
      
      const cached = transcriptCache.get(videoId);
      
      if (!cached) {
        console.log(`❌ Video ${videoId} not found in cache`);
        return `❌ Video ${videoId} not found in cache. Please share the video link first.`;
      }
      
      // Check if cache has expired
      const now = Date.now();
      if (now - cached.timestamp > CACHE_TTL) {
        console.log(`❌ Video ${videoId} cache expired`);
        transcriptCache.delete(videoId);
        return `❌ Transcript cache expired (older than 1 hour). Please share the video link again to refresh the cache.`;
      }
      
      // Find chunk containing this timestamp
      const chunk = findChunkByTimestamp(cached.chunks, targetMs);
      
      if (!chunk) {
        const formattedTime = formatTimestamp(targetMs);
        console.log(`❌ No chunk found for timestamp ${formattedTime} in video ${videoId}`);
        return `❌ No chunk found for timestamp ${formattedTime}. Available chunks:\n${cached.chunks.map(c => `  📍 Chunk ${c.index}: ${c.startTime} - ${c.endTime}`).join('\n')}`;
      }
      
      console.log(`🕐 Found chunk ${chunk.index} for timestamp ${formatTimestamp(targetMs)} (${chunk.startTime} - ${chunk.endTime})`);
      
      return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 VIDEO TRANSCRIPT CHUNK ${chunk.index}/${cached.chunks.length} (by Discord Bot)
"${cached.metadata.title}"
⏱️ Timerange: ${chunk.startTime} - ${chunk.endTime}
🕐 Requested time: ${formatTimestamp(targetMs)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${chunk.text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
    }
  }
  
  // Pattern: "chunk X of VIDEO_ID" or "chunk X" or "show me chunk X"
  // Also supports: "chunk X", "chunkX", "chunk: X", etc.
  // 🔥 FIX: More specific pattern to avoid false positives with normal numbers
  // Pattern matches:
  // - "chunk X of VIDEO_ID" or "chunk X von VIDEO_ID" (explicit video ID, supports German "von")
  // - "show me chunk X" / "give me chunk X" / "get chunk X" (command-like)
  // - "chunk X" at start of message or after punctuation
  // Does NOT match: "chunk X" in middle of normal sentence
  const chunkPattern = /(?:^|[\s\.\!\?])(?:show me |give me |get |send me |read |please |can you |could you )?chunk\s*:?\s*(\d+)(?:\s+(?:of|von)\s+([a-zA-Z0-9_-]{11}))?/i;
  const match = content.match(chunkPattern);
  
  if (!match) {
    console.log(`🔍 Chunk request pattern not matched in: "${content.substring(0, 100)}"`);
    return null;
  }
  
  // 🔥 FIX: Additional validation - avoid false positives
  // If "chunk X" appears in middle of sentence without command words, skip it
  const matchIndex = match.index || 0;
  const beforeMatch = content.substring(0, matchIndex).trim();
  const matchText = match[0].trim();
  
  // If there's significant text before and it doesn't look like a command, skip
  if (beforeMatch.length > 0) {
    const wordsBefore = beforeMatch.split(/\s+/);
    const lastWord = wordsBefore[wordsBefore.length - 1].toLowerCase();
    
    // Allow if it's after punctuation or command words
    const allowedBefore = ['me', 'you', 'please', 'can', 'could', 'show', 'give', 'get', 'send', 'read', 'video', 'youtube'];
    const isAfterPunctuation = /[\.\!\?]$/.test(beforeMatch);
    
    // If there are multiple words before and it's not a command context, skip
    if (wordsBefore.length > 2 && !allowedBefore.includes(lastWord) && !isAfterPunctuation) {
      console.log(`🎥 Skipping false positive: "${matchText}" in context "${beforeMatch}..."`);
      return null;
    }
  }
  
  console.log(`✅ Chunk request pattern matched: "${match[0]}" (chunk: ${match[1]}, videoId: ${match[2] || 'none'})`);

  const chunkNumber = parseInt(match[1], 10);
  let videoId = match[2];

  // If no video ID specified, try to find the most recent one in cache
  if (!videoId) {
    console.log(`📖 No video ID specified, looking for most recent cached video...`);
    console.log(`📖 Current cache size: ${transcriptCache.size} entries`);
    
    const now = Date.now();
    const recentVideos = Array.from(transcriptCache.entries())
      .filter(([id, data]) => {
        // Filter out expired entries
        const age = now - data.timestamp;
        const isExpired = age > CACHE_TTL;
        if (isExpired) {
          console.log(`📖 Video ${id} expired (age: ${Math.round(age / 1000 / 60)} minutes, TTL: ${CACHE_TTL / 1000 / 60} minutes)`);
        }
        return !isExpired;
      })
      .sort((a, b) => b[1].timestamp - a[1].timestamp); // Sort by timestamp DESC (newest first)
    
    console.log(`📖 Found ${recentVideos.length} non-expired video(s) in cache`);
    
    if (recentVideos.length === 0) {
      console.log(`❌ No cached videos found for chunk request (cache size: ${transcriptCache.size}, but all expired or empty)`);
      return `❌ No cached video transcript found. Please share a YouTube video link first, then request chunks.`;
    }
    
    // Log all available videos for debugging
    recentVideos.forEach(([id, data], index) => {
      const age = Math.round((now - data.timestamp) / 1000 / 60);
      console.log(`📖   ${index === 0 ? '→' : ' '} Video ${id}: "${data.metadata.title}" (age: ${age} min, ${data.chunks.length} chunks)`);
    });
    
    videoId = recentVideos[0][0];
    const videoAge = Math.round((Date.now() - recentVideos[0][1].timestamp) / 1000 / 60);
    console.log(`📖 ✅ Using most recent video: ${videoId} (age: ${videoAge} minutes, ${recentVideos[0][1].chunks.length} chunks)`);
  }

  const cached = transcriptCache.get(videoId);

  if (!cached) {
    console.log(`❌ Video ${videoId} not found in cache`);
    return `❌ Video ${videoId} not found in cache. Please share the video link first.`;
  }

  // 🔥 FIX: Check if cache has expired
  const now = Date.now();
  if (now - cached.timestamp > CACHE_TTL) {
    console.log(`❌ Video ${videoId} cache expired (age: ${Math.round((now - cached.timestamp) / 1000 / 60)} minutes)`);
    transcriptCache.delete(videoId); // Clean up expired entry
    return `❌ Transcript cache expired (older than 1 hour). Please share the video link again to refresh the cache.`;
  }

  if (chunkNumber < 1 || chunkNumber > cached.chunks.length) {
    console.log(`❌ Invalid chunk number: ${chunkNumber} (available: 1-${cached.chunks.length})`);
    return `❌ Invalid chunk number. Available chunks: 1-${cached.chunks.length}`;
  }

  const chunk = cached.chunks[chunkNumber - 1];
  
  console.log(`📖 Sending chunk ${chunkNumber}/${cached.chunks.length} of ${videoId} (${chunk.startTime} - ${chunk.endTime})`);
  console.log(`📖 Chunk text length: ${chunk.text.length} characters`);

  // 🔥 FIX: Add context so agent knows this is a chunk request response
  return `[YouTube Transcript Chunk Request Response]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 VIDEO TRANSCRIPT CHUNK ${chunkNumber}/${cached.chunks.length} (by Discord Bot)
"${cached.metadata.title}"
⏱️ Timerange: ${chunk.startTime} - ${chunk.endTime}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${chunk.text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
}

/**
 * Cleanup old cached transcripts (runs periodically)
 */
export function cleanupTranscriptCache(): void {
  const now = Date.now();
  let removed = 0;

  for (const [videoId, data] of transcriptCache.entries()) {
    if (now - data.timestamp > CACHE_TTL) {
      transcriptCache.delete(videoId);
      removed++;
    }
  }

  if (removed > 0) {
    console.log(`🗑️ Cleaned up ${removed} expired transcript(s) from cache`);
  }
}

/**
 * Get the most recent video from cache (for cross-cache comparison)
 */
export function getMostRecentVideo(): { id: string; timestamp: number } | null {
  if (transcriptCache.size === 0) return null;
  
  const recentVideos = Array.from(transcriptCache.entries())
    .sort((a, b) => b[1].timestamp - a[1].timestamp);
  
  return {
    id: recentVideos[0][0],
    timestamp: recentVideos[0][1].timestamp
  };
}

// Start cleanup task (runs every 10 minutes)
setInterval(cleanupTranscriptCache, 600000);

