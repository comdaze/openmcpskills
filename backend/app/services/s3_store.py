"""S3-based skill package storage with versioning."""

import json
import logging
from pathlib import Path

import aioboto3

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class S3SkillStore:
    """Upload/download/version skill packages in S3."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._session = aioboto3.Session()

    def _client_kwargs(self) -> dict:
        kw: dict = {"region_name": self._settings.aws_region}
        if self._settings.s3_endpoint_url:
            kw["endpoint_url"] = self._settings.s3_endpoint_url
        return kw

    @property
    def _bucket(self) -> str:
        return self._settings.s3_skills_bucket

    def _skill_prefix(self, skill_id: str, version: str) -> str:
        return f"{self._settings.s3_skills_prefix}{skill_id}/{version}/"

    def _latest_key(self, skill_id: str) -> str:
        return f"{self._settings.s3_skills_prefix}{skill_id}/latest.json"

    async def upload_skill(self, skill_id: str, version: str, local_path: Path) -> str:
        """Upload a skill directory to S3. Returns the S3 prefix."""
        prefix = self._skill_prefix(skill_id, version)
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            for file_path in local_path.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith("."):
                    key = prefix + str(file_path.relative_to(local_path))
                    await s3.upload_file(str(file_path), self._bucket, key)
                    logger.debug(f"Uploaded {key}")

            # Update latest.json
            latest = json.dumps({"version": version}).encode()
            await s3.put_object(Bucket=self._bucket, Key=self._latest_key(skill_id), Body=latest)

        logger.info(f"Uploaded skill {skill_id} {version} to s3://{self._bucket}/{prefix}")
        return prefix

    async def download_skill(self, skill_id: str, version: str | None = None) -> Path:
        """Download a skill to local cache. Returns local path."""
        cache_dir = self._settings.skill_cache_dir
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            # Resolve version
            if version is None:
                try:
                    resp = await s3.get_object(Bucket=self._bucket, Key=self._latest_key(skill_id))
                    data = json.loads(await resp["Body"].read())
                    version = data["version"]
                except Exception:
                    version = "v1"

            prefix = self._skill_prefix(skill_id, version)
            local_path = cache_dir / skill_id
            local_path.mkdir(parents=True, exist_ok=True)

            resp = await s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
            for obj in resp.get("Contents", []):
                rel = obj["Key"][len(prefix):]
                if not rel:
                    continue
                dest = local_path / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                await s3.download_file(self._bucket, obj["Key"], str(dest))

        return local_path

    async def list_versions(self, skill_id: str) -> list[str]:
        """List all versions of a skill."""
        prefix = f"{self._settings.s3_skills_prefix}{skill_id}/"
        versions: list[str] = []
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            resp = await s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix, Delimiter="/")
            for cp in resp.get("CommonPrefixes", []):
                v = cp["Prefix"][len(prefix):].rstrip("/")
                if v.startswith("v"):
                    versions.append(v)
        return sorted(versions)

    async def sync_all_to_local(self) -> int:
        """Download all latest skills to local cache. Returns count."""
        cache_dir = self._settings.skill_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        prefix = self._settings.s3_skills_prefix
        count = 0

        async with self._session.client("s3", **self._client_kwargs()) as s3:
            # List skill directories
            skill_ids: list[str] = []
            try:
                resp = await s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix, Delimiter="/")
                logger.info(f"S3 list response: CommonPrefixes={resp.get('CommonPrefixes', [])}")
                for cp in resp.get("CommonPrefixes", []):
                    sid = cp["Prefix"][len(prefix):].rstrip("/")
                    if sid:
                        skill_ids.append(sid)
            except Exception as e:
                logger.error(f"Failed to list S3 skills: {e}")
                return 0

        logger.info(f"Found {len(skill_ids)} skills in S3: {skill_ids}")
        for sid in skill_ids:
            try:
                await self.download_skill(sid)
                count += 1
            except Exception as e:
                logger.error(f"Failed to sync skill {sid}: {e}")

        logger.info(f"Synced {count} skills from S3 to {cache_dir}")
        return count

    async def delete_version(self, skill_id: str, version: str) -> bool:
        """Delete a specific version of a skill from S3."""
        prefix = self._skill_prefix(skill_id, version)
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            resp = await s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
            for obj in resp.get("Contents", []):
                await s3.delete_object(Bucket=self._bucket, Key=obj["Key"])
        return True
