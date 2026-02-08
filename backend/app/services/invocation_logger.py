"""DynamoDB-based invocation log writer."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

import aioboto3

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class InvocationLogger:
    """Async invocation log writer to DynamoDB."""

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
        return self._settings.dynamodb_invocation_logs_table

    def log(self, skill_id: str, session_id: str, method: str,
            duration_ms: int, status: str, error: str | None = None,
            params: str | None = None) -> None:
        """Fire-and-forget log write. Non-blocking."""
        asyncio.create_task(self._write(skill_id, session_id, method, duration_ms, status, error, params))

    async def _write(self, skill_id: str, session_id: str, method: str,
                     duration_ms: int, status: str, error: str | None,
                     params: str | None) -> None:
        now = datetime.utcnow()
        invoked_at = f"{now.isoformat()}#{uuid.uuid4().hex[:8]}"
        ttl_days = self._settings.invocation_log_ttl_days
        expires = int((now + timedelta(days=ttl_days)).timestamp())

        item: dict = {
            "skill_id": {"S": skill_id},
            "invoked_at": {"S": invoked_at},
            "session_id": {"S": session_id},
            "method": {"S": method},
            "duration_ms": {"N": str(duration_ms)},
            "status": {"S": status},
            "expires_at": {"N": str(expires)},
        }
        if error:
            item["error_message"] = {"S": error[:1000]}
        if params:
            item["request_params"] = {"S": params[:1024]}

        try:
            async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
                await ddb.put_item(TableName=self._table, Item=item)
        except Exception as e:
            logger.error(f"Failed to write invocation log: {e}")

    async def query_logs(self, skill_id: str, limit: int = 50) -> list[dict]:
        """Query recent logs for a skill, newest first."""
        async with self._session.client("dynamodb", **self._client_kwargs()) as ddb:
            resp = await ddb.query(
                TableName=self._table,
                KeyConditionExpression="skill_id = :sid",
                ExpressionAttributeValues={":sid": {"S": skill_id}},
                ScanIndexForward=False,
                Limit=limit,
            )
        results = []
        for item in resp.get("Items", []):
            row: dict = {}
            for k, v in item.items():
                if "S" in v:
                    row[k] = v["S"]
                elif "N" in v:
                    row[k] = int(v["N"])
            results.append(row)
        return results
