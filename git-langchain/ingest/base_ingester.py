from abc import ABC, abstractmethod
from typing import Dict, Any
from config import CollectorConfig


class BaseIngester(ABC):
    """Abstract base class for all ingesters"""

    def __init__(self, config: CollectorConfig):
        self.config = config

    def ingest(self) -> Dict[str, Any]:
        """Main ingestion method - template method pattern"""
        data = self.fetch()
        return self.parse(data)

    @abstractmethod
    def fetch(self) -> Any:
        """Fetch raw data from the source"""
        pass

    @abstractmethod
    def parse(self, data: Any) -> Dict[str, Any]:
        """Parse raw data into structured format"""
        pass
