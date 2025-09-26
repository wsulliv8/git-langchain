"""
Vector indexer implementation using ChromaDB and LangChain
Provides semantic search capabilities for Git Odyssey summaries
"""

from typing import Dict, List, Optional, Any
import chromadb
from chromadb.config import Settings
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.schema import Document
from .base_indexer import BaseVectorIndexer, IndexDocument, SearchResult


class ChromaVectorIndexer(BaseVectorIndexer):
    """Vector indexer using ChromaDB for semantic search"""

    def __init__(
        self,
        collection_name: str = "git_odyssey",
        persist_directory: str = "./chroma_db",
        embedding_model: str = "text-embedding-ada-002",
    ):
        """
        Initialize the ChromaDB vector indexer

        Args:
            collection_name: Name of the ChromaDB collection
            persist_directory: Directory to persist the database
            embedding_model: OpenAI embedding model to use
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.embedding_model = embedding_model

        # Initialize embeddings
        self.embeddings = OpenAIEmbeddings(model=embedding_model)

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=persist_directory, settings=Settings(anonymized_telemetry=False)
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},  # Use cosine similarity
        )

        # Initialize LangChain Chroma vectorstore for compatibility
        self.vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=persist_directory,
        )

    def add_documents(self, documents: List[IndexDocument]) -> None:
        """Add documents to the vector index"""
        if not documents:
            return

        # Prepare documents for ChromaDB
        ids = []
        documents_text = []
        metadatas = []

        for doc in documents:
            ids.append(doc.id)
            documents_text.append(doc.content)

            # Prepare metadata (ChromaDB requires string values)
            metadata = {}
            for key, value in doc.metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    metadata[key] = str(value)
                elif isinstance(value, list):
                    metadata[key] = ",".join(str(v) for v in value)
                else:
                    metadata[key] = str(value)

            # Add timestamp if available
            if doc.timestamp:
                metadata["timestamp"] = doc.timestamp.isoformat()

            metadatas.append(metadata)

        # Add to ChromaDB collection
        try:
            self.collection.add(ids=ids, documents=documents_text, metadatas=metadatas)
            print(f"Added {len(documents)} documents to vector index")
        except Exception as e:
            print(f"Error adding documents to vector index: {str(e)}")
            raise

    def search(
        self, query: str, top_k: int = 10, filters: Optional[Dict] = None
    ) -> List[SearchResult]:
        """Search for similar documents using vector similarity"""

        # Convert filters to ChromaDB format
        where_clause = self._convert_filters_to_where(filters) if filters else None

        try:
            # Perform vector search
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_clause,
                include=["documents", "metadatas", "distances"],
            )

            # Convert results to SearchResult objects
            search_results = []

            if results["documents"] and results["documents"][0]:
                for i, (doc, metadata, distance) in enumerate(
                    zip(
                        results["documents"][0],
                        results["metadatas"][0],
                        results["distances"][0],
                    )
                ):
                    # Convert distance to similarity score (higher is better)
                    score = 1.0 - distance if distance <= 1.0 else 0.0

                    search_result = SearchResult(
                        content=doc,
                        metadata=metadata,
                        score=score,
                        source_type=metadata.get("source_type", "unknown"),
                        source_id=metadata.get("source_id", "unknown"),
                    )
                    search_results.append(search_result)

            return search_results

        except Exception as e:
            print(f"Error searching vector index: {str(e)}")
            return []

    def delete_documents(self, document_ids: List[str]) -> None:
        """Delete documents from the index"""
        if not document_ids:
            return

        try:
            self.collection.delete(ids=document_ids)
            print(f"Deleted {len(document_ids)} documents from vector index")
        except Exception as e:
            print(f"Error deleting documents from vector index: {str(e)}")
            raise

    def get_document(self, document_id: str) -> Optional[IndexDocument]:
        """Get a specific document by ID"""
        try:
            results = self.collection.get(
                ids=[document_id], include=["documents", "metadatas"]
            )

            if results["documents"] and results["documents"][0]:
                doc_text = results["documents"][0]
                metadata = results["metadatas"][0]

                # Parse timestamp if present
                timestamp = None
                if "timestamp" in metadata:
                    try:
                        from datetime import datetime

                        timestamp = datetime.fromisoformat(metadata["timestamp"])
                    except:
                        pass

                return IndexDocument(
                    id=document_id,
                    content=doc_text,
                    metadata=metadata,
                    timestamp=timestamp,
                )

            return None

        except Exception as e:
            print(f"Error getting document from vector index: {str(e)}")
            return None

    def _convert_filters_to_where(self, filters: Dict) -> Dict:
        """Convert generic filters to ChromaDB where clause format"""
        where_clause = {}

        for key, value in filters.items():
            if key == "source_type" and isinstance(value, str):
                where_clause["source_type"] = {"$eq": value}
            elif key == "source_type" and isinstance(value, list):
                where_clause["source_type"] = {"$in": value}
            elif key == "path" and isinstance(value, str):
                # For path filtering, we'll use contains for partial matches
                where_clause["path"] = {"$regex": f".*{value}.*"}
            elif key == "author" and isinstance(value, str):
                where_clause["author"] = {"$eq": value}
            elif key == "intent_tags" and isinstance(value, list):
                # Check if any of the tags are in the document's intent_tags
                where_clause["intent_tags"] = {"$in": value}
            elif key == "date_from":
                where_clause["timestamp"] = {"$gte": value}
            elif key == "date_to":
                if "timestamp" not in where_clause:
                    where_clause["timestamp"] = {}
                where_clause["timestamp"]["$lte"] = value

        return where_clause

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the collection"""
        try:
            count = self.collection.count()
            return {
                "collection_name": self.collection_name,
                "document_count": count,
                "embedding_model": self.embedding_model,
            }
        except Exception as e:
            return {
                "collection_name": self.collection_name,
                "document_count": 0,
                "error": str(e),
            }

    def clear_collection(self) -> None:
        """Clear all documents from the collection"""
        try:
            # Get all document IDs
            results = self.collection.get(include=["documents"])
            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                print(f"Cleared {len(results['ids'])} documents from collection")
        except Exception as e:
            print(f"Error clearing collection: {str(e)}")
            raise

