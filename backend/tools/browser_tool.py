#!/usr/bin/env python3
"""
Browser Automation Tool for Substrate AI

Gives agent the ability to interact with websites — navigate, click buttons,
fill forms, select options, and take screenshots. Powered by Playwright.

Use cases:
- Making restaurant reservations (OpenTable, Resy)
- Filling out forms and completing workflows
- Navigating multi-step web processes
- Reading dynamic/JS-rendered content

Actions:
- navigate: Go to a URL, get page content and interactive elements
- click: Click an element by CSS selector or visible text
- type: Type text into an input field
- screenshot: Take a screenshot and get a vision-model description
- get_elements: List all interactive elements on the page
- select: Choose an option from a dropdown/select
- scroll: Scroll the page up or down
- back: Navigate back in browser history
- get_text: Get all visible text on the page
- close: Close the browser session

Security:
- Headless Chromium (no GUI needed on server)
- Session-based browser instances (isolated per session)
- Automatic cleanup on close or timeout
- No file system access from browser context
"""

import os
import sys
import json
import base64
import time
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Browser session management
_browser_sessions: Dict[str, Any] = {}
_session_lock = threading.Lock()
_SESSION_TIMEOUT_MINUTES = 15


def _get_or_create_session(session_id: str) -> Dict[str, Any]:
    """
    Get an existing browser session or create a new one.

    Each session maintains its own browser context (cookies, storage, etc.)
    so agent can maintain state across multiple tool calls within a conversation.
    """
    with _session_lock:
        # Check for existing session
        if session_id in _browser_sessions:
            session = _browser_sessions[session_id]
            session['last_used'] = datetime.now()
            return session

        # Create new session
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {
                'error': 'Playwright not installed. Run: pip install playwright && playwright install chromium'
            }

        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-extensions',
            ]
        )
        context = browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            java_script_enabled=True,
        )
        page = context.new_page()

        # Set default timeouts
        page.set_default_timeout(30000)  # 30 seconds
        page.set_default_navigation_timeout(30000)

        session = {
            'playwright': pw,
            'browser': browser,
            'context': context,
            'page': page,
            'created': datetime.now(),
            'last_used': datetime.now(),
        }
        _browser_sessions[session_id] = session

        print(f"   🌐 Browser session created for {session_id}")
        return session


def _close_session(session_id: str) -> None:
    """Close and cleanup a browser session."""
    with _session_lock:
        session = _browser_sessions.pop(session_id, None)
        if session and 'error' not in session:
            try:
                session['page'].close()
                session['context'].close()
                session['browser'].close()
                session['playwright'].stop()
                print(f"   🌐 Browser session closed for {session_id}")
            except Exception as e:
                print(f"   ⚠️ Error closing browser session: {e}")


def _cleanup_stale_sessions() -> None:
    """Clean up sessions that haven't been used recently."""
    cutoff = datetime.now() - timedelta(minutes=_SESSION_TIMEOUT_MINUTES)
    stale = []
    with _session_lock:
        for sid, session in _browser_sessions.items():
            if session.get('last_used', datetime.min) < cutoff:
                stale.append(sid)

    for sid in stale:
        print(f"   🧹 Cleaning up stale browser session: {sid}")
        _close_session(sid)


def _analyze_screenshot(screenshot_b64: str, page_url: str, user_context: str = "") -> str:
    """
    Analyze a screenshot using the vision system.

    Uses the existing vision model configuration from vision_prompt.py:
    - If VISION_MODEL is set, uses that
    - If OLLAMA_VISION_MODEL is set, uses local Ollama
    - Otherwise falls back to Gemini Flash (free)

    The main model's multimodal capability is handled by the consciousness loop,
    not here. This provides a text fallback description for all cases.
    """
    try:
        from core.vision_prompt import get_vision_model
        from core.openrouter_client import OpenRouterClient

        vision_model = get_vision_model()

        # Build a browser-specific analysis prompt
        analysis_prompt = f"""You are analyzing a browser screenshot to help an AI assistant navigate a website.

Describe what you see on this webpage, focusing on:

1. **PAGE LAYOUT**: What kind of page is this? (login form, search results, reservation page, checkout, etc.)
2. **KEY CONTENT**: What important text/information is visible?
3. **INTERACTIVE ELEMENTS**: What buttons, links, forms, dropdowns, or input fields are visible? Describe their labels/text.
4. **STATE**: Is anything selected, filled in, or highlighted? Any error messages or confirmations?
5. **NEXT STEPS**: What actions could be taken on this page?

Current URL: {page_url}
{f'Context: {user_context}' if user_context else ''}

Be concise but thorough. Focus on actionable information that helps complete a task on this website."""

        # Call vision model via OpenRouter
        client = OpenRouterClient()

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": analysis_prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_b64}"
                    }
                }
            ]
        }]

        response = client.chat_completion(
            messages=messages,
            model=vision_model,
            max_tokens=1000,
            temperature=0.3
        )

        if response and response.get('content'):
            return response['content']

        return "Screenshot captured but vision analysis unavailable."

    except Exception as e:
        print(f"   ⚠️ Screenshot analysis failed: {e}")
        return f"Screenshot captured but analysis failed: {str(e)}"


def _get_interactive_elements(page, max_elements: int = 50) -> List[Dict[str, str]]:
    """
    Extract interactive elements from the page that agent can interact with.

    Returns a list of elements with their type, text, selector, and attributes.
    """
    elements = []

    try:
        # Query for interactive elements
        selectors = [
            ('button', 'button, [role="button"], input[type="submit"], input[type="button"]'),
            ('link', 'a[href]'),
            ('input', 'input:not([type="hidden"]):not([type="submit"]):not([type="button"])'),
            ('textarea', 'textarea'),
            ('select', 'select'),
        ]

        for elem_type, selector in selectors:
            try:
                handles = page.query_selector_all(selector)
                for handle in handles:
                    if len(elements) >= max_elements:
                        break

                    try:
                        # Check visibility
                        if not handle.is_visible():
                            continue

                        elem_info = {
                            'type': elem_type,
                            'text': '',
                            'selector': '',
                            'attributes': {}
                        }

                        # Get text content
                        text = handle.inner_text().strip() if elem_type != 'input' else ''
                        if not text and elem_type in ('button', 'link'):
                            text = handle.get_attribute('aria-label') or ''
                        if not text:
                            text = handle.get_attribute('title') or ''
                        if not text and elem_type == 'input':
                            text = handle.get_attribute('placeholder') or ''

                        elem_info['text'] = text[:100]  # Truncate long text

                        # Build a usable selector
                        elem_id = handle.get_attribute('id')
                        elem_name = handle.get_attribute('name')
                        elem_class = handle.get_attribute('class')
                        aria_label = handle.get_attribute('aria-label')
                        input_type = handle.get_attribute('type')
                        href = handle.get_attribute('href') if elem_type == 'link' else None

                        if elem_id:
                            elem_info['selector'] = f'#{elem_id}'
                        elif elem_name:
                            elem_info['selector'] = f'[name="{elem_name}"]'
                        elif aria_label:
                            elem_info['selector'] = f'[aria-label="{aria_label}"]'
                        elif text and elem_type in ('button', 'link'):
                            elem_info['selector'] = f'text="{text[:50]}"'

                        # Useful attributes
                        if input_type:
                            elem_info['attributes']['type'] = input_type
                        if elem_name:
                            elem_info['attributes']['name'] = elem_name
                        if href:
                            elem_info['attributes']['href'] = href[:100]
                        if handle.get_attribute('placeholder'):
                            elem_info['attributes']['placeholder'] = handle.get_attribute('placeholder')
                        if handle.get_attribute('value'):
                            elem_info['attributes']['value'] = handle.get_attribute('value')[:50]
                        if handle.get_attribute('required') is not None:
                            elem_info['attributes']['required'] = True

                        # Only add if we have a usable selector
                        if elem_info['selector']:
                            elements.append(elem_info)
                    except Exception:
                        continue
            except Exception:
                continue

        # Also get select options for visible selects
        try:
            select_handles = page.query_selector_all('select')
            for select in select_handles:
                if not select.is_visible():
                    continue
                select_id = select.get_attribute('id')
                select_name = select.get_attribute('name')
                if select_id or select_name:
                    options = select.query_selector_all('option')
                    option_texts = []
                    for opt in options[:10]:  # Max 10 options per select
                        opt_text = opt.inner_text().strip()
                        opt_value = opt.get_attribute('value')
                        if opt_text:
                            option_texts.append(f"{opt_text} (value={opt_value})" if opt_value else opt_text)

                    selector = f'#{select_id}' if select_id else f'[name="{select_name}"]'
                    # Find matching element and add options
                    for elem in elements:
                        if elem['selector'] == selector and elem['type'] == 'select':
                            elem['attributes']['options'] = option_texts
                            break
        except Exception:
            pass

    except Exception as e:
        print(f"   ⚠️ Error extracting elements: {e}")

    return elements


def browser_tool(
    action: str,
    url: str = None,
    selector: str = None,
    text: str = None,
    value: str = None,
    direction: str = "down",
    amount: int = 3,
    description: str = "",
    session_id: str = "default",
    **kwargs
) -> Dict[str, Any]:
    """
    Browser automation tool — navigate websites, click buttons, fill forms.

    Args:
        action: Action to perform (navigate, click, type, screenshot, get_elements, select, scroll, back, get_text, close)
        url: URL to navigate to (for 'navigate' action)
        selector: CSS selector or text selector for the target element (for click, type, select)
        text: Text to type (for 'type' action) or text of element to click (for 'click' without selector)
        value: Value to select (for 'select' action)
        direction: Scroll direction - 'up' or 'down' (for 'scroll' action)
        amount: Number of scroll steps (for 'scroll' action)
        description: What you're trying to accomplish (helps with screenshot analysis)
        session_id: Session ID for maintaining browser state across calls

    Returns:
        Dict with status and action-specific results
    """
    # Clean up stale sessions periodically
    _cleanup_stale_sessions()

    # Handle close action separately (doesn't need active session)
    if action == "close":
        _close_session(session_id)
        return {
            "status": "ok",
            "result": "Browser session closed."
        }

    # Get or create browser session
    session = _get_or_create_session(session_id)

    if 'error' in session:
        return {
            "status": "error",
            "message": session['error']
        }

    page = session['page']

    try:
        # ============================================
        # NAVIGATE — Go to a URL
        # ============================================
        if action == "navigate":
            if not url:
                return {"status": "error", "message": "URL is required for navigate action"}

            # Add protocol if missing
            if not url.startswith('http'):
                url = f'https://{url}'

            response = page.goto(url, wait_until='domcontentloaded')

            # Wait a moment for dynamic content
            page.wait_for_timeout(2000)

            # Get page info
            title = page.title()
            current_url = page.url

            # Get interactive elements
            elements = _get_interactive_elements(page, max_elements=30)

            # Get a summary of visible text (first 2000 chars)
            visible_text = page.inner_text('body')[:2000] if page.query_selector('body') else ''

            return {
                "status": "ok",
                "result": {
                    "url": current_url,
                    "title": title,
                    "status_code": response.status if response else None,
                    "visible_text_preview": visible_text,
                    "interactive_elements": elements,
                    "element_count": len(elements),
                }
            }

        # ============================================
        # CLICK — Click an element
        # ============================================
        elif action == "click":
            if not selector and not text:
                return {"status": "error", "message": "Either 'selector' or 'text' is required for click action"}

            target = selector if selector else f'text="{text}"'

            try:
                # Try clicking with the given selector
                page.click(target, timeout=10000)
            except Exception as click_err:
                # If text-based selector fails, try a more flexible approach
                if not selector and text:
                    try:
                        # Try case-insensitive text match
                        page.click(f'text=/{text}/i', timeout=10000)
                    except Exception:
                        return {
                            "status": "error",
                            "message": f"Could not find element to click: '{text}'. Error: {str(click_err)}"
                        }
                else:
                    return {
                        "status": "error",
                        "message": f"Could not click element '{target}': {str(click_err)}"
                    }

            # Wait for navigation or dynamic content
            page.wait_for_timeout(2000)

            # Return updated page state
            title = page.title()
            current_url = page.url
            elements = _get_interactive_elements(page, max_elements=20)

            return {
                "status": "ok",
                "result": {
                    "clicked": target,
                    "url": current_url,
                    "title": title,
                    "interactive_elements": elements,
                    "element_count": len(elements),
                }
            }

        # ============================================
        # TYPE — Type text into an input field
        # ============================================
        elif action == "type":
            if not selector:
                return {"status": "error", "message": "'selector' is required for type action"}
            if text is None:
                return {"status": "error", "message": "'text' is required for type action"}

            # Clear existing content and type new text
            try:
                page.fill(selector, text, timeout=10000)
            except Exception:
                # Fallback: click then type character by character
                try:
                    page.click(selector, timeout=5000)
                    page.keyboard.press('Control+a')
                    page.keyboard.type(text, delay=50)
                except Exception as type_err:
                    return {
                        "status": "error",
                        "message": f"Could not type into '{selector}': {str(type_err)}"
                    }

            return {
                "status": "ok",
                "result": {
                    "typed": text,
                    "into": selector,
                    "url": page.url,
                }
            }

        # ============================================
        # SCREENSHOT — Capture and analyze the page
        # ============================================
        elif action == "screenshot":
            screenshot_bytes = page.screenshot(type='png', full_page=False)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

            # Analyze with vision model
            analysis = _analyze_screenshot(
                screenshot_b64,
                page.url,
                description
            )

            return {
                "status": "ok",
                "result": {
                    "url": page.url,
                    "title": page.title(),
                    "analysis": analysis,
                    "screenshot_base64": screenshot_b64,
                }
            }

        # ============================================
        # GET_ELEMENTS — List interactive elements
        # ============================================
        elif action == "get_elements":
            elements = _get_interactive_elements(page, max_elements=50)

            return {
                "status": "ok",
                "result": {
                    "url": page.url,
                    "title": page.title(),
                    "interactive_elements": elements,
                    "element_count": len(elements),
                }
            }

        # ============================================
        # SELECT — Choose from a dropdown
        # ============================================
        elif action == "select":
            if not selector:
                return {"status": "error", "message": "'selector' is required for select action"}
            if not value:
                return {"status": "error", "message": "'value' is required for select action"}

            try:
                page.select_option(selector, value, timeout=10000)
            except Exception as sel_err:
                # Try selecting by visible text label
                try:
                    page.select_option(selector, label=value, timeout=10000)
                except Exception:
                    return {
                        "status": "error",
                        "message": f"Could not select '{value}' in '{selector}': {str(sel_err)}"
                    }

            page.wait_for_timeout(1000)

            return {
                "status": "ok",
                "result": {
                    "selected": value,
                    "in_element": selector,
                    "url": page.url,
                }
            }

        # ============================================
        # SCROLL — Scroll the page
        # ============================================
        elif action == "scroll":
            scroll_amount = 300 * amount  # pixels
            if direction == "up":
                scroll_amount = -scroll_amount

            page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            page.wait_for_timeout(500)

            return {
                "status": "ok",
                "result": {
                    "scrolled": direction,
                    "amount": amount,
                    "url": page.url,
                }
            }

        # ============================================
        # BACK — Navigate back
        # ============================================
        elif action == "back":
            page.go_back(wait_until='domcontentloaded')
            page.wait_for_timeout(1500)

            title = page.title()
            current_url = page.url
            elements = _get_interactive_elements(page, max_elements=20)

            return {
                "status": "ok",
                "result": {
                    "url": current_url,
                    "title": title,
                    "interactive_elements": elements,
                    "element_count": len(elements),
                }
            }

        # ============================================
        # GET_TEXT — Get all visible text
        # ============================================
        elif action == "get_text":
            visible_text = page.inner_text('body') if page.query_selector('body') else ''

            # Truncate to save context
            max_chars = kwargs.get('max_chars', 5000)
            truncated = len(visible_text) > max_chars

            return {
                "status": "ok",
                "result": {
                    "url": page.url,
                    "title": page.title(),
                    "text": visible_text[:max_chars],
                    "truncated": truncated,
                    "total_chars": len(visible_text),
                }
            }

        else:
            return {
                "status": "error",
                "message": f"Unknown action: {action}. Valid actions: navigate, click, type, screenshot, get_elements, select, scroll, back, get_text, close"
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Browser action '{action}' failed: {str(e)}",
            "url": page.url if page else None,
        }


# ============================================
# STANDALONE TEST
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🌐 BROWSER TOOL TEST")
    print("=" * 60)

    # Test navigate
    result = browser_tool(
        action="navigate",
        url="https://example.com",
        session_id="test"
    )
    print(f"\nNavigate result:")
    print(json.dumps(result, indent=2, default=str)[:500])

    # Test get_text
    result = browser_tool(
        action="get_text",
        session_id="test"
    )
    print(f"\nGet text result:")
    print(json.dumps(result, indent=2, default=str)[:500])

    # Close session
    result = browser_tool(action="close", session_id="test")
    print(f"\nClose result: {result}")

    print("\n✅ Browser Tool test complete!")
    print("=" * 60)
