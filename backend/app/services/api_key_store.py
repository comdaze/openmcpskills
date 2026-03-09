"""DynamoDB-based API key storage with SHA-256 hashing.

Keys are stored as SHA-256 hashes. The raw key is only returned at generation
time and is never persisted. An in-memory hash→id cache speeds up verification.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

import aioboto3

from app.core.config import get_settings

logger = logging.getLogger(__name__)

KEY_PREFIX = "sk-mcp-"


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


class ApiKeyStore:
    """Persistent API key storage backed by DynamoDB."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._session = aioboto3.Session()
        # hash → api_key_id cache for O(1) verification
        self._cache: dict[str, str] = {}

    def _client_kwargs(self) -> dict:
        kw: dict = {"region_name": self._settings.aws_region}
        if self._settings.dynamodb_endpoint_url:
            kw["endpoint_url"] = self._settings.dynamodb_endpoint_url
        return kw

    @property
    def _table(self) -> str:
        return self._settings.dynamodb_api_keys_table

    async def _ensure_table(self, ddb) -> None:
        """Create the table if it doesn't exist."""
        try:
            await ddb.describe_table(TableName=self._table)
        except ddb.exceptions.ResourceNotFoundException:
            logger.info("Creating DynamoDB table %s", self._table)
            await ddb.create_table(
                TableName=self._table,
                KeySchema=[{"AttributeName": "api_key_id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "api_key_id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            waiter = ddb.get_waiter("table_exists")
            await waiter.wait(TableName=self._table)
            logger.info("Table %s created", self._table)

    async def load_all(self) -> int:
        """Load all active key hashes into the in-memory cache. Returns count."""
        self._cache.clear()
        async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
            await self._ensure_table(ddb)
            resp = await ddb.scan(
                TableName=self._table,
                ProjectionExpression="api_key_id, hashed_key, #s",
                ExpressionAttributeNames={"#s": "status"},
            )
            for item in resp.get("Items", []):
                status = item.get("status", {}).get("S", "active")
                if status == "active":
                    hashed = item["hashed_key"]["S"]
                    key_id = item["api_key_id"]["S"]
                    self._cache[hashed] = key_id
        logger.info("Loaded %d API keys from DynamoDB", len(self._cache))
        return len(self._cache)

    async def generate_key(self, name: str) -> dict:
        """Generate a new API key. Returns dict with raw key (shown once) and metadata."""
        raw_key = f"{KEY_PREFIX}{secrets.token_hex(16)}"
        hashed = _hash_key(raw_key)
        key_id = f"key_{secrets.token_hex(8)}"
        now = datetime.now(timezone.utc).isoformat()

        item = {
            "api_key_id": {"S": key_id},
            "hashed_key": {"S": hashed},
            "key_prefix": {"S": raw_key[:12] + "..."},
            "name": {"S": name},
            "created_at": {"S": now},
            "last_used_at": {"S": "never"},
            "status": {"S": "active"},
        }

        async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
            await ddb.put_item(TableName=self._table, Item=item)

        self._cache[hashed] = key_id
        logger.info("Generated API key %s (%s)", key_id, name)

        return {
            "api_key_id": key_id,
            "raw_key": raw_key,
            "key_prefix": raw_key[:12] + "...",
            "name": name,
            "created_at": now,
        }

    async def verify_key(self, raw_key: str) -> Optional[str]:
        """Verify a raw key against the cache. Returns api_key_id or None."""
        hashed = _hash_key(raw_key)
        key_id = self._cache.get(hashed)
        if key_id:
            # Update last_used_at in background (best effort)
            try:
                now = datetime.now(timezone.utc).isoformat()
                async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
                    await ddb.update_item(
                        TableName=self._table,
                        Key={"api_key_id": {"S": key_id}},
                        UpdateExpression="SET last_used_at = :now",
                        ExpressionAttributeValues={":now": {"S": now}},
                    )
            except Exception:
                pass  # non-critical
        return key_id

    async def list_keys(self) -> list[dict]:
        """List all keys (prefix only, no hashes)."""
        async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
            resp = await ddb.scan(TableName=self._table)
        keys = []
        for item in resp.get("Items", []):
            keys.append({
                "api_key_id": item.get("api_key_id", {}).get("S", ""),
                "key_prefix": item.get("key_prefix", {}).get("S", ""),
                "name": item.get("name", {}).get("S", ""),
                "created_at": item.get("created_at", {}).get("S", ""),
                "last_used_at": item.get("last_used_at", {}).get("S", ""),
                "status": item.get("status", {}).get("S", ""),
            })
        return keys

    async def revoke_key(self, api_key_id: str) -> bool:
        """Revoke a key by ID. Returns True if found and revoked."""
        async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
            # Get the hashed_key so we can remove from cache
            resp = await ddb.get_item(
                TableName=self._table,
                Key={"api_key_id": {"S": api_key_id}},
            )
            item = resp.get("Item")
            if not item:
                return False

            # Update status to revoked
            await ddb.update_item(
                TableName=self._table,
                Key={"api_key_id": {"S": api_key_id}},
                UpdateExpression="SET #s = :revoked",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":revoked": {"S": "revoked"}},
            )

        # Remove from cache
        hashed = item.get("hashed_key", {}).get("S", "")
        self._cache.pop(hashed, None)
        logger.info("Revoked API key %s", api_key_id)
        return True

    @property
    def active_count(self) -> int:
        return len(self._cache)


# Module-level singleton
_api_key_store: Optional[ApiKeyStore] = None


def get_api_key_store() -> Optional[ApiKeyStore]:
    return _api_key_store


def set_api_key_store(store: ApiKeyStore) -> None:
    global _api_key_store
    _api_key_store = store
