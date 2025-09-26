"""
Hunk-level summarizer for Git Odyssey
Summarizes individual code hunks (diff chunks) with structured prompts
"""

from typing import Dict, Optional, List
from langchain_core.prompts import ChatPromptTemplate
from .base_summarizer import BaseSummarizer, SummaryResult
from ..models import Hunk


class HunkSummarizer(BaseSummarizer):
    """Summarizes individual code hunks"""

    def __init__(self, model_name: str = "gpt-3.5-turbo", temperature: float = 0.1):
        super().__init__(model_name, temperature)

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are Git Odyssey, an AI tool that summarizes code changes in git commits. 
            
Your task is to analyze a code hunk (diff chunk) and provide a concise, structured summary.

Focus on:
1. What functionality was added, removed, or modified
2. Key changes in logic, data structures, or behavior
3. The intent behind the change

Keep the summary to 1-2 sentences maximum. Be specific about function names, variables, and logic changes.""",
                ),
                (
                    "human",
                    """Analyze this code hunk:

File: {file_path}
Hunk Range: Lines {start_old}-{len_old} (old) -> {start_new}-{len_new} (new)

Diff:
```
{hunk_text}
```

Provide a concise summary of what changed and why.""",
                ),
            ]
        )

    def summarize(self, hunk: Hunk, context: Optional[Dict] = None) -> SummaryResult:
        """Summarize a single hunk"""

        # Format the prompt
        messages = self.prompt.format_messages(
            file_path=hunk.pathNew,
            start_old=hunk.startOld,
            len_old=hunk.lenOld,
            start_new=hunk.startNew,
            len_new=hunk.lenNew,
            hunk_text=hunk.text,
        )

        # Get LLM response
        response = self.llm.invoke(messages)
        summary_text = response.content.strip()

        # Extract intent tags
        intent_tags = self._extract_intent_tags(summary_text)

        # Calculate confidence based on response quality
        confidence = self._calculate_confidence(summary_text, hunk)

        return SummaryResult(
            content=summary_text,
            intent_tags=intent_tags,
            confidence=confidence,
            metadata={
                "hunk_sha": hunk.sha,
                "file_path": hunk.pathNew,
                "line_range": f"{hunk.startOld}-{hunk.startOld + hunk.lenOld} -> {hunk.startNew}-{hunk.startNew + hunk.lenNew}",
            },
        )

    def _calculate_confidence(self, summary: str, hunk: Hunk) -> float:
        """Calculate confidence score based on summary quality and hunk characteristics"""
        base_confidence = 0.7

        # Boost confidence for longer, more detailed summaries
        if len(summary.split()) > 10:
            base_confidence += 0.1

        # Boost confidence for hunks with substantial changes
        total_lines = hunk.lenOld + hunk.lenNew
        if total_lines > 10:
            base_confidence += 0.1

        # Reduce confidence for very short hunks (might be whitespace/formatting)
        if total_lines < 3:
            base_confidence -= 0.2

        return min(1.0, max(0.1, base_confidence))

    def summarize_batch(
        self, hunks: List[Hunk], context: Optional[Dict] = None
    ) -> List[SummaryResult]:
        """Summarize multiple hunks in batch for efficiency"""
        results = []
        for hunk in hunks:
            try:
                result = self.summarize(hunk, context)
                results.append(result)
            except Exception as e:
                # Log error and create fallback summary
                fallback_result = SummaryResult(
                    content=f"Error summarizing hunk: {str(e)}",
                    intent_tags=["error"],
                    confidence=0.0,
                    metadata={"hunk_sha": hunk.sha, "error": str(e)},
                )
                results.append(fallback_result)

        return results
