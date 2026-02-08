"""DynamoDB-based skill metadata storage."""

import json
import logging
from datetime import datetime

import aioboto3

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class MetadataStore:
    """CRUD for skill metadata in DynamoDB, plus atomic invocation counting."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._session = aioboto3.Session()

    def _client_kwargs(self) -> dict:
        kw: dict = {"region_name": self._settings.aws_region}
        if self._settings.dynamodb_endpoint_url:
            kw["endpoint_url"] = self._settings.dynamodb_endpoint_url
        return kw

    @property
    def _table(self) -> str:
        return self._settings.dynamodb_skills_table

    async def put_skill(self, skill_id: str, *, name: str, description: str,
                        version: str, status: str, s3_key: str,
                        manifest_json: str, author: str | None = None,
                        tags: list[str] | None = None) -> None:
        now = datetime.utcnow().isoformat()
        item: dict = {
            "skill_id": {"S": skill_id},
            "name": {"S": name},
            "description": {"S": description},
            "version": {"S": version},
            "status": {"S": status},
            "s3_key": {"S": s3_key},
            "manifest_json": {"S": manifest_json},
            "updated_at": {"S": now},
            "invocation_count": {"N": "0"},
        }
        if author:
            item["author"] = {"S": author}
        if tags:
            item["tags"] = {"L": [{"S": t} for t in tags]}

        # Preserve created_at if exists
        existing = await self.get_skill(skill_id)
        item["created_at"] = {"S": existing["created_at"] if existing else now}
        if existing and "invocation_count" in existing:
            item["invocation_count"] = {"N": str(existing["invocation_count"])}

        # Preserve all_versions
        all_versions = existing.get("all_versions", []) if existing else []
        if version not in all_versions:
            all_versions.append(version)
        item["all_versions"] = {"L": [{"S": v} for v in all_versions]}

        async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
            await ddb.put_item(TableName=self._table, Item=item)

    async def get_skill(self, skill_id: str) -> dict | None:
        async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
            resp = await ddb.get_item(TableName=self._table, Key={"skill_id": {"S": skill_id}})
        item = resp.get("Item")
        if not item:
            return None
        return self._deserialize(item)

    async def list_skills(self, status: str | None = None) -> list[dict]:
        async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
            if status:
                resp = await ddb.query(
                    TableName=self._table,
                    IndexName="status-index",
                    KeyConditionExpression="#s = :s",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":s": {"S": status}},
                )
            else:
                resp = await ddb.scan(TableName=self._table)
        return [self._deserialize(i) for i in resp.get("Items", [])]

    async def delete_skill(self, skill_id: str) -> bool:
        async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
            await ddb.delete_item(TableName=self._table, Key={"skill_id": {"S": skill_id}})
        return True

    async def increment_invocation(self, skill_id: str) -> None:
        now = datetime.utcnow().isoformat()
        async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
            await ddb.update_item(
                TableName=self._table,
                Key={"skill_id": {"S": skill_id}},
                UpdateExpression="ADD invocation_count :one SET last_invoked_at = :now, updated_at = :now",
                ExpressionAttributeValues={":one": {"N": "1"}, ":now": {"S": now}},
            )

    @staticmethod
    def _deserialize(item: dict) -> dict:
        """Simple DynamoDB item → plain dict."""
        out: dict = {}
        for k, v in item.items():
            if "S" in v:
                out[k] = v["S"]
            elif "N" in v:
                out[k] = int(v["N"])
            elif "L" in v:
                out[k] = [i.get("S", "") for i in v["L"]]
            elif "BOOL" in v:
                out[k] = v["BOOL"]
            elif "NULL" in v:
                out[k] = None
        return out
