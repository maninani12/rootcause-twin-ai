"""Synchronous memory operations supported by hindsight-client 0.10.2."""

import os
from pathlib import Path

from dotenv import load_dotenv
from hindsight_client import Hindsight


def _client() -> tuple[Hindsight, str]:
    # Resolve .env relative to this project, regardless of the working directory.
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    api_key = os.getenv("HINDSIGHT_API_KEY", "").strip()
    if not api_key or api_key == "your_hindsight_api_key_here":
        raise ValueError(
            "HINDSIGHT_API_KEY is missing. Copy .env.example to .env and set "
            "your real Hindsight API key locally. Never commit .env."
        )
    base_url = os.getenv(
        "HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io"
    ).strip()
    bank_id = os.getenv("HINDSIGHT_BANK_ID", "rootcause-twin").strip()
    if not base_url or not bank_id:
        raise ValueError("HINDSIGHT_BASE_URL and HINDSIGHT_BANK_ID must not be blank.")
    return Hindsight(base_url=base_url, api_key=api_key), bank_id


def retain_incident(content: str):
    """Store incident evidence and return the SDK RetainResponse."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Incident content must be a non-empty string.")
    client, bank_id = _client()
    try:
        return client.retain(bank_id=bank_id, content=content, retain_async=False)
    finally:
        client.close()


def recall_incidents(query: str):
    """Retrieve relevant memories and return the SDK RecallResponse."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Recall query must be a non-empty string.")
    client, bank_id = _client()
    try:
        return client.recall(bank_id=bank_id, query=query, include_chunks=True)
    finally:
        client.close()
