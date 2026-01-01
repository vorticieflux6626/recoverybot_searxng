#!/usr/bin/env python3
"""
Local Documentation Search with Meilisearch

Indexes and searches local FANUC/industrial documentation:
- PDF manuals and guides
- Text files and markdown
- Extracted content from technical documents

Integrates with SearXNG to provide unified search results from both
web engines and local document collections.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Optional imports
try:
    import meilisearch
    MEILISEARCH_AVAILABLE = True
except ImportError:
    MEILISEARCH_AVAILABLE = False
    logger.warning("meilisearch not available - install with: pip install meilisearch")

try:
    import pypdf
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("pypdf not available - PDF indexing disabled")


@dataclass
class DocumentConfig:
    """Configuration for document search."""
    meilisearch_url: str = "http://localhost:7700"
    meilisearch_key: str = "recoverybot_meili_key"
    index_name: str = "fanuc_docs"
    documents_path: str = "./documents"

    # Indexing settings
    chunk_size: int = 1000  # Characters per chunk
    chunk_overlap: int = 100  # Overlap between chunks
    supported_extensions: tuple = (".pdf", ".txt", ".md", ".rst")


@dataclass
class DocumentChunk:
    """A chunk of a document for indexing."""
    id: str
    file_path: str
    file_name: str
    title: str
    content: str
    page_number: Optional[int] = None
    chunk_index: int = 0
    total_chunks: int = 1
    file_type: str = "text"
    indexed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "title": self.title,
            "content": self.content,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "file_type": self.file_type,
            "indexed_at": self.indexed_at,
        }


@dataclass
class SearchResult:
    """A search result from local docs."""
    title: str
    content: str
    file_path: str
    file_name: str
    page_number: Optional[int]
    score: float
    highlights: Dict[str, List[str]] = field(default_factory=dict)

    def to_searxng_format(self) -> Dict[str, Any]:
        """Convert to SearXNG-compatible result format."""
        # Create a file:// URL for local documents
        url = f"file://{os.path.abspath(self.file_path)}"
        if self.page_number:
            url += f"#page={self.page_number}"

        return {
            "url": url,
            "title": self.title,
            "content": self.content[:300] + "..." if len(self.content) > 300 else self.content,
            "engine": "local_docs",
            "score": self.score,
            "category": "files",
            "metadata": {
                "file_name": self.file_name,
                "page_number": self.page_number,
                "highlights": self.highlights,
            }
        }


class LocalDocsSearch:
    """
    Search and index local documentation using Meilisearch.

    Provides:
    - PDF text extraction and indexing
    - Chunked document storage for better search
    - Typo-tolerant search with highlighting
    - Integration with SearXNG results
    """

    def __init__(self, config: Optional[DocumentConfig] = None):
        self.config = config or DocumentConfig()
        self._client: Optional[meilisearch.Client] = None
        self._index = None
        self._initialized = False
        self._stats = {
            "total_documents": 0,
            "total_chunks": 0,
            "total_searches": 0,
            "avg_search_time_ms": 0.0,
        }

    async def initialize(self) -> bool:
        """Initialize Meilisearch connection and index."""
        if self._initialized:
            return True

        if not MEILISEARCH_AVAILABLE:
            logger.error("Meilisearch client not available")
            return False

        try:
            self._client = meilisearch.Client(
                self.config.meilisearch_url,
                self.config.meilisearch_key
            )

            # Check connection
            self._client.health()

            # Get or create index
            try:
                self._index = self._client.get_index(self.config.index_name)
            except meilisearch.errors.MeilisearchApiError:
                # Create index if it doesn't exist
                task = self._client.create_index(
                    self.config.index_name,
                    {"primaryKey": "id"}
                )
                self._client.wait_for_task(task.task_uid)
                self._index = self._client.get_index(self.config.index_name)

            # Configure searchable attributes
            self._index.update_searchable_attributes([
                "title",
                "content",
                "file_name",
            ])

            # Configure filterable attributes
            self._index.update_filterable_attributes([
                "file_type",
                "file_name",
            ])

            # Update stats
            stats = self._index.get_stats()
            self._stats["total_documents"] = stats.number_of_documents

            self._initialized = True
            logger.info(f"LocalDocsSearch initialized: {stats.number_of_documents} documents")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Meilisearch: {e}")
            return False

    def _generate_chunk_id(self, file_path: str, chunk_index: int) -> str:
        """Generate unique ID for a document chunk."""
        content = f"{file_path}:{chunk_index}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _extract_pdf_text(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract text from PDF file, page by page."""
        if not PDF_AVAILABLE:
            logger.warning(f"Cannot extract PDF: {file_path} (pypdf not installed)")
            return []

        pages = []
        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                for page_num, page in enumerate(reader.pages, start=1):
                    text = page.extract_text()
                    if text and text.strip():
                        pages.append({
                            "page_number": page_num,
                            "content": text.strip(),
                        })
        except Exception as e:
            logger.error(f"Failed to extract PDF {file_path}: {e}")

        return pages

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.config.chunk_size
            chunk = text[start:end]

            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk.rfind(".")
                last_newline = chunk.rfind("\n")
                break_point = max(last_period, last_newline)
                if break_point > self.config.chunk_size // 2:
                    chunk = chunk[:break_point + 1]
                    end = start + break_point + 1

            chunks.append(chunk.strip())
            start = end - self.config.chunk_overlap

        return chunks

    async def index_file(self, file_path: str) -> int:
        """
        Index a single file.

        Returns number of chunks indexed.
        """
        if not self._initialized:
            await self.initialize()

        path = Path(file_path)
        if not path.exists():
            logger.warning(f"File not found: {file_path}")
            return 0

        if path.suffix.lower() not in self.config.supported_extensions:
            logger.debug(f"Unsupported file type: {file_path}")
            return 0

        chunks = []
        file_name = path.name
        title = path.stem.replace("_", " ").replace("-", " ").title()

        # Extract content based on file type
        if path.suffix.lower() == ".pdf":
            pages = self._extract_pdf_text(file_path)
            for page in pages:
                text_chunks = self._chunk_text(page["content"])
                for i, chunk_text in enumerate(text_chunks):
                    chunk = DocumentChunk(
                        id=self._generate_chunk_id(file_path, len(chunks)),
                        file_path=str(path.absolute()),
                        file_name=file_name,
                        title=f"{title} - Page {page['page_number']}",
                        content=chunk_text,
                        page_number=page["page_number"],
                        chunk_index=i,
                        total_chunks=len(text_chunks),
                        file_type="pdf",
                    )
                    chunks.append(chunk.to_dict())
        else:
            # Text file
            try:
                content = path.read_text(encoding="utf-8")
                text_chunks = self._chunk_text(content)
                for i, chunk_text in enumerate(text_chunks):
                    chunk = DocumentChunk(
                        id=self._generate_chunk_id(file_path, i),
                        file_path=str(path.absolute()),
                        file_name=file_name,
                        title=title,
                        content=chunk_text,
                        chunk_index=i,
                        total_chunks=len(text_chunks),
                        file_type=path.suffix.lower()[1:],
                    )
                    chunks.append(chunk.to_dict())
            except Exception as e:
                logger.error(f"Failed to read {file_path}: {e}")
                return 0

        # Index chunks
        if chunks:
            try:
                task = self._index.add_documents(chunks)
                self._client.wait_for_task(task.task_uid)
                self._stats["total_chunks"] += len(chunks)
                logger.info(f"Indexed {len(chunks)} chunks from {file_name}")
            except Exception as e:
                logger.error(f"Failed to index {file_path}: {e}")
                return 0

        return len(chunks)

    async def index_directory(self, directory: Optional[str] = None) -> Dict[str, int]:
        """
        Index all supported files in a directory.

        Returns dict mapping file paths to chunk counts.
        """
        if not self._initialized:
            await self.initialize()

        doc_dir = Path(directory or self.config.documents_path)
        if not doc_dir.exists():
            logger.warning(f"Documents directory not found: {doc_dir}")
            return {}

        results = {}
        for ext in self.config.supported_extensions:
            for file_path in doc_dir.rglob(f"*{ext}"):
                count = await self.index_file(str(file_path))
                if count > 0:
                    results[str(file_path)] = count

        self._stats["total_documents"] = len(results)
        return results

    async def search(
        self,
        query: str,
        limit: int = 10,
        file_type: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Search indexed documents.

        Args:
            query: Search query
            limit: Maximum results
            file_type: Filter by file type (pdf, txt, md)

        Returns:
            List of SearchResult objects
        """
        if not self._initialized:
            await self.initialize()

        if not self._index:
            return []

        start_time = time.time()

        try:
            # Build search options
            options = {
                "limit": limit,
                "attributesToHighlight": ["content", "title"],
                "highlightPreTag": "**",
                "highlightPostTag": "**",
            }

            if file_type:
                options["filter"] = f"file_type = {file_type}"

            # Execute search
            response = self._index.search(query, options)

            # Update stats
            search_time = (time.time() - start_time) * 1000
            self._stats["total_searches"] += 1
            self._stats["avg_search_time_ms"] = (
                (self._stats["avg_search_time_ms"] * (self._stats["total_searches"] - 1) + search_time)
                / self._stats["total_searches"]
            )

            # Convert to SearchResult
            results = []
            for hit in response["hits"]:
                highlights = {}
                if "_formatted" in hit:
                    if "content" in hit["_formatted"]:
                        highlights["content"] = [hit["_formatted"]["content"]]
                    if "title" in hit["_formatted"]:
                        highlights["title"] = [hit["_formatted"]["title"]]

                result = SearchResult(
                    title=hit.get("title", "Untitled"),
                    content=hit.get("content", ""),
                    file_path=hit.get("file_path", ""),
                    file_name=hit.get("file_name", ""),
                    page_number=hit.get("page_number"),
                    score=1.0 - (results.index(result) * 0.1 if results else 0),
                    highlights=highlights,
                )
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def search_for_searxng(
        self,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search and return results in SearXNG-compatible format.

        For integration with the main search pipeline.
        """
        results = await self.search(query, limit=limit)
        return [r.to_searxng_format() for r in results]

    def get_stats(self) -> Dict[str, Any]:
        """Get indexing and search statistics."""
        return self._stats.copy()

    async def clear_index(self):
        """Clear all indexed documents."""
        if self._index:
            try:
                task = self._index.delete_all_documents()
                self._client.wait_for_task(task.task_uid)
                self._stats["total_documents"] = 0
                self._stats["total_chunks"] = 0
                logger.info("Index cleared")
            except Exception as e:
                logger.error(f"Failed to clear index: {e}")


# Singleton instance
_local_docs: Optional[LocalDocsSearch] = None


def get_local_docs(config: Optional[DocumentConfig] = None) -> LocalDocsSearch:
    """Get or create the local docs search singleton."""
    global _local_docs
    if _local_docs is None:
        _local_docs = LocalDocsSearch(config)
    return _local_docs


async def example_usage():
    """Demonstrate local docs search."""
    docs = get_local_docs()

    print("=== Local Docs Search Demo ===")

    # Initialize
    if not await docs.initialize():
        print("Failed to initialize - is Meilisearch running?")
        return

    # Index documents directory
    print("\nIndexing documents...")
    results = await docs.index_directory()
    print(f"Indexed {len(results)} files, {docs._stats['total_chunks']} chunks")

    # Search
    print("\nSearching for 'servo alarm'...")
    search_results = await docs.search("servo alarm", limit=5)
    for i, result in enumerate(search_results, 1):
        print(f"  {i}. {result.title}")
        print(f"     File: {result.file_name}")
        print(f"     Content: {result.content[:100]}...")

    # Get stats
    print(f"\nStats: {docs.get_stats()}")


if __name__ == "__main__":
    asyncio.run(example_usage())
