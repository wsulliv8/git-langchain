"""
Keyword indexer implementation using SQLite
Provides exact match and field-based filtering capabilities
"""

from typing import Dict, List, Optional, Any
import sqlite3
import json
import re
from datetime import datetime
from .base_indexer import BaseKeywordIndexer, IndexDocument, SearchResult


class SQLiteKeywordIndexer(BaseKeywordIndexer):
    """Keyword indexer using SQLite for exact matches and filtering"""

    def __init__(self, db_path: str = "./git_odyssey_keyword.db"):
        """
        Initialize the SQLite keyword indexer

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the SQLite database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Create documents table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    timestamp TEXT,
                    source_type TEXT,
                    source_id TEXT,
                    path TEXT,
                    author TEXT,
                    intent_tags TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create full-text search table
            cursor.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    id,
                    content,
                    metadata,
                    source_type,
                    path,
                    author,
                    intent_tags,
                    content='documents',
                    content_rowid='rowid'
                )
            """
            )

            # Create indexes for common queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_source_type 
                ON documents(source_type)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_source_id 
                ON documents(source_id)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_path 
                ON documents(path)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_author 
                ON documents(author)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_timestamp 
                ON documents(timestamp)
            """
            )

            conn.commit()

    def add_documents(self, documents: List[IndexDocument]) -> None:
        """Add documents to the keyword index"""
        if not documents:
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for doc in documents:
                try:
                    # Prepare metadata as JSON string
                    metadata_json = json.dumps(doc.metadata)

                    # Extract common fields from metadata
                    source_type = doc.metadata.get("source_type", "unknown")
                    source_id = doc.metadata.get("source_id", doc.id)
                    path = doc.metadata.get("path", doc.metadata.get("file_path", ""))
                    author = (
                        doc.metadata.get("author", {}).get("name", "")
                        if isinstance(doc.metadata.get("author"), dict)
                        else doc.metadata.get("author", "")
                    )
                    intent_tags = (
                        ",".join(doc.metadata.get("intent_tags", []))
                        if isinstance(doc.metadata.get("intent_tags"), list)
                        else str(doc.metadata.get("intent_tags", ""))
                    )
                    timestamp = doc.timestamp.isoformat() if doc.timestamp else None

                    # Insert into main documents table
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO documents 
                        (id, content, metadata, timestamp, source_type, source_id, path, author, intent_tags)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            doc.id,
                            doc.content,
                            metadata_json,
                            timestamp,
                            source_type,
                            source_id,
                            path,
                            author,
                            intent_tags,
                        ),
                    )

                    # Insert into FTS table
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO documents_fts 
                        (id, content, metadata, source_type, path, author, intent_tags)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            doc.id,
                            doc.content,
                            metadata_json,
                            source_type,
                            path,
                            author,
                            intent_tags,
                        ),
                    )

                except Exception as e:
                    print(f"Error adding document {doc.id}: {str(e)}")
                    continue

            conn.commit()
            print(f"Added {len(documents)} documents to keyword index")

    def search(self, query: str, filters: Optional[Dict] = None) -> List[SearchResult]:
        """Search for documents using keyword matching and filters"""

        # Build the search query
        where_conditions = []
        params = []

        # Full-text search on content
        if query.strip():
            # Use FTS5 for full-text search
            fts_query = self._prepare_fts_query(query)
            where_conditions.append(f"documents_fts MATCH ?")
            params.append(fts_query)

        # Apply filters
        if filters:
            filter_conditions, filter_params = self._build_filter_conditions(filters)
            where_conditions.extend(filter_conditions)
            params.extend(filter_params)

        # Build final query
        if where_conditions:
            where_clause = " AND ".join(where_conditions)
            sql = f"""
                SELECT d.id, d.content, d.metadata, 
                       d.source_type, d.source_id,
                       documents_fts.rank
                FROM documents d
                JOIN documents_fts ON d.id = documents_fts.id
                WHERE {where_clause}
                ORDER BY documents_fts.rank, d.timestamp DESC
            """
        else:
            # No search query, just return recent documents
            sql = """
                SELECT id, content, metadata, source_type, source_id, 0 as rank
                FROM documents
                ORDER BY timestamp DESC
                LIMIT 100
            """

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                results = cursor.fetchall()

                search_results = []
                for row in results:
                    doc_id, content, metadata_json, source_type, source_id, rank = row

                    # Parse metadata
                    try:
                        metadata = json.loads(metadata_json)
                    except:
                        metadata = {}

                    # Convert rank to score (FTS5 rank is lower for better matches)
                    score = max(0.0, 1.0 - (rank / 100.0)) if rank > 0 else 0.5

                    search_result = SearchResult(
                        content=content,
                        metadata=metadata,
                        score=score,
                        source_type=source_type,
                        source_id=source_id,
                    )
                    search_results.append(search_result)

                return search_results

        except Exception as e:
            print(f"Error searching keyword index: {str(e)}")
            return []

    def delete_documents(self, document_ids: List[str]) -> None:
        """Delete documents from the index"""
        if not document_ids:
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Delete from both tables
            placeholders = ",".join("?" * len(document_ids))

            cursor.execute(
                f"""
                DELETE FROM documents WHERE id IN ({placeholders})
            """,
                document_ids,
            )

            cursor.execute(
                f"""
                DELETE FROM documents_fts WHERE id IN ({placeholders})
            """,
                document_ids,
            )

            conn.commit()
            print(f"Deleted {len(document_ids)} documents from keyword index")

    def get_document(self, document_id: str) -> Optional[IndexDocument]:
        """Get a specific document by ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, content, metadata, timestamp
                FROM documents
                WHERE id = ?
            """,
                (document_id,),
            )

            result = cursor.fetchone()
            if result:
                doc_id, content, metadata_json, timestamp = result

                # Parse metadata
                try:
                    metadata = json.loads(metadata_json)
                except:
                    metadata = {}

                # Parse timestamp
                parsed_timestamp = None
                if timestamp:
                    try:
                        parsed_timestamp = datetime.fromisoformat(timestamp)
                    except:
                        pass

                return IndexDocument(
                    id=doc_id,
                    content=content,
                    metadata=metadata,
                    timestamp=parsed_timestamp,
                )

            return None

    def _prepare_fts_query(self, query: str) -> str:
        """Prepare query for FTS5 full-text search"""
        # Escape special characters and add quotes for phrase matching
        escaped_query = query.replace('"', '""')

        # If query contains multiple words, treat as phrase
        if " " in query.strip():
            return f'"{escaped_query}"'
        else:
            return escaped_query

    def _build_filter_conditions(self, filters: Dict) -> tuple[List[str], List[Any]]:
        """Build SQL WHERE conditions from filters"""
        conditions = []
        params = []

        for key, value in filters.items():
            if key == "source_type":
                if isinstance(value, str):
                    conditions.append("source_type = ?")
                    params.append(value)
                elif isinstance(value, list):
                    placeholders = ",".join("?" * len(value))
                    conditions.append(f"source_type IN ({placeholders})")
                    params.extend(value)

            elif key == "source_id":
                conditions.append("source_id = ?")
                params.append(value)

            elif key == "path":
                if isinstance(value, str):
                    conditions.append("path LIKE ?")
                    params.append(f"%{value}%")
                elif isinstance(value, list):
                    path_conditions = []
                    for path in value:
                        path_conditions.append("path LIKE ?")
                        params.append(f"%{path}%")
                    conditions.append(f"({' OR '.join(path_conditions)})")

            elif key == "author":
                conditions.append("author = ?")
                params.append(value)

            elif key == "intent_tags":
                if isinstance(value, list):
                    tag_conditions = []
                    for tag in value:
                        tag_conditions.append("intent_tags LIKE ?")
                        params.append(f"%{tag}%")
                    conditions.append(f"({' OR '.join(tag_conditions)})")
                else:
                    conditions.append("intent_tags LIKE ?")
                    params.append(f"%{value}%")

            elif key == "date_from":
                conditions.append("timestamp >= ?")
                params.append(value)

            elif key == "date_to":
                conditions.append("timestamp <= ?")
                params.append(value)

        return conditions, params

    def get_database_stats(self) -> Dict[str, Any]:
        """Get statistics about the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get document count
            cursor.execute("SELECT COUNT(*) FROM documents")
            doc_count = cursor.fetchone()[0]

            # Get counts by source type
            cursor.execute(
                """
                SELECT source_type, COUNT(*) 
                FROM documents 
                GROUP BY source_type
            """
            )
            type_counts = dict(cursor.fetchall())

            # Get recent activity
            cursor.execute(
                """
                SELECT COUNT(*) 
                FROM documents 
                WHERE created_at >= datetime('now', '-7 days')
            """
            )
            recent_count = cursor.fetchone()[0]

            return {
                "total_documents": doc_count,
                "documents_by_type": type_counts,
                "recent_documents": recent_count,
                "database_path": self.db_path,
            }

    def clear_database(self) -> None:
        """Clear all documents from the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM documents")
            cursor.execute("DELETE FROM documents_fts")

            conn.commit()
            print("Cleared all documents from keyword index")

