#!/usr/bin/env python3
"""Debug why test script shows empty results."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# Force reload
if 'skills.skill_parser' in sys.modules:
    del sys.modules['skills.skill_parser']

from skills.skill_parser import parse_skill_md


def debug_test():
    """带详细调试的测试."""
    
    skill_path = Path("skills/ascend-profiling-anomaly/SKILL.md")
    
    print("=" * 70)
    print("DEBUG TEST - Checking parse_skill_md internals")
    print("=" * 70)
    
    # Step 1: Check if rulebook exists
    rulebook_path = skill_path.parent / "references" / "rulebook.md"
    print(f"\n1. Rulebook exists: {rulebook_path.exists()}")
    
    # Step 2: Manually call _parse_rulebook_thresholds
    from skills.skill_parser import SkillConfig, _parse_rulebook_thresholds
    
    rulebook_content = rulebook_path.read_text(encoding="utf-8")
    config = SkillConfig()
    
    print(f"2. Config before parsing: diagnostic_rules={config.diagnostic_rules}")
    
    _parse_rulebook_thresholds(rulebook_content, config)
    
    print(f"3. Config after _parse_rulebook_thresholds: diagnostic_rules={config.diagnostic_rules}")
    
    # Step 3: Call full parse_skill_md
    print("\n4. Calling parse_skill_md...")
    full_config = parse_skill_md(skill_path)
    print(f"   Full config diagnostic_rules: {full_config.diagnostic_rules}")
    print(f"   Full config type: {type(full_config)}")
    print(f"   Full config dict keys: {full_config.__dict__.keys()}")
    

if __name__ == "__main__":
    debug_test()
