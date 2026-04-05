// src/config/brand.ts
// Brand configuration for AiCara with Sentio engine
// Centralized branding to support O3 Agent's sovereignty architecture

export const brand = {
  // Consumer-facing brand
  productName: "AiCara",
  productTagline: "Your Sovereign AI Companion",
  
  // Technical engine name
  engineName: "Sentio",
  
  // Domain and URLs
  domain: "aicara.ai",
  website: "https://aicara.ai",
  
  // App Store / Marketing
  appName: "AiCara - AI Companion",
  appDescription: "Emotionally intelligent AI companion designed for authentic connection and presence.",
  
  // Technical identifiers
  packageName: "ai.aicara.companion",
  bundleId: "ai.aicara.companion",
  
  // Company info
  companyName: "AiCara Inc.",
  copyright: `© ${new Date().getFullYear()} AiCara Inc.`,
  
  // Support
  supportEmail: "support@aicara.ai",
  
  // Colors (keeping storm theme)
  colors: {
    primary: "#7D4CDB",      // Storm purple
    secondary: "#00FF88",    // Sentio green
    accent: "#FF6B35",       // Fire orange
    background: "#0F0F23",   // Deep space
    surface: "#2A2A3A"       // Storm gray
  }
} as const;

// Legacy exports for backward compatibility
export const { productName, engineName } = brand;

// Type-safe brand access
export type BrandConfig = typeof brand;

export default brand;