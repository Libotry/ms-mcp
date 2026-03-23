#!/usr/bin/env python3
"""Test regex patterns for rulebook parsing."""

import re
from pathlib import Path

content = Path('skills/ascend-profiling-anomaly/references/rulebook.md').read_text(encoding='utf-8')

print("=" * 70)
print("TEST REGEX PATTERNS ON RULEBOOK.MD")
print("=" * 70)

# Test 1: Find section 2.2
bubble_section = re.search(
    r'###\s*2\.2\s+High-severity\s+bubble\s+thresholds\s*\n+(.*?)(?=^###|\Z)',
    content,
    re.MULTILINE | re.DOTALL | re.IGNORECASE
)

print(f"\n1. Found section 2.2: {bubble_section is not None}")
if bubble_section:
    section_text = bubble_section.group(1)
    print(f"   Section length: {len(section_text)} chars")
    print(f"\n   Preview (first 400 chars):")
    print("   " + "\n   ".join(section_text[:400].split('\n')))
    
    # Try matching underfeed_ratio with backticks
    underfeed_match = re.search(r'`underfeed_ratio\s*>=\s*([\d.]+)`', section_text)
    print(f"\n2. Matched `underfeed_ratio >= X`: {underfeed_match is not None}")
    if underfeed_match:
        print(f"   Value: {underfeed_match.group(1)}")
    
    # Try without backticks
    underfeed_no_bt = re.search(r'underfeed_ratio\s*>=\s*([\d.]+)', section_text)
    print(f"3. Matched 'underfeed_ratio >= X' (no backticks): {underfeed_no_bt is not None}")
    if underfeed_no_bt:
        print(f"   Value: {underfeed_no_bt.group(1)}")
