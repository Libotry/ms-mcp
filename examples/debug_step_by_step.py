#!/usr/bin/env python3
"""Debug rulebook parsing step by step."""

import re
from pathlib import Path

# 手动模拟 parse_skill_md 的逻辑
skill_path = Path("skills/ascend-profiling-anomaly/SKILL.md")
print(f"Checking if {skill_path} exists: {skill_path.exists()}")

if skill_path.exists():
    content = skill_path.read_text(encoding="utf-8")
    
    # Check for frontmatter
    frontmatter_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    print(f"\nFrontmatter found: {frontmatter_match is not None}")
    
    # Check for Purpose section
    purpose_match = re.search(
        r'##\s*Purpose\s*\n+(.*?)(?=^##|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    print(f"Purpose section found: {purpose_match is not None}")
    if purpose_match:
        print(f"  Content preview: {purpose_match.group(1)[:100]}...")
    
    # Check for rulebook.md
    rulebook_path = skill_path.parent / "references" / "rulebook.md"
    print(f"\nRulebook path: {rulebook_path}")
    print(f"Rulebook exists: {rulebook_path.exists()}")
    
    if rulebook_path.exists():
        rulebook_content = rulebook_path.read_text(encoding="utf-8")
        
        # Try to match section 2.2
        bubble_section = re.search(
            r'###\s*2\.2\s+High-severity\s+bubble\s+thresholds\s*\n+(.*?)(?=^###|\Z)',
            rulebook_content,
            re.MULTILINE | re.DOTALL | re.IGNORECASE
        )
        print(f"\nBubble section (2.2) found: {bubble_section is not None}")
        
        if bubble_section:
            section_text = bubble_section.group(1)
            print(f"Section text length: {len(section_text)} chars")
            
            # Try matching underfeed_ratio
            underfeed_match = re.search(r'`underfeed_ratio\s*>=\s*([\d.]+)`', section_text)
            print(f"Underfeed match: {underfeed_match}")
            if underfeed_match:
                print(f"  Value: {underfeed_match.group(1)}")
            else:
                # Print the actual lines containing underfeed
                print("\nLines with 'underfeed':")
                for line in section_text.split('\n'):
                    if 'underfeed' in line.lower():
                        print(f"  {repr(line)}")
