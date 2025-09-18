import os
from dotenv import load_dotenv
from functools import lru_cache
from typing import Optional

from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name, default)
    return val


@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient:
    """Create (cached) MongoClient using env MONGODB_URI, tuned for Atlas.

    Env:
      - MONGODB_URI: e.g., mongodb+srv://<user>:<pass>@<cluster>/?retryWrites=true&w=majority
      - MONGODB_TIMEOUT_MS (optional): server selection timeout in ms (default 5000)
    """
    load_dotenv()
    uri = _get_env("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is not set")

    timeout_ms = int(_get_env("MONGODB_TIMEOUT_MS", "5000"))
    client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
    # Validate connectivity early
    try:
        client.admin.command("ping")
    except ServerSelectionTimeoutError as e:
        raise RuntimeError(f"Cannot connect to MongoDB: {e}")
    return client


def get_db_name() -> str:
    name = _get_env("MONGODB_DB_NAME", "slide_agents")
    return name


def get_db():
    return get_mongo_client()[get_db_name()]


def close_client():
    client = get_mongo_client.cache_info()
    # lru_cache doesn't expose the instance; just ignore. Clients typically
    # are long-lived for app lifecycle; no-op here.
    pass
