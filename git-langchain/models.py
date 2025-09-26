from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class Commit(BaseModel):
    sha: str
    parents: List[str]
    author: Dict[str, str]
    date: str
    message: str
    branchHints: List[str] = Field(default_factory=list)
    tagHints: List[str] = Field(default_factory=list)


class FileDelta(BaseModel):
    sha: str
    pathOld: Optional[str] = None
    pathNew: Optional[str] = None
    status: str = Field(description="Add/Mod/Del/Rename")
    lang: Optional[str] = None
    locAdd: int = 0
    locDel: int = 0


class Hunk(BaseModel):
    sha: str
    pathNew: str
    startOld: int
    lenOld: int
    startNew: int
    lenNew: int
    text: str


class PR(BaseModel):
    id: int
    title: str
    body: str
    state: str
    createdAt: str
    mergedAt: Optional[str] = None
    commits: List[str] = Field(default_factory=list)
    issues: List[int] = Field(default_factory=list)


class Issue(BaseModel):
    id: int
    title: str
    body: str
    labels: List[str] = Field(default_factory=list)
    closedAt: Optional[str] = None


class APIData(BaseModel):
    PRs: List[PR]
    Issues: List[Issue]


class LocalData(BaseModel):
    Commits: List[Commit]
    FileDeltas: List[FileDelta]
    Hunks: List[Hunk]


class IngestData(BaseModel):
    APIData: APIData
    LocalData: LocalData
