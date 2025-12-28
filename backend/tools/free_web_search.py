#!/usr/bin/env python3
"""
Free Web Search - NO API KEY NEEDED! 🦆

Uses DuckDuckGo (completely free, no rate limits!)
Plus Wikipedia for factual knowledge.

Perfect for budget-conscious AI agents.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    print("⚠️ duckduckgo-search not installed. Run: pip install duckduckgo-search")

try:
    import wikipediaapi
    WIKIPEDIA_AVAILABLE = True
except ImportError:
    WIKIPEDIA_AVAILABLE = False
    print("⚠️ wikipedia-api not installed. Run: pip install wikipedia-api")

logger = logging.getLogger(__name__)


class FreeWebSearch:
    """
    Free Web Search - DuckDuckGo + Wikipedia.
    
    NO API KEY NEEDED! Completely free! 🎉
    """
    
    def __init__(self):
        """Initialize free web search"""
        # Don't create DDGS instance here - create fresh for each search to avoid API issues
        self.ddgs_available = DDGS_AVAILABLE

        # Wikipedia requires a User-Agent (be nice to Wikipedia!)
        if WIKIPEDIA_AVAILABLE:
            self.wiki = wikipediaapi.Wikipedia(
                user_agent='SubstrateAI/1.0 (https://github.com/yourusername/substrate-ai)',
                language='en'
            )
        else:
            self.wiki = None

        if not DDGS_AVAILABLE:
            logger.warning("⚠️ DuckDuckGo search not available (library not installed)")

        logger.info("✅ Free Web Search initialized (DuckDuckGo + Wikipedia)")
    
    def search(
        self,
        query: str,
        max_results: int = 10,
        region: str = "wt-wt",  # Worldwide
        safesearch: str = "moderate",  # "on", "moderate", "off"
        timelimit: Optional[str] = None  # "d" (day), "w" (week), "m" (month), "y" (year)
    ) -> Dict[str, Any]:
        """
        Search the web using DuckDuckGo (FREE!).
        
        Args:
            query: Search query
            max_results: Max results (default: 10)
            region: Region code (default: wt-wt = worldwide)
            safesearch: "on", "moderate", or "off"
            timelimit: Filter by time (d/w/m/y)
        
        Returns:
            {
                'status': 'OK' or 'error',
                'query': str,
                'results': [
                    {
                        'title': str,
                        'url': str,
                        'snippet': str,  # Description/excerpt
                        'source': 'duckduckgo'
                    },
                    ...
                ],
                'total_results': int
            }
        """
        if not self.ddgs_available:
            return {
                "status": "error",
                "message": "DuckDuckGo library not installed. Run: pip install duckduckgo-search",
                "query": query
            }

        try:
            logger.info(f"🦆 DuckDuckGo Search: '{query}' (max={max_results})")

            # Perform search
            results = []

            # Use DDGS API (v8.x compatible)
            # Version 8.1.1 uses simple instantiation without context manager
            ddgs = DDGS()
            ddgs_results = ddgs.text(
                keywords=query,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit,
                max_results=max_results
            )
            
            # Convert to our format
            for r in ddgs_results:
                results.append({
                    'title': r.get('title', ''),
                    'url': r.get('href', r.get('link', '')),
                    'snippet': r.get('body', ''),
                    'source': 'duckduckgo'
                })
            
            logger.info(f"✅ Found {len(results)} results")
            
            return {
                "status": "OK",
                "query": query,
                "results": results,
                "total_results": len(results),
                "search_engine": "DuckDuckGo (Free!)"
            }
        
        except Exception as e:
            error_msg = f"DuckDuckGo search failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                "status": "error",
                "message": error_msg,
                "query": query
            }
    
    def search_news(
        self,
        query: str,
        max_results: int = 10,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: str = "w"  # Last week by default
    ) -> Dict[str, Any]:
        """
        Search news using DuckDuckGo (FREE!).
        
        Same as search() but optimized for news with time filtering.
        """
        if not self.ddgs_available:
            return {
                "status": "error",
                "message": "DuckDuckGo library not installed",
                "query": query
            }

        try:
            logger.info(f"📰 DuckDuckGo News: '{query}' (time={timelimit})")

            results = []

            # Create fresh DDGS instance for each search (avoids API compatibility issues)
            with DDGS() as ddgs:
                # Use news search (new DDGS API!)
                ddgs_results = ddgs.news(
                    query,  # Query is now positional argument!
                    region=region,
                    safesearch=safesearch,
                    timelimit=timelimit,
                    max_results=max_results
                )
            
            # Convert to our format
            for r in ddgs_results:
                results.append({
                    'title': r.get('title', ''),
                    'url': r.get('url', ''),
                    'snippet': r.get('body', ''),
                    'date': r.get('date', ''),
                    'source': r.get('source', 'unknown'),
                    'search_engine': 'duckduckgo_news'
                })
            
            logger.info(f"✅ Found {len(results)} news results")
            
            return {
                "status": "OK",
                "query": query,
                "results": results,
                "total_results": len(results),
                "search_engine": "DuckDuckGo News (Free!)"
            }
        
        except Exception as e:
            error_msg = f"DuckDuckGo news search failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                "status": "error",
                "message": error_msg,
                "query": query
            }
    
    def search_wikipedia(
        self,
        query: str,
        sentences: int = 5
    ) -> Dict[str, Any]:
        """
        Search Wikipedia for factual information.
        
        Args:
            query: Search query (article title)
            sentences: Number of sentences to return (default: 5)
        
        Returns:
            {
                'status': 'OK' or 'error',
                'query': str,
                'title': str,
                'summary': str,
                'url': str,
                'source': 'wikipedia'
            }
        """
        if not self.wiki:
            return {
                "status": "error",
                "message": "Wikipedia library not installed. Run: pip install wikipedia-api",
                "query": query
            }
        
        try:
            logger.info(f"📚 Wikipedia Search: '{query}'")
            
            # Get page
            page = self.wiki.page(query)
            
            if not page.exists():
                # Try to find suggestions
                logger.warning(f"⚠️ Wikipedia page '{query}' not found")
                return {
                    "status": "not_found",
                    "message": f"No Wikipedia article found for '{query}'",
                    "query": query
                }
            
            # Get summary (first N sentences)
            summary = page.summary[:sentences * 200] if page.summary else ""
            
            logger.info(f"✅ Found Wikipedia article: {page.title}")
            
            return {
                "status": "OK",
                "query": query,
                "title": page.title,
                "summary": summary,
                "url": page.fullurl,
                "source": "wikipedia"
            }
        
        except Exception as e:
            error_msg = f"Wikipedia search failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                "status": "error",
                "message": error_msg,
                "query": query
            }
    
    def smart_search(
        self,
        query: str,
        max_results: int = 10,
        include_wikipedia: bool = True
    ) -> Dict[str, Any]:
        """
        Smart search - combines DuckDuckGo + Wikipedia.
        
        If query looks like a factual question, also searches Wikipedia.
        
        Args:
            query: Search query
            max_results: Max DuckDuckGo results
            include_wikipedia: Also search Wikipedia (default: True)
        
        Returns:
            Combined results from DuckDuckGo and Wikipedia
        """
        logger.info(f"🧠 Smart Search: '{query}'")
        
        # Always do DuckDuckGo search
        ddg_results = self.search(query, max_results=max_results)
        
        # If Wikipedia available and requested, try it too
        wiki_result = None
        if include_wikipedia and self.wiki:
            # Extract potential Wikipedia article name from query
            # Remove question words
            wiki_query = query.replace('what is ', '').replace('who is ', '').replace('?', '').strip()
            wiki_result = self.search_wikipedia(wiki_query)
        
        # Combine results
        combined = {
            "status": ddg_results.get("status"),
            "query": query,
            "web_results": ddg_results.get("results", []),
            "wikipedia": wiki_result if wiki_result and wiki_result.get("status") == "OK" else None,
            "total_sources": len(ddg_results.get("results", [])) + (1 if wiki_result and wiki_result.get("status") == "OK" else 0),
            "search_engine": "DuckDuckGo + Wikipedia (Free!)"
        }
        
        logger.info(f"✅ Smart search complete: {combined['total_sources']} total sources")
        
        return combined


# Singleton
_free_search: Optional[FreeWebSearch] = None


def get_free_search() -> FreeWebSearch:
    """Get or create free search singleton"""
    global _free_search
    if _free_search is None:
        _free_search = FreeWebSearch()
    return _free_search


def web_search(query: str, max_results: int = 10, **kwargs) -> Dict[str, Any]:
    """
    Free web search - DuckDuckGo (no API key needed!)
    
    Args:
        query: Search query
        max_results: Max results
    
    Returns:
        Search results
    """
    searcher = get_free_search()
    return searcher.search(query, max_results=max_results, **kwargs)


def smart_search(query: str, max_results: int = 10, **kwargs) -> Dict[str, Any]:
    """
    Smart search - DuckDuckGo + Wikipedia
    
    Args:
        query: Search query
        max_results: Max results
    
    Returns:
        Combined search results
    """
    searcher = get_free_search()
    return searcher.smart_search(query, max_results=max_results, **kwargs)


if __name__ == "__main__":
    # Test
    print("\n🧪 Testing Free Web Search (DuckDuckGo + Wikipedia)\n")
    
    # Test 1: Regular search
    print("1️⃣ DuckDuckGo Search:")
    result = web_search("Python best practices 2025", max_results=3)
    print(f"Status: {result['status']}")
    print(f"Results: {len(result.get('results', []))}")
    if result.get('results'):
        for i, r in enumerate(result['results'][:2], 1):
            print(f"  {i}. {r['title'][:60]}...")
            print(f"     {r['url']}")
    print()
    
    # Test 2: Wikipedia
    print("2️⃣ Wikipedia Search:")
    searcher = get_free_search()
    wiki_result = searcher.search_wikipedia("Artificial Intelligence")
    print(f"Status: {wiki_result['status']}")
    if wiki_result.get('summary'):
        print(f"Title: {wiki_result['title']}")
        print(f"Summary: {wiki_result['summary'][:150]}...")
        print(f"URL: {wiki_result['url']}")
    print()
    
    # Test 3: Smart Search
    print("3️⃣ Smart Search (DuckDuckGo + Wikipedia):")
    smart_result = smart_search("What is machine learning?", max_results=3)
    print(f"Status: {smart_result['status']}")
    print(f"Web results: {len(smart_result.get('web_results', []))}")
    print(f"Wikipedia: {'Yes' if smart_result.get('wikipedia') else 'No'}")
    print(f"Total sources: {smart_result.get('total_sources', 0)}")

