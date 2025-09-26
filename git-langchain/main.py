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
    merged_data = ingester.ingest()

    # Output results
    if config.output_file:
        with open(config.output_file, "w") as f:
            json.dump(merged_data, f, indent=2)
        print(f"Data written to {config.output_file}")
    else:
        print(json.dumps(merged_data, indent=2))


if __name__ == "__main__":
    main()
