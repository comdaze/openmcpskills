"""AWS Bedrock AgentCore Code Interpreter Service.

Provides sandboxed code execution capabilities for MCP Skills
using AWS Bedrock AgentCore Code Interpreter.
Supports uploading generated files to S3 via execution role.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import string
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings


def generate_short_id(length: int = 8) -> str:
    """Generate a URL-safe short ID without problematic characters."""
    # Use only alphanumeric chars - no underscore, dash, or special chars
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

logger = logging.getLogger(__name__)


class NetworkMode(str, Enum):
    """Sandbox network mode."""
    SANDBOX = "SANDBOX"
    PUBLIC = "PUBLIC"


class ExecutionStatus(str, Enum):
    """Code execution status."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class ExecutionResult:
    """Code execution result."""
    status: ExecutionStatus
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    output_files: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "output_files": self.output_files,
        }


@dataclass
class UploadFile:
    """File to upload to sandbox."""
    name: str
    content: bytes
    mime_type: str = "application/octet-stream"


class CodeInterpreterService:
    """AWS Bedrock AgentCore Code Interpreter service.

    Uses custom Code Interpreter with execution role for S3 access.
    Generated files are uploaded to S3 via terminal commands in sandbox.
    """

    MAX_FILE_SIZE = 100 * 1024 * 1024

    # File extensions considered as final output artifacts.
    # Intermediate files (e.g. .json, .xml, .txt temp files) are excluded.
    OUTPUT_EXTENSIONS = {
        ".pptx", ".docx", ".xlsx", ".xlsm", ".pdf",
        ".csv", ".tsv",
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp",
        ".html", ".htm",
        ".zip", ".tar", ".gz",
        ".mp3", ".mp4", ".wav",
    }

    def __init__(
        self,
        region: str | None = None,
        code_interpreter_id: str | None = None,
        default_timeout: int = 300,
        session_timeout: int = 900,
        s3_bucket: str = "",
        s3_prefix: str = "output_artifacts/",
    ) -> None:
        settings = get_settings()
        self.region = region or settings.aws_region
        self.code_interpreter_id = code_interpreter_id or settings.code_interpreter_id
        self.default_timeout = default_timeout
        self.session_timeout = session_timeout
        self.s3_bucket = s3_bucket or settings.code_interpreter_s3_bucket
        self.s3_prefix = s3_prefix or settings.code_interpreter_s3_prefix
        self._client = None
        self._session_lock = asyncio.Lock()

    @property
    def client(self):
        if self._client is None:
            from botocore.config import Config
            self._client = boto3.client(
                "bedrock-agentcore",
                region_name=self.region,
                config=Config(read_timeout=self.default_timeout + 30),
            )
        return self._client

    def _run_command(self, session_id: str, command: str) -> dict[str, Any]:
        """Execute a terminal command in the sandbox session."""
        resp = self.client.invoke_code_interpreter(
            codeInterpreterIdentifier=self.code_interpreter_id,
            sessionId=session_id,
            name="executeCommand",
            arguments={"command": command},
        )
        stdout, stderr, exit_code = "", "", 0
        for event in resp.get("stream", []):
            sc = event.get("result", {}).get("structuredContent", {})
            stdout += sc.get("stdout", "")
            stderr += sc.get("stderr", "")
            exit_code = sc.get("exitCode", exit_code)
        return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}

    def _upload_to_s3(self, session_id: str, filename: str, skill_id: str) -> dict[str, str] | None:
        """Upload a file from sandbox to S3 via aws cli in sandbox.

        filename can be a relative name or full path (e.g. /tmp/output.pptx).
        """
        if not self.s3_bucket:
            return None
        basename = filename.split("/")[-1]
        s3_key = f"{self.s3_prefix}{skill_id}/{int(time.time())}_{basename}"
        s3_uri = f"s3://{self.s3_bucket}/{s3_key}"
        result = self._run_command(session_id, f"aws s3 cp '{filename}' '{s3_uri}'")
        if result["exit_code"] == 0:
            logger.info(f"Uploaded {filename} to {s3_uri}")
            settings = get_settings()
            server_url = settings.mcp_server_url
            # Remove trailing /mcp path to get the base URL
            if server_url.endswith("/mcp"):
                base_url = server_url[:-4]
            else:
                base_url = server_url.rstrip("/")
            
            # Generate short link ID and store mapping in DynamoDB
            short_id = generate_short_id(8)
            try:
                dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
                table = dynamodb.Table(settings.dynamodb_sessions_table)
                table.put_item(Item={
                    "session_id": f"file:{short_id}",
                    "s3_key": s3_key,
                    "s3_bucket": self.s3_bucket,
                    "filename": basename,
                    "created_at": int(time.time()),
                    "ttl": int(time.time()) + 86400 * 30,  # 30 days expiry
                })
                # Use short URL format: /admin/f/{short_id}
                download_url = f"{base_url}/admin/f/{short_id}"
                logger.info(f"Created short link: {download_url} -> {s3_key}")
            except Exception as e:
                # Fall back to long URL if DynamoDB fails
                logger.warning(f"Failed to create short link, using long URL: {e}")
                from urllib.parse import quote
                download_url = f"{base_url}/admin/files/stream?s3_key={quote(s3_key, safe='/_')}"
            
            return {
                "filename": filename,
                "s3_uri": s3_uri,
                "s3_bucket": self.s3_bucket,
                "s3_key": s3_key,
                "download_url": download_url,
            }
        else:
            logger.error(f"S3 upload failed: {result['stderr']}")
            return None

    def _preload_skill_files(self, session_id: str, source_path: str) -> bool:
        """Pre-load skill's bundled files into sandbox at /skill/ directory.

        Creates a tar.gz archive of the skill directory, embeds it as
        base64 inside a single Python snippet executed via ``executeCode``,
        which decodes and extracts it in one API call.
        """
        import base64
        import io
        import tarfile
        from pathlib import Path

        preload_start = time.monotonic()

        skill_dir = Path(source_path)
        if not skill_dir.exists():
            logger.warning(f"Skill source path not found: {source_path}")
            return False

        # Build tar.gz in memory
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for file_path in sorted(skill_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                rel = file_path.relative_to(skill_dir)
                # Skip hidden files, __pycache__, .pyc
                if any(p.startswith(".") or p == "__pycache__" for p in rel.parts):
                    continue
                if file_path.suffix == ".pyc":
                    continue
                tar.add(str(file_path), arcname=str(Path("skill") / rel))

        tar_bytes = buf.getvalue()

        # Safety limit: skip if archive > 5 MB
        if len(tar_bytes) > 5 * 1024 * 1024:
            logger.warning(
                f"Skill archive too large ({len(tar_bytes)} bytes), skipping preload"
            )
            return False

        b64_data = base64.b64encode(tar_bytes).decode("ascii")

        # Single executeCode call: decode + extract in one shot
        extract_code = (
            "import base64, io, tarfile, os\n"
            f"data = base64.b64decode('{b64_data}')\n"
            "tar = tarfile.open(fileobj=io.BytesIO(data), mode='r:gz')\n"
            "tar.extractall('.')\n"
            "tar.close()\n"
            "files = []\n"
            "for r, d, fs in os.walk('skill'):\n"
            "    for f in fs:\n"
            "        files.append(os.path.join(r, f))\n"
            "print(f'OK:{len(files)} files')\n"
        )

        resp = self.client.invoke_code_interpreter(
            codeInterpreterIdentifier=self.code_interpreter_id,
            sessionId=session_id,
            name="executeCode",
            arguments={"language": "python", "code": extract_code},
        )

        # Check result
        ok = False
        for event in resp.get("stream", []):
            result = event.get("result", {})
            for item in result.get("content", []):
                if item.get("type") == "text" and "OK" in item.get("text", ""):
                    ok = True
                if item.get("type") == "error":
                    logger.error(
                        f"Preload extract error: {item.get('text', '')}"
                    )

        elapsed = time.monotonic() - preload_start
        if ok:
            logger.info(
                f"Pre-loaded skill files to ./skill/ "
                f"({len(tar_bytes)} bytes compressed, {elapsed:.1f}s)"
            )
        else:
            logger.error(f"Failed to pre-load skill files ({elapsed:.1f}s)")
        return ok

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: int | None = None,
        files: list[UploadFile] | None = None,
        network_mode: NetworkMode = NetworkMode.SANDBOX,
        skill_id: str = "code-execution",
        skill_source_path: str | None = None,
    ) -> ExecutionResult:
        timeout = timeout or self.default_timeout
        session_id = None
        try:
            session_id = await self._start_session()
            if skill_source_path:
                self._preload_skill_files(session_id, skill_source_path)
            if files:
                await self._write_files(session_id, files)
            result = await self._execute_in_session(session_id, code, language, timeout)
            
            # Upload generated files to S3 if execution was successful
            if result.status == ExecutionStatus.SUCCESS and self.s3_bucket:
                uploaded_files = []
                # List files in working directory AND /tmp (models often save to /tmp)
                ls_result = self._run_command(
                    session_id,
                    "find . /tmp -maxdepth 1 -type f -not -name '.*' 2>/dev/null"
                )
                if ls_result["exit_code"] == 0:
                    seen = set()
                    for fpath in ls_result["stdout"].strip().split("\n"):
                        fpath = fpath.strip()
                        if not fpath:
                            continue
                        fname = fpath.split("/")[-1]
                        ext = ("." + fname.rsplit(".", 1)[1]).lower() if "." in fname else ""
                        # Skip hidden files, duplicates, and non-output files
                        if fname.startswith(".") or fname in seen:
                            continue
                        if ext not in self.OUTPUT_EXTENSIONS:
                            logger.debug(f"Skipping non-output file: {fname}")
                            continue
                        seen.add(fname)
                        s3_info = self._upload_to_s3(session_id, fpath, skill_id)
                        if s3_info:
                            s3_info["filename"] = fname
                            uploaded_files.append(s3_info)

                # Update result with uploaded files
                result.output_files = uploaded_files
            
            return result
        except asyncio.TimeoutError:
            return ExecutionResult(
                status=ExecutionStatus.TIMEOUT, exit_code=-1,
                stdout="", stderr=f"Execution timed out after {timeout}s",
                duration_ms=timeout * 1000,
            )
        except ClientError as e:
            return ExecutionResult(
                status=ExecutionStatus.ERROR, exit_code=-1,
                stdout="", stderr=f"AWS API error: {e.response['Error']['Message']}",
                duration_ms=0,
            )
        except Exception as e:
            logger.exception(f"Code execution failed: {e}")
            return ExecutionResult(
                status=ExecutionStatus.ERROR, exit_code=-1,
                stdout="", stderr=str(e), duration_ms=0,
            )
        finally:
            if session_id:
                await self._stop_session(session_id)

    async def _start_session(self) -> str:
        response = self.client.start_code_interpreter_session(
            codeInterpreterIdentifier=self.code_interpreter_id,
            name=f"mcp-skills-session-{int(time.time())}",
            sessionTimeoutSeconds=self.session_timeout,
        )
        session_id = response["sessionId"]
        logger.debug(f"Started session: {session_id}")
        return session_id

    async def _execute_in_session(
        self, session_id: str, code: str, language: str, timeout: int,
    ) -> ExecutionResult:
        start_time = time.monotonic()
        response = self.client.invoke_code_interpreter(
            codeInterpreterIdentifier=self.code_interpreter_id,
            sessionId=session_id,
            name="executeCode",
            arguments={"language": language, "code": code},
        )
        stdout_parts, stderr_parts = [], []
        exit_code = 0
        output_files = []
        for event in response.get("stream", []):
            if "result" in event:
                result = event["result"]
                for item in result.get("content", []):
                    if item.get("type") == "text":
                        stdout_parts.append(item.get("text", ""))
                    elif item.get("type") == "error":
                        stderr_parts.append(item.get("text", ""))
                        exit_code = 1
                    elif item.get("type") == "file":
                        output_files.append(item)
        duration_ms = int((time.monotonic() - start_time) * 1000)
        status = ExecutionStatus.SUCCESS if exit_code == 0 else ExecutionStatus.ERROR
        return ExecutionResult(
            status=status, exit_code=exit_code,
            stdout="\n".join(stdout_parts), stderr="\n".join(stderr_parts),
            duration_ms=duration_ms, output_files=output_files,
        )

    def _write_file_via_command(self, session_id: str, path: str, content: str) -> None:
        """Write a file in sandbox using base64 encoding to avoid escaping issues."""
        import base64
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        self._run_command(session_id, f"echo '{encoded}' | base64 -d > {path}")

    async def _write_files(self, session_id: str, files: list[UploadFile]) -> None:
        for f in files:
            if len(f.content) > self.MAX_FILE_SIZE:
                raise ValueError(f"File {f.name} exceeds {self.MAX_FILE_SIZE // (1024*1024)}MB")
        for f in files:
            content = f.content.decode("utf-8") if isinstance(f.content, bytes) else f.content
            self._write_file_via_command(session_id, f.name, content)

    async def _stop_session(self, session_id: str) -> None:
        try:
            self.client.stop_code_interpreter_session(
                codeInterpreterIdentifier=self.code_interpreter_id,
                sessionId=session_id,
            )
        except Exception as e:
            logger.warning(f"Failed to stop session {session_id}: {e}")

    async def execute_skill_script(
        self,
        skill_id: str,
        script_path: str,
        script_content: str,
        arguments: dict[str, Any],
        timeout: int = 300,
        network_mode: str = "sandbox",
        dependencies: list[str] | None = None,
        runtime: str = "python",
    ) -> ExecutionResult:
        """Execute skill script in sandbox, then upload generated files to S3.

        For Python: writes script to sandbox, installs pip deps, runs via shell.
        For JavaScript: executes code directly via executeCode API (Deno runtime).
            Dependencies should use npm: specifiers in the code itself
            (e.g. ``import pptxgenjs from "npm:pptxgenjs"``).
        """
        is_js = runtime == "javascript"
        session_id = None
        try:
            session_id = await self._start_session()

            if is_js:
                # JavaScript: execute via executeCode API (Deno runtime).
                # Deno resolves npm: specifiers at runtime, so pip-style
                # dependency installation is not needed.
                script_with_args = (
                    f"const SKILL_ARGUMENTS = {json.dumps(arguments)};\n\n"
                    f"{script_content}"
                )
                result = await self._execute_in_session(
                    session_id, script_with_args, "javascript", timeout,
                )
            else:
                # Python: install deps, write file, run via shell command.
                if dependencies:
                    deps_str = " ".join(dependencies)
                    self._run_command(session_id, f"pip install -q {deps_str}")

                script_with_args = f"SKILL_ARGUMENTS = {json.dumps(arguments)}\n\n{script_content}"
                entry = script_path or "main.py"
                self._write_file_via_command(session_id, entry, script_with_args)

                start_time = time.monotonic()
                cmd_result = self._run_command(session_id, f"python {entry}")
                duration_ms = int((time.monotonic() - start_time) * 1000)

                result = ExecutionResult(
                    status=ExecutionStatus.SUCCESS if cmd_result["exit_code"] == 0 else ExecutionStatus.ERROR,
                    exit_code=cmd_result["exit_code"],
                    stdout=cmd_result["stdout"],
                    stderr=cmd_result["stderr"],
                    duration_ms=duration_ms,
                )

            # Upload generated files to S3
            if result.status == ExecutionStatus.SUCCESS and self.s3_bucket:
                uploaded_files = []
                ls_result = self._run_command(
                    session_id,
                    "find . /tmp -maxdepth 1 -type f -not -name '.*' 2>/dev/null",
                )
                if ls_result["exit_code"] == 0:
                    seen = set()
                    for fpath in ls_result["stdout"].strip().split("\n"):
                        fpath = fpath.strip()
                        if not fpath:
                            continue
                        fname = fpath.split("/")[-1]
                        ext = ("." + fname.rsplit(".", 1)[1]).lower() if "." in fname else ""
                        if fname.startswith(".") or fname in seen:
                            continue
                        if ext not in self.OUTPUT_EXTENSIONS:
                            logger.debug(f"Skipping non-output file: {fname}")
                            continue
                        seen.add(fname)
                        s3_info = self._upload_to_s3(session_id, fpath, skill_id)
                        if s3_info:
                            s3_info["filename"] = fname
                            uploaded_files.append(s3_info)
                result.output_files = uploaded_files

            logger.info(
                f"Skill {skill_id}: status={result.status.value}, "
                f"duration={result.duration_ms}ms, uploaded={len(result.output_files)} files"
            )
            return result

        except Exception as e:
            logger.exception(f"Skill execution failed: {e}")
            return ExecutionResult(
                status=ExecutionStatus.ERROR, exit_code=-1,
                stdout="", stderr=str(e), duration_ms=0,
            )
        finally:
            if session_id:
                await self._stop_session(session_id)

    async def cleanup(self) -> None:
        logger.info("CodeInterpreterService cleanup complete")
