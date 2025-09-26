"""
File-level summarizer for Git Odyssey
Rolls up hunk summaries to create file-level summaries
"""

from typing import Dict, Optional, List
from langchain_core.prompts import ChatPromptTemplate
from .base_summarizer import BaseSummarizer, SummaryResult
from .hunk_summarizer import HunkSummarizer
from ..models import FileDelta


class FileDeltaSummarizer(BaseSummarizer):
    """Summarizes file-level changes by rolling up hunk summaries"""

    def __init__(self, model_name: str = "gpt-3.5-turbo", temperature: float = 0.1):
        super().__init__(model_name, temperature)
        self.hunk_summarizer = HunkSummarizer(model_name, temperature)

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are Git Odyssey, an AI tool that summarizes code changes in git commits.

Your task is to analyze file-level changes by synthesizing multiple hunk summaries into a cohesive file summary.

Focus on:
1. Overall purpose and scope of changes to the file
2. Key functions, classes, or modules affected
3. The main intent behind all changes to this file
4. Any patterns or themes across the hunks

Keep the summary concise but comprehensive, highlighting the most important changes.""",
                ),
                (
                    "human",
                    """Analyze these file changes:

File: {file_path}
Change Type: {change_type}
Language: {language}
Lines Added: {lines_added}
Lines Deleted: {lines_deleted}

Hunk Summaries:
{hunk_summaries}

Provide a comprehensive summary of all changes made to this file.""",
                ),
            ]
        )

    def summarize(
        self,
        file_delta: FileDelta,
        hunk_summaries: List[SummaryResult],
        context: Optional[Dict] = None,
    ) -> SummaryResult:
        """Summarize file-level changes using hunk summaries"""

        if not hunk_summaries:
            # Handle case with no hunk summaries (e.g., binary files, very large changes)
            return self._create_fallback_summary(file_delta)

        # Format hunk summaries for the prompt
        hunk_summary_text = self._format_hunk_summaries(hunk_summaries)

        # Format the prompt
        messages = self.prompt.format_messages(
            file_path=file_delta.pathNew or file_delta.pathOld,
            change_type=file_delta.status,
            language=file_delta.lang or "unknown",
            lines_added=file_delta.locAdd,
            lines_deleted=file_delta.locDel,
            hunk_summaries=hunk_summary_text,
        )

        # Get LLM response
        response = self.llm.invoke(messages)
        summary_text = response.content.strip()

        # Aggregate intent tags from hunk summaries
        intent_tags = self._aggregate_intent_tags(hunk_summaries)

        # Calculate confidence based on hunk summary quality
        confidence = self._calculate_file_confidence(hunk_summaries, file_delta)

        return SummaryResult(
            content=summary_text,
            intent_tags=intent_tags,
            confidence=confidence,
            metadata={
                "file_sha": file_delta.sha,
                "file_path": file_delta.pathNew or file_delta.pathOld,
                "change_type": file_delta.status,
                "language": file_delta.lang,
                "lines_added": file_delta.locAdd,
                "lines_deleted": file_delta.locDel,
                "hunk_count": len(hunk_summaries),
            },
        )

    def _format_hunk_summaries(self, hunk_summaries: List[SummaryResult]) -> str:
        """Format hunk summaries for the prompt"""
        formatted = []
        for i, summary in enumerate(hunk_summaries, 1):
            line_range = summary.metadata.get("line_range", "unknown")
            formatted.append(f"Hunk {i} (Lines {line_range}): {summary.content}")
            if summary.intent_tags:
                formatted.append(f"  Intent: {', '.join(summary.intent_tags)}")

        return "\n".join(formatted)

    def _aggregate_intent_tags(self, hunk_summaries: List[SummaryResult]) -> List[str]:
        """Aggregate intent tags from hunk summaries"""
        all_tags = []
        for summary in hunk_summaries:
            all_tags.extend(summary.intent_tags)

        # Count tag frequency and return most common ones
        tag_counts = {}
        for tag in all_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Return tags that appear in at least half of the hunks, or top 3 most common
        threshold = max(1, len(hunk_summaries) // 2)
        common_tags = [tag for tag, count in tag_counts.items() if count >= threshold]

        # If no common tags, return the most frequent ones
        if not common_tags:
            sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
            common_tags = [tag for tag, count in sorted_tags[:3]]

        return common_tags if common_tags else ["other"]

    def _calculate_file_confidence(
        self, hunk_summaries: List[SummaryResult], file_delta: FileDelta
    ) -> float:
        """Calculate confidence based on hunk summary quality and file characteristics"""
        if not hunk_summaries:
            return 0.1

        # Average confidence from hunk summaries
        avg_hunk_confidence = sum(s.confidence for s in hunk_summaries) / len(
            hunk_summaries
        )

        # Boost confidence for substantial changes
        total_lines = file_delta.locAdd + file_delta.locDel
        if total_lines > 50:
            avg_hunk_confidence += 0.1
        elif total_lines < 5:
            avg_hunk_confidence -= 0.1

        # Boost confidence for files with multiple hunks (more context)
        if len(hunk_summaries) > 3:
            avg_hunk_confidence += 0.05

        # Reduce confidence for very large files (might be incomplete analysis)
        if total_lines > 500:
            avg_hunk_confidence -= 0.1

        return min(1.0, max(0.1, avg_hunk_confidence))

    def _create_fallback_summary(self, file_delta: FileDelta) -> SummaryResult:
        """Create a fallback summary when no hunk summaries are available"""
        file_path = file_delta.pathNew or file_delta.pathOld

        if file_delta.status == "Add":
            summary = f"Added new file: {file_path}"
            intent_tags = ["feature"]
        elif file_delta.status == "Del":
            summary = f"Deleted file: {file_path}"
            intent_tags = ["refactor"]
        elif file_delta.status == "Rename":
            summary = f"Renamed file from {file_delta.pathOld} to {file_delta.pathNew}"
            intent_tags = ["refactor"]
        else:
            summary = f"Modified file: {file_path} ({file_delta.locAdd} additions, {file_delta.locDel} deletions)"
            intent_tags = ["other"]

        return SummaryResult(
            content=summary,
            intent_tags=intent_tags,
            confidence=0.3,  # Lower confidence for fallback
            metadata={
                "file_sha": file_delta.sha,
                "file_path": file_path,
                "change_type": file_delta.status,
                "fallback": True,
            },
        )
