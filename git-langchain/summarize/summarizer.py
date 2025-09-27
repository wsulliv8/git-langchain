"""
Main summarizer orchestrator for Git Odyssey
Coordinates the hierarchical summarization process: Hunk -> FileDelta -> Commit
"""

from typing import Dict, List, Optional, Tuple
from .hunk_summarizer import HunkSummarizer, SummaryResult
from .file_summarizer import FileDeltaSummarizer
from .commit_summarizer import CommitSummarizer
from ..models import Commit, FileDelta, Hunk


class GitSummarizer:
    """Main orchestrator for the hierarchical summarization process"""

    def __init__(self, model_name: str = "gpt-3.5-turbo", temperature: float = 0.1):
        self.hunk_summarizer = HunkSummarizer(model_name, temperature)
        self.file_summarizer = FileDeltaSummarizer(model_name, temperature)
        self.commit_summarizer = CommitSummarizer(model_name, temperature)

        # Cache for storing summaries to avoid re-computation
        self._summary_cache = {}

    def summarize_commit(
        self,
        commit: Commit,
        file_deltas: List[FileDelta],
        hunks: List[Hunk],
        context: Optional[Dict] = None,
    ) -> Dict[str, any]:
        """
        Perform complete hierarchical summarization for a single commit

        Returns:
            Dict containing hunk summaries, file summaries, and commit summary
        """
        commit_key = commit.sha
        if commit_key in self._summary_cache:
            return self._summary_cache[commit_key]

        # Group hunks by file delta
        hunks_by_file = self._group_hunks_by_file(hunks, file_deltas)

        # Step 1: Summarize hunks
        print(f"Summarizing {len(hunks)} hunks for commit {commit.sha[:8]}...")
        hunk_summaries = self.hunk_summarizer.summarize_batch(hunks)

        # Step 2: Summarize files using hunk summaries
        print(f"Summarizing {len(file_deltas)} files for commit {commit.sha[:8]}...")
        file_summaries = []
        for file_delta in file_deltas:
            file_hunks = hunks_by_file.get(file_delta.pathNew or file_delta.pathOld, [])
            file_hunk_summaries = [
                s
                for s in hunk_summaries
                if s.metadata.get("file_path")
                == (file_delta.pathNew or file_delta.pathOld)
            ]

            file_summary = self.file_summarizer.summarize(
                file_delta, file_hunk_summaries, context
            )
            file_summaries.append(file_summary)

        # Step 3: Summarize commit using file summaries
        print(f"Summarizing commit {commit.sha[:8]}...")
        commit_summary = self.commit_summarizer.summarize(
            commit, file_summaries, context
        )

        # Prepare result
        result = {
            "commit": commit.model_dump(),  # Pydantic serialization
            "commit_summary": {
                "content": commit_summary.content,
                "intent_tags": commit_summary.intent_tags,
                "confidence": commit_summary.confidence,
                "metadata": commit_summary.metadata,
            },
            "file_summaries": [
                {
                    "file_delta": file_delta.model_dump(),  # Pydantic serialization
                    "summary": {
                        "content": summary.content,
                        "intent_tags": summary.intent_tags,
                        "confidence": summary.confidence,
                        "metadata": summary.metadata,
                    },
                }
                for file_delta, summary in zip(file_deltas, file_summaries)
            ],
            "hunk_summaries": [
                {
                    "hunk": self._find_hunk_by_metadata(hunks, summary.metadata),
                    "summary": {
                        "content": summary.content,
                        "intent_tags": summary.intent_tags,
                        "confidence": summary.confidence,
                        "metadata": summary.metadata,
                    },
                }
                for summary in hunk_summaries
            ],
        }

        # Cache the result
        self._summary_cache[commit_key] = result

        return result

    def summarize_commits_batch(
        self, commits_data: List[Dict], context: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Summarize multiple commits in batch

        Args:
            commits_data: List of dicts containing commit, file_deltas, and hunks
            context: Optional context for summarization

        Returns:
            List of summarized commit data
        """
        results = []

        for i, data in enumerate(commits_data):
            # Convert dict data to dataclass objects for type safety
            commit = Commit(**data["commit"])
            file_deltas = [FileDelta(**fd) for fd in data["fileDeltas"]]
            hunks = [Hunk(**h) for h in data["hunks"]]

            print(f"Processing commit {i+1}/{len(commits_data)}: {commit.sha[:8]}")

            try:
                result = self.summarize_commit(commit, file_deltas, hunks, context)
                results.append(result)
            except Exception as e:
                print(f"Error summarizing commit {commit.sha[:8]}: {str(e)}")
                # Create error result
                error_result = {
                    "commit": commit.model_dump(),  # Pydantic serialization
                    "commit_summary": {
                        "content": f"Error during summarization: {str(e)}",
                        "intent_tags": ["error"],
                        "confidence": 0.0,
                        "metadata": {"error": str(e)},
                    },
                    "file_summaries": [],
                    "hunk_summaries": [],
                }
                results.append(error_result)

        return results

    def summarize_commits_batch_typed(
        self,
        commits: List[Commit],
        file_deltas_by_commit: Dict[str, List[FileDelta]],
        hunks_by_commit: Dict[str, List[Hunk]],
        context: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Summarize multiple commits in batch using typed dataclass objects

        This is more efficient than summarize_commits_batch as it avoids
        dict -> dataclass conversion overhead.

        Args:
            commits: List of Commit dataclass objects
            file_deltas_by_commit: Dict mapping commit SHA to list of FileDelta objects
            hunks_by_commit: Dict mapping commit SHA to list of Hunk objects
            context: Optional context for summarization

        Returns:
            List of summarized commit data
        """
        results = []

        for i, commit in enumerate(commits):
            commit_file_deltas = file_deltas_by_commit.get(commit.sha, [])
            commit_hunks = hunks_by_commit.get(commit.sha, [])

            print(f"Processing commit {i+1}/{len(commits)}: {commit.sha[:8]}")

            try:
                result = self.summarize_commit(
                    commit, commit_file_deltas, commit_hunks, context
                )
                results.append(result)
            except Exception as e:
                print(f"Error summarizing commit {commit.sha[:8]}: {str(e)}")
                # Create error result
                error_result = {
                    "commit": commit.model_dump(),  # Pydantic serialization
                    "commit_summary": {
                        "content": f"Error during summarization: {str(e)}",
                        "intent_tags": ["error"],
                        "confidence": 0.0,
                        "metadata": {"error": str(e)},
                    },
                    "file_summaries": [],
                    "hunk_summaries": [],
                }
                results.append(error_result)

        return results

    def _group_hunks_by_file(
        self, hunks: List[Hunk], file_deltas: List[FileDelta]
    ) -> Dict[str, List[Hunk]]:
        """Group hunks by their file path"""
        hunks_by_file = {}

        for hunk in hunks:
            file_path = hunk.pathNew
            if file_path not in hunks_by_file:
                hunks_by_file[file_path] = []
            hunks_by_file[file_path].append(hunk)

        return hunks_by_file

    def _find_hunk_by_metadata(self, hunks: List[Hunk], metadata: Dict) -> Dict:
        """Find the original hunk data by metadata"""
        hunk_sha = metadata.get("hunk_sha")
        if hunk_sha:
            for hunk in hunks:
                if hunk.sha == hunk_sha:
                    return hunk.model_dump()  # Pydantic serialization

        # Fallback: return metadata as dict
        return metadata

    def get_summary_statistics(self) -> Dict:
        """Get statistics about the summarization process"""
        total_commits = len(self._summary_cache)

        if total_commits == 0:
            return {"total_commits": 0}

        # Calculate average confidence scores
        commit_confidences = []
        file_confidences = []
        hunk_confidences = []

        for result in self._summary_cache.values():
            commit_confidences.append(result["commit_summary"]["confidence"])

            for file_summary in result["file_summaries"]:
                file_confidences.append(file_summary["summary"]["confidence"])

            for hunk_summary in result["hunk_summaries"]:
                hunk_confidences.append(hunk_summary["summary"]["confidence"])

        return {
            "total_commits": total_commits,
            "total_files": len(file_confidences),
            "total_hunks": len(hunk_confidences),
            "avg_commit_confidence": (
                sum(commit_confidences) / len(commit_confidences)
                if commit_confidences
                else 0
            ),
            "avg_file_confidence": (
                sum(file_confidences) / len(file_confidences) if file_confidences else 0
            ),
            "avg_hunk_confidence": (
                sum(hunk_confidences) / len(hunk_confidences) if hunk_confidences else 0
            ),
        }

    def clear_cache(self):
        """Clear the summary cache"""
        self._summary_cache.clear()

    def export_summaries(self, output_format: str = "json") -> str:
        """Export all summaries in the specified format"""
        if output_format == "json":
            import json

            return json.dumps(list(self._summary_cache.values()), indent=2)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")
