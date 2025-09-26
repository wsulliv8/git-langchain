import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class CollectorConfig:
    """Configuration for Git Odyssey data collection"""

    github_token: str
    api_url: str
    repo_owner: str
    repo_name: str
    repo_path: str
    query_file: str
    output_file: Optional[str] = "git-langchain/logs/output.json"

    @classmethod
    def from_env(cls) -> "CollectorConfig":
        """Load configuration from environment variables"""
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN environment variable is required")

        return cls(
            github_token=github_token,
            api_url=os.getenv("API_URL", "https://api.github.com/graphql"),
            repo_owner=os.getenv("REPO_OWNER", "wsulliv8"),
            repo_name=os.getenv("REPO_NAME", "go-raft"),
            repo_path=os.getenv("REPO_PATH", "../distributed-systems/go/go-raft"),
            query_file=os.getenv("QUERY_FILE", "git-langchain/graphql/query.graphql"),
            output_file=os.getenv("OUTPUT_FILE", "git-langchain/logs/output.json"),
        )
