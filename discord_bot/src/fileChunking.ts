/**
 * FILE CHUNKING SYSTEM - For large text files
 * 
 * Similar to YouTube transcript chunking, this system handles large text files
 * by splitting them into manageable chunks that can be requested on-demand.
 * 
 * Features:
 * - Auto-download small files (<10KB) - inline in message
 * - Cache medium/large files (10KB+) with chunking
 * - On-demand chunk retrieval via "show me chunk X of FILE_ID" pattern
 * 
 * @author the bot - Credit-saving file handling system
 */

// ===== CONFIGURATION =====
const INLINE_THRESHOLD = 10240; // 10KB - files smaller than this are sent inline
const CHUNK_SIZE = 50000; // 50KB per chunk
const PREVIEW_SIZE = 2000; // 2KB preview for beginning/end
const CACHE_TTL = 3600000; // 1 hour cache retention
const MAX_PDF_SIZE = 10 * 1024 * 1024; // 10MB limit for PDFs
const MAX_TEXT_FILE_SIZE = 100 * 1024; // 100KB limit for regular text files
const MAX_OCR_IMAGES = 20; // max images to OCR per PDF to avoid timeout
const OCR_TIMEOUT = 30000; // 30s timeout per image

// ===== TYPES =====
interface FileChunk {
  text: string;
  index: number;
  startChar: number;
  endChar: number;
}

interface FileMetadata {
  filename: string;
  fileType: string;
  size: number;
  sizeHuman: string;
  url: string;
  length: number; // Character count
  pages?: number; // For PDFs: total page count
}

interface CachedFile {
  full: string;
  chunks: FileChunk[];
  metadata: FileMetadata;
  timestamp: number;
}

// ===== CACHE =====
const fileCache = new Map<string, CachedFile>();

// Clean up old cache entries periodically
setInterval(() => {
  const now = Date.now();
  for (const [id, cached] of fileCache.entries()) {
    if (now - cached.timestamp > CACHE_TTL) {
      fileCache.delete(id);
      console.log(`🗑️ Cleaned up cached file: ${id}`);
    }
  }
}, 60000); // Check every minute

// ===== HELPER FUNCTIONS =====

/**
 * Generate a unique file ID from URL (last part + size hash)
 */
function generateFileId(url: string, size: number): string {
  const urlParts = url.split('/');
  const filename = urlParts[urlParts.length - 1].split('?')[0];
  const hash = filename.substring(0, 8) + '_' + size.toString(36);
  return hash;
}

/**
 * Create chunks from long text content
 */
function createChunks(content: string, chunkSize: number): FileChunk[] {
  const chunks: FileChunk[] = [];
  let startChar = 0;
  let chunkIndex = 1;
  
  while (startChar < content.length) {
    const endChar = Math.min(startChar + chunkSize, content.length);
    const chunkText = content.substring(startChar, endChar);
    
    chunks.push({
      text: chunkText,
      index: chunkIndex++,
      startChar,
      endChar
    });
    
    startChar = endChar;
  }
  
  return chunks;
}

/**
 * Format file size for human readability
 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

/**
 * Check if file is a PDF
 */
function isPDF(type: string, name: string): boolean {
  return type.includes('application/pdf') || name.toLowerCase().endsWith('.pdf');
}

/**
 * Extract text from PDF file using pdf-parse
 */
async function extractPDFText(fileBytes: Buffer): Promise<{
  text: string;
  pages: number;
  metadata?: any;
} | null> {
  try {
    const pdfParse = require('pdf-parse');
    const data = await pdfParse(fileBytes);
    
    return {
      text: data.text || '',
      pages: data.numpages || 0,
      metadata: data.info || {}
    };
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    console.error(`❌ PDF text extraction failed: ${errorMsg}`);
    return null;
  }
}

/**
 * Extract images from PDF using pdfjs-dist
 */
async function extractPDFImages(fileBytes: Buffer): Promise<Buffer[]> {
  const images: Buffer[] = [];
  
  try {
    const pdfjsLib = require('pdfjs-dist/legacy/build/pdf.js');
    
    // Load PDF document
    const loadingTask = pdfjsLib.getDocument({ data: fileBytes });
    const pdfDocument = await loadingTask.promise;
    
    // Process each page
    for (let pageNum = 1; pageNum <= pdfDocument.numPages && images.length < MAX_OCR_IMAGES; pageNum++) {
      try {
        const page = await pdfDocument.getPage(pageNum);
        const operatorList = await page.getOperatorList();
        
        // Extract images from operators
        for (let i = 0; i < operatorList.fnArray.length && images.length < MAX_OCR_IMAGES; i++) {
          const op = operatorList.fnArray[i];
          const args = operatorList.argsArray[i];
          
          // Check for image rendering operations
          if (op === pdfjsLib.OPS.paintImageXObject || op === pdfjsLib.OPS.paintJpegXObject) {
            try {
              const imageName = args[0];
              if (imageName) {
                const image = await page.objs.get(imageName);
                
                if (image && image.data) {
                  // Convert image data to buffer
                  let imageData: Uint8Array;
                  
                  if (image.data instanceof Uint8Array) {
                    imageData = image.data;
                  } else if (image.data instanceof ArrayBuffer) {
                    imageData = new Uint8Array(image.data);
                  } else if (typeof image.data === 'string') {
                    // Base64 encoded
                    imageData = Buffer.from(image.data, 'base64');
                  } else {
                    continue; // Skip unsupported format
                  }
                  
                  const imageBuffer = Buffer.from(imageData);
                  images.push(imageBuffer);
                }
              }
            } catch (imgErr) {
              // Skip this image and continue
              continue;
            }
          }
        }
      } catch (pageErr) {
        // Skip this page and continue
        console.warn(`⚠️ Error processing page ${pageNum}: ${pageErr instanceof Error ? pageErr.message : String(pageErr)}`);
        continue;
      }
    }
    
    console.log(`📸 Extracted ${images.length} image(s) from PDF`);
    return images;
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    console.error(`❌ PDF image extraction failed: ${errorMsg}`);
    return images; // Return what we have so far (might be empty, that's OK)
  }
}

/**
 * Perform OCR on an image using tesseract.js
 */
async function performOCR(imageBuffer: Buffer, imageIndex: number, totalImages: number): Promise<string> {
  try {
    const { createWorker } = require('tesseract.js');
    const worker = await createWorker('eng'); // English language
    
    console.log(`🔍 [OCR ${imageIndex + 1}/${totalImages}] Processing image...`);
    
    const { data: { text } } = await Promise.race([
      worker.recognize(imageBuffer),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('OCR timeout')), OCR_TIMEOUT)
      )
    ]) as any;
    
    await worker.termiagent();
    
    const ocrText = text.trim();
    if (ocrText) {
      console.log(`✅ [OCR ${imageIndex + 1}/${totalImages}] Extracted ${ocrText.length} chars`);
      return ocrText;
    }
    
    return '';
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    console.error(`⚠️ [OCR ${imageIndex + 1}/${totalImages}] Failed: ${errorMsg}`);
    return '';
  }
}

/**
 * Process PDF with text extraction and OCR for images
 */
async function processPDFWithOCR(fileBytes: Buffer): Promise<{
  text: string;
  pages: number;
  ocrStats: { imagesFound: number; imagesProcessed: number; ocrTextLength: number };
} | null> {
  try {
    console.log('📄 Starting PDF processing with OCR...');
    
    // Step 1: Extract text from PDF text layer
    const textResult = await extractPDFText(fileBytes);
    if (!textResult) {
      throw new Error('Failed to extract text from PDF');
    }
    
    let combinedText = textResult.text;
    const pages = textResult.pages;
    
    console.log(`✅ Extracted ${combinedText.length} chars from PDF text layer (${pages} pages)`);
    
    // Step 2: Extract images from PDF
    const images = await extractPDFImages(fileBytes);
    const imagesFound = images.length;
    let imagesProcessed = 0;
    let ocrTextLength = 0;
    
    // Step 3: Perform OCR on images
    if (images.length > 0) {
      console.log(`🔍 Starting OCR on ${images.length} image(s)...`);
      
      for (let i = 0; i < images.length; i++) {
        const ocrText = await performOCR(images[i], i, images.length);
        
        if (ocrText) {
          imagesProcessed++;
          ocrTextLength += ocrText.length;
          
          // Append OCR text to combined text
          combinedText += `\n\n[OCR from image ${i + 1}]:\n${ocrText}`;
        }
      }
      
      console.log(`✅ OCR complete: ${imagesProcessed}/${imagesFound} images processed, ${ocrTextLength} chars extracted`);
    }
    
    return {
      text: combinedText,
      pages,
      ocrStats: {
        imagesFound,
        imagesProcessed,
        ocrTextLength
      }
    };
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    console.error(`❌ PDF processing with OCR failed: ${errorMsg}`);
    return null;
  }
}

/**
 * Process file intelligently (inline, cached with chunks, or fallback to URL)
 */
export async function processFileAttachment(
  name: string,
  url: string,
  type: string,
  size: number
): Promise<string> {
  const sizeStr = formatFileSize(size);
  
  // Check if it's a PDF
  const isPdf = isPDF(type, name);
  
  // Check if it's a text file we can download
  const isTextFile = type.includes('text/') || 
                     type.includes('application/json') || 
                     type.includes('application/xml') ||
                     type.includes('yaml') ||
                     name.endsWith('.md') ||
                     name.endsWith('.txt') ||
                     name.endsWith('.log') ||
                     name.endsWith('.py') ||
                     name.endsWith('.js') ||
                     name.endsWith('.ts') ||
                     name.endsWith('.jsx') ||
                     name.endsWith('.tsx') ||
                     name.endsWith('.java') ||
                     name.endsWith('.c') ||
                     name.endsWith('.cpp') ||
                     name.endsWith('.go') ||
                     name.endsWith('.rs') ||
                     name.endsWith('.sh') ||
                     isPdf; // PDFs are treated as text files after extraction
  
  // Different size limits for PDFs vs text files
  const isSmallEnough = isPdf 
    ? size <= MAX_PDF_SIZE  // PDFs: up to 10MB
    : size <= MAX_TEXT_FILE_SIZE; // Text files: up to 100KB
  
  // For PDFs: check if too large
  if (isPdf && size > MAX_PDF_SIZE) {
    return `- \`${name}\` (${type}, ${sizeStr})\n  URL: ${url}\n  ⚠️ PDF too large (max ${formatFileSize(MAX_PDF_SIZE)})\n  💡 You can use \`download_discord_file(url="${url}")\` to read this file!`;
  }
  
  // For non-text/non-PDF or very large text files: provide URL + tool hint
  if ((!isTextFile && !isPdf) || (!isPdf && size > MAX_TEXT_FILE_SIZE)) {
    return `- \`${name}\` (${type}, ${sizeStr})\n  URL: ${url}\n  💡 You can use \`download_discord_file(url="${url}")\` to read this file!`;
  }
  
  // Try to download the file
  try {
    const controller = new AbortController();
    // PDFs need more time (they're larger and need OCR processing)
    const timeout = isPdf ? 120000 : 10000; // 120s for PDFs, 10s for text
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    const response = await fetch(url, { signal: controller.signal });
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    let content: string;
    let pages: number | undefined;
    let ocrStats: { imagesFound: number; imagesProcessed: number; ocrTextLength: number } | undefined;
    
    // Handle PDFs differently - download as binary and extract text + OCR
    if (isPdf) {
      console.log(`📄 Processing PDF: ${name} (${sizeStr})...`);
      const arrayBuffer = await response.arrayBuffer();
      const buffer = Buffer.from(arrayBuffer);
      
      const pdfResult = await processPDFWithOCR(buffer);
      
      if (!pdfResult || !pdfResult.text || pdfResult.text.length === 0) {
        throw new Error('PDF text extraction failed or PDF is empty');
      }
      
      content = pdfResult.text;
      pages = pdfResult.pages;
      ocrStats = pdfResult.ocrStats;
      
      const ocrInfo = ocrStats.imagesFound > 0 
        ? `, ${pages} pages, OCR: ${ocrStats.imagesProcessed}/${ocrStats.imagesFound} images (${ocrStats.ocrTextLength} chars)`
        : `, ${pages} pages`;
      
      console.log(`✅ PDF extracted: ${name} - ${content.length} chars${ocrInfo}`);
    } else {
      // Regular text file
      content = await response.text();
    }
    
    const fileId = generateFileId(url, size);
    
    // SMALL FILE (<10KB): Send inline completely
    if (content.length <= INLINE_THRESHOLD) {
      const fileTypeLabel = isPdf ? 'PDF' : 'File';
      const pageInfo = pages ? ` (${pages} pages)` : '';
      const ocrInfo = ocrStats && ocrStats.imagesFound > 0 
        ? ` | OCR: ${ocrStats.imagesProcessed}/${ocrStats.imagesFound} images`
        : '';
      
      console.log(`📄 Small file auto-downloaded: ${name} (${content.length} chars${pageInfo}${ocrInfo})`);
      return `- 📄 **${fileTypeLabel}: \`${name}\`** (${type}, ${sizeStr}${pageInfo}${ocrInfo})\n  ✅ **Content auto-downloaded:**\n\`\`\`\n${content}\n\`\`\``;
    }
    
    // MEDIUM/LARGE FILE (>10KB): Cache with chunks and send preview
    const chunks = createChunks(content, CHUNK_SIZE);
    
    const metadata: FileMetadata = {
      filename: name,
      fileType: type,
      size,
      sizeHuman: sizeStr,
      url,
      length: content.length,
      pages: pages // Store page count for PDFs
    };
    
    fileCache.set(fileId, {
      full: content,
      chunks,
      metadata,
      timestamp: Date.now()
    });
    
    const fileTypeLabel = isPdf ? 'PDF' : 'File';
    const pageInfo = pages ? ` (${pages} pages)` : '';
    const ocrInfo = ocrStats && ocrStats.imagesFound > 0 
      ? ` | OCR: ${ocrStats.imagesProcessed}/${ocrStats.imagesFound} images (${ocrStats.ocrTextLength} chars)`
      : '';
    
    console.log(`📄 Large file cached: ${name} (${chunks.length} chunks, ${content.length} chars${pageInfo}${ocrInfo})`);
    
    // Create chunk overview
    const chunkList = chunks.map(chunk => 
      `  📍 Chunk ${chunk.index}: chars ${chunk.startChar}-${chunk.endChar} (${chunk.text.length} chars)`
    ).join('\n');
    
    const beginning = content.slice(0, PREVIEW_SIZE);
    const ending = content.slice(-PREVIEW_SIZE);
    const middleLength = content.length - (PREVIEW_SIZE * 2);
    
    return `- 📄 **${fileTypeLabel}: \`${name}\`** (${type}, ${sizeStr}${pageInfo}${ocrInfo})
  ✅ **Content auto-downloaded and cached!**
  📚 **Available in ${chunks.length} chunks** (${content.length.toLocaleString()} chars total)
  
  **Preview (first ${PREVIEW_SIZE} chars):**
\`\`\`
${beginning}
\`\`\`
  
  ... [ ${middleLength.toLocaleString()} chars omitted ] ...
  
  **Preview (last ${PREVIEW_SIZE} chars):**
\`\`\`
${ending}
\`\`\`
  
  📚 **CHUNKS AVAILABLE:**
${chunkList}
  
  💡 **Request chunks with:** "chunk X" or "chunk X of ${fileId}"
  💡 **File ID:** ${fileId}`;
    
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    console.error(`⚠️ Failed to auto-download ${name}:`, errorMsg);
    
    // Special error message for PDFs
    if (isPdf) {
      return `- \`${name}\` (${type}, ${sizeStr})\n  URL: ${url}\n  ⚠️ PDF extraction failed: ${errorMsg}\n  💡 You can use \`download_discord_file(url="${url}")\` to read this file!`;
    }
    
    // Fallback to URL + tool hint
    return `- \`${name}\` (${type}, ${sizeStr})\n  URL: ${url}\n  ⚠️ Auto-download failed\n  💡 You can use \`download_discord_file(url="${url}")\` to read this file!`;
  }
}

/**
 * Handle chunk requests from Letta/the bot
 * Detects patterns like: "show me chunk 2 of FILE_ID" or "chunk 2"
 */
export function handleFileChunkRequest(content: string): string | null {
  // 🔥 FIX: More specific pattern to avoid false positives with normal numbers
  // Pattern matches:
  // - "chunk X of FILE_ID" or "chunk X von FILE_ID" (explicit file ID, supports German "von")
  // - "show me chunk X" / "give me chunk X" / "get chunk X" (command-like)
  // - "chunk X" at start of message or after punctuation
  // Does NOT match: "chunk X" in middle of normal sentence
  const chunkPattern = /(?:^|[\s\.\!\?])(?:show me |give me |get |send me |read |please |can you |could you )?chunk\s+(\d+)(?:\s+(?:of|von)\s+([a-zA-Z0-9_.-]+))?/i;
  const match = content.match(chunkPattern);
  
  if (!match) return null;
  
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
    const allowedBefore = ['me', 'you', 'please', 'can', 'could', 'show', 'give', 'get', 'send', 'read'];
    const isAfterPunctuation = /[\.\!\?]$/.test(beforeMatch);
    
    // If there are multiple words before and it's not a command context, skip
    if (wordsBefore.length > 2 && !allowedBefore.includes(lastWord) && !isAfterPunctuation) {
      console.log(`📄 Skipping false positive: "${matchText}" in context "${beforeMatch}..."`);
      return null;
    }
  }
  
  const chunkNumber = parseInt(match[1], 10);
  let fileId = match[2];
  
  // 🔥 FIX: If fileId is exactly 11 characters, it might be a YouTube video ID
  // Let YouTube handler try first in that case
  if (fileId && fileId.length === 11 && /^[a-zA-Z0-9_-]{11}$/.test(fileId)) {
    console.log(`📄 File ID "${fileId}" looks like a YouTube video ID (11 chars) - letting YouTube handler try first`);
    return null;
  }
  
  // If no file ID specified, try to find the most recent one in cache
  if (!fileId) {
    const recentFiles = Array.from(fileCache.entries())
      .filter(([id, data]) => {
        // Filter out expired entries
        const now = Date.now();
        return (now - data.timestamp) <= CACHE_TTL;
      })
      .sort((a, b) => b[1].timestamp - a[1].timestamp);
    
    if (recentFiles.length === 0) {
      // 🔥 FIX: Return null instead of error message, so YouTube handler can try
      // But only if this really looks like a chunk request (not just random "chunk" in text)
      const isExplicitRequest = /^(show me |give me |get |send me |read |please |can you |could you )?chunk\s+\d+/i.test(content.trim());
      if (!isExplicitRequest) {
        // Probably not a real chunk request, just "chunk" in normal text
        return null;
      }
      console.log('📄 No cached files found for chunk request - letting YouTube handler try');
      return null;
    }
    
    fileId = recentFiles[0][0];
    console.log(`📖 Using most recent file: ${fileId}`);
  }
  
  let cached = fileCache.get(fileId);
  
  // 🔥 FIX: If exact match not found, try fuzzy matching (e.g. "message._8q" -> "message._8qi")
  if (!cached) {
    // Try to find a file ID that starts with the provided ID
    const matchingFiles = Array.from(fileCache.keys())
      .filter(id => id.startsWith(fileId))
      .sort((a, b) => a.length - b.length); // Prefer shorter matches (closer to input)
    
    if (matchingFiles.length > 0) {
      const fuzzyMatch = matchingFiles[0];
      console.log(`📄 File ${fileId} not found, but found fuzzy match: ${fuzzyMatch}`);
      cached = fileCache.get(fuzzyMatch);
      fileId = fuzzyMatch; // Update fileId for the response
    }
  }
  
  if (!cached) {
    // 🔥 FIX: If fileId is 11 chars and not found, might be YouTube video ID
    if (fileId.length === 11 && /^[a-zA-Z0-9_-]{11}$/.test(fileId)) {
      console.log(`📄 File ${fileId} not found, but it looks like a YouTube video ID - letting YouTube handler try`);
      return null;
    }
    
    // Show available files in cache for debugging
    const availableFiles = Array.from(fileCache.keys()).slice(0, 5);
    const availableFilesStr = availableFiles.length > 0 
      ? `\n💡 Available files in cache: ${availableFiles.join(', ')}${fileCache.size > 5 ? '...' : ''}`
      : '';
    
    console.log(`❌ File ${fileId} not found in cache`);
    return `❌ File ${fileId} not found in cache. The file may have expired (1 hour cache) or was never downloaded.${availableFilesStr}`;
  }
  
  if (chunkNumber < 1 || chunkNumber > cached.chunks.length) {
    console.log(`❌ Invalid chunk number ${chunkNumber} for ${fileId}`);
    return `❌ Invalid chunk number. File has ${cached.chunks.length} chunks (you requested chunk ${chunkNumber}).`;
  }
  
  const chunk = cached.chunks[chunkNumber - 1];
  
  console.log(`📖 Sending chunk ${chunkNumber}/${cached.chunks.length} of ${fileId}`);
  
  const pageInfo = cached.metadata.pages ? `Pages: ${cached.metadata.pages} | ` : '';
  
  return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📄 FILE CHUNK ${chunk.index}/${cached.chunks.length} (by Discord Bot)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

File: "${cached.metadata.filename}"
File ID: ${fileId}
Type: ${cached.metadata.fileType}
Size: ${cached.metadata.sizeHuman}
${pageInfo}Chars: ${chunk.startChar}-${chunk.endChar} of ${cached.metadata.length}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTENT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${chunk.text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
${chunk.index < cached.chunks.length ? `💡 Next: "chunk ${chunk.index + 1}" or "chunk ${chunk.index + 1} of ${fileId}"` : '✅ This is the last chunk'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
}

/**
 * Get info about a cached file
 */
export function getFileInfo(fileId: string): string | null {
  const cached = fileCache.get(fileId);
  
  if (!cached) {
    return `❌ File ${fileId} not found in cache.`;
  }
  
  const chunkList = cached.chunks.map(chunk => 
    `  📍 Chunk ${chunk.index}: chars ${chunk.startChar}-${chunk.endChar}`
  ).join('\n');
  
  const pageInfo = cached.metadata.pages ? `Pages: ${cached.metadata.pages}\n` : '';
  
  return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 FILE INFO (by Discord Bot)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Filename: "${cached.metadata.filename}"
File ID: ${fileId}
Type: ${cached.metadata.fileType}
Size: ${cached.metadata.sizeHuman}
${pageInfo}Total Length: ${cached.metadata.length.toLocaleString()} chars

📚 AVAILABLE CHUNKS (${cached.chunks.length}):
${chunkList}

💡 Request chunks with: "show me chunk X of ${fileId}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
}

// Export cache for debugging/monitoring
export function getCacheStats(): { count: number; files: string[] } {
  return {
    count: fileCache.size,
    files: Array.from(fileCache.keys())
  };
}

/**
 * Get the most recent file from cache (for cross-cache comparison)
 */
export function getMostRecentFile(): { id: string; timestamp: number } | null {
  if (fileCache.size === 0) return null;
  
  const recentFiles = Array.from(fileCache.entries())
    .sort((a, b) => b[1].timestamp - a[1].timestamp);
  
  return {
    id: recentFiles[0][0],
    timestamp: recentFiles[0][1].timestamp
  };
}

