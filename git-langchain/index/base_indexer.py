"""
Base indexer classes for Git Odyssey
Implements hybrid indexing: vector (semantic) + keyword/field (exact, time, path)
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import json


@dataclass
class SearchResult:
    """Result from a search query"""

    content: str
    metadata: Dict[str, Any]
    score: float
    source_type: str  # "hunk", "file", "commit", "pr"
    source_id: str  # SHA or ID


@dataclass
class IndexDocument:
    """Document to be indexed"""

    id: str
    content: str
    metadata: Dict[str, Any]
    embeddings: Optional[List[float]] = None
    timestamp: Optional[datetime] = None


class BaseVectorIndexer(ABC):
    """Abstract base class for vector indexing"""

    @abstractmethod
    def add_documents(self, documents: List[IndexDocument]) -> None:
        """Add documents to the vector index"""
        pass

    @abstractmethod
    def search(
        self, query: str, top_k: int = 10, filters: Optional[Dict] = None
    ) -> List[SearchResult]:
        """Search for similar documents using vector similarity"""
        pass

    @abstractmethod
    def delete_documents(self, document_ids: List[str]) -> None:
        """Delete documents from the index"""
        pass

    @abstractmethod
    def get_document(self, document_id: str) -> Optional[IndexDocument]:
        """Get a specific document by ID"""
        pass


class BaseKeywordIndexer(ABC):
    """Abstract base class for keyword/field indexing"""

    @abstractmethod
    def add_documents(self, documents: List[IndexDocument]) -> None:
        """Add documents to the keyword index"""
        pass

    @abstractmethod
    def search(self, query: str, filters: Optional[Dict] = None) -> List[SearchResult]:
        """Search for documents using keyword matching and filters"""
        pass

    @abstractmethod
    def delete_documents(self, document_ids: List[str]) -> None:
        """Delete documents from the index"""
        pass

    @abstractmethod
    def get_document(self, document_id: str) -> Optional[IndexDocument]:
        """Get a specific document by ID"""
        pass


class HybridIndexer:
    """Combines vector and keyword indexing for hybrid search"""

    def __init__(
        self, vector_indexer: BaseVectorIndexer, keyword_indexer: BaseKeywordIndexer
    ):
        self.vector_indexer = vector_indexer
        self.keyword_indexer = keyword_indexer

    def add_documents(self, documents: List[IndexDocument]) -> None:
        """Add documents to both indexes"""
        self.vector_indexer.add_documents(documents)
        self.keyword_indexer.add_documents(documents)

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None,
        search_type: str = "hybrid",
    ) -> List[SearchResult]:
        """
        Perform hybrid search combining vector and keyword search

        Args:
            query: Search query
            top_k: Number of results to return
            filters: Filters to apply (path, date, author, etc.)
            search_type: "vector", "keyword", or "hybrid"

        Returns:
            List of search results ranked by relevance
        """
        if search_type == "vector":
            return self.vector_indexer.search(query, top_k, filters)
        elif search_type == "keyword":
            return self.keyword_indexer.search(query, filters)[:top_k]
        else:  # hybrid
            return self._hybrid_search(query, top_k, filters)

    def _hybrid_search(
        self, query: str, top_k: int, filters: Optional[Dict]
    ) -> List[SearchResult]:
        """Combine vector and keyword search results"""

        # Get results from both indexes
        vector_results = self.vector_indexer.search(query, top_k * 2, filters)
        keyword_results = self.keyword_indexer.search(query, filters)

        # Combine and deduplicate results
        combined_results = {}

        # Add vector results with semantic scoring
        for result in vector_results:
            doc_id = result.metadata.get("id", result.source_id)
            if doc_id not in combined_results:
                combined_results[doc_id] = result
                # Boost score for semantic relevance
                result.score *= 1.2
            else:
                # Combine scores if document appears in both
                combined_results[doc_id].score = max(
                    combined_results[doc_id].score, result.score
                )

        # Add keyword results with exact match scoring
        for result in keyword_results:
            doc_id = result.metadata.get("id", result.source_id)
            if doc_id not in combined_results:
                combined_results[doc_id] = result
                # Boost score for exact matches
                result.score *= 1.1
            else:
                # Boost existing result for keyword match
                combined_results[doc_id].score *= 1.1

        # Sort by combined score and return top_k
        sorted_results = sorted(
            combined_results.values(), key=lambda x: x.score, reverse=True
        )

        return sorted_results[:top_k]

    def delete_documents(self, document_ids: List[str]) -> None:
        """Delete documents from both indexes"""
        self.vector_indexer.delete_documents(document_ids)
        self.keyword_indexer.delete_documents(document_ids)

    def get_document(self, document_id: str) -> Optional[IndexDocument]:
        """Get document from either index (prefer vector index)"""
        doc = self.vector_indexer.get_document(document_id)
        if doc is None:
            doc = self.keyword_indexer.get_document(document_id)
        return doc

