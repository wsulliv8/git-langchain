#!/usr/bin/env python3
"""
Demo script showing how to use the Git Odyssey Summarizer and Indexer
This script demonstrates the complete pipeline from ingestion to search
"""

import os
import sys
from typing import Dict, List, Any

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ingest.ingest_local import GitLocalIngester
from summarize.summarizer import GitSummarizer
from index.indexer import GitIndexer
from config import CollectorConfig


def demo_complete_pipeline():
    """Demonstrate the complete Git Odyssey pipeline"""

    print("🚀 Git Odyssey - Complete Pipeline Demo")
    print("=" * 50)

    # Step 1: Configuration
    print("\n1. Setting up configuration...")
    config = CollectorConfig(
        repo_path=".",  # Current directory
        output_dir="./output",
        max_commits=10,  # Limit for demo
    )

    # Step 2: Ingestion
    print("\n2. Ingesting Git data...")
    ingester = GitLocalIngester(config)
    try:
        raw_data = ingester.ingest()
        print(f"✅ Ingested {len(raw_data['commits'])} commits")
        print(f"✅ Found {len(raw_data['fileDeltas'])} file changes")
        print(f"✅ Found {len(raw_data['hunks'])} code hunks")
    except Exception as e:
        print(f"❌ Ingestion failed: {str(e)}")
        return

    # Step 3: Summarization
    print("\n3. Summarizing commits...")
    summarizer = GitSummarizer()

    # Use Pydantic models directly - no serialization needed!
    commits = raw_data["commits"][:5]  # Process first 5 commits for demo

    # Group file deltas and hunks by commit SHA
    file_deltas_by_commit = {}
    hunks_by_commit = {}

    for file_delta in raw_data["fileDeltas"]:
        sha = file_delta.sha
        if sha not in file_deltas_by_commit:
            file_deltas_by_commit[sha] = []
        file_deltas_by_commit[sha].append(file_delta)

    for hunk in raw_data["hunks"]:
        sha = hunk.sha
        if sha not in hunks_by_commit:
            hunks_by_commit[sha] = []
        hunks_by_commit[sha].append(hunk)

    try:
        summaries = summarizer.summarize_commits_batch_typed(
            commits, file_deltas_by_commit, hunks_by_commit
        )
        print(f"✅ Generated summaries for {len(summaries)} commits")

        # Show summary statistics
        stats = summarizer.get_summary_statistics()
        print(f"📊 Summary Statistics:")
        print(f"   - Total commits: {stats['total_commits']}")
        print(f"   - Total files: {stats['total_files']}")
        print(f"   - Total hunks: {stats['total_hunks']}")
        print(f"   - Avg commit confidence: {stats['avg_commit_confidence']:.2f}")
        print(f"   - Avg file confidence: {stats['avg_file_confidence']:.2f}")
        print(f"   - Avg hunk confidence: {stats['avg_hunk_confidence']:.2f}")

    except Exception as e:
        print(f"❌ Summarization failed: {str(e)}")
        return

    # Step 4: Indexing
    print("\n4. Indexing summaries...")
    indexer = GitIndexer(
        vector_db_path="./demo_chroma_db", keyword_db_path="./demo_keyword.db"
    )

    try:
        indexer.index_summaries_batch(summaries)
        print("✅ Indexed all summaries")

        # Show index statistics
        index_stats = indexer.get_index_statistics()
        print(f"📊 Index Statistics:")
        print(f"   - Total documents: {index_stats['total_documents']}")
        print(f"   - Documents by type: {index_stats['documents_by_type']}")

    except Exception as e:
        print(f"❌ Indexing failed: {str(e)}")
        return

    # Step 5: Search Demo
    print("\n5. Search demonstrations...")

    # Demo different types of searches
    search_demos = [
        {
            "name": "Semantic Search",
            "query": "authentication or login functionality",
            "type": "hybrid",
        },
        {
            "name": "Bug Fix Search",
            "query": "",
            "filters": {"intent_tags": ["bug_fix"]},
            "type": "keyword",
        },
        {
            "name": "Feature Addition Search",
            "query": "",
            "filters": {"intent_tags": ["feature"]},
            "type": "keyword",
        },
        {
            "name": "Refactoring Search",
            "query": "",
            "filters": {"intent_tags": ["refactor"]},
            "type": "keyword",
        },
    ]

    for demo in search_demos:
        print(f"\n🔍 {demo['name']}:")
        try:
            results = indexer.search(
                query=demo["query"],
                top_k=3,
                filters=demo.get("filters"),
                search_type=demo["type"],
            )

            if results:
                for i, result in enumerate(results, 1):
                    print(f"   {i}. [{result.source_type}] {result.content[:100]}...")
                    print(
                        f"      Score: {result.score:.3f}, Source: {result.source_id[:8]}"
                    )
            else:
                print("   No results found")

        except Exception as e:
            print(f"   ❌ Search failed: {str(e)}")

    print("\n🎉 Demo completed successfully!")
    print("\nNext steps:")
    print("- Try modifying the search queries in the demo")
    print("- Add more commits to the ingestion process")
    print("- Experiment with different embedding models")
    print("- Build a web interface using the search capabilities")


def demo_search_only():
    """Demo just the search functionality (assumes indexes already exist)"""

    print("🔍 Git Odyssey - Search Demo")
    print("=" * 30)

    # Initialize indexer
    indexer = GitIndexer(
        vector_db_path="./demo_chroma_db", keyword_db_path="./demo_keyword.db"
    )

    # Get statistics
    stats = indexer.get_index_statistics()
    print(f"📊 Index contains {stats['total_documents']} documents")

    # Interactive search
    while True:
        query = input("\nEnter search query (or 'quit' to exit): ").strip()

        if query.lower() in ["quit", "exit", "q"]:
            break

        if not query:
            continue

        try:
            results = indexer.search(query, top_k=5, search_type="hybrid")

            if results:
                print(f"\nFound {len(results)} results:")
                for i, result in enumerate(results, 1):
                    print(
                        f"\n{i}. [{result.source_type.upper()}] Score: {result.score:.3f}"
                    )
                    print(f"   Content: {result.content}")
                    print(f"   Source: {result.source_id[:8]}")
                    if result.metadata.get("intent_tags"):
                        print(f"   Tags: {', '.join(result.metadata['intent_tags'])}")
            else:
                print("No results found")

        except Exception as e:
            print(f"Search error: {str(e)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Git Odyssey Demo")
    parser.add_argument(
        "--search-only",
        action="store_true",
        help="Only run search demo (assumes indexes exist)",
    )

    args = parser.parse_args()

    if args.search_only:
        demo_search_only()
    else:
        demo_complete_pipeline()
