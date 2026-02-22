"""Quick test for lazy loading without pytest."""

import asyncio
import sys
from pathlib import Path
import tempfile

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.skill_loader import SkillLoader


async def test_lazy_loading():
    """Test that skills are registered but not fully loaded until accessed."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        
        # Create test skill
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        
        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

# Test Skill

This is a test skill with instructions.
""")
        
        loader = SkillLoader()
        
        # Test lazy loading
        print("Testing lazy loading...")
        count = await loader.load_from_directory(skills_dir, lazy=True)
        
        assert count == 1, f"Expected 1 skill, got {count}"
        assert "test-skill" in loader._skill_paths, "Skill not in paths"
        assert "test-skill" not in loader._skills, "Skill should not be loaded yet"
        print("✓ Skill registered but not loaded")
        
        # Access skill - should trigger loading
        skill = await loader.get_skill("test-skill")
        
        assert skill is not None, "Skill not found"
        assert skill.manifest.name == "test-skill"
        assert "This is a test skill" in skill.manifest.instructions
        assert "test-skill" in loader._skills, "Skill should be loaded now"
        print("✓ Skill loaded on first access")


async def test_full_loading():
    """Test that lazy=False loads immediately."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        
        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

# Test Skill

Instructions here.
""")
        
        loader = SkillLoader()
        
        print("\nTesting full loading...")
        count = await loader.load_from_directory(skills_dir, lazy=False)
        
        assert count == 1
        assert "test-skill" in loader._skills, "Skill should be loaded immediately"
        print("✓ Skill loaded immediately with lazy=False")


async def main():
    try:
        await test_lazy_loading()
        await test_full_loading()
        print("\n✅ All lazy loading tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
