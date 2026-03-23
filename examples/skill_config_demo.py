#!/usr/bin/env python
"""Demonstration: Using SKILL.md as Dynamic Configuration

This script demonstrates how to use the skill_parser module to:
1. Load diagnostic thresholds from SKILL.md and rulebook.md
2. Access workflow patterns for structuring analysis reports
3. Use extracted rules in actual profiling analysis
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.skill_parser import parse_skill_md, load_skill_config, get_default_thresholds


def demo_basic_parsing():
    """演示基础解析功能."""
    print("=" * 70)
    print("DEMO 1: Basic SKILL.md Parsing")
    print("=" * 70)
    
    skill_path = Path("skills/ascend-profiling-anomaly/SKILL.md")
    config = parse_skill_md(skill_path)
    
    print(f"\n📋 Skill Metadata:")
    print(f"   Name: {config.name}")
    print(f"   Description: {config.description[:80]}...")
    
    print(f"\n🎯 Methodology Summary:")
    print(f"   {config.methodology_summary}")
    
    print(f"\n⚙️  Diagnostic Rules ({len(config.diagnostic_rules)} total):")
    for key, value in sorted(config.diagnostic_rules.items()):
        print(f"   • {key}: {value}")
    
    print(f"\n🔄 Workflow Patterns ({len(config.workflow_patterns)} pipelines):")
    for pattern in config.workflow_patterns:
        print(f"   {pattern}")


def demo_load_with_fallback():
    """演示带降级处理的配置加载."""
    print("\n" + "=" * 70)
    print("DEMO 2: Config Loading with Fallback")
    print("=" * 70)
    
    # Try loading from current directory
    profiling_dir = Path(".")
    config, thresholds = load_skill_config(profiling_dir)
    
    if config.diagnostic_rules:
        print(f"✓ Loaded from SKILL.md/rulebook.md")
        print(f"   {len(thresholds)} thresholds extracted")
    else:
        print(f"ℹ SKILL.md not found, using defaults")
        print(f"   {len(thresholds)} default thresholds")
    
    print(f"\nSample thresholds:")
    for key in ['underfeed_heavy', 'internal_bubble_ratio', 'wait_anchor_ratio']:
        if key in thresholds:
            print(f"   {key}: {thresholds[key]}")


def demo_comparison():
    """比较 SKILL-derived 和默认阈值."""
    print("\n" + "=" * 70)
    print("DEMO 3: SKILL vs Default Threshold Comparison")
    print("=" * 70)
    
    skill_path = Path("skills/ascend-profiling-anomaly/SKILL.md")
    config = parse_skill_md(skill_path)
    skill_thresholds = config.diagnostic_rules or get_default_thresholds()
    default_thresholds = get_default_thresholds()
    
    print("\nThreshold Source Analysis:")
    common_keys = set(skill_thresholds.keys()) & set(default_thresholds.keys())
    
    matched = []
    different = []
    
    for key in common_keys:
        if abs(skill_thresholds[key] - default_thresholds[key]) < 0.001:
            matched.append(key)
        else:
            different.append((key, skill_thresholds[key], default_thresholds[key]))
    
    print(f"   ✓ Matched: {len(matched)} thresholds")
    print(f"   ⚠ Different: {len(different)} thresholds")
    
    if different:
        print("\nDifferences:")
        for key, skill_val, default_val in different:
            print(f"   {key}:")
            print(f"      SKILL: {skill_val}")
            print(f"      Default: {default_val}")


def demo_practical_usage():
    """演示在实际分析中使用 SKILL 配置."""
    print("\n" + "=" * 70)
    print("DEMO 4: Practical Usage in Analysis Code")
    print("=" * 70)
    
    # Simulate loading configuration for analysis
    config, thresholds = load_skill_config(Path("."))
    
    print("\nExample: Bubble Detection Logic")
    print("-" * 70)
    
    # Sample metrics (simulated)
    sample_metrics = {
        'underfeed_ratio': 0.35,
        'largest_internal_bubble_ms': 15.0,
        'service_ms': 100.0,
        'prelaunch_gap_ms': 2.0,
        'tail_gap_ms': 12.0,
        'wait_ratio': 0.97,
    }
    
    print("\nInput Metrics:")
    for k, v in sample_metrics.items():
        print(f"   {k}: {v}")
    
    print("\nApplying SKILL-derived thresholds:")
    
    # Check underfeed
    if sample_metrics['underfeed_ratio'] >= thresholds.get('underfeed_heavy', 0.30):
        print(f"   ⚠ HEAVY UNDERFEED DETECTED")
        print(f"      Ratio {sample_metrics['underfeed_ratio']} >= {thresholds.get('underfeed_heavy')}")
    
    # Check internal bubble
    threshold = max(1.0, thresholds.get('internal_bubble_ratio', 0.10) * sample_metrics['service_ms'])
    if sample_metrics['largest_internal_bubble_ms'] >= threshold:
        print(f"   ⚠ INTERNAL BUBBLE DETECTED")
        print(f"      {sample_metrics['largest_internal_bubble_ms']}ms >= {threshold:.1f}ms threshold")
    
    # Check tail gap
    tail_threshold = max(1.0, thresholds.get('tail_gap_ratio', 0.10) * sample_metrics['service_ms'])
    if sample_metrics['tail_gap_ms'] >= tail_threshold:
        print(f"   ⚠ TAIL GAP DETECTED")
        print(f"      {sample_metrics['tail_gap_ms']}ms >= {tail_threshold:.1f}ms threshold")
    
    # Check wait-anchor
    if sample_metrics['wait_ratio'] > thresholds.get('wait_anchor_ratio', 0.95):
        print(f"   ⚠ WAIT-ANCHOR ANOMALY DETECTED")
        print(f"      Wait ratio {sample_metrics['wait_ratio']} > {thresholds.get('wait_anchor_ratio')}")
    
    print("\nAnalysis Report Structure (from workflow patterns):")
    for i, pattern in enumerate(config.workflow_patterns, 1):
        print(f"   Pipeline {i}: {pattern.split(':')[0]}")


if __name__ == "__main__":
    print("\n" + "📘" * 35)
    print("SKILL.MLD CONFIGURATION DEMONSTRATION")
    print("📘" * 35 + "\n")
    
    demo_basic_parsing()
    demo_load_with_fallback()
    demo_comparison()
    demo_practical_usage()
    
    print("\n" + "=" * 70)
    print("✅ Demonstration Complete!")
    print("=" * 70)
    print("""
Key Takeaways:
1. SKILL.md serves as dynamic configuration source
2. Thresholds are extracted from rulebook.md automatically
3. Workflow patterns guide report structure
4. Graceful fallback to defaults when SKILL.md unavailable
5. Enables consistent, reproducible analysis across runs

Next Steps:
• Integrate load_skill_config() into your analyzer
• Extend _parse_rulebook_thresholds() for more rules
• Customize thresholds by editing rulebook.md
""")
