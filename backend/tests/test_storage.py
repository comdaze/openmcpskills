"""Integration tests for Phase 3 storage services.

Tests S3SkillStore, MetadataStore, and InvocationLogger against
DynamoDB Local and LocalStack (or mocked via moto).
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

# Force local storage config for tests
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    """Create a minimal skill directory for testing."""
    skill_path = tmp_path / "test-skill"
    skill_path.mkdir()
    (skill_path / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\n---\n\n# Test Skill\n\nInstructions here.\n"
    )
    scripts = skill_path / "scripts"
    scripts.mkdir()
    (scripts / "main.py").write_text("print('hello')\n")
    return skill_path


class TestMetadataStore:
    """Tests for MetadataStore against DynamoDB."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set DynamoDB endpoint to local."""
        os.environ["DYNAMODB_ENDPOINT_URL"] = "http://localhost:8001"

    @pytest.mark.asyncio
    async def test_put_and_get_skill(self):
        from app.services.metadata_store import MetadataStore
        store = MetadataStore()
        await store.put_skill(
            "test-skill", name="test-skill", description="A test",
            version="v1", status="active", s3_key="skills/test-skill/v1/",
            manifest_json=json.dumps({"name": "test-skill"}),
            author="tester", tags=["test"],
        )
        result = await store.get_skill("test-skill")
        assert result is not None
        assert result["skill_id"] == "test-skill"
        assert result["version"] == "v1"
        assert result["status"] == "active"
        assert result["invocation_count"] == 0

    @pytest.mark.asyncio
    async def test_increment_invocation(self):
        from app.services.metadata_store import MetadataStore
        store = MetadataStore()
        await store.put_skill(
            "counter-skill", name="counter-skill", description="Count test",
            version="v1", status="active", s3_key="skills/counter-skill/v1/",
            manifest_json="{}",
        )
        await store.increment_invocation("counter-skill")
        await store.increment_invocation("counter-skill")
        result = await store.get_skill("counter-skill")
        assert result is not None
        assert result["invocation_count"] == 2
        assert "last_invoked_at" in result

    @pytest.mark.asyncio
    async def test_list_skills(self):
        from app.services.metadata_store import MetadataStore
        store = MetadataStore()
        await store.put_skill(
            "list-skill", name="list-skill", description="List test",
            version="v1", status="active", s3_key="x", manifest_json="{}",
        )
        results = await store.list_skills()
        ids = [r["skill_id"] for r in results]
        assert "list-skill" in ids

    @pytest.mark.asyncio
    async def test_delete_skill(self):
        from app.services.metadata_store import MetadataStore
        store = MetadataStore()
        await store.put_skill(
            "del-skill", name="del-skill", description="Delete test",
            version="v1", status="active", s3_key="x", manifest_json="{}",
        )
        await store.delete_skill("del-skill")
        result = await store.get_skill("del-skill")
        assert result is None


class TestInvocationLogger:
    """Tests for InvocationLogger against DynamoDB."""

    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ["DYNAMODB_ENDPOINT_URL"] = "http://localhost:8001"

    @pytest.mark.asyncio
    async def test_write_and_query(self):
        from app.services.invocation_logger import InvocationLogger
        logger = InvocationLogger()
        # Write directly (not fire-and-forget) for testing
        await logger._write(
            skill_id="log-test", session_id="sess-1", method="tools/call",
            duration_ms=42, status="success", error=None, params='{"a":1}',
        )
        logs = await logger.query_logs("log-test", limit=10)
        assert len(logs) >= 1
        assert logs[0]["skill_id"] == "log-test"
        assert logs[0]["method"] == "tools/call"
        assert logs[0]["duration_ms"] == 42


class TestS3SkillStore:
    """Tests for S3SkillStore against LocalStack."""

    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ["S3_ENDPOINT_URL"] = "http://localhost:4566"
        os.environ["S3_SKILLS_BUCKET"] = "mcp-skills-bucket"
        os.environ["SKILL_CACHE_DIR"] = tempfile.mkdtemp()

    @pytest.mark.asyncio
    async def test_upload_and_download(self, skill_dir: Path):
        from app.services.s3_store import S3SkillStore
        store = S3SkillStore()
        # Ensure bucket exists
        import aioboto3
        session = aioboto3.Session()
        async with session.client("s3", endpoint_url="http://localhost:4566", region_name="us-east-1") as s3:
            try:
                await s3.create_bucket(Bucket="mcp-skills-bucket")
            except Exception:
                pass

        prefix = await store.upload_skill("test-skill", "v1", skill_dir)
        assert "test-skill/v1/" in prefix

        local = await store.download_skill("test-skill", "v1")
        assert (local / "SKILL.md").exists()

    @pytest.mark.asyncio
    async def test_list_versions(self, skill_dir: Path):
        from app.services.s3_store import S3SkillStore
        store = S3SkillStore()
        import aioboto3
        session = aioboto3.Session()
        async with session.client("s3", endpoint_url="http://localhost:4566", region_name="us-east-1") as s3:
            try:
                await s3.create_bucket(Bucket="mcp-skills-bucket")
            except Exception:
                pass

        await store.upload_skill("ver-skill", "v1", skill_dir)
        await store.upload_skill("ver-skill", "v2", skill_dir)
        versions = await store.list_versions("ver-skill")
        assert "v1" in versions
        assert "v2" in versions
