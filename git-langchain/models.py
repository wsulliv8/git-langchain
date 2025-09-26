from dataclasses import dataclass
from typing import Dict, List, Optional


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
