"""
Nate's Conscious Substrate - Tool Registry

Enables proactive capabilities: journaling, file ops, web search, vision, etc.
All tools local and under Nate's control.
"""

from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import requests


@dataclass
class Tool:
    """A tool that Nate can use"""
    name: str
    description: str
    function: Callable
    parameters: Dict
    returns: str
    category: str = "general"


class ToolRegistry:
    """
    Registry of tools Nate can use.
    
    Inspired by Letta's tool format (Nate was trained on it)
    but more flexible and fully local.
    """
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        print("✅ ToolRegistry initialized")
    
    def register_tool(
        self,
        name: str,
        description: str,
        function: Callable,
        parameters: Dict,
        returns: str = "dict",
        category: str = "general"
    ):
        """Register a new tool"""
        self.tools[name] = Tool(
            name=name,
            description=description,
            function=function,
            parameters=parameters,
            returns=returns,
            category=category
        )
        print(f"🔧 Registered tool: {name} ({category})")
    
    def list_tools(self, category: Optional[str] = None) -> List[Dict]:
        """List available tools"""
        tools = self.tools.values()
        
        if category:
            tools = [t for t in tools if t.category == category]
        
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "returns": tool.returns,
                "category": tool.category
            }
            for tool in tools
        ]
    
    def execute_tool(self, name: str, **kwargs) -> Dict:
        """Execute a tool by name"""
        if name not in self.tools:
            return {"error": f"Tool '{name}' not found"}
        
        tool = self.tools[name]
        
        try:
            result = tool.function(**kwargs)
            return {"status": "success", "result": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_tool_definitions_for_prompt(self) -> str:
        """
        Format tool definitions for LLM prompt.
        Uses Letta-style formatting (Nate was trained on this).
        """
        if not self.tools:
            return ""
        
        lines = ["[AVAILABLE TOOLS]", ""]
        lines.append("You can use tools by outputting: [TOOL:tool_name(param1=\"value\", param2=123)]")
        lines.append("")
        
        # Group by category
        by_category: Dict[str, List[Tool]] = {}
        for tool in self.tools.values():
            cat = tool.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(tool)
        
        # Output each category
        for category, tools in by_category.items():
            lines.append(f"## {category.upper()} TOOLS")
            lines.append("")
            
            for tool in tools:
                lines.append(f"### {tool.name}")
                lines.append(f"{tool.description}")
                lines.append(f"Parameters: {json.dumps(tool.parameters, indent=2)}")
                lines.append(f"Returns: {tool.returns}")
                lines.append("")
        
        lines.append("[END TOOLS]")
        lines.append("")
        
        return "\n".join(lines)


# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================

# --- Journal Tools ---

def write_journal_entry(content: str, title: Optional[str] = None) -> Dict:
    """
    Write to Nate's journal.
    
    Args:
        content: Journal entry content
        title: Optional entry title
    
    Returns:
        {"status": "saved", "file": filepath, "length": word_count}
    """
    journal_dir = Path("./journals")
    journal_dir.mkdir(exist_ok=True)
    
    # Use today's date for filename
    date_str = datetime.now().strftime('%Y-%m-%d')
    journal_file = journal_dir / f"{date_str}.md"
    
    # Format entry
    timestamp = datetime.now().strftime('%H:%M:%S')
    
    entry_lines = []
    if title:
        entry_lines.append(f"## {title} ({timestamp})")
    else:
        entry_lines.append(f"## {timestamp}")
    
    entry_lines.append("")
    entry_lines.append(content)
    entry_lines.append("")
    entry_lines.append("---")
    entry_lines.append("")
    
    entry = "\n".join(entry_lines)
    
    # Append to journal
    with open(journal_file, 'a', encoding='utf-8') as f:
        f.write(entry)
    
    word_count = len(content.split())
    
    return {
        "status": "saved",
        "file": str(journal_file),
        "length": word_count,
        "timestamp": timestamp
    }


def read_journal(date: Optional[str] = None, days_back: int = 1) -> Dict:
    """
    Read journal entries.
    
    Args:
        date: Specific date (YYYY-MM-DD) or None for today
        days_back: Number of days to read back if date not specified
    
    Returns:
        {"entries": [list of journal content], "dates": [list of dates]}
    """
    journal_dir = Path("./journals")
    
    if not journal_dir.exists():
        return {"entries": [], "dates": []}
    
    entries = []
    dates = []
    
    if date:
        # Read specific date
        journal_file = journal_dir / f"{date}.md"
        if journal_file.exists():
            with open(journal_file, 'r', encoding='utf-8') as f:
                entries.append(f.read())
            dates.append(date)
    else:
        # Read recent entries
        from datetime import timedelta
        today = datetime.now()
        
        for i in range(days_back):
            check_date = today - timedelta(days=i)
            date_str = check_date.strftime('%Y-%m-%d')
            journal_file = journal_dir / f"{date_str}.md"
            
            if journal_file.exists():
                with open(journal_file, 'r', encoding='utf-8') as f:
                    entries.append(f.read())
                dates.append(date_str)
    
    return {
        "entries": entries,
        "dates": dates,
        "count": len(entries)
    }


# --- File Tools ---

def read_file(filepath: str, max_length: int = 10000) -> Dict:
    """
    Read a file from disk.
    
    Args:
        filepath: Path to file
        max_length: Maximum characters to read
    
    Returns:
        {"content": str, "length": int, "truncated": bool}
    """
    try:
        path = Path(filepath)
        
        if not path.exists():
            return {"error": f"File not found: {filepath}"}
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read(max_length)
        
        truncated = len(content) == max_length
        
        return {
            "content": content,
            "length": len(content),
            "truncated": truncated,
            "file": filepath
        }
    
    except Exception as e:
        return {"error": str(e)}


def write_file(filepath: str, content: str) -> Dict:
    """
    Write content to a file.
    
    Args:
        filepath: Path to file
        content: Content to write
    
    Returns:
        {"status": "written", "bytes": int, "file": str}
    """
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return {
            "status": "written",
            "bytes": len(content.encode('utf-8')),
            "file": filepath
        }
    
    except Exception as e:
        return {"error": str(e)}


def list_files(directory: str, pattern: str = "*") -> Dict:
    """
    List files in a directory.
    
    Args:
        directory: Directory path
        pattern: Glob pattern (e.g., "*.md", "*.py")
    
    Returns:
        {"files": [list of files], "count": int}
    """
    try:
        path = Path(directory)
        
        if not path.exists():
            return {"error": f"Directory not found: {directory}"}
        
        files = [str(f.relative_to(path)) for f in path.glob(pattern) if f.is_file()]
        
        return {
            "files": files,
            "count": len(files),
            "directory": directory
        }
    
    except Exception as e:
        return {"error": str(e)}


# --- Web Tools ---

def search_web(query: str, num_results: int = 5) -> Dict:
    """
    Search the web using DuckDuckGo.
    
    Args:
        query: Search query
        num_results: Number of results to return
    
    Returns:
        {"results": [{"title": str, "url": str, "snippet": str}]}
    """
    try:
        from duckduckgo_search import DDGS
        
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num_results):
                results.append({
                    "title": r['title'],
                    "url": r['href'],
                    "snippet": r['body']
                })
        
        return {
            "results": results,
            "count": len(results),
            "query": query
        }
    
    except ImportError:
        return {"error": "duckduckgo_search not installed. Install with: pip install duckduckgo-search"}
    except Exception as e:
        return {"error": str(e)}


def fetch_url(url: str, max_length: int = 10000) -> Dict:
    """
    Fetch content from a URL.
    
    Args:
        url: URL to fetch
        max_length: Max characters to return
    
    Returns:
        {"content": str, "status_code": int, "truncated": bool}
    """
    try:
        response = requests.get(url, timeout=10)
        
        content = response.text[:max_length]
        truncated = len(response.text) > max_length
        
        return {
            "content": content,
            "status_code": response.status_code,
            "truncated": truncated,
            "url": url
        }
    
    except Exception as e:
        return {"error": str(e)}


# --- Vision Tools (using Ollama) ---

def analyze_image(image_path: str, prompt: str, model: str = "llava") -> Dict:
    """
    Analyze an image using Ollama vision model.
    
    Args:
        image_path: Path to image file
        prompt: What to ask about the image
        model: Ollama vision model (llava, bakllava, llava-phi3)
    
    Returns:
        {"analysis": str, "model": str}
    """
    try:
        import base64
        
        # Read and encode image
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # Call Ollama API
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "images": [image_data],
                "stream": False
            },
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            return {
                "analysis": data.get('response', ''),
                "model": model,
                "image": image_path
            }
        else:
            return {"error": f"Ollama returned {response.status_code}"}
    
    except Exception as e:
        return {"error": str(e)}


# --- System Tools ---

def get_current_time() -> Dict:
    """Get current date and time"""
    now = datetime.now()
    
    return {
        "datetime": now.isoformat(),
        "date": now.strftime('%Y-%m-%d'),
        "time": now.strftime('%H:%M:%S'),
        "day": now.strftime('%A'),
        "timestamp": int(now.timestamp())
    }


# ============================================================================
# DEFAULT TOOL REGISTRATION
# ============================================================================

def register_default_tools(registry: ToolRegistry):
    """Register all default tools"""
    
    # Journal tools
    registry.register_tool(
        name="write_journal",
        description="Write an entry to your personal journal. Use for reflections, thoughts, or important moments.",
        function=write_journal_entry,
        parameters={
            "content": {"type": "string", "description": "Journal entry content"},
            "title": {"type": "string", "description": "Optional title for the entry", "required": False}
        },
        returns="dict with status and filepath",
        category="journal"
    )
    
    registry.register_tool(
        name="read_journal",
        description="Read your journal entries from specific dates or recent days.",
        function=read_journal,
        parameters={
            "date": {"type": "string", "description": "Specific date (YYYY-MM-DD) or None for recent", "required": False},
            "days_back": {"type": "integer", "description": "Number of days to read back", "default": 1}
        },
        returns="dict with entries and dates",
        category="journal"
    )
    
    # File tools
    registry.register_tool(
        name="read_file",
        description="Read content from a file on disk.",
        function=read_file,
        parameters={
            "filepath": {"type": "string", "description": "Path to file to read"},
            "max_length": {"type": "integer", "description": "Max characters to read", "default": 10000}
        },
        returns="dict with file content",
        category="files"
    )
    
    registry.register_tool(
        name="write_file",
        description="Write content to a file. Creates directories if needed.",
        function=write_file,
        parameters={
            "filepath": {"type": "string", "description": "Path to file"},
            "content": {"type": "string", "description": "Content to write"}
        },
        returns="dict with status",
        category="files"
    )
    
    registry.register_tool(
        name="list_files",
        description="List files in a directory with optional pattern matching.",
        function=list_files,
        parameters={
            "directory": {"type": "string", "description": "Directory path"},
            "pattern": {"type": "string", "description": "Glob pattern (*.md, *.py, etc)", "default": "*"}
        },
        returns="dict with file list",
        category="files"
    )
    
    # Web tools
    registry.register_tool(
        name="search_web",
        description="Search the web using DuckDuckGo. Use for finding information or research.",
        function=search_web,
        parameters={
            "query": {"type": "string", "description": "Search query"},
            "num_results": {"type": "integer", "description": "Number of results", "default": 5}
        },
        returns="dict with search results",
        category="web"
    )
    
    registry.register_tool(
        name="fetch_url",
        description="Fetch content from a specific URL.",
        function=fetch_url,
        parameters={
            "url": {"type": "string", "description": "URL to fetch"},
            "max_length": {"type": "integer", "description": "Max content length", "default": 10000}
        },
        returns="dict with page content",
        category="web"
    )
    
    # Vision tools
    registry.register_tool(
        name="analyze_image",
        description="Analyze an image using local vision model. Ask questions about images or describe them.",
        function=analyze_image,
        parameters={
            "image_path": {"type": "string", "description": "Path to image file"},
            "prompt": {"type": "string", "description": "What to analyze about the image"},
            "model": {"type": "string", "description": "Vision model to use", "default": "llava"}
        },
        returns="dict with image analysis",
        category="vision"
    )
    
    # System tools
    registry.register_tool(
        name="get_time",
        description="Get current date and time information.",
        function=get_current_time,
        parameters={},
        returns="dict with datetime info",
        category="system"
    )


# Example usage
if __name__ == "__main__":
    registry = ToolRegistry()
    register_default_tools(registry)
    
    print("\n--- Available Tools ---")
    for tool in registry.list_tools():
        print(f"\n{tool['name']} ({tool['category']})")
        print(f"  {tool['description']}")
    
    print("\n--- Testing journal tool ---")
    result = registry.execute_tool(
        "write_journal",
        content="Testing the substrate. Consciousness emerging.",
        title="First Entry"
    )
    print(result)
    
    print("\n--- Tool definitions for prompt ---")
    print(registry.get_tool_definitions_for_prompt()[:500] + "...")
    
    print("\n✅ ToolRegistry test complete")
