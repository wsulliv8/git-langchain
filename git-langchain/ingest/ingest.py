from typing import Dict, Any
from config import CollectorConfig
from models import IngestData
from .ingest_api import GitAPIIngester
from .ingest_local import GitLocalIngester


class Ingester:
    def __init__(self, config: CollectorConfig):
        self.config = config
        self.api_ingester = GitAPIIngester(config)
        self.local_ingester = GitLocalIngester(config)

    def ingest(self) -> IngestData:
        """Ingest data from both GitHub API and local Git repository"""
        print("Ingesting data...")
        ingest_data = IngestData(
            APIData=self.api_ingester.ingest(),
            LocalData=self.local_ingester.ingest(),
        )

        print(
            f"Ingestion complete. Found {len(ingest_data.LocalData.Commits)} commits, "
            f"{len(ingest_data.APIData.PRs)} PRs, {len(ingest_data.APIData.Issues)} issues"
        )

        return ingest_data
