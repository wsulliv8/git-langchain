import requests
import os
import json
import subprocess
import re
import sys
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

load_dotenv()


@dataclass
class Commit:
    sha: str
    parents: List[str]
    author: Dict[str, str]
    date: str
    message: str
    branchHints: List[str]
    tagHints: List[str]


@dataclass
class FileDelta:
    sha: str
    pathOld: Optional[str]
    pathNew: Optional[str]
    status: str  # Add/Mod/Del/Rename
    lang: Optional[str]
    locAdd: int
    locDel: int


@dataclass
class Hunk:
    sha: str
    pathNew: str
    startOld: int
    lenOld: int
    startNew: int
    lenNew: int
    text: str


@dataclass
class PR:
    id: int
    title: str
    body: str
    state: str
    createdAt: str
    mergedAt: Optional[str]
    commits: List[str]
    issues: List[int]


@dataclass
class Issue:
    id: int
    title: str
    body: str
    labels: List[str]
    closedAt: Optional[str]


class GitOdysseyDataCollector:
    def __init__(self):
        self.url = "https://api.github.com/graphql"
        self.token = os.getenv("GITHUB_TOKEN")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def load_query(self, query_file: str) -> str:
        with open(query_file, "r") as file:
            return file.read()

    def fetch_data(self, owner: str, repo_name: str) -> Dict[str, Any]:
        query = self.load_query("query.graphql")
        variables = {
            "owner": owner,
            "repoName": repo_name,
        }
        response = requests.post(
            self.url,
            headers=self.headers,
            json={"query": query, "variables": variables},
        )

        if response.status_code != 200:
            raise Exception(f"GraphQL request failed: {response.status_code}")

        result = response.json()

        return result

    def process_data(self, data: Dict[str, Any]) -> Dict[str, List]:
        repo_data = data["data"]["repository"]

        # Process PRs
        prs = []
        for pr_node in repo_data["pullRequests"]["nodes"]:
            pr = PR(
                id=pr_node["number"],
                title=pr_node["title"],
                body=pr_node["body"] or "",
                state=pr_node["state"],
                createdAt=pr_node["createdAt"],
                mergedAt=pr_node["mergedAt"],
                commits=[
                    commit["commit"]["oid"] for commit in pr_node["commits"]["nodes"]
                ],
                issues=[],  # Will be populated by linking logic if needed
            )
            prs.append(pr)

        # Process Issues
        issues = []
        for issue_node in repo_data["issues"]["nodes"]:
            issue = Issue(
                id=issue_node["number"],
                title=issue_node["title"],
                body=issue_node["body"] or "",
                labels=[label["name"] for label in issue_node["labels"]["nodes"]],
                closedAt=issue_node["closedAt"],
            )
            issues.append(issue)

        return {
            "prs": [asdict(pr) for pr in prs],
            "issues": [asdict(issue) for issue in issues],
        }


def main():
    collector = GitOdysseyDataCollector()

    # Fetch PRs and Issues data
    data = collector.fetch_data("wsulliv8", "go-raft")

    # Process data
    processed_data = collector.process_data(data)

    # Output results
    print(json.dumps(processed_data, indent=2))


if __name__ == "__main__":
    main()
