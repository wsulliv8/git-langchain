from typing import Dict, Any, List
import pygit2 as pg
from dataclasses import asdict
from config import CollectorConfig
from models import Commit, FileDelta, Hunk
from .base_ingester import BaseIngester
from utils.file_utils import detect_language


class GitLocalIngester(BaseIngester):
    def __init__(self, config: CollectorConfig):
        super().__init__(config)
        self.status_map = {
            pg.GIT_DELTA_UNMODIFIED: "Unmodified",
            pg.GIT_DELTA_ADDED: "Add",
            pg.GIT_DELTA_DELETED: "Del",
            pg.GIT_DELTA_MODIFIED: "Mod",
            pg.GIT_DELTA_RENAMED: "Rename",
            pg.GIT_DELTA_COPIED: "Copy",
            pg.GIT_DELTA_IGNORED: "Ignored",
            pg.GIT_DELTA_UNTRACKED: "Untracked",
            pg.GIT_DELTA_TYPECHANGE: "TypeChange",
            pg.GIT_DELTA_UNREADABLE: "Unreadable",
            pg.GIT_DELTA_CONFLICTED: "Conflicted",
        }

    def fetch(self) -> pg.Repository:
        """Use pygit2 to fetch local Git data"""
        try:
            repo = pg.Repository(self.config.repo_path)
        except pg.GitError as e:
            raise Exception(
                f"Could not open repository at {self.config.repo_path}: {e}"
            )

        return repo or None

    def parse(self, repo: pg.Repository) -> Dict[str, Any]:
        if repo is None:
            raise Exception("Repository is None")

        commits = []
        file_deltas = []
        hunks = []

        # Get all commits from all branches
        seen_commits = set()
        all_commits = []

        # Walk through origin branches only
        for branch_name in repo.branches.remote:
            try:
                branch_ref = repo.lookup_reference(f"refs/remotes/{branch_name}")
                branch_commit = branch_ref.peel(pg.Commit)
                # Walk from this branch tip
                for commit in repo.walk(branch_commit.id, pg.enums.SortMode.TIME):
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

                # Iterate over patches directly (each patch corresponds to a delta)
                for patch in diff:
                    delta = patch.delta
                    # Get line stats from the patch
                    additions = 0
                    deletions = 0

                    try:
                        line_stats = patch.line_stats
                        additions = line_stats[1]  # insertions
                        deletions = line_stats[2]  # deletions
                    except (pg.GitError, AttributeError):
                        # If we can't get line stats, use 0 for counts
                        pass

                    # Create FileDelta object
                    file_delta = FileDelta(
                        sha=str(commit.id),
                        pathOld=delta.old_file.path if delta.old_file.path else None,
                        pathNew=delta.new_file.path if delta.new_file.path else None,
                        status=self.status_map[delta.status],
                        lang=detect_language(
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
                    if entry.type == pg.GIT_OBJECT_BLOB:
                        file_delta = FileDelta(
                            sha=str(commit.id),
                            pathOld=None,
                            pathNew=entry.name,
                            status="Add",
                            lang=detect_language(entry.name),
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

    def _populate_branch_hints(self, repo: pg.Repository, commits: List[Commit]):
        """Populate branch hints for commits"""
        branch_map = {}

        # Get all branches
        for branch_name in repo.branches.remote:
            try:
                branch_ref = repo.lookup_reference(f"refs/remotes/{branch_name}")
                commit_id = branch_ref.peel(pg.Commit).id
                branch_map[str(commit_id)] = branch_name
            except pg.GitError:
                continue

        # Update commits with branch hints
        for commit in commits:
            if commit.sha in branch_map:
                commit.branchHints.append(branch_map[commit.sha])

    def _populate_tag_hints(self, repo: pg.Repository, commits: List[Commit]):
        """Populate tag hints for commits"""
        tag_map = {}

        # Get all tag references
        for ref_name in repo.references:
            if ref_name.startswith("refs/tags/"):
                try:
                    tag_ref = repo.lookup_reference(ref_name)
                    tag_name = ref_name.replace("refs/tags/", "")

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
