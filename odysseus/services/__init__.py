# services/__init__.py
"""
Service layer — plug-in capabilities for the chat core.

Each service:
- Does one thing well
- Exposes a clean async interface
- Can run in-process or as a standalone HTTP service
"""

from .docs import DocChunk, DocsService, IndexResult
from .memory import Memory, MemorySearchResult, MemoryService
from .research import ResearchResult, ResearchService, ResearchSource
from .search import SearchResponse, SearchResult, SearchService
from .shell import ShellResult, ShellService

__all__ = [
    "DocChunk",
    # Docs
    "DocsService",
    "IndexResult",
    "Memory",
    "MemorySearchResult",
    # Memory
    "MemoryService",
    "ResearchResult",
    # Research
    "ResearchService",
    "ResearchSource",
    "SearchResponse",
    "SearchResult",
    # Search
    "SearchService",
    "ShellResult",
    # Shell
    "ShellService",
]
