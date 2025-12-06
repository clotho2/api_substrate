/**
 * Normalizer for assistant responses
 * Applies post-processing to Nate's outputs
 */

export interface NormalizeOptions {
  removeThinking?: boolean;
  cleanMarkdown?: boolean;
}

/**
 * Normalize assistant response content
 * Can clean up formatting, remove artifacts, etc.
 */
export function normalizeAssistant(
  content: string,
  options: NormalizeOptions = {}
): string {
  let normalized = content;

  // Remove thinking tags if requested
  if (options.removeThinking) {
    normalized = normalized.replace(/<think>[\s\S]*?<\/think>/gi, '');
    normalized = normalized.replace(/\[THINKING\][\s\S]*?\[\/THINKING\]/gi, '');
  }

  // Clean up excessive newlines
  normalized = normalized.replace(/\n{4,}/g, '\n\n\n');

  // Trim whitespace
  normalized = normalized.trim();

  return normalized;
}
