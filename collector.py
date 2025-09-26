import requests
import os
import json
import subprocess
import re
import sys
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import pygit2 as pg
from pygit2.enums import Delta

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

    def fetch_data_api(self, owner: str, repo_name: str) -> Dict[str, Any]:
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

        if "errors" in result:
            raise Exception(f"GraphQL errors: {result['errors']}")

        return result

    def fetch_data_local(self, repo_path: str = ".") -> Dict[str, Any]:
        """Use pygit2 to fetch local Git data"""
        try:
            repo = pg.Repository(repo_path)
        except pg.GitError as e:
            raise Exception(f"Could not open repository at {repo_path}: {e}")

        commits = []
        file_deltas = []
        hunks = []

        # Get all commits from all branches
        seen_commits = set()
        all_commits = []

        # Walk through origin branches only
        for branch in repo.branches.remote:
            try:
                branch_commit = branch.peel(pg.Commit)
                # Walk from this branch tip
                for commit in repo.walk(branch_commit.id, pg.SortMode.TIME):
                    commit_id = str(commit.id)
                    if commit_id not in seen_commits:
                        seen_commits.add(commit_id)
                        all_commits.append(commit)
            except pg.GitError:
                continue

        # Process all commits
        for commit in all_commits:
            # Create Commit object
            commit_obj = Commit(
                sha=str(commit.id),
                parents=[str(parent.id) for parent in commit.parents],
                author={
                    "name": commit.author.name,
                    "email": commit.author.email,
                },
                date=commit.commit_time,
                message=commit.message,
                branchHints=[],  # Will be populated by branch analysis
                tagHints=[],  # Will be populated by tag analysis
            )
            commits.append(commit_obj)

            # Get file deltas and hunks for this commit
            if commit.parents:
                # Compare with first parent
                parent = commit.parents[0]
                diff = repo.diff(parent, commit)

                for delta in diff.deltas:
                    # Get patch once and reuse for both stats and hunks
                    additions = 0
                    deletions = 0
                    patch = None

                    try:
                        patch = repo.diff(
                            parent, commit, delta.old_file.path, delta.new_file.path
                        )
                        # Use line_stats for efficient counting
                        line_stats = patch.line_stats
                        additions = line_stats[1]  # insertions
                        deletions = line_stats[2]  # deletions
                    except pg.GitError:
                        # If we can't get patch, use 0 for counts
                        pass

                    # Create FileDelta object
                    file_delta = FileDelta(
                        sha=str(commit.id),
                        pathOld=delta.old_file.path if delta.old_file.path else None,
                        pathNew=delta.new_file.path if delta.new_file.path else None,
                        status=self._get_delta_status(delta.status),
                        lang=self.detect_language(
                            delta.new_file.path or delta.old_file.path
                        ),
                        locAdd=additions,
                        locDel=deletions,
                    )
                    file_deltas.append(file_delta)

                    if patch:
                        for hunk in patch.hunks:
                            hunk_obj = Hunk(
                                sha=str(commit.id),
                                pathNew=delta.new_file.path or delta.old_file.path,
                                startOld=hunk.old_start,
                                lenOld=hunk.old_lines,
                                startNew=hunk.new_start,
                                lenNew=hunk.new_lines,
                                text=hunk.header
                                + "\n"
                                + "\n".join(line.content for line in hunk.lines),
                            )
                            hunks.append(hunk_obj)
            else:
                # Initial commit - all files are added
                tree = commit.tree
                for entry in tree:
                    if entry.type == pg.GIT_OBJ_BLOB:
                        file_delta = FileDelta(
                            sha=str(commit.id),
                            pathOld=None,
                            pathNew=entry.name,
                            status="Add",
                            lang=self.detect_language(entry.name),
                            locAdd=0,  # TODO: Count lines for initial commit
                            locDel=0,  # TODO: Count lines for initial commit
                        )
                        file_deltas.append(file_delta)

        # Get branch hints
        self._populate_branch_hints(repo, commits)

        # Get tag hints
        self._populate_tag_hints(repo, commits)

        return {
            "commits": [asdict(commit) for commit in commits],
            "fileDeltas": [asdict(delta) for delta in file_deltas],
            "hunks": [asdict(hunk) for hunk in hunks],
        }

    def _get_delta_status(self, status: int) -> str:
        """Convert pygit2 delta status to string"""
        status_map = {
            Delta.ADDED: "Add",
            Delta.DELETED: "Del",
            Delta.MODIFIED: "Mod",
            Delta.RENAMED: "Rename",
            Delta.COPIED: "Copy",
            Delta.IGNORED: "Ignored",
            Delta.UNTRACKED: "Untracked",
            Delta.TYPECHANGE: "TypeChange",
        }
        return status_map.get(status, "Mod")

    def _populate_branch_hints(self, repo: pg.Repository, commits: List[Commit]):
        """Populate branch hints for commits"""
        branch_map = {}

        # Get all branches
        for branch in repo.branches.remote:
            try:
                commit_id = branch.peel(pg.Commit).id
                branch_map[str(commit_id)] = branch.name
            except pg.GitError:
                continue

        # Update commits with branch hints
        for commit in commits:
            if commit.sha in branch_map:
                commit.branchHints.append(branch_map[commit.sha])

    def _populate_tag_hints(self, repo: pg.Repository, commits: List[Commit]):
        """Populate tag hints for commits"""
        tag_map = {}

        # Get all tags
        for tag_name in repo.tags:
            try:
                tag_ref = repo.lookup_reference(f"refs/tags/{tag_name}")
                if tag_ref.type == pg.GIT_REF_OID:
                    commit_id = tag_ref.peel(pg.Commit).id
                    tag_map[str(commit_id)] = tag_name
                elif tag_ref.type == pg.GIT_REF_SYMBOLIC:
                    # Handle annotated tags
                    target_ref = repo.lookup_reference(tag_ref.target)
                    if target_ref.type == pg.GIT_REF_OID:
                        commit_id = target_ref.peel(pg.Commit).id
                        tag_map[str(commit_id)] = tag_name
            except pg.GitError:
                continue

        # Update commits with tag hints
        for commit in commits:
            if commit.sha in tag_map:
                commit.tagHints.append(tag_map[commit.sha])

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
    data = collector.fetch_data_api("wsulliv8", "raft-kv-store")

    # Process data
    processed_data = collector.process_data(data)

    # Output results
    print(json.dumps(processed_data, indent=2))


if __name__ == "__main__":
    main()
