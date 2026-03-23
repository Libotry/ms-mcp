#!/usr/bin/env python3
"""Test improved SKILL.md parser with rulebook integration."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.skill_parser import parse_skill_md, get_default_thresholds


def test_improved_parsing():
    """测试增强版解析器的功能."""
    
    skill_path = Path("skills/ascend-profiling-anomaly/SKILL.md")
    
    print("=" * 70)
    print("IMPROVED SKILL.MD PARSER TEST")
    print("=" * 70)
    
    # 解析 SKILL.md（会自动加载 rulebook.md）
    config = parse_skill_md(skill_path)
    
    print("\n📋 Basic Metadata:")
    print(f"  Name: {config.name}")
    print(f"  Description: {config.description}")
    print(f"  Methodology: {config.methodology_summary}")
    
    print("\n🔄 Workflow Patterns:")
    for i, pattern in enumerate(config.workflow_patterns, 1):
        print(f"  {i}. {pattern}")
    
    print("\n⚙️  Diagnostic Rules (loaded from rulebook.md):")
    if config.diagnostic_rules:
        sorted_keys = sorted(config.diagnostic_rules.keys())
        for key in sorted_keys:
            value = config.diagnostic_rules[key]
            print(f"  • {key}: {value}")
    else:
        print("  ⚠️ No rules extracted!")
    
    print("\n✅ Parsing Complete!")
    print(f"Total diagnostic rules: {len(config.diagnostic_rules)}")
    

if __name__ == "__main__":
    test_improved_parsing()
