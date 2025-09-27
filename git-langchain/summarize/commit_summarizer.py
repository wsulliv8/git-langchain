"""
Commit-level summarizer for Git Odyssey
Combines file summaries and commit messages to create comprehensive commit summaries
"""

from typing import Dict, Optional, List
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from .hunk_summarizer import SummaryResult
from ..models import Commit


class CommitSummarizer:
    """Summarizes entire commits by combining file summaries and commit messages"""

    def __init__(self, model_name: str = "gpt-3.5-turbo", temperature: float = 0.1):
        self.llm = ChatOpenAI(
            model_name=model_name, temperature=temperature, max_tokens=500
        )

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are Git Odyssey, an AI tool that summarizes git commits.

Your task is to create a comprehensive commit summary by analyzing the commit message and all file changes.

Focus on:
1. The main purpose and intent of the commit
2. Key changes and their impact
3. Whether this is a bug fix, feature addition, refactor, or other type of change
4. Any important patterns or themes across the files
5. The overall scope and significance of the commit

Provide a clear, concise summary that captures the essence of the commit. Use the commit message as context but don't just repeat it - synthesize it with the actual code changes.""",
                ),
                (
                    "human",
                    """Analyze this commit:

Commit SHA: {commit_sha}
Author: {author}
Date: {date}
Branch Hints: {branch_hints}

Commit Message:
```
{commit_message}
```

File Changes:
{file_summaries}

Provide a comprehensive summary of this commit's purpose and changes.""",
                ),
            ]
        )

    def summarize(
        self,
        commit: Commit,
        file_summaries: List[SummaryResult],
        context: Optional[Dict] = None,
    ) -> SummaryResult:
        """Summarize a commit using file summaries and commit message"""

        if not file_summaries:
            # Handle case with no file summaries (merge commits, etc.)
            return self._create_fallback_summary(commit)

        # Format file summaries for the prompt
        file_summary_text = self._format_file_summaries(file_summaries)

        # Format the prompt
        messages = self.prompt.format_messages(
            commit_sha=commit.sha[:8],  # Short SHA
            author=f"{commit.author.get('name', 'Unknown')} <{commit.author.get('email', 'unknown')}>",
            date=commit.date,
            branch_hints=(
                ", ".join(commit.branchHints) if commit.branchHints else "main"
            ),
            commit_message=commit.message.strip(),
            file_summaries=file_summary_text,
        )

        # Get LLM response
        response = self.llm.invoke(messages)
        summary_text = response.content.strip()

        # Aggregate intent tags from file summaries
        intent_tags = self._aggregate_intent_tags(file_summaries)

        # Calculate confidence based on file summary quality and commit characteristics
        confidence = self._calculate_commit_confidence(file_summaries, commit)

        return SummaryResult(
            content=summary_text,
            intent_tags=intent_tags,
            confidence=confidence,
            metadata={
                "commit_sha": commit.sha,
                "author": commit.author,
                "date": commit.date,
                "branch_hints": commit.branchHints,
                "tag_hints": commit.tagHints,
                "parent_count": len(commit.parents),
                "file_count": len(file_summaries),
                "commit_message": commit.message.strip(),
            },
        )

    def _format_file_summaries(self, file_summaries: List[SummaryResult]) -> str:
        """Format file summaries for the prompt"""
        formatted = []
        for i, summary in enumerate(file_summaries, 1):
            file_path = summary.metadata.get("file_path", "unknown")
            change_type = summary.metadata.get("change_type", "unknown")
            formatted.append(f"File {i}: {file_path} ({change_type})")
            formatted.append(f"  Summary: {summary.content}")
            if summary.intent_tags:
                formatted.append(f"  Intent: {', '.join(summary.intent_tags)}")
            formatted.append("")  # Empty line for readability

        return "\n".join(formatted)

    def _aggregate_intent_tags(self, file_summaries: List[SummaryResult]) -> List[str]:
        """Aggregate intent tags from file summaries"""
        all_tags = []
        for summary in file_summaries:
            all_tags.extend(summary.intent_tags)

        # Count tag frequency
        tag_counts = {}
        for tag in all_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Return tags that appear in at least half of the files, or top 3 most common
        threshold = max(1, len(file_summaries) // 2)
        common_tags = [tag for tag, count in tag_counts.items() if count >= threshold]

        # If no common tags, return the most frequent ones
        if not common_tags:
            sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
            common_tags = [tag for tag, count in sorted_tags[:3]]

        # Add commit-specific tags based on analysis
        commit_specific_tags = self._analyze_commit_specific_intent(file_summaries)
        common_tags.extend(commit_specific_tags)

        return list(set(common_tags)) if common_tags else ["other"]

    def _analyze_commit_specific_intent(
        self, file_summaries: List[SummaryResult]
    ) -> List[str]:
        """Analyze commit-specific intent patterns"""
        tags = []

        # Analyze file change patterns
        file_count = len(file_summaries)
        total_additions = sum(s.metadata.get("lines_added", 0) for s in file_summaries)
        total_deletions = sum(
            s.metadata.get("lines_deleted", 0) for s in file_summaries
        )

        # Large commits
        if file_count > 10 or total_additions + total_deletions > 200:
            tags.append("large_change")

        # Merge commits (usually have many files with minimal changes)
        if file_count > 5 and total_additions + total_deletions < file_count * 2:
            tags.append("merge")

        # Documentation commits
        doc_files = [
            s
            for s in file_summaries
            if "doc" in s.metadata.get("file_path", "").lower()
        ]
        if len(doc_files) == file_count:
            tags.append("docs")

        # Test commits
        test_files = [
            s
            for s in file_summaries
            if "test" in s.metadata.get("file_path", "").lower()
        ]
        if len(test_files) == file_count:
            tags.append("test")

        return tags

    def _calculate_commit_confidence(
        self, file_summaries: List[SummaryResult], commit: Commit
    ) -> float:
        """Calculate confidence based on file summary quality and commit characteristics"""
        if not file_summaries:
            return 0.1

        # Average confidence from file summaries
        avg_file_confidence = sum(s.confidence for s in file_summaries) / len(
            file_summaries
        )

        # Boost confidence for commits with good commit messages
        commit_message_quality = self._assess_commit_message_quality(commit.message)
        avg_file_confidence += commit_message_quality * 0.2

        # Boost confidence for commits with moderate file counts (not too many, not too few)
        file_count = len(file_summaries)
        if 2 <= file_count <= 8:
            avg_file_confidence += 0.1
        elif file_count > 15:  # Very large commits might be incomplete
            avg_file_confidence -= 0.1

        # Reduce confidence for merge commits (often have complex, hard-to-summarize changes)
        if len(commit.parents) > 1:
            avg_file_confidence -= 0.1

        return min(1.0, max(0.1, avg_file_confidence))

    def _assess_commit_message_quality(self, message: str) -> float:
        """Assess the quality of a commit message (0.0 to 1.0)"""
        if not message or len(message.strip()) < 10:
            return 0.1

        quality_score = 0.5  # Base score

        # Boost for descriptive messages
        if len(message) > 50:
            quality_score += 0.2

        # Boost for conventional commit format
        conventional_patterns = [
            "fix:",
            "feat:",
            "docs:",
            "style:",
            "refactor:",
            "test:",
            "chore:",
        ]
        if any(
            message.lower().startswith(pattern) for pattern in conventional_patterns
        ):
            quality_score += 0.2

        # Boost for messages that explain "why" not just "what"
        why_words = [
            "because",
            "to fix",
            "in order to",
            "so that",
            "to prevent",
            "to improve",
        ]
        if any(word in message.lower() for word in why_words):
            quality_score += 0.1

        return min(1.0, quality_score)

    def _create_fallback_summary(self, commit: Commit) -> SummaryResult:
        """Create a fallback summary when no file summaries are available"""
        # This typically happens for merge commits or commits with only metadata changes

        if len(commit.parents) > 1:
            summary = f"Merge commit: {commit.message.strip()[:100]}..."
            intent_tags = ["merge"]
        else:
            summary = f"Commit with metadata changes: {commit.message.strip()[:100]}..."
            intent_tags = ["other"]

        return SummaryResult(
            content=summary,
            intent_tags=intent_tags,
            confidence=0.3,  # Lower confidence for fallback
            metadata={
                "commit_sha": commit.sha,
                "author": commit.author,
                "date": commit.date,
                "fallback": True,
                "parent_count": len(commit.parents),
            },
        )
