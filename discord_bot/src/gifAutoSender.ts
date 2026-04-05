/**
 * 🎬 GIF Auto-Sender
 * 
 * Automatically detects when a GIF would be appropriate and sends it directly
 * WITHOUT going through Letta. Uses semantic embeddings for intelligent matching.
 * 
 * Created: November 17, 2025
 * Updated: November 17, 2025 - Added embedding-based semantic matching
 */

import { pipeline } from '@xenova/transformers';

// Configuration
const GIF_PROBABILITY = 0.15; // 15% chance to send GIF when context matches (not every time!)
const COOLDOWN_SECONDS = 300; // 5 minutes between GIFs (prevent spam)
const SIMILARITY_THRESHOLD = 0.65; // Minimum cosine similarity to match a category
const TENOR_API_KEY = process.env.TENOR_API_KEY || ''; // Get free API key at: https://developers.google.com/tenor

// Embedding model: multilingual model that supports German + English
const EMBEDDING_MODEL = 'Xenova/paraphrase-multilingual-mpnet-base-v2'; // 50+ languages including German

// Track last GIF sent per channel/user
const lastGifTime: Map<string, number> = new Map();

// Track pending GIF notifications per channel (for transparency)
interface GifNotification {
  category: string;
  similarity: number;
  timestamp: number;
  gifUrl?: string;
}

const pendingGifNotifications: Map<string, GifNotification> = new Map();

// Embedding pipeline (lazy-loaded)
let embeddingPipeline: any = null;
let categoryEmbeddings: Map<string, Float32Array> | null = null;

// Category descriptions (used for embedding matching)
const GIF_CATEGORIES: { [key: string]: string } = {
  // Emotions
  'happy': 'glücklich freudig happy joyful freude',
  'sad': 'traurig trauer sad unhappy deprimiert',
  'excited': 'aufgeregt excited hyped begeistert',
  'tired': 'müde erschöpft tired sleepy exhausted',
  'confused': 'verwirrt confused unsicher what huh',
  'angry': 'wütend angry frustrated verärgert',
  'love': 'liebe love herz heart',
  'celebration': 'feiern celebration party party',
  
  // Actions
  'dance': 'tanzen dance dancing',
  'wave': 'winken wave hello hi',
  'hug': 'umarmen hug cuddle',
  'sleep': 'schlafen sleep bed',
  'work': 'arbeiten work coding programming',
  'coffee': 'kaffee coffee',
  'food': 'essen food eating hungry',
  
  // Reactions
  'ok': 'ok okay alright sure',
  'yes': 'ja yes yep affirmative',
  'no': 'nein no nope negative',
  'thanks': 'danke thanks thank you',
  'welcome': 'gern geschehen welcome bitte',
  'goodbye': 'tschüss goodbye bye ciao',
  
  // Situations
  'success': 'erfolg success done finished completed',
  'error': 'fehler error oops mistake',
  'thinking': 'denken thinking überlegen ponder',
  'waiting': 'warten waiting loading',
};

/**
 * Initialize embedding pipeline (lazy loading)
 */
async function getEmbeddingPipeline(): Promise<any> {
  if (!embeddingPipeline) {
    console.log('🎬 Loading embedding model...');
    embeddingPipeline = await pipeline('feature-extraction', EMBEDDING_MODEL, {
      quantized: true, // Use quantized model for faster loading
    });
    console.log('✅ Embedding model loaded');
  }
  return embeddingPipeline;
}

/**
 * Generate embeddings for category descriptions (cached)
 */
async function getCategoryEmbeddings(): Promise<Map<string, Float32Array>> {
  if (categoryEmbeddings) {
    return categoryEmbeddings;
  }
  
  console.log('🎬 Generating category embeddings...');
  const pipeline = await getEmbeddingPipeline();
  categoryEmbeddings = new Map();
  
  for (const [category, description] of Object.entries(GIF_CATEGORIES)) {
    const output = await pipeline(description, { pooling: 'mean', normalize: true });
    categoryEmbeddings.set(category, output.data as Float32Array);
  }
  
  console.log(`✅ Generated embeddings for ${categoryEmbeddings.size} categories`);
  return categoryEmbeddings;
}

/**
 * Calculate cosine similarity between two vectors
 */
function cosineSimilarity(a: Float32Array, b: Float32Array): number {
  let dotProduct = 0;
  let normA = 0;
  let normB = 0;
  
  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}

/**
 * Check if message content suggests a GIF would be appropriate
 * Uses semantic embeddings for intelligent matching (supports German + English)
 */
async function shouldSendGif(content: string): Promise<{ should: boolean; category?: string; similarity?: number }> {
  if (!content || content.trim().length === 0) {
    return { should: false };
  }
  
  try {
    // Get embeddings
    const pipeline = await getEmbeddingPipeline();
    const categories = await getCategoryEmbeddings();
    
    // Generate embedding for bot response
    const output = await pipeline(content, { pooling: 'mean', normalize: true });
    const responseEmbedding = output.data as Float32Array;
    
    // Find best matching category
    let bestMatch: { category: string; similarity: number } | null = null;
    
    for (const [category, categoryEmbedding] of categories.entries()) {
      const similarity = cosineSimilarity(responseEmbedding, categoryEmbedding);
      
      if (similarity >= SIMILARITY_THRESHOLD) {
        if (!bestMatch || similarity > bestMatch.similarity) {
          bestMatch = { category, similarity };
        }
      }
    }
    
    if (bestMatch) {
      // Random chance to actually send (not every match!)
      if (Math.random() < GIF_PROBABILITY) {
        console.log(`🎬 Semantic match: "${content.substring(0, 50)}..." → ${bestMatch.category} (similarity: ${bestMatch.similarity.toFixed(3)})`);
        return { should: true, category: bestMatch.category, similarity: bestMatch.similarity };
      }
    }
    
    return { should: false };
  } catch (error) {
    console.error('❌ Error in embedding-based GIF detection:', error);
    // Fallback to simple keyword matching if embeddings fail
    return fallbackKeywordMatching(content);
  }
}

/**
 * Fallback: Simple keyword matching if embeddings fail
 */
function fallbackKeywordMatching(content: string): { should: boolean; category?: string } {
  const lowerContent = content.toLowerCase();
  
  // Simple keyword triggers (backup)
  const keywords: { [key: string]: string[] } = {
    'happy': ['happy', 'glücklich', 'freude', 'yay', 'yeah', '🎉', '😊', '😄'],
    'sad': ['sad', 'traurig', 'deprimiert', '😢', '😭'],
    'excited': ['excited', 'aufgeregt', 'hyped', '🔥', '💥'],
    'tired': ['tired', 'müde', 'erschöpft', '😴', '💤'],
    'confused': ['confused', 'verwirrt', 'what', 'huh', '🤔', '😕'],
    'angry': ['angry', 'wütend', 'frustriert', '😠', '😡'],
    'love': ['love', 'liebe', '❤️', '💕', '💖'],
    'celebration': ['celebration', 'feiern', 'party', '🎊', '🎈'],
    'dance': ['dance', 'tanzen', 'dancing'],
    'wave': ['wave', 'winken', 'hi', 'hello', 'hey'],
    'hug': ['hug', 'umarmen', 'cuddle'],
    'sleep': ['sleep', 'schlafen', 'bed'],
    'work': ['work', 'arbeiten', 'coding', 'programming'],
    'coffee': ['coffee', 'kaffee', '☕'],
    'food': ['food', 'essen', 'hungry', '🍕', '🍔'],
    'ok': ['ok', 'okay', 'alright', 'sure'],
    'yes': ['yes', 'ja', 'yep', 'yeah'],
    'no': ['no', 'nein', 'nope', 'nah'],
    'thanks': ['thanks', 'thank you', 'danke', 'merci'],
    'welcome': ['welcome', 'gern geschehen', 'bitte'],
    'goodbye': ['goodbye', 'bye', 'tschüss', 'ciao', 'see you'],
    'success': ['success', 'erfolg', 'done', 'finished', '✅'],
    'error': ['error', 'fehler', 'oops', '❌'],
    'thinking': ['thinking', 'denken', 'überlegen', '🤔'],
    'waiting': ['waiting', 'warten', 'loading', '⏳'],
  };
  
  for (const [category, keywordList] of Object.entries(keywords)) {
    for (const keyword of keywordList) {
      if (lowerContent.includes(keyword.toLowerCase())) {
        if (Math.random() < GIF_PROBABILITY) {
          return { should: true, category };
        }
      }
    }
  }
  
  return { should: false };
}

/**
 * Search for GIF using Tenor API
 */
async function searchGif(category: string): Promise<string | null> {
  try {
    // Map our categories to Tenor search terms
    const searchTerms: { [key: string]: string } = {
      'happy': 'happy celebration',
      'sad': 'sad crying',
      'excited': 'excited jumping',
      'tired': 'tired sleep',
      'confused': 'confused thinking',
      'angry': 'angry frustrated',
      'love': 'love heart',
      'celebration': 'celebration party',
      'dance': 'dancing',
      'wave': 'waving hello',
      'hug': 'hugging',
      'sleep': 'sleeping',
      'work': 'working coding',
      'coffee': 'coffee',
      'food': 'food eating',
      'ok': 'ok thumbs up',
      'yes': 'yes nod',
      'no': 'no shake head',
      'thanks': 'thank you',
      'welcome': 'you\'re welcome',
      'goodbye': 'goodbye wave',
      'success': 'success celebration',
      'error': 'oops mistake',
      'thinking': 'thinking',
      'waiting': 'waiting loading',
    };
    
    const searchTerm = searchTerms[category] || category;
    const url = `https://tenor.googleapis.com/v2/search?q=${encodeURIComponent(searchTerm)}&key=${TENOR_API_KEY}&client_key=discord_bot&limit=10&media_filter=gif`;
    
    console.log(`🎬 Searching GIF for category: ${category} (term: ${searchTerm})`);
    
    const response = await fetch(url);
    if (!response.ok) {
      console.error(`❌ Tenor API error: ${response.status}`);
      return null;
    }
    
    const data = await response.json();
    if (data.results && data.results.length > 0) {
      // Pick random GIF from results
      const randomGif = data.results[Math.floor(Math.random() * data.results.length)];
      const gifUrl = randomGif.media_formats?.gif?.url || randomGif.media_formats?.tinygif?.url;
      
      if (gifUrl) {
        console.log(`✅ Found GIF: ${gifUrl}`);
        return gifUrl;
      }
    }
    
    return null;
  } catch (error) {
    console.error('❌ Error searching GIF:', error);
    return null;
  }
}

/**
 * Check cooldown - prevent GIF spam
 */
function checkCooldown(channelId: string): boolean {
  const now = Date.now();
  const lastTime = lastGifTime.get(channelId) || 0;
  const timeSince = (now - lastTime) / 1000; // seconds
  
  if (timeSince < COOLDOWN_SECONDS) {
    console.log(`⏳ GIF cooldown active (${Math.floor(COOLDOWN_SECONDS - timeSince)}s remaining)`);
    return false;
  }
  
  return true;
}

/**
 * Main function: Check if we should send a GIF and send it
 * Returns true if GIF was sent, false otherwise
 */
export async function checkAndSendGif(
  message: any, // Discord message object
  botResponse: string // The response the bot is about to send
): Promise<boolean> {
  // Feature disabled?
  if (!process.env.ENABLE_AUTO_GIF || process.env.ENABLE_AUTO_GIF !== 'true') {
    return false;
  }
  
  // Check cooldown
  const channelId = message.channel?.id || 'unknown';
  if (!checkCooldown(channelId)) {
    return false;
  }
  
  // Check if response suggests a GIF (now async with embeddings!)
  const { should, category, similarity } = await shouldSendGif(botResponse);
  
  if (!should || !category) {
    return false;
  }
  
  console.log(`🎬 GIF trigger detected! Category: ${category}${similarity ? ` (similarity: ${similarity.toFixed(3)})` : ''}`);
  
  // Search for GIF
  const gifUrl = await searchGif(category);
  
  if (!gifUrl) {
    console.log('⚠️ No GIF found, skipping');
    return false;
  }
  
  // Send GIF
  try {
    await message.channel.send({
      content: gifUrl
    });
    
    // Update cooldown
    lastGifTime.set(channelId, Date.now());
    
    // 🆕 Store notification for next bot response (transparency)
    pendingGifNotifications.set(channelId, {
      category,
      similarity: similarity || 0,
      timestamp: Date.now(),
      gifUrl: gifUrl
    });
    
    console.log(`✅ GIF sent successfully! (Category: ${category}, Similarity: ${similarity?.toFixed(3) || 'N/A'})`);
    return true;
  } catch (error) {
    console.error('❌ Error sending GIF:', error);
    return false;
  }
}

/**
 * Get and clear pending GIF notification for a channel
 * Returns notification metadata if available, null otherwise
 */
export function getAndClearGifNotification(channelId: string): GifNotification | null {
  const notification = pendingGifNotifications.get(channelId);
  if (notification) {
    pendingGifNotifications.delete(channelId);
    return notification;
  }
  return null;
}

/**
 * Format GIF notification as a message prefix
 */
export function formatGifNotification(notification: GifNotification): string {
  const timeAgo = Math.floor((Date.now() - notification.timestamp) / 1000);
  const timeStr = timeAgo < 60 ? `${timeAgo}s` : `${Math.floor(timeAgo / 60)}min`;
  
  return `🎬 **GIF gesendet** (vor ${timeStr}): Kategorie "${notification.category}" (Similarity: ${notification.similarity.toFixed(2)})\n\n`;
}

/**
 * Get GIF auto-sender stats
 */
export function getGifStats(): {
  enabled: boolean;
  probability: number;
  cooldown: number;
  lastGifTimes: { [key: string]: number };
} {
  return {
    enabled: process.env.ENABLE_AUTO_GIF === 'true',
    probability: GIF_PROBABILITY,
    cooldown: COOLDOWN_SECONDS,
    lastGifTimes: Object.fromEntries(lastGifTime)
  };
}

