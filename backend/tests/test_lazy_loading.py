"""Test lazy loading functionality."""

import asyncio
from pathlib import Path
import tempfile
import pytest

from app.services.skill_loader import SkillLoader


@pytest.mark.asyncio
async def test_lazy_loading():
    """Test that skills are registered but not fully loaded until accessed."""
    
    # Create temporary skill directory
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        
        # Create a test skill
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: test-skill
description: A test skill
---

# Test Skill

This is a test skill with instructions.
""")
        
        # Initialize loader
        loader = SkillLoader()
        
        # Load with lazy=True
        count = await loader.load_from_directory(skills_dir, lazy=True)
        
        # Should register 1 skill
        assert count == 1
        
        # Skill should be in paths but not in loaded skills yet
        assert "test-skill" in loader._skill_paths
        assert "test-skill" not in loader._skills
        
        # Access the skill - should trigger loading
        skill = await loader.get_skill("test-skill")
        
        # Now it should be loaded
        assert skill is not None
        assert skill.manifest.name == "test-skill"
        assert "This is a test skill" in skill.manifest.instructions
        assert "test-skill" in loader._skills


@pytest.mark.asyncio
async def test_full_loading():
    """Test that lazy=False loads skills immediately."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: test-skill
description: A test skill
---

# Test Skill

Instructions here.
""")
        
        loader = SkillLoader()
        
        # Load with lazy=False
        count = await loader.load_from_directory(skills_dir, lazy=False)
        
        assert count == 1
        
        # Skill should be immediately loaded
        assert "test-skill" in loader._skills
        skill = loader._skills["test-skill"]
        assert skill.manifest.instructions == "# Test Skill\n\nInstructions here."


if __name__ == "__main__":
    asyncio.run(test_lazy_loading())
    asyncio.run(test_full_loading())
    print("✅ All lazy loading tests passed!")
