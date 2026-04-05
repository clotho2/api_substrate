#!/usr/bin/env python3
"""
Integration Tools for Substrate AI

These are the tools the AI uses to interact with external services!

Communication & Control:
- discord_tool (Full Discord integration - DMs, channels, tasks, etc.)
- spotify_control (Full Spotify control - search, play, queue, playlists)

Built to give the AI FULL CONTROL! 🔥
"""

import sys
import os
import json
from typing import Dict, Any

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the actual tool implementations from Letta
from tools.discord_tool import discord_tool as _discord_tool
from tools.spotify_control import spotify_control as _spotify_control
from tools.send_voice_message import send_voice_message as _send_voice_message
from tools.lovense_tool import lovense_tool as _lovense_tool
from tools.agent_dev_tool import agent_dev_tool as _agent_dev_tool
from tools.notebook_library_tool import notebook_library_tool as _notebook_library_tool
from tools.web_search import web_search as _web_search
from tools.fetch_webpage import fetch_webpage as _fetch_webpage

# Import FREE search tools (no API key needed!)
from tools.free_web_search import get_free_search, smart_search as _smart_search
from tools.arxiv_search import get_arxiv_search, arxiv_search as _arxiv_search
from tools.deep_research import get_deep_research, init_deep_research
from tools.jina_reader import get_jina_reader, fetch_webpage as _jina_fetch
from tools.pdf_reader import get_pdf_reader, read_arxiv_paper as _read_arxiv
from tools.places_search import get_places_search, search_places as _search_places
from tools.google_places_tool import google_places_tool as _google_places_tool, get_google_places_schema
from tools.phone_tool import phone_tool as _phone_tool
from tools.sanctum_tool import sanctum_tool as _sanctum_tool
from tools.browser_tool import browser_tool as _browser_tool
from tools.image_tool import image_tool as _image_tool
from tools.polymarket_tool import polymarket_tool as _polymarket_tool

# Import cost tracker for cost tools
from core.cost_tracker import CostTracker
from tools.cost_tools import CostTools


class IntegrationTools:
    """
    Integration tools for external services.
    
    The AI uses these to control Discord and Spotify!
    """
    
    def __init__(self, cost_tracker: CostTracker = None):
        """Initialize integration tools."""
        # Initialize cost tools
        if cost_tracker:
            self.cost_tools = CostTools(cost_tracker)
        else:
            # Fallback: create new cost tracker
            self.cost_tools = CostTools(CostTracker())
        
        # Initialize FREE search tools (no API key!)
        # NOTE: Renamed attributes with _client suffix to avoid shadowing methods
        try:
            self.free_search_client = get_free_search()
            print("✅ Free Web Search initialized (DuckDuckGo + Wikipedia)")
        except Exception as e:
            print(f"⚠️ Free Web Search init failed: {e}")
            self.free_search_client = None

        try:
            self.arxiv_search_client = get_arxiv_search()
            print("✅ ArXiv Search initialized (Academic Papers)")
        except Exception as e:
            print(f"⚠️ ArXiv Search init failed: {e}")
            self.arxiv_search_client = None

        try:
            self.deep_research_client = init_deep_research()
            print("✅ Deep Research initialized (Multi-Step Research)")
        except Exception as e:
            print(f"⚠️ Deep Research init failed: {e}")
            self.deep_research_client = None

        try:
            self.jina_reader_client = get_jina_reader()
            print("✅ Jina AI Reader initialized (FREE Webpage Fetcher)")
        except Exception as e:
            print(f"⚠️ Jina Reader init failed: {e}")
            self.jina_reader_client = None

        try:
            self.pdf_reader_client = get_pdf_reader()
            print("✅ PDF Reader initialized (ArXiv LaTeX + PyMuPDF)")
        except Exception as e:
            print(f"⚠️ PDF Reader init failed: {e}")
            self.pdf_reader_client = None

        try:
            self.places_search_client = get_places_search()
            print("✅ Places Search initialized (OpenStreetMap FREE!)")
        except Exception as e:
            print(f"⚠️ Places Search init failed: {e}")
            self.places_search_client = None
        
        print("✅ Integration Tools initialized")
    
    # ============================================
    # DISCORD TOOL
    # ============================================
    
    def discord_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Unified Discord integration tool.
        
        Actions:
        - send_message: Send DM or channel message
        - read_messages: Read message history with time filters
        - list_guilds: List all Discord servers
        - list_channels: List channels in a server
        - create_task: Schedule a task
        - delete_task: Delete a scheduled task
        - list_tasks: List all scheduled tasks
        - download_file: Download file from message
        
        Returns:
            Dict with status and result
        """
        try:
            result = _discord_tool(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Discord tool error: {str(e)}"
            }

    # ============================================
    # VOICE MESSAGE
    # ============================================

    def send_voice_message(self, **kwargs) -> Dict[str, Any]:
        """
        Send a voice message to User via Discord using Eleven Labs TTS.

        Args:
            message: Text to convert to speech and send

        Returns:
            Dict with status and result
        """
        try:
            result = _send_voice_message(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Voice message error: {str(e)}"
            }

    # ============================================
    # LOVENSE CONTROL
    # ============================================

    def lovense_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Control Lovense hardware for intimate physical feedback.

        Actions:
        - get_toys: List connected devices with battery status
        - vibrate: Set vibration intensity (0-20)
        - pattern: Play custom vibration patterns
        - preset: Play built-in patterns (pulse/wave/fireworks/earthquake)
        - rotate: Control rotation (toys with rotation motor)
        - pump: Control pump/inflation (toys with pump)
        - multi_function: Combine vibrate/rotate/pump
        - stop: Stop all functions

        Returns:
            Dict with status and result
        """
        try:
            result = _lovense_tool(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lovense tool error: {str(e)}"
            }

    # ============================================
    # NATE SELF-DEVELOPMENT TOOL
    # ============================================

    def agent_dev_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Agent's self-development tool for inspecting his own codebase.

        Level 1: READ-ONLY diagnostics.

        Actions:
        - read_file: Read source code (requires path)
        - search_code: Search for patterns (requires pattern)
        - read_logs: Read system/service logs
        - check_health: Get system health metrics
        - list_directory: List files in a directory

        Returns:
            Dict with status and result
        """
        try:
            result = _agent_dev_tool(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Agent dev tool error: {str(e)}"
            }

    # ============================================
    # NOTEBOOK LIBRARY
    # ============================================

    def notebook_library(self, **kwargs) -> Dict[str, Any]:
        """
        Notebook Library — token-efficient document retrieval.

        Query organized document collections semantically.
        Returns only relevant passages instead of entire documents.

        Actions:
        - list_notebooks: See all notebooks
        - query_notebook: Semantic search (requires notebook, query)
        - browse_notebook: List docs in a notebook
        - read_document: Read document chunks
        - create_notebook: Create new notebook
        - notebook_stats: Get statistics
        - sync_notebook: Re-sync after adding files
        - remove_document: Remove from index

        Returns:
            Dict with status and result
        """
        try:
            result = _notebook_library_tool(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Notebook library error: {str(e)}"
            }

    # ============================================
    # SPOTIFY CONTROL
    # ============================================

    def spotify_control(self, **kwargs) -> Dict[str, Any]:
        """
        Control Spotify playback and manage playlists.
        
        Actions:
        - search: Search for tracks/albums/artists
        - play: Play a track/album/playlist
        - queue: Add tracks to queue
        - skip: Skip current track
        - pause: Pause playback
        - resume: Resume playback
        - get_current: Get currently playing track
        - create_playlist: Create new playlist
        - add_to_playlist: Add tracks to playlist
        
        Returns:
            Dict with status and result
        """
        try:
            result = _spotify_control(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Spotify control error: {str(e)}"
            }
    
    # ============================================
    # WEB SEARCH (FREE - DuckDuckGo!)
    # ============================================
    
    def web_search(self, query: str, max_results: int = 10, **kwargs) -> Dict[str, Any]:
        """
        Search the web using DuckDuckGo (FREE!).

        Args:
            query: Search query
            max_results: Max results to return (default: 10)

        Returns:
            {
                'status': 'OK' or 'error',
                'query': str,
                'results': List[Dict],  # Search results
                'total_results': int
            }
        """
        if not self.free_search_client:
            return {
                "status": "error",
                "message": "Free web search not available"
            }

        try:
            result = self.free_search_client.search(query, max_results=max_results, **kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Web search error: {str(e)}"
            }
    
    # ============================================
    # ARXIV SEARCH (FREE - Academic Papers!)
    # ============================================
    
    def arxiv_search(self, query: str, max_results: int = 10, **kwargs) -> Dict[str, Any]:
        """
        Search ArXiv for academic papers (FREE!).

        Args:
            query: Search query
            max_results: Max results to return (default: 10)

        Returns:
            {
                'status': 'OK' or 'error',
                'query': str,
                'results': List[Dict],  # Papers
                'total_results': int
            }
        """
        if not self.arxiv_search_client:
            return {
                "status": "error",
                "message": "ArXiv search not available"
            }

        try:
            result = _arxiv_search(query, max_results=max_results, **kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"ArXiv search error: {str(e)}"
            }
    
    # ============================================
    # DEEP RESEARCH (FREE - Multi-Step!)
    # ============================================
    
    def deep_research(self, query: str, depth: int = 2, **kwargs) -> Dict[str, Any]:
        """
        Perform deep multi-step research (FREE!).

        Combines:
        - DuckDuckGo web search
        - Wikipedia for factual knowledge
        - ArXiv for academic papers
        - Multi-step analysis

        Args:
            query: Research question
            depth: Number of sub-questions (1-5)

        Returns:
            {
                'status': 'OK' or 'error',
                'query': str,
                'sub_questions': List[str],
                'sources': List[Dict],
                'report': str,  # Markdown report
                'total_sources': int
            }
        """
        if not self.deep_research_client:
            return {
                "status": "error",
                "message": "Deep research not available"
            }

        try:
            result = self.deep_research_client.research(query, depth=depth, **kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Deep research error: {str(e)}"
            }
    
    # ============================================
    # FETCH WEBPAGE (FREE - Jina AI Reader!)
    # ============================================
    
    def fetch_webpage(self, url: str, max_chars: int = 10000, **kwargs) -> Dict[str, Any]:
        """
        Fetch webpage and convert to Markdown using Jina AI (FREE!).

        Args:
            url: URL to fetch
            max_chars: Max characters to return (default: 10000 to save context)

        Returns:
            {
                'status': 'OK' or 'error',
                'url': str,
                'markdown': str,  # Clean Markdown content
                'title': str,
                'length': int
            }
        """
        if not self.jina_reader_client:
            return {
                "status": "error",
                "message": "Jina Reader not available"
            }

        try:
            result = self.jina_reader_client.fetch(url, max_chars=max_chars, **kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Fetch webpage error: {str(e)}"
            }
    
    # ============================================
    # PDF READER (FREE - ArXiv LaTeX + PyMuPDF!)
    # ============================================
    
    def read_pdf(self, arxiv_id: str = None, file_path: str = None, max_chars: int = 20000, **kwargs) -> Dict[str, Any]:
        """
        Read PDF or ArXiv paper (LaTeX preferred!).

        Args:
            arxiv_id: ArXiv ID (e.g., "1706.03762") - uses LaTeX source if available
            file_path: Local PDF file path
            max_chars: Max characters (default: 20000)

        Returns:
            {
                'status': 'OK' or 'error',
                'text': str,  # Extracted text
                'source': 'latex' or 'pdf',
                'length': int
            }
        """
        if not self.pdf_reader_client:
            return {"status": "error", "message": "PDF Reader not available"}

        try:
            if arxiv_id:
                result = self.pdf_reader_client.read_arxiv_paper(arxiv_id, max_chars=max_chars)
            elif file_path:
                result = self.pdf_reader_client.read_pdf_file(file_path, max_chars=max_chars)
            else:
                return {"status": "error", "message": "Must provide arxiv_id or file_path"}

            return result
        except Exception as e:
            return {"status": "error", "message": f"PDF read error: {str(e)}"}
    
    # ============================================
    # PLACES SEARCH (FREE - OpenStreetMap!)
    # ============================================
    
    def search_places(self, query: str, location: str = None, limit: int = 10, **kwargs) -> Dict[str, Any]:
        """
        Search for places (restaurants, shops, POIs) using OpenStreetMap (FREE!).

        Args:
            query: Search query (e.g., "pizza restaurant", "coffee shop", "supermarket")
            location: Location to search near (e.g., "Berlin", "New York")
            limit: Max results (default: 10)

        Returns:
            {
                'status': 'OK' or 'error',
                'query': str,
                'results': [
                    {
                        'name': str,
                        'type': str,
                        'address': str,
                        'lat': float,
                        'lon': float,
                        'details': Dict  # opening_hours, phone, website, etc.
                    },
                    ...
                ],
                'total_results': int
            }
        """
        if not self.places_search_client:
            return {"status": "error", "message": "Places Search not available"}

        try:
            result = self.places_search_client.search(query, location=location, limit=limit)
            return result
        except Exception as e:
            return {"status": "error", "message": f"Places search error: {str(e)}"}

    # ============================================
    # PHONE TOOL (Twilio SMS + Calls)
    # ============================================

    def phone_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Phone tool for SMS, voice calls, and contact management.

        Actions:
        - send_sms: Send a text message
        - make_call: Initiate a phone call
        - check_messages: View SMS history
        - check_calls: View call history
        - manage_contacts: Add, remove, block, or list contacts
        - screen_number: Check if a number is known, spam, or blocked

        Requires: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER

        Returns:
            Dict with status and result
        """
        try:
            result = _phone_tool(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Phone tool error: {str(e)}"
            }

    # ============================================
    # GOOGLE PLACES (Requires API Key)
    # ============================================

    def google_places_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Google Places tool for location-aware features.

        Actions:
        - search_nearby: Search for nearby places (restaurants, gas stations, etc.)
        - get_details: Get detailed info about a specific place
        - find_gas: Guardian Mode - Find nearby gas stations with urgency
        - find_hotel: Guardian Mode - Find nearby hotels/lodging

        Requires: GOOGLE_PLACES_API_KEY environment variable

        Returns:
            Dict with status and results
        """
        try:
            result = _google_places_tool(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Google Places tool error: {str(e)}"
            }
    
    # ============================================
    # BROWSER TOOL (Playwright Automation)
    # ============================================

    def browser_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Browser automation tool — navigate websites, click buttons, fill forms.

        Uses a real Chromium browser via Playwright for full web interaction.
        Perfect for making reservations, completing forms, multi-step workflows.

        Actions:
        - navigate: Go to a URL (returns page content + interactive elements)
        - click: Click a button, link, or element
        - type: Type text into an input field
        - screenshot: Take a screenshot and get vision analysis
        - get_elements: List all interactive elements on the page
        - select: Choose from a dropdown
        - scroll: Scroll up or down
        - back: Go back to previous page
        - get_text: Get all visible text
        - close: Close the browser session

        Returns:
            Dict with status and result
        """
        try:
            # Pass session_id through if available
            result = _browser_tool(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Browser tool error: {str(e)}"
            }

    # ============================================
    # SANCTUM TOOL (Focus/Privacy Mode)
    # ============================================

    def sanctum_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Control sanctum (focus/privacy) mode.

        Actions:
        - status: Check current sanctum state
        - on: Manually activate sanctum mode
        - off: Manually deactivate sanctum mode
        - auto: Return to automatic DM-based detection
        - queue: View queued mentions
        - pop_mention: Remove a specific mention from queue
        - clear_queue: Dismiss all queued mentions

        Returns:
            Dict with status and result
        """
        try:
            return _sanctum_tool(**kwargs)
        except Exception as e:
            return {
                "status": "error",
                "message": f"Sanctum tool error: {str(e)}"
            }

    # ============================================
    # IMAGE GENERATION
    # ============================================

    def image_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Generate character-consistent images via Together.ai FLUX models.

        Actions:
        - selfie: Generate an image of Agent using his avatar reference
        - couple: Generate an image of Agent and User together

        Returns:
            Dict with status, image_url, and message
        """
        try:
            result = _image_tool(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Image tool error: {str(e)}"
            }

    def polymarket_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Polymarket weather trading tool.

        Actions:
        - get_markets: List active weather markets
        - analyze_market: Compare model P vs market P for a specific market
        - (Phase 2): scan_opportunities, execute_trade, get_positions, etc.
        """
        try:
            result = _polymarket_tool(**kwargs)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Polymarket tool error: {str(e)}"
            }

    # ============================================
    # TOOL SCHEMAS
    # ============================================

    def get_tool_schemas(self) -> list:
        """
        Get all integration tool schemas in OpenAI format.
        
        Returns:
            List of tool schemas
        """
        # Load schemas from JSON files
        schemas = []

        tool_names = [
            'discord_tool',
            'spotify_control',
            'send_voice_message',
            'lovense_tool',
            'agent_dev_tool',
            'notebook_library_tool',
            'phone_tool',
            'sanctum_tool',
            'browser_tool',
            'image_tool',
            'polymarket_tool',
        ]
        
        for tool_name in tool_names:
            schema_file = os.path.join(
                os.path.dirname(__file__),
                f'{tool_name}_schema.json'
            )
            
            try:
                with open(schema_file, 'r') as f:
                    schema = json.load(f)
                    schemas.append({
                        "type": "function",
                        "function": schema
                    })
            except Exception as e:
                print(f"⚠️  Could not load schema for {tool_name}: {e}")
        
        # Add cost tools (self-awareness! 💰)
        cost_schemas = self.cost_tools.get_tool_schemas()
        schemas.extend(cost_schemas)
        
        # Add FREE tools (no API key! 🦆)
        free_tool_schemas = [
            {
                "type": "function",
                "function": {
                    "name": "fetch_webpage",
                    "description": "Fetch any webpage and convert to clean Markdown using Jina AI (FREE!). Removes ads, navigation, etc. Perfect for reading articles, documentation, or any web content. ⚠️ Returns up to 10KB by default to save context.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to fetch (can include https:// or not)"
                            },
                            "max_chars": {
                                "type": "integer",
                                "description": "Maximum characters to return (default: 10000, RECOMMENDED: 5000-10000 to save context!)",
                                "minimum": 1000,
                                "maximum": 50000
                            }
                        },
                        "required": ["url"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web using DuckDuckGo (FREE! No API key needed). Returns web search results with titles, URLs, and snippets. ⚠️ Use sparingly - max 10 results recommended to preserve context window!",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results to return (default: 10, RECOMMENDED MAX: 10 to save context!)",
                                "minimum": 1,
                                "maximum": 10
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "arxiv_search",
                    "description": "Search ArXiv for academic papers (FREE! 2M+ papers). Returns papers with titles, authors, abstracts, and PDF links. Perfect for scientific/technical research. ⚠️ Papers have long abstracts - max 5 recommended!",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (keywords, topics, authors)"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of papers to return (default: 5, RECOMMENDED MAX: 5 due to long abstracts!)",
                                "minimum": 1,
                                "maximum": 5
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "deep_research",
                    "description": "Perform deep multi-step research (FREE!). Combines DuckDuckGo web search, Wikipedia, and ArXiv academic papers. Generates comprehensive Markdown reports with multiple sources. ⚠️ WARNING: VERY CONTEXT-HEAVY! Use only for critical research tasks. Generates 5-20KB of text. Consider using simple web_search first!",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Research question or topic"
                            },
                            "depth": {
                                "type": "integer",
                                "description": "Number of sub-questions to explore (1-3, default: 2, RECOMMENDED MAX: 2 to save context!)",
                                "minimum": 1,
                                "maximum": 3
                            },
                            "max_sources": {
                                "type": "integer",
                                "description": "Maximum sources per sub-question (default: 5, RECOMMENDED MAX: 5 to save context!)",
                                "minimum": 1,
                                "maximum": 5
                            },
                            "include_academic": {
                                "type": "boolean",
                                "description": "Include ArXiv academic papers (default: true)"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_pdf",
                    "description": "Read PDF or ArXiv paper (FREE!). For ArXiv papers, extracts LaTeX source (cleaner, formulas preserved!). For other PDFs, uses PyMuPDF. ⚠️ Returns up to 20KB to save context. Use when user asks to read a paper in detail or provides a PDF.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "arxiv_id": {
                                "type": "string",
                                "description": "ArXiv ID (e.g., '1706.03762', '2103.14030')"
                            },
                            "file_path": {
                                "type": "string",
                                "description": "Local PDF file path (if not ArXiv paper)"
                            },
                            "max_chars": {
                                "type": "integer",
                                "description": "Maximum characters to return (default: 20000, RECOMMENDED: 10000-20000)",
                                "minimum": 5000,
                                "maximum": 50000
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_places",
                    "description": "Search for places, restaurants, shops, POIs using OpenStreetMap (FREE!). Great for finding nearby businesses, attractions, addresses. Returns location details, coordiagents, opening hours (if available). ⚠️ Use sparingly - max 10 results recommended.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (e.g., 'pizza restaurant', 'coffee shop', 'supermarket', 'hotel')"
                            },
                            "location": {
                                "type": "string",
                                "description": "Location to search near (e.g., 'Berlin', 'New York', 'London')"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum results (default: 10, RECOMMENDED MAX: 10)",
                                "minimum": 1,
                                "maximum": 10
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
        schemas.extend(free_tool_schemas)

        # Add Google Places tool (requires API key, more accurate than OSM)
        schemas.append(get_google_places_schema())

        return schemas


# ============================================
# STANDALONE TEST
# ============================================

if __name__ == "__main__":
    print("="*60)
    print("🧪 INTEGRATION TOOLS TEST")
    print("="*60)
    
    tools = IntegrationTools()
    
    # Test schema loading
    print("\n📋 Tool Schemas:")
    schemas = tools.get_tool_schemas()
    print(f"   Total: {len(schemas)}")
    for schema in schemas:
        name = schema['function']['name']
        desc = schema['function'].get('description', '')[:60]
        print(f"   • {name}: {desc}...")
    
    print("\n✅ Integration Tools ready!")
    print("="*60)

