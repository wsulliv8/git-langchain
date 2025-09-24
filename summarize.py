import requests
import os
from dotenv import load_dotenv
from pprint import pprint

load_dotenv()

URL = "https://api.github.com/graphql"
TOKEN = os.getenv("GITHUB_TOKEN")

with open("query.graphql", "r") as file:
    query = file.read()

variables = {
    "owner": "wsulliv8",
    "repoName": "raft-kv-store",
    "branchName": "main",
}

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

resp = requests.post(
    URL, headers=headers, json={"query": query, "variables": variables}
)

pprint(resp.json())
