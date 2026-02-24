"""Bridge service for skill-seekers integration.

Wraps the skill-seekers package to generate skill packages from
documentation websites, GitHub repositories, and PDF files.

After generation, uses the platform's own Bedrock LLM to enhance
the SKILL.md with richer instructions synthesised from references.

Uses lazy imports so the rest of the system is unaffected when
skill-seekers is not installed.
"""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import boto3
import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_frontmatter(skill_dir: Path, name: str, description: str) -> None:
    """Ensure SKILL.md has valid YAML frontmatter required by the platform.

    skill-seekers may produce SKILL.md without ``---`` frontmatter.
    This function checks and prepends it when missing.
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return

    content = skill_md.read_text(encoding="utf-8")

    if content.startswith("---"):
        return

    safe_desc = description.replace('"', '\\"') if description else f"Skill generated for {name}"
    frontmatter = (
        "---\n"
        f"name: {name}\n"
        f'description: "{safe_desc}"\n'
        "---\n\n"
    )
    skill_md.write_text(frontmatter + content, encoding="utf-8")


def check_available() -> bool:
    """Return True if the skill-seekers package is installed."""
    try:
        import skill_seekers  # noqa: F401

        return True
    except ImportError:
        return False


def _ensure_available() -> None:
    """Raise ImportError with a friendly message when skill-seekers is missing."""
    if not check_available():
        raise ImportError(
            "skill-seekers is not installed. "
            "Install it with: pip install 'open-mcp-skills[seekers]'"
        )


# ---------------------------------------------------------------------------
# Bedrock-based SKILL.md enhancement
# ---------------------------------------------------------------------------

def _read_references(skill_dir: Path, max_total: int = 100_000) -> dict[str, str]:
    """Read reference files from a skill directory.

    Returns a mapping of ``filename -> content``, respecting *max_total*
    aggregate character budget.
    """
    refs_dir = skill_dir / "references"
    if not refs_dir.exists():
        return {}

    refs: dict[str, str] = {}
    total = 0
    for f in sorted(refs_dir.rglob("*")):
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if total + len(text) > max_total:
            remaining = max_total - total
            if remaining > 500:
                text = text[:remaining] + "\n\n[truncated]"
            else:
                break
        rel = str(f.relative_to(refs_dir))
        refs[rel] = text
        total += len(text)
    return refs


def _build_enhancement_prompt(name: str, description: str,
                              current_skill_md: str,
                              references: dict[str, str],
                              custom_prompt: str = "") -> str:
    """Build a prompt that asks Claude to produce a high-quality SKILL.md."""

    ref_section = ""
    for filename, content in references.items():
        ref_section += f"\n#### {filename}\n```markdown\n{content}\n```\n"

    custom_section = ""
    if custom_prompt.strip():
        custom_section = f"""
USER CUSTOM INSTRUCTIONS:
The user has provided the following specific requirements for this skill. \
These instructions take priority over defaults:

{custom_prompt.strip()}

"""

    return f"""You are enhancing a Claude skill's SKILL.md file.

SKILL OVERVIEW:
- Name: {name}
- Description: {description}
- Reference files: {len(references)}
{custom_section}
CURRENT SKILL.MD:
```markdown
{current_skill_md}
```

REFERENCE DOCUMENTATION:
{ref_section}

YOUR TASK:
Create an enhanced SKILL.md that synthesises knowledge from the reference \
documentation into a comprehensive, practical skill file.

Requirements:
1. **Keep the YAML frontmatter** (---\\nname: ...\\ndescription: ...\\n---) \
intact at the top, with the same name. You may improve the description.
2. **"When to Use This Skill" section** — specific trigger conditions and \
concrete use cases.
3. **Quick Reference** — extract 5-10 of the best, most practical code \
examples or command snippets from the references. Keep them short (5-20 lines).
4. **Key Concepts** — explain core concepts and terminology.
5. **Reference Files description** — explain what is in each reference file \
so users can navigate them.
6. **Working with This Skill** — practical guidance for beginners through \
advanced users.

IMPORTANT:
- Extract REAL examples from the reference docs, don't invent them.
- Be concise but useful — not overly verbose.
- Use proper markdown formatting with language-tagged code blocks.
- Prioritise actionable, practical content.
- If the user provided custom instructions above, follow them carefully.

OUTPUT:
Return ONLY the complete SKILL.md content, starting with the --- frontmatter.
"""


async def _enhance_skill_md(skill_dir: Path, name: str, description: str,
                            custom_prompt: str = "") -> None:
    """Enhance the SKILL.md in *skill_dir* using the platform's Bedrock LLM.

    Reads the current SKILL.md and all reference files, sends them to Claude
    via Bedrock, and overwrites SKILL.md with the enhanced version.
    Falls back gracefully if enhancement fails (keeps original).
    """
    settings = get_settings()

    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        return

    current_skill_md = skill_md_path.read_text(encoding="utf-8")
    references = _read_references(skill_dir)

    if not references:
        logger.info("No reference files found — skipping enhancement")
        return

    prompt = _build_enhancement_prompt(name, description, current_skill_md, references, custom_prompt)

    # Call Bedrock (same pattern as playground.py)
    client_kwargs: dict = {"region_name": settings.aws_region}
    if settings.bedrock_endpoint:
        client_kwargs["endpoint_url"] = settings.bedrock_endpoint

    model_id = settings.claude_sonnet_model_id

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        bedrock = boto3.client("bedrock-runtime", **client_kwargs)
        response = await asyncio.to_thread(
            bedrock.invoke_model,
            modelId=model_id,
            body=json.dumps(body),
        )

        result = json.loads(response["body"].read())
        enhanced_text = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                enhanced_text = block["text"]
                break

        if not enhanced_text or "---" not in enhanced_text:
            logger.warning("Enhancement returned unexpected content — keeping original")
            return

        # Backup original, write enhanced
        backup_path = skill_md_path.with_suffix(".md.original")
        backup_path.write_text(current_skill_md, encoding="utf-8")
        skill_md_path.write_text(enhanced_text, encoding="utf-8")
        logger.info(
            "Enhanced SKILL.md: %d chars -> %d chars",
            len(current_skill_md),
            len(enhanced_text),
        )
    except Exception as e:
        logger.warning("SKILL.md enhancement failed (keeping original): %s", e)


# ---------------------------------------------------------------------------
# Smart reference organisation (GitHub)
# ---------------------------------------------------------------------------


def _safe_filename(name: str, ext: str = ".md") -> str:
    """Sanitise a string into a safe filename, preserving existing extension."""
    base = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    base = base.strip("_")[:80] or "unnamed"
    if not base.endswith(ext):
        base += ext
    return base


def _write_ref(path: Path, content: str) -> None:
    """Write content to a reference file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_github_references(skill_dir: Path, result, code_analysis: dict) -> None:
    """Organise all available data from AnalysisResult into a structured
    ``references/`` tree.

    Layout::

        references/
        ├── documentation/          # README, CONTRIBUTING, docs/ files
        │   ├── README.md
        │   ├── CONTRIBUTING.md
        │   └── {original-path}.md  # each docs_files entry
        ├── code-analysis/          # file structure, imports, entry points
        │   ├── structure.md
        │   └── statistics.md
        ├── architecture/           # C3.7 architectural patterns
        │   └── patterns.md
        ├── design-patterns/        # C3.1
        │   └── patterns.md
        ├── examples/               # C3.2 test examples
        │   └── examples.md
        ├── guides/                 # C3.3 how-to guides
        │   └── {guide-name}.md
        ├── config/                 # C3.4 config patterns
        │   └── config-patterns.md
        └── issues/                 # GitHub issues insights
            ├── common-problems.md
            └── known-solutions.md
    """
    refs = skill_dir / "references"

    # ---- 1. Documentation ----
    docs = result.github_docs or {}

    if docs.get("readme"):
        _write_ref(refs / "documentation" / "README.md", docs["readme"])

    if docs.get("contributing"):
        _write_ref(refs / "documentation" / "CONTRIBUTING.md", docs["contributing"])

    docs_files = docs.get("docs_files") or []
    if isinstance(docs_files, list):
        for entry in docs_files:
            if isinstance(entry, dict) and entry.get("content"):
                # Preserve original path structure from repo
                original_path = entry.get("path", "")
                if original_path:
                    fname = _safe_filename(
                        original_path.replace("/", "_").replace("\\", "_")
                    )
                else:
                    fname = _safe_filename(f"doc_{docs_files.index(entry)}")
                _write_ref(refs / "documentation" / fname, entry["content"])
    elif isinstance(docs_files, str) and docs_files.strip():
        _write_ref(refs / "documentation" / "docs.md", docs_files)

    # ---- 2. Code analysis (basic) ----
    structure = code_analysis.get("structure")
    if structure:
        lines = ["# Repository Structure\n"]
        if isinstance(structure, dict):
            lines.append(f"```\n{json.dumps(structure, indent=2)}\n```")
        else:
            lines.append(str(structure))
        _write_ref(refs / "code-analysis" / "structure.md", "\n".join(lines))

    stats = code_analysis.get("statistics")
    if stats:
        lines = ["# Code Statistics\n"]
        if isinstance(stats, dict):
            for k, v in stats.items():
                lines.append(f"- **{k}**: {v}")
        else:
            lines.append(str(stats))
        _write_ref(refs / "code-analysis" / "statistics.md", "\n".join(lines))

    entry_points = code_analysis.get("entry_points")
    if entry_points:
        lines = ["# Entry Points\n"]
        if isinstance(entry_points, list):
            for ep in entry_points:
                lines.append(f"- `{ep}`" if isinstance(ep, str) else f"- {ep}")
        else:
            lines.append(str(entry_points))
        _write_ref(refs / "code-analysis" / "entry-points.md", "\n".join(lines))

    imports = code_analysis.get("imports")
    if imports:
        lines = ["# Dependencies & Imports\n"]
        if isinstance(imports, dict):
            for mod, imp_list in imports.items():
                lines.append(f"\n## {mod}\n")
                if isinstance(imp_list, list):
                    for i in imp_list:
                        lines.append(f"- `{i}`")
                else:
                    lines.append(str(imp_list))
        else:
            lines.append(str(imports))
        _write_ref(refs / "code-analysis" / "imports.md", "\n".join(lines))

    # ---- 3. C3.1 Design Patterns ----
    patterns = code_analysis.get("c3_1_patterns") or []
    if patterns:
        lines = ["# Design Patterns\n"]
        for p in patterns:
            if isinstance(p, dict):
                lines.append(f"## {p.get('name', p.get('pattern', 'Pattern'))}\n")
                if p.get("description"):
                    lines.append(f"{p['description']}\n")
                if p.get("file") or p.get("location"):
                    lines.append(f"**Location**: `{p.get('file') or p.get('location')}`\n")
                if p.get("confidence"):
                    lines.append(f"**Confidence**: {p['confidence']}\n")
            else:
                lines.append(f"- {p}")
        _write_ref(refs / "design-patterns" / "patterns.md", "\n".join(lines))

    # ---- 4. C3.2 Test Examples ----
    examples = code_analysis.get("c3_2_examples") or []
    if examples:
        lines = ["# Test & Code Examples\n"]
        for ex in examples[:30]:  # cap to avoid huge files
            if isinstance(ex, dict):
                lines.append(f"## {ex.get('name', ex.get('title', 'Example'))}\n")
                if ex.get("description"):
                    lines.append(f"{ex['description']}\n")
                if ex.get("code"):
                    lang = ex.get("language", "")
                    lines.append(f"```{lang}\n{ex['code']}\n```\n")
                if ex.get("file"):
                    lines.append(f"*Source: `{ex['file']}`*\n")
            else:
                lines.append(f"- {ex}")
        _write_ref(refs / "examples" / "examples.md", "\n".join(lines))

    # ---- 5. C3.3 How-to Guides ----
    guides = code_analysis.get("c3_3_guides") or []
    if guides:
        for g in guides:
            if isinstance(g, dict):
                title = g.get("title", g.get("name", "guide"))
                fname = _safe_filename(title)
                lines = [f"# {title}\n"]
                if g.get("description"):
                    lines.append(f"{g['description']}\n")
                if g.get("steps"):
                    for i, step in enumerate(g["steps"], 1):
                        lines.append(f"{i}. {step}")
                    lines.append("")
                if g.get("code"):
                    lines.append(f"```\n{g['code']}\n```\n")
                _write_ref(refs / "guides" / fname, "\n".join(lines))

    # ---- 6. C3.4 Config Patterns ----
    configs = code_analysis.get("c3_4_configs") or []
    if configs:
        lines = ["# Configuration Patterns\n"]
        for c in configs:
            if isinstance(c, dict):
                lines.append(f"## {c.get('file', c.get('name', 'Config'))}\n")
                if c.get("type") or c.get("config_type"):
                    lines.append(f"**Type**: {c.get('type') or c.get('config_type')}\n")
                if c.get("description"):
                    lines.append(f"{c['description']}\n")
                if c.get("content"):
                    lines.append(f"```\n{c['content']}\n```\n")
            else:
                lines.append(f"- {c}")
        _write_ref(refs / "config" / "config-patterns.md", "\n".join(lines))

    # ---- 7. C3.7 Architecture ----
    arch = code_analysis.get("c3_7_architecture") or []
    if arch:
        lines = ["# Architectural Patterns\n"]
        for a in arch:
            if isinstance(a, dict):
                lines.append(f"## {a.get('name', a.get('pattern', 'Pattern'))}\n")
                if a.get("description"):
                    lines.append(f"{a['description']}\n")
                if a.get("components"):
                    lines.append("**Components**:")
                    for comp in a["components"]:
                        lines.append(f"- {comp}")
                    lines.append("")
            else:
                lines.append(f"- {a}")
        _write_ref(refs / "architecture" / "patterns.md", "\n".join(lines))

    # ---- 8. GitHub Issues Insights ----
    insights = result.github_insights or {}

    problems = insights.get("common_problems") or []
    if problems:
        lines = ["# Common Problems\n"]
        for p in problems:
            if isinstance(p, dict):
                title = p.get("title", "")
                lines.append(f"## {title}\n" if title else "")
                if p.get("count"):
                    lines.append(f"**Occurrences**: {p['count']}\n")
                if p.get("description") or p.get("body"):
                    lines.append(f"{p.get('description') or p.get('body', '')}\n")
            else:
                lines.append(f"- {p}")
        _write_ref(refs / "issues" / "common-problems.md", "\n".join(lines))

    solutions = insights.get("known_solutions") or []
    if solutions:
        lines = ["# Known Solutions\n"]
        for s in solutions:
            if isinstance(s, dict):
                title = s.get("title", "")
                lines.append(f"## {title}\n" if title else "")
                if s.get("description") or s.get("body"):
                    lines.append(f"{s.get('description') or s.get('body', '')}\n")
            else:
                lines.append(f"- {s}")
        _write_ref(refs / "issues" / "known-solutions.md", "\n".join(lines))

    metadata = insights.get("metadata") or {}
    if metadata:
        lines = ["# Repository Metadata\n"]
        for k, v in metadata.items():
            if v is not None:
                lines.append(f"- **{k}**: {v}")
        labels = insights.get("top_labels") or []
        if labels:
            lines.append("\n## Top Labels\n")
            for lb in labels:
                if isinstance(lb, dict):
                    lines.append(f"- **{lb.get('name', '')}**: {lb.get('count', '')}")
                else:
                    lines.append(f"- {lb}")
        _write_ref(refs / "issues" / "metadata.md", "\n".join(lines))


# ---------------------------------------------------------------------------
# Domain-aware CSS selectors for content extraction
# ---------------------------------------------------------------------------

# Known domains whose HTML structure doesn't match the default
# ``div[role="main"]`` selector used by skill-seekers.
_DOMAIN_SELECTORS: dict[str, dict[str, str]] = {
    "mp.weixin.qq.com": {
        "main_content": "#js_content, .rich_media_content, .rich_media_area_primary_inner",
    },
}

# Broad fallback chain used for unknown domains.  The original default
# (``div[role="main"]``) is listed first so existing behaviour is preserved;
# additional common containers are appended as fallbacks.
_FALLBACK_MAIN_CONTENT = (
    'div[role="main"], main, article, '
    ".content, #content, .post-content, .entry-content, "
    ".article-content, .rich_media_content"
)


def _selectors_for_url(url: str) -> dict[str, str]:
    """Return CSS selector config for the given URL.

    Known domains get tailored selectors; everything else gets a broad
    fallback chain so that content is found even when the default
    ``div[role="main"]`` doesn't match.
    """
    domain = urlparse(url).netloc.lower()
    for known, sels in _DOMAIN_SELECTORS.items():
        if domain == known or domain.endswith("." + known):
            return sels
    return {"main_content": _FALLBACK_MAIN_CONTENT}


# ---------------------------------------------------------------------------
# Generation entry points
# ---------------------------------------------------------------------------


async def generate_skill_from_docs(url: str, name: str, description: str,
                                   custom_prompt: str = "") -> Path:
    """Generate a skill package by scraping a documentation website.

    Uses ``DocToSkillConverter`` from skill-seekers which writes the
    complete skill directory (SKILL.md + references/) to ``output/{name}/``.
    We run it inside a temporary working directory then move the result out.

    Returns:
        Path to the generated skill directory.
    """
    _ensure_available()
    from skill_seekers.cli.doc_scraper import DocToSkillConverter

    tmp = tempfile.mkdtemp(prefix="seekers_docs_")
    prev_cwd = os.getcwd()
    try:
        os.chdir(tmp)

        config = {
            "name": name,
            "base_url": url,
            "description": description or f"Skill generated from {url}",
            "max_pages": 50,
            "async_mode": True,
            "workers": 4,
            "selectors": _selectors_for_url(url),
        }

        converter = DocToSkillConverter(config)
        await converter.scrape_all_async()
        converter.build_skill()

        skill_dir = Path(tmp) / "output" / name

        # llms.txt scenario: skill-seekers downloads references but
        # build_skill() may fail because there are no scraped HTML pages.
        # In that case the references/ directory already has content — we
        # just need to create a minimal SKILL.md ourselves.
        refs_dir = skill_dir / "references"
        has_refs = refs_dir.exists() and any(refs_dir.iterdir())

        if not (skill_dir / "SKILL.md").exists():
            if not has_refs:
                raise RuntimeError(f"skill-seekers did not produce output at {skill_dir}")

            logger.info("build_skill produced no SKILL.md but references exist (llms.txt path) — generating stub")
            safe_desc = (description or f"Skill generated from {url}").replace('"', '\\"')
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                f"name: {name}\n"
                f'description: "{safe_desc}"\n'
                "---\n\n"
                f"# {name}\n\n{description or f'Skill generated from {url}'}\n",
                encoding="utf-8",
            )

        _ensure_frontmatter(skill_dir, name, description or f"Skill generated from {url}")
        await _enhance_skill_md(skill_dir, name, description or f"Skill generated from {url}", custom_prompt)
        return skill_dir
    finally:
        os.chdir(prev_cwd)


async def generate_skill_from_github(repo_url: str, name: str, description: str,
                                     custom_prompt: str = "") -> Path:
    """Generate a skill package by analysing a GitHub repository.

    Uses ``UnifiedCodebaseAnalyzer`` which returns an ``AnalysisResult``
    dataclass.  We convert its output into a standard skill directory.

    Returns:
        Path to the generated skill directory.
    """
    _ensure_available()
    from skill_seekers.cli.unified_codebase_analyzer import UnifiedCodebaseAnalyzer

    tmp = tempfile.mkdtemp(prefix="seekers_gh_")
    prev_cwd = os.getcwd()
    try:
        os.chdir(tmp)

        analyzer = UnifiedCodebaseAnalyzer()
        result = await asyncio.to_thread(
            analyzer.analyze,
            source=repo_url,
            depth="c3x",
            fetch_github_metadata=True,
            output_dir=Path(tmp),
            interactive=False,
        )

        # Build skill directory from the AnalysisResult dataclass
        skill_dir = Path(tmp) / "output" / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        code_analysis = result.code_analysis or {}

        # ---- Organise references by category ----
        _build_github_references(skill_dir, result, code_analysis)

        # ---- Compose initial SKILL.md ----
        summary_parts = []
        if description:
            summary_parts.append(description)
        if code_analysis.get("summary"):
            summary_parts.append(str(code_analysis["summary"]))
        if code_analysis.get("architecture"):
            summary_parts.append(f"## Architecture\n\n{code_analysis['architecture']}")
        if code_analysis.get("key_components"):
            summary_parts.append(
                "## Key Components\n\n"
                + "\n".join(f"- {c}" for c in code_analysis["key_components"])
            )

        safe_desc = (description or f"Skill generated from {repo_url}").replace('"', '\\"')
        body = "\n\n".join(summary_parts) if summary_parts else f"Skill generated from {repo_url}"
        skill_md_content = (
            "---\n"
            f"name: {name}\n"
            f'description: "{safe_desc}"\n'
            "---\n\n"
            f"# {name}\n\n{body}\n"
        )
        (skill_dir / "SKILL.md").write_text(skill_md_content, encoding="utf-8")

        await _enhance_skill_md(skill_dir, name, description or f"Skill generated from {repo_url}", custom_prompt)
        return skill_dir
    finally:
        os.chdir(prev_cwd)


async def generate_skill_from_pdf(pdf_url: str, name: str, description: str,
                                  custom_prompt: str = "") -> Path:
    """Generate a skill package from a PDF document.

    Downloads the PDF from *pdf_url*, then uses ``PDFToSkillConverter``.

    Returns:
        Path to the generated skill directory.
    """
    _ensure_available()
    from skill_seekers.cli.pdf_scraper import PDFToSkillConverter

    tmp = tempfile.mkdtemp(prefix="seekers_pdf_")
    prev_cwd = os.getcwd()
    try:
        os.chdir(tmp)

        # Download the PDF
        pdf_path = Path(tmp) / f"{name}.pdf"
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(pdf_url)
            resp.raise_for_status()
            pdf_path.write_bytes(resp.content)

        config = {
            "name": name,
            "pdf_path": str(pdf_path),
            "description": description or "Skill generated from PDF",
        }

        converter = PDFToSkillConverter(config)
        await asyncio.to_thread(converter.extract_pdf)
        await asyncio.to_thread(converter.build_skill)

        skill_dir = Path(tmp) / "output" / name
        if not skill_dir.exists() or not (skill_dir / "SKILL.md").exists():
            raise RuntimeError(f"skill-seekers did not produce output at {skill_dir}")

        _ensure_frontmatter(skill_dir, name, description or "Skill generated from PDF")
        await _enhance_skill_md(skill_dir, name, description or "Skill generated from PDF", custom_prompt)
        return skill_dir
    finally:
        os.chdir(prev_cwd)
