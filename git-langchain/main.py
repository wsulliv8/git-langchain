import json
from config import CollectorConfig
from ingest.ingest import Ingester


def main():
    # Load and validate configuration
    config = CollectorConfig.from_env()

    print(
        f"Starting Git Odyssey data collection for {config.repo_owner}/{config.repo_name}"
    )
    print(f"Repository path: {config.repo_path}")

    # Initialize ingester with config
    ingester = Ingester(config)

    # Ingest all data
    ingest_data = ingester.ingest()

    # Output results - serialize IngestData for JSON output
    if config.output_file:
        with open(config.output_file, "w") as f:
            json.dump(ingest_data.model_dump(), f, indent=2)
        print(f"Data written to {config.output_file}")
    else:
        print(json.dumps(ingest_data.model_dump(), indent=2))


if __name__ == "__main__":
    main()
