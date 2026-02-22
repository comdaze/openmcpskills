#!/usr/bin/env python3
"""Performance comparison: lazy vs full loading."""

import asyncio
import time
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.skill_loader import SkillLoader


async def create_test_skills(directory: Path, count: int):
    """Create N test skills."""
    for i in range(count):
        skill_dir = directory / f"skill-{i:03d}"
        skill_dir.mkdir()
        
        (skill_dir / "SKILL.md").write_text(f"""---
name: skill-{i:03d}
description: Test skill number {i}
metadata:
  version: 1.0.0
---

# Skill {i}

Instructions for skill {i}.
This is a longer instruction block to simulate real skills.
It contains multiple lines and paragraphs.

## Section 1
More content here.

## Section 2
Even more content.
""")


async def benchmark_loading(count: int):
    """Benchmark lazy vs full loading."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        
        print(f"Creating {count} test skills...")
        await create_test_skills(skills_dir, count)
        
        # Test lazy loading
        print(f"\n{'='*60}")
        print(f"LAZY LOADING ({count} skills)")
        print('='*60)
        
        loader1 = SkillLoader()
        start = time.time()
        registered = await loader1.load_from_directory(skills_dir, lazy=True)
        lazy_time = time.time() - start
        
        print(f"✓ Registered: {registered} skills")
        print(f"✓ Time: {lazy_time:.3f}s")
        print(f"✓ Loaded in memory: {len(loader1._skills)}")
        print(f"✓ Registered paths: {len(loader1._skill_paths)}")
        
        # Access one skill to trigger loading
        start = time.time()
        skill = await loader1.get_skill("skill-050")
        access_time = time.time() - start
        print(f"✓ First access time: {access_time:.3f}s")
        
        # Test full loading
        print(f"\n{'='*60}")
        print(f"FULL LOADING ({count} skills)")
        print('='*60)
        
        loader2 = SkillLoader()
        start = time.time()
        loaded = await loader2.load_from_directory(skills_dir, lazy=False)
        full_time = time.time() - start
        
        print(f"✓ Loaded: {loaded} skills")
        print(f"✓ Time: {full_time:.3f}s")
        print(f"✓ Loaded in memory: {len(loader2._skills)}")
        
        # Summary
        print(f"\n{'='*60}")
        print("PERFORMANCE COMPARISON")
        print('='*60)
        print(f"Lazy loading:  {lazy_time:.3f}s")
        print(f"Full loading:  {full_time:.3f}s")
        print(f"Speedup:       {full_time/lazy_time:.1f}x faster")
        print(f"First access:  {access_time:.3f}s (acceptable overhead)")


async def main():
    print("Performance Benchmark: Lazy vs Full Loading\n")
    
    for count in [10, 50, 100]:
        await benchmark_loading(count)
        print()


if __name__ == "__main__":
    asyncio.run(main())
