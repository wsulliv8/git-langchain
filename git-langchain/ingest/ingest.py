from typing import Dict, Any
from config import CollectorConfig
from models import IngestData
from .ingest_api import GitAPIIngester
from .ingest_local import GitLocalIngester
from .base_ingester import BaseIngester


class Ingester(BaseIngester):
    def __init__(self, config: CollectorConfig):
        super().__init__(config)
        self.ingest_api = GitAPIIngester(config)
        self.ingest_local = GitLocalIngester(config)

    def ingest(self) -> Dict[str, Any]:
        """Ingest data from both GitHub API and local Git repository"""
        print("Ingesting data...")
        ingest_data = IngestData(
            APIData=self.ingest_api.ingest(),
            LocalData=self.ingest_local.ingest(),
        )

        print(
            f"Ingestion complete. Found {len(ingest_data.LocalData.Commits)} commits, "
            f"{len(ingest_data.APIData.PRs)} PRs, {len(ingest_data.APIData.Issues)} issues"
        )

        return ingest_data

    def fetch(self) -> None:
        """Not used in composite ingester - delegates to sub-ingesters"""
        pass

    def parse(self, data: None) -> Dict[str, Any]:
        """Not used in composite ingester - delegates to sub-ingesters"""
        return {}
