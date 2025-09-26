from typing import Dict, Any, List
from config import CollectorConfig
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
        print("Ingesting GitHub API data...")
        api_data = self.ingest_api.ingest()

        print("Ingesting local Git data...")
        local_data = self.ingest_local.ingest()

        # Merge the data
        merged_data = {
            **api_data,
            **local_data,
        }

        print(
            f"Ingestion complete. Found {len(merged_data.get('commits', []))} commits, "
            f"{len(merged_data.get('prs', []))} PRs, {len(merged_data.get('issues', []))} issues"
        )

        return merged_data

    def fetch(self) -> None:
        """Not used in composite ingester - delegates to sub-ingesters"""
        pass

    def parse(self, data: None) -> Dict[str, Any]:
        """Not used in composite ingester - delegates to sub-ingesters"""
        return {}
