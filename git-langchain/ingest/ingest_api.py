from typing import Dict, Any, List
from dataclasses import asdict
import requests
from config import CollectorConfig
from models import PR, Issue
from .base_ingester import BaseIngester


class GitAPIIngester(BaseIngester):
    def __init__(self, config: CollectorConfig):
        super().__init__(config)
        self.headers = {
            "Authorization": f"Bearer {config.github_token}",
            "Content-Type": "application/json",
        }

    def fetch(self) -> Dict[str, Any]:
        with open(self.config.query_file, "r") as file:
            query = file.read()

        variables = {
            "owner": self.config.repo_owner,
            "repoName": self.config.repo_name,
        }
        response = requests.post(
            self.config.api_url,
            headers=self.headers,
            json={"query": query, "variables": variables},
        )

        if response.status_code != 200:
            raise Exception(f"GraphQL request failed: {response.status_code}")

        result = response.json()

        if "errors" in result:
            raise Exception(f"GraphQL errors: {result['errors']}")

        return result

    def parse(self, data: Dict[str, Any]) -> Dict[str, List]:
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
