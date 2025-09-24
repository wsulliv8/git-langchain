import requests
import os
import json
import subprocess
import re
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
        self.url = "https://api.github.com/"
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
        query = self.load_query("query.graphql")
        variables = {
            "owner": owner,
            "repoName": repo_name,
            "branchName": branch_name,
        }
        response = requests.post(
            self.url + "graphql",
            headers=self.headers,
            json={"query": query, "variables": variables},
        )

        if response.status_code != 200:
            raise Exception(f"GraphQL request failed: {response.status_code}")

        return response.json()

    def fetch_diffs(
        self, owner: str, repo_name: str, commit_sha: str
    ) -> Dict[str, Any]:
        response = requests.get(
            self.url + f"repos/{owner}/{repo_name}/commits/{commit_sha}",
            headers=self.headers,
        )

        if response.status_code != 200:
            raise Exception(f"REST request failed: {response.status_code}")

        return response.json().get("files", [])

    def get_file_extension(self, filepath: str) -> Optional[str]:
        """Extract file extension for language detection"""
        if not filepath or "." not in filepath:
            return None
        return filepath.split(".")[-1].lower()

    def detect_language(self, filepath: str) -> Optional[str]:
        """Simple language detection based on file extension"""
        ext = self.get_file_extension(filepath)
        lang_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "java": "java",
            "cpp": "cpp",
            "c": "c",
            "go": "go",
            "rs": "rust",
            "rb": "ruby",
            "php": "php",
            "swift": "swift",
            "kt": "kotlin",
            "scala": "scala",
            "sh": "shell",
            "bash": "shell",
            "sql": "sql",
            "html": "html",
            "css": "css",
            "json": "json",
            "xml": "xml",
            "yaml": "yaml",
            "yml": "yaml",
            "md": "markdown",
            "txt": "text",
        }
        return lang_map.get(ext)

    def parse_file_delta(self, file_data: Dict[str, Any], commit_sha: str) -> FileDelta:
        """Parse GitHub API file data into FileDelta object"""
        status_map = {
            "added": "Add",
            "modified": "Mod",
            "removed": "Del",
            "renamed": "Rename",
        }

        return FileDelta(
            sha=commit_sha,
            pathOld=file_data.get("previous_filename"),
            pathNew=file_data.get("filename"),
            status=status_map.get(file_data.get("status", ""), "Mod"),
            lang=self.detect_language(file_data.get("filename", "")),
            locAdd=file_data.get("additions", 0),
            locDel=file_data.get("deletions", 0),
        )

    def parse_hunks(
        self, patch_content: str, commit_sha: str, filepath: str
    ) -> List[Hunk]:
        """Parse patch content into Hunk objects"""
        hunks = []

        if not patch_content:
            return hunks

        # Split patch into individual hunks
        hunk_pattern = r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
        hunk_matches = list(re.finditer(hunk_pattern, patch_content))

        for i, match in enumerate(hunk_matches):
            start_old = int(match.group(1))
            len_old = int(match.group(2)) if match.group(2) else 1
            start_new = int(match.group(3))
            len_new = int(match.group(4)) if match.group(4) else 1

            # Extract the hunk content
            start_pos = match.end()
            end_pos = (
                hunk_matches[i + 1].start()
                if i + 1 < len(hunk_matches)
                else len(patch_content)
            )
            hunk_text = patch_content[start_pos:end_pos].strip()

            hunk = Hunk(
                sha=commit_sha,
                pathNew=filepath,
                startOld=start_old,
                lenOld=len_old,
                startNew=start_new,
                lenNew=len_new,
                text=hunk_text,
            )
            hunks.append(hunk)

        return hunks

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
        file_deltas = []
        hunks = []
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

            # Fetch and process diffs for this commit
            try:
                files_data = self.fetch_diffs("wsulliv8", "raft-kv-store", commit_sha)

                for file_data in files_data:
                    # Create FileDelta
                    file_delta = self.parse_file_delta(file_data, commit_sha)
                    file_deltas.append(file_delta)

                    # Create Hunks from patch content
                    patch_content = file_data.get("patch", "")
                    file_hunks = self.parse_hunks(
                        patch_content, commit_sha, file_data.get("filename", "")
                    )
                    hunks.extend(file_hunks)

            except Exception as e:
                print(f"Warning: Could not fetch diffs for commit {commit_sha}: {e}")
                continue

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
            "fileDeltas": [asdict(delta) for delta in file_deltas],
            "hunks": [asdict(hunk) for hunk in hunks],
        }


def main():
    collector = GitOdysseyDataCollector()

    # Fetch data
    data = collector.fetch_data("wsulliv8", "go-raft", "main")

    # Process data
    processed_data = collector.process_data(data)

    # Output results
    print(json.dumps(processed_data, indent=2))


if __name__ == "__main__":
    main()
