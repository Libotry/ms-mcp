"""SKILL.md Parser and Rule Engine

Parses SKILL.md and rulebook.md to extract diagnostic rules, thresholds,
and workflow configurations for skill-driven profiling analysis.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class SkillConfig:
    """Configuration extracted from SKILL.md."""
    name: str = ""
    description: str = ""
    methodology_summary: str = ""
    workflow_patterns: List[str] = field(default_factory=list)
    diagnostic_rules: Dict[str, float] = field(default_factory=dict)


def parse_skill_md(skill_path: Path) -> SkillConfig:
    """Parse SKILL.md file and extract configuration.
    
    Args:
        skill_path: Path to SKILL.md
        
    Returns:
        SkillConfig object with extracted data
    """
    if not skill_path.exists():
        return SkillConfig()
    
    content = skill_path.read_text(encoding="utf-8")
    config = SkillConfig()
    
    # Extract basic metadata from frontmatter
    frontmatter_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if frontmatter_match:
        yaml_content = frontmatter_match.group(1)
        try:
            import yaml
            frontmatter = yaml.safe_load(yaml_content)
            config.name = frontmatter.get('name', '')
            config.description = frontmatter.get('description', '')
        except Exception:
            pass
    
    # Extract workflow patterns from Purpose section
    purpose_match = re.search(
        r'##\s*Purpose\s*\n+(.*?)(?=^##|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if purpose_match:
        purpose_section = purpose_match.group(1)
        # Look for numbered pipelines
        pipelines = re.findall(r'\d+\.\s*\*\*(.+?)\*\*:?\s*(.*)', purpose_section)
        config.workflow_patterns = [f"{idx+1}. {title.strip()}: {desc.strip()}" 
                                   for idx, (title, desc) in enumerate(pipelines)]
        
        # Extract methodology summary
        if 'core philosophy' in purpose_section.lower():
            philo_match = re.search(r'The core philosophy is\s+(.+?)(?:\.|\n)', purpose_section, re.IGNORECASE)
            if philo_match:
                config.methodology_summary = philo_match.group(1).strip()
    
    # Parse diagnostic rules from rulebook.md if it exists
    rulebook_path = skill_path.parent / "references" / "rulebook.md"
    if rulebook_path.exists():
        rulebook_content = rulebook_path.read_text(encoding="utf-8")
        _parse_rulebook_thresholds(rulebook_content, config)
    
    return config


def _parse_rulebook_thresholds(content: str, config: SkillConfig) -> None:
    """从 rulebook.md 中解析阈值规则."""
    thresholds = {}
    
    # 解析 2.2 High-severity bubble thresholds
    bubble_section = re.search(
        r'###\s*2\.2\s+High-severity\s+bubble\s+thresholds\s*\n+(.*?)(?=^###|\Z)',
        content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    if bubble_section:
        section_text = bubble_section.group(1)
        
        # 提取 underfeed_ratio 阈值
        underfeed_match = re.search(r'underfeed_ratio\s*>=\s*([\d.]+)', section_text)
        if underfeed_match:
            thresholds['underfeed_heavy'] = float(underfeed_match.group(1))
        
        # 提取 internal_bubble 阈值公式
        int_bub_match = re.search(r'largest_internal_bubble_ms\s*>=\s*max\(1\.0,\s*([\d.]+)\s*\*\s*service_ms\)', section_text)
        if int_bub_match:
            thresholds['internal_bubble_ratio'] = float(int_bub_match.group(1))
        
        # 提取 prelaunch_gap 阈值
        prelaunch_match = re.search(r'prelaunch_gap_ms\s*>=\s*max\(1\.0,\s*([\d.]+)\s*\*\s*service_ms\)', section_text)
        if prelaunch_match:
            thresholds['prelaunch_gap_ratio'] = float(prelaunch_match.group(1))
            
        # 提取 tail_gap 阈值
        tail_match = re.search(r'tail_gap_ms\s*>=\s*max\(1\.0,\s*([\d.]+)\s*\*\s*service_ms\)', section_text)
        if tail_match:
            thresholds['tail_gap_ratio'] = float(tail_match.group(1))
    
    # 解析 5.1 Wait-Anchor 规则
    wait_anchor_section = re.search(
        r'###\s*5\.1\s+Definition\s*\n+(.*?)(?=^###|\Z)',
        content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    if wait_anchor_section:
        wa_match = re.search(r'wait_ratio\s*>\s*([\d.]+)', wait_anchor_section.group(1))
        if wa_match:
            thresholds['wait_anchor_ratio'] = float(wa_match.group(1))
    
    # 解析 6.1 AICPU 分类规则
    aicpu_section = re.search(
        r'###\s*6\.1\s+Classification\s+by\s+masked_ratio\s*\n+(.*?)(?=^###|\Z)',
        content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    if aicpu_section:
        section_text = aicpu_section.group(1)
        
        # masked_ratio >= 0.9
        masked_high = re.search(r'masked_ratio\s*>=\s*([\d.]+)', section_text)
        if masked_high:
            thresholds['aicpu_masked_high'] = float(masked_high.group(1))
        
        # 0.2 <= masked_ratio < 0.9
        masked_mid = re.search(r'([\d.]+)\s*<=\s*masked_ratio\s*<\s*([\d.]+)', section_text)
        if masked_mid:
            thresholds['aicpu_partially_exposed_low'] = float(masked_mid.group(1))
            thresholds['aicpu_partially_exposed_high'] = float(masked_mid.group(2))
    
    # 存储到 config
    config.diagnostic_rules.update(thresholds)


def get_default_thresholds() -> Dict[str, float]:
    """获取默认阈值配置（当 SKILL.md 不存在时使用）."""
    return {
        # Bubble detection thresholds (from rulebook.md Section 2.2)
        "underfeed_heavy": 0.30,  # underfeed_ratio >= 0.30
        "internal_bubble_ratio": 0.10,  # largest_internal_bubble_ms >= max(1.0, 0.10 * service_ms)
        "prelaunch_gap_ratio": 0.10,  # prelaunch_gap_ms >= max(1.0, 0.10 * service_ms)
        "tail_gap_ratio": 0.10,  # tail_gap_ms >= max(1.0, 0.10 * service_ms)
        
        # Absolute thresholds (fallback when service_ms unknown)
        "prelaunch_gap_high": 5.0,  # ms
        "tail_gap_medium": 3.0,  # ms
        "tail_gap_high": 10.0,  # ms
        "internal_bubble_medium": 10.0,  # ms
        "internal_bubble_high": 30.0,  # ms
        
        # Wait-Anchor threshold (Section 5.1)
        "wait_anchor_ratio": 0.95,  # wait_ratio > 0.95
        
        # AICPU classification thresholds (Section 6.1)
        "aicpu_masked_high": 0.9,  # masked_ratio >= 0.9
        "aicpu_partially_exposed_low": 0.2,  # 0.2 <= masked_ratio < 0.9
        "aicpu_partially_exposed_high": 0.9,
        
        # Underfeed severity levels
        "underfeed_critical": 0.7,
        "underfeed_high": 0.3,
    }


def load_skill_config(profiling_dir: Path) -> tuple[SkillConfig, Dict[str, float]]:
    """从指定目录或默认位置加载 SKILL.md 配置。
    
    Args:
        profiling_dir: Profiling 数据目录
        
    Returns:
        (SkillConfig, thresholds_dict) 元组
    """
    skill_paths = [
        profiling_dir / "SKILL.md",
        profiling_dir / "ascend-profiling-anomaly" / "SKILL.md",
        Path(__file__).parent / "ascend-profiling-anomaly" / "SKILL.md",
    ]
    
    for sp in skill_paths:
        if sp.exists():
            config = parse_skill_md(sp)
            thresholds = _build_thresholds_from_config(config)
            return config, thresholds
    
    # 回退到默认配置
    return SkillConfig(), get_default_thresholds()


def _build_thresholds_from_config(config: SkillConfig) -> Dict[str, float]:
    """从 SkillConfig 构建阈值的字典."""
    # 优先使用从 rulebook.md 解析的阈值
    if config.diagnostic_rules:
        return config.diagnostic_rules.copy()
    
    # 否则使用默认值
    return get_default_thresholds()
