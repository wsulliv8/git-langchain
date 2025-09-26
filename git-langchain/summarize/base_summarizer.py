"""
Base summarizer class for Git Odyssey
Follows the hierarchical summarization pattern: Hunk -> FileDelta -> Commit -> PR -> Branch/Release
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from langchain.schema import BaseMessage
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
import json


@dataclass
class SummaryResult:
    """Structured result from summarization"""

    content: str
    intent_tags: List[str]  # e.g., ["bug_fix", "refactor", "feature", "docs"]
    confidence: float  # 0.0 to 1.0
    metadata: Dict[str, Any]


class BaseSummarizer(ABC):
    """Abstract base class for all summarizers"""

    def __init__(self, model_name: str = "gpt-3.5-turbo", temperature: float = 0.1):
        self.llm = ChatOpenAI(
            model_name=model_name, temperature=temperature, max_tokens=500
        )

    @abstractmethod
    def summarize(self, data: Any, context: Optional[Dict] = None) -> SummaryResult:
        """Summarize the input data and return structured result"""
        pass

    def _extract_intent_tags(self, summary: str) -> List[str]:
        """Extract intent tags from summary text"""
        # This could be enhanced with a separate classification model
        tags = []
        summary_lower = summary.lower()

        if any(word in summary_lower for word in ["fix", "bug", "error", "issue"]):
            tags.append("bug_fix")
        if any(word in summary_lower for word in ["refactor", "clean", "restructure"]):
            tags.append("refactor")
        if any(
            word in summary_lower for word in ["feature", "add", "implement", "new"]
        ):
            tags.append("feature")
        if any(word in summary_lower for word in ["doc", "comment", "readme"]):
            tags.append("docs")
        if any(word in summary_lower for word in ["test", "spec", "unit"]):
            tags.append("test")
        if any(word in summary_lower for word in ["security", "auth", "permission"]):
            tags.append("security")
        if any(word in summary_lower for word in ["performance", "optimize", "speed"]):
            tags.append("performance")

        return tags if tags else ["other"]
