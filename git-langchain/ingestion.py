from typing import Iterator, List, Optional
import argparse
import pygit2
from enum import Enum
from pydantic import BaseModel, Field
import os


class DiffLine(BaseModel):
    """Represents a single line in a diff."""
    origin: str = Field(...,
                        description="Line origin: '+' added, '-' removed, ' ' context")
    content: str = Field(...,
                         description="Line content without trailing newline")
    old_lineno: Optional[int] = Field(
        None, description="Line number in old file (None for added lines)")
    new_lineno: Optional[int] = Field(
        None, description="Line number in new file (None for removed lines)")


class DiffHunk(BaseModel):
    """Represents a hunk (block of changes) in a diff."""
    old_start: int = Field(..., description="Starting line number in old file")
    old_lines: int = Field(..., description="Number of lines in old file")
    new_start: int = Field(..., description="Starting line number in new file")
    new_lines: int = Field(..., description="Number of lines in new file")
    lines: List[DiffLine] = Field(
        default_factory=list, description="List of lines in this hunk")


class FileChangeStatus(Enum):
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"
    RENAMED = "renamed"
    COPIED = "copied"

    def __str__(self) -> str:
        return self.value


class FileChange(BaseModel):
    """Represents a file change within a commit."""
    old_path: str = Field(...,
                          description="Path in the old version of the file")
    new_path: str = Field(...,
                          description="Path in the new version of the file")
    status: FileChangeStatus = Field(
        ..., description="Type of change (added, deleted, modified, renamed, copied)")
    hunks: List[DiffHunk] = Field(
        default_factory=list, description="List of hunks containing the actual changes")
    snapshot: Optional[str] = Field(
        None,
        description="Full file content snapshot. New version for existing files; old version for deletions.")


class Commit(BaseModel):
    """Represents a commit."""
    sha: str = Field(..., description="Full SHA hash of the commit")
    author: Optional[str] = Field(None, description="Author name")
    email: Optional[str] = Field(None, description="Author email")
    time: int = Field(...,
                      description="Commit timestamp in epoch seconds")
    message: str = Field(..., description="Commit message")
    file_changes: List[FileChange] = Field(
        default_factory=list, description="List of file changes in the commit")


def get_file_change_status(status: int) -> FileChangeStatus:
    if status == 1:
        return FileChangeStatus.ADDED
    elif status == 2:
        return FileChangeStatus.DELETED
    elif status == 3:
        return FileChangeStatus.MODIFIED
    elif status == 4:
        return FileChangeStatus.RENAMED
    elif status == 5:
        return FileChangeStatus.COPIED
    else:
        raise ValueError(f"Invalid status: {status}")


def get_snapshot(repo: pygit2.Repository, tree: pygit2.Tree, path: str) -> Optional[str]:
    """
    Retrieves the snapshot of a file from a tree.
    """
    try:
        parts = [p for p in path.split('/') if p]
        current = tree
        for idx, part in enumerate(parts):
            entry = current[part]
            obj = repo[entry.id]
            if idx < len(parts) - 1:
                if isinstance(obj, pygit2.Tree):
                    current = obj
                    continue
                else:
                    return None
            if hasattr(obj, 'data'):
                return obj.data.decode("utf-8", "replace")
            return None
    except Exception:
        return None


def get_commit_diffs(
    repo_path: str,
    ref: str = "HEAD",
    context_lines: int = 0,
    max_commits: int = None,
) -> Iterator[FileChange]:
    """
    Yields a CommitChange per file-change (patch) for every commit reachable from `ref`.
    Each CommitChange includes commit metadata, file delta info, and hunk ranges/lines.

    Args:
        repo_path: Path to the git repository
        ref: Git reference to start walking from (default: "HEAD")
        context_lines: Number of context lines to include in diffs
        max_commits: Maximum number of commits to process (None for unlimited)
    """
    repo = pygit2.Repository(repo_path)

    tip = repo.revparse_single(ref)  # e.g., "HEAD", "origin/main", a SHA
    sort = pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_REVERSE
    walker = repo.walk(tip.id, sort)

    for i, commit in enumerate(walker):
        if max_commits is not None and i >= max_commits:
            break

        # Compute the diff for this commit vs parent (or root)
        if commit.parents:
            diff = repo.diff(
                commit.parents[0], commit, context_lines=context_lines)
        else:
            # Root commit: diff the empty tree against commit.tree
            diff = commit.tree.diff_to_tree(context_lines=context_lines)

        author_name = commit.author.name if commit.author else None
        author_email = commit.author.email if commit.author else None
        commit_time = commit.commit_time
        commit_message = commit.message.strip() if commit.message else ""

        file_changes = []

        # Iterate over file patches
        for patch in diff:
            delta = patch.delta
            hunks = []

            for h in patch.hunks:
                lines = []
                for ln in h.lines:
                    content = (
                        ln.content.decode("utf-8", "replace")
                        if isinstance(ln.content, (bytes, bytearray))
                        else ln.content
                    )
                    lines.append(DiffLine(
                        origin=ln.origin,
                        content=content.rstrip("\n"),
                        old_lineno=ln.old_lineno,
                        new_lineno=ln.new_lineno,
                    ))

                hunks.append(DiffHunk(
                    old_start=h.old_start,
                    old_lines=h.old_lines,
                    new_start=h.new_start,
                    new_lines=h.new_lines,
                    lines=lines,
                ))

            # Determine which snapshot to display
            status_enum = get_file_change_status(delta.status)
            snapshot_text: Optional[str] = None
            if status_enum == FileChangeStatus.DELETED:
                # For deletions, the file exists in the parent tree
                if commit.parents:
                    parent_tree = commit.parents[0].tree
                    snapshot_text = get_snapshot(
                        repo, parent_tree, delta.old_file.path)
            else:
                # For adds/modifies/etc, take the new version from this commit
                snapshot_text = get_snapshot(
                    repo, commit.tree, delta.new_file.path)

            file_change = FileChange(
                old_path=delta.old_file.path,
                new_path=delta.new_file.path,
                status=status_enum,
                hunks=hunks,
                snapshot=snapshot_text,
            )
            file_changes.append(file_change)

        yield Commit(
            sha=str(commit.id),
            author=author_name,
            email=author_email,
            time=commit_time,
            message=commit_message,
            file_changes=file_changes
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo_path", type=str, required=True)
    parser.add_argument("--ref", type=str, required=False, default="HEAD")
    parser.add_argument("--max_commits", type=int, required=False, default=2)
    parser.add_argument("--context_lines", type=int, required=False, default=0)
    parser.add_argument("--output_dir", type=str, required=False,
                        help="Optional output directory to write results to", default="output")
    args = parser.parse_args()

    # Ensure output directory exists
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    # Determine output destination
    for commit in get_commit_diffs(args.repo_path, ref=args.ref, context_lines=args.context_lines, max_commits=args.max_commits):
        output_file = open(os.path.join(
            args.output_dir, f"{commit.sha[:8]}.txt"), 'w', encoding='utf-8')

        try:
            line = f"{commit.sha[:8]} - {commit.message}\n\n"
            output_file.write(line)

            for file_change in commit.file_changes:
                line = f" {file_change.status} - {file_change.old_path} -> {file_change.new_path}\n"
                output_file.write(line)

                # Write file snapshot before hunks
                if file_change.snapshot is not None:
                    output_file.write(" --- start snapshot ---\n")
                    output_file.write(file_change.snapshot)
                    if not file_change.snapshot.endswith("\n"):
                        output_file.write("\n")
                    output_file.write(" --- end snapshot ---\n\n")

                for hunk in file_change.hunks:
                    line = f" @@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@\n"
                    output_file.write(line)

                    for line_data in hunk.lines:
                        origin = line_data.origin
                        content = line_data.content
                        line = f"   {origin}{content}\n"
                        output_file.write(line)

                    output_file.write("\n")
                output_file.write(f"{'=' * 100}\n")
        finally:
            output_file.close()


if __name__ == "__main__":
    main()
