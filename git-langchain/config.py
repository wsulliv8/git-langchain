import os
from pydantic import BaseModel, Field
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class CollectorConfig(BaseModel):
    """Configuration for Git Odyssey data collection"""

    github_token: str
    openai_api_key: str
    api_url: str = Field(default="https://api.github.com/graphql")
    repo_owner: str = Field(default="wsulliv8")
    repo_name: str = Field(default="go-raft")
    repo_path: str = Field(default="../distributed-systems/go/go-raft")
    query_file: str = Field(default="git-langchain/graphql/query.graphql")
    output_file: Optional[str] = Field(default="git-langchain/logs/output.json")

    @classmethod
    def from_env(cls) -> "CollectorConfig":
        """Load configuration from environment variables"""

        return cls(
            github_token=os.getenv("GITHUB_TOKEN"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            api_url=os.getenv("API_URL", "https://api.github.com/graphql"),
            repo_owner=os.getenv("REPO_OWNER", "wsulliv8"),
            repo_name=os.getenv("REPO_NAME", "go-raft"),
            repo_path=os.getenv("REPO_PATH", "../distributed-systems/go/go-raft"),
            query_file=os.getenv("QUERY_FILE", "git-langchain/graphql/query.graphql"),
            output_file=os.getenv("OUTPUT_FILE", "git-langchain/logs/output.json"),
        )
