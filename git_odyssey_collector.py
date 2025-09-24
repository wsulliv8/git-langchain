import requests
import os
import json
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

    def fetch_data(
        self, owner: str, repo_name: str, branch_name: str = "main"
    ) -> Dict[str, Any]:
        query = self.load_query("comprehensive_query.graphql")
        variables = {
            "owner": owner,
            "repoName": repo_name,
            "branchName": branch_name,
            "firstCommits": 50,
            "firstPRs": 20,
            "firstIssues": 20,
        }

        response = requests.post(
            self.url,
            headers=self.headers,
            json={"query": query, "variables": variables},
        )

        if response.status_code != 200:
            raise Exception(f"GraphQL request failed: {response.status_code}")

        return response.json()

    def process_data(self, data: Dict[str, Any]) -> Dict[str, List]:
        repo_data = data["data"]["repository"]

        # Extract branch and tag mappings
        branch_map = {}
        tag_map = {}

        for ref in repo_data["refs"]:
            if ref["name"].startswith("refs/heads/"):
                branch_name = ref["name"].replace("refs/heads/", "")
                if ref["target"] and "oid" in ref["target"]:
                    branch_map[ref["target"]["oid"]] = branch_name

        for ref in repo_data["refs"]:
            if ref["name"].startswith("refs/tags/"):
                tag_name = ref["name"].replace("refs/tags/", "")
                target_oid = None
                if ref["target"]:
                    if "oid" in ref["target"]:
                        target_oid = ref["target"]["oid"]
                    elif "target" in ref["target"] and "oid" in ref["target"]["target"]:
                        target_oid = ref["target"]["target"]["oid"]
                if target_oid:
                    tag_map[target_oid] = tag_name

        # Process commits
        commits = []
        commit_edges = repo_data["ref"]["target"]["history"]["edges"]

        for edge in commit_edges:
            node = edge["node"]
            commit_sha = node["oid"]

            # Get branch and tag hints
            branch_hints = [branch_map.get(commit_sha, "")]
            tag_hints = [tag_map.get(commit_sha, "")]

            commit = Commit(
                sha=commit_sha,
                parents=[parent["oid"] for parent in node["parents"]["nodes"]],
                author={
                    "name": node["author"]["name"],
                    "email": node["author"]["email"],
                    "login": (
                        node["author"]["user"]["login"]
                        if node["author"]["user"]
                        else None
                    ),
                },
                date=node["committedDate"],
                message=f"{node['messageHeadline']}\n{node['messageBody']}".strip(),
                branchHints=[hint for hint in branch_hints if hint],
                tagHints=[hint for hint in tag_hints if hint],
            )
            commits.append(commit)

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
                issues=[
                    issue["number"]
                    for issue in pr_node["closingIssuesReferences"]["nodes"]
                ],
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
            "commits": [asdict(commit) for commit in commits],
            "prs": [asdict(pr) for pr in prs],
            "issues": [asdict(issue) for issue in issues],
            "fileDeltas": [],  # Will be populated by git diff analysis
            "hunks": [],  # Will be populated by git diff analysis
        }


def main():
    collector = GitOdysseyDataCollector()

    # Fetch data
    data = collector.fetch_data("wsulliv8", "raft-kv-store", "main")

    # Process data
    processed_data = collector.process_data(data)

    # Output results
    print(json.dumps(processed_data, indent=2))


if __name__ == "__main__":
    main()
