"""Web-related MCP tools: search and fetch web pages."""

import requests
import html2text  # type: ignore[import-not-found]
from ddgs import DDGS  # type: ignore[import-not-found]

from .mcp_instance import mcp

h2t = html2text.HTML2Text()
h2t.ignore_links = False
h2t.ignore_images = True


@mcp.tool()
def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search the web"""
    results = DDGS().text(query, max_results=int(max_results))
    return list(results) if results else []


@mcp.tool()
def read_web_page(url: str) -> str:
    """Fetch and convert web page to text"""
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return str(h2t.handle(response.text))
