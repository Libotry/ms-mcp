#!/usr/bin/env python3
"""Debug rulebook parsing."""

import re
from pathlib import Path

rulebook_path = Path("skills/ascend-profiling-anomaly/references/rulebook.md")
content = rulebook_path.read_text(encoding="utf-8")

print("Looking for section 2.2...")
bubble_section = re.search(
    r'###\s*2\.2\s+High-severity\s+bubble\s+thresholds\s*\n+(.*?)(?=^###|\Z)',
    content,
    re.MULTILINE | re.DOTALL | re.IGNORECASE
)

if bubble_section:
    print("✓ Found section 2.2")
    print("-" * 60)
    print(bubble_section.group(1)[:500])
    print("-" * 60)
    
    # Try matching underfeed_ratio
    underfeed_match = re.search(r'underfeed_ratio\s*>=\s*`?([\d.]+)`?', bubble_section.group(1))
    if underfeed_match:
        print(f"\n✓ Found underfeed_ratio: {underfeed_match.group(1)}")
    else:
        print("\n✗ Did NOT match underfeed_ratio")
        
        # Show the actual line
        lines = bubble_section.group(1).split('\n')
        for line in lines:
            if 'underfeed' in line.lower():
                print(f"Actual line: {repr(line)}")
else:
    print("✗ Section 2.2 not found!")
    print("\nSearching for any '2.2' pattern...")
    matches = re.findall(r'.{0,50}2\.2.{0,100}', content)
    for m in matches[:3]:
        print(m)
