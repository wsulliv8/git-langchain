"""
Main indexer orchestrator for Git Odyssey
Combines summarization results with hybrid indexing (vector + keyword)
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from .base_indexer import HybridIndexer, IndexDocument, SearchResult
from .vector_indexer import ChromaVectorIndexer
from .keyword_indexer import SQLiteKeywordIndexer
from ..summarize.base_summarizer import SummaryResult


class GitIndexer:
    """Main orchestrator for indexing Git Odyssey summaries"""

    def __init__(
        self,
        vector_db_path: str = "./chroma_db",
        keyword_db_path: str = "./git_odyssey_keyword.db",
        collection_name: str = "git_odyssey",
        embedding_model: str = "text-embedding-ada-002",
    ):
        """
        Initialize the Git indexer with hybrid search capabilities

        Args:
            vector_db_path: Path for ChromaDB storage
            keyword_db_path: Path for SQLite keyword storage
            collection_name: Name for ChromaDB collection
            embedding_model: OpenAI embedding model to use
        """
        # Initialize vector indexer
        self.vector_indexer = ChromaVectorIndexer(
            collection_name=collection_name,
            persist_directory=vector_db_path,
            embedding_model=embedding_model,
        )

        # Initialize keyword indexer
        self.keyword_indexer = SQLiteKeywordIndexer(db_path=keyword_db_path)

        # Create hybrid indexer
        self.hybrid_indexer = HybridIndexer(
            vector_indexer=self.vector_indexer, keyword_indexer=self.keyword_indexer
        )

    def index_summaries(self, summary_data: Dict[str, Any]) -> None:
        """
        Index a single commit's summary data

        Args:
            summary_data: Dict containing commit, file, and hunk summaries
        """
        documents = []

        # Extract commit summary
        commit_summary = summary_data.get("commit_summary", {})
        if commit_summary:
            commit_doc = IndexDocument(
                id=f"commit_{summary_data['commit']['sha']}",
                content=commit_summary.get("content", ""),
                metadata={
                    **commit_summary.get("metadata", {}),
                    "source_type": "commit",
                    "source_id": summary_data["commit"]["sha"],
                    "intent_tags": commit_summary.get("intent_tags", []),
                    "confidence": commit_summary.get("confidence", 0.0),
                },
                timestamp=datetime.now(),
            )
            documents.append(commit_doc)

        # Extract file summaries
        for file_summary_data in summary_data.get("file_summaries", []):
            file_summary = file_summary_data.get("summary", {})
            file_delta = file_summary_data.get("file_delta", {})

            if file_summary:
                file_doc = IndexDocument(
                    id=f"file_{file_delta.get('sha', '')}_{file_delta.get('pathNew', '')}",
                    content=file_summary.get("content", ""),
                    metadata={
                        **file_summary.get("metadata", {}),
                        **file_delta,
                        "source_type": "file",
                        "source_id": file_delta.get("sha", ""),
                        "intent_tags": file_summary.get("intent_tags", []),
                        "confidence": file_summary.get("confidence", 0.0),
                    },
                    timestamp=datetime.now(),
                )
                documents.append(file_doc)

        # Extract hunk summaries
        for hunk_summary_data in summary_data.get("hunk_summaries", []):
            hunk_summary = hunk_summary_data.get("summary", {})
            hunk_data = hunk_summary_data.get("hunk", {})

            if hunk_summary:
                hunk_doc = IndexDocument(
                    id=f"hunk_{hunk_data.get('sha', '')}_{hunk_data.get('pathNew', '')}_{hunk_data.get('startNew', 0)}",
                    content=hunk_summary.get("content", ""),
                    metadata={
                        **hunk_summary.get("metadata", {}),
                        **hunk_data,
                        "source_type": "hunk",
                        "source_id": hunk_data.get("sha", ""),
                        "intent_tags": hunk_summary.get("intent_tags", []),
                        "confidence": hunk_summary.get("confidence", 0.0),
                    },
                    timestamp=datetime.now(),
                )
                documents.append(hunk_doc)

        # Add documents to hybrid index
        if documents:
            self.hybrid_indexer.add_documents(documents)
            print(
                f"Indexed {len(documents)} documents for commit {summary_data['commit']['sha'][:8]}"
            )

    def index_summaries_batch(self, summaries_data: List[Dict[str, Any]]) -> None:
        """
        Index multiple commits' summary data in batch

        Args:
            summaries_data: List of summary data dicts
        """
        total_documents = 0

        for i, summary_data in enumerate(summaries_data):
            print(
                f"Indexing commit {i+1}/{len(summaries_data)}: {summary_data['commit']['sha'][:8]}"
            )
            self.index_summaries(summary_data)

            # Count documents added
            commit_docs = 1  # commit summary
            commit_docs += len(summary_data.get("file_summaries", []))
            commit_docs += len(summary_data.get("hunk_summaries", []))
            total_documents += commit_docs

        print(
            f"Indexed {total_documents} total documents from {len(summaries_data)} commits"
        )

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None,
        search_type: str = "hybrid",
    ) -> List[SearchResult]:
        """
        Search across indexed summaries

        Args:
            query: Search query
            top_k: Number of results to return
            filters: Filters to apply (source_type, path, author, date_range, etc.)
            search_type: "vector", "keyword", or "hybrid"

        Returns:
            List of search results
        """
        return self.hybrid_indexer.search(query, top_k, filters, search_type)

    def search_by_intent(
        self, intent_tags: List[str], top_k: int = 10
    ) -> List[SearchResult]:
        """
        Search for documents with specific intent tags

        Args:
            intent_tags: List of intent tags to search for
            top_k: Number of results to return

        Returns:
            List of search results
        """
        filters = {"intent_tags": intent_tags}
        return self.search("", top_k, filters, "keyword")

    def search_by_author(self, author: str, top_k: int = 10) -> List[SearchResult]:
        """
        Search for documents by author

        Args:
            author: Author name to search for
            top_k: Number of results to return

        Returns:
            List of search results
        """
        filters = {"author": author}
        return self.search("", top_k, filters, "keyword")

    def search_by_path(self, path_pattern: str, top_k: int = 10) -> List[SearchResult]:
        """
        Search for documents by file path pattern

        Args:
            path_pattern: Path pattern to search for
            top_k: Number of results to return

        Returns:
            List of search results
        """
        filters = {"path": path_pattern}
        return self.search("", top_k, filters, "keyword")

    def search_by_date_range(
        self, date_from: str, date_to: str, top_k: int = 10
    ) -> List[SearchResult]:
        """
        Search for documents within a date range

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)
            top_k: Number of results to return

        Returns:
            List of search results
        """
        filters = {"date_from": date_from, "date_to": date_to}
        return self.search("", top_k, filters, "keyword")

    def get_commit_summaries(self, commit_sha: str) -> List[SearchResult]:
        """
        Get all summaries related to a specific commit

        Args:
            commit_sha: Commit SHA to search for

        Returns:
            List of search results for the commit
        """
        filters = {"source_id": commit_sha}
        return self.search("", 100, filters, "keyword")

    def get_file_summaries(self, file_path: str) -> List[SearchResult]:
        """
        Get all summaries related to a specific file

        Args:
            file_path: File path to search for

        Returns:
            List of search results for the file
        """
        filters = {"path": file_path}
        return self.search("", 100, filters, "keyword")

    def delete_commit(self, commit_sha: str) -> None:
        """
        Delete all summaries related to a specific commit

        Args:
            commit_sha: Commit SHA to delete
        """
        # Find all document IDs related to this commit
        commit_results = self.get_commit_summaries(commit_sha)
        document_ids = [
            result.metadata.get("id")
            for result in commit_results
            if result.metadata.get("id")
        ]

        if document_ids:
            self.hybrid_indexer.delete_documents(document_ids)
            print(f"Deleted {len(document_ids)} documents for commit {commit_sha[:8]}")

    def get_index_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the index"""
        vector_stats = self.vector_indexer.get_collection_stats()
        keyword_stats = self.keyword_indexer.get_database_stats()

        return {
            "vector_index": vector_stats,
            "keyword_index": keyword_stats,
            "total_documents": keyword_stats.get("total_documents", 0),
            "documents_by_type": keyword_stats.get("documents_by_type", {}),
            "recent_activity": keyword_stats.get("recent_documents", 0),
        }

    def clear_all_indexes(self) -> None:
        """Clear all indexes (use with caution!)"""
        self.vector_indexer.clear_collection()
        self.keyword_indexer.clear_database()
        print("Cleared all indexes")

    def export_search_results(
        self, results: List[SearchResult], format: str = "json"
    ) -> str:
        """Export search results in specified format"""
        if format == "json":
            import json

            export_data = []
            for result in results:
                export_data.append(
                    {
                        "content": result.content,
                        "metadata": result.metadata,
                        "score": result.score,
                        "source_type": result.source_type,
                        "source_id": result.source_id,
                    }
                )
            return json.dumps(export_data, indent=2)
        else:
            # Plain text format
            lines = []
            for i, result in enumerate(results, 1):
                lines.append(f"Result {i} (Score: {result.score:.3f})")
                lines.append(f"Type: {result.source_type}")
                lines.append(f"Source: {result.source_id}")
                lines.append(f"Content: {result.content}")
                lines.append("-" * 50)
            return "\n".join(lines)

