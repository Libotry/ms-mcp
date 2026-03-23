"""SKILL.md Parser and Rule Engine

Parses SKILL.md files to extract diagnostic rules, thresholds, and methodologies.
Makes the skill specifications programmatically accessible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ThresholdRule:
    """单个阈值规则。"""
    
    metric_name: str
    condition: str  # e.g., ">20ms", "<5%", ">=10"
    severity: str   # "low", "medium", "high", "critical"
    raw_value: str  # original matched string
    
    
@dataclass  
class WorkflowPattern:
    """工作流程模式."""
    
    pattern_type: str
    description: str
    

@dataclass
class DiagnosticRule:
    """诊断规则."""
    
    rule_id: str
    symptom_pattern: str
    suggested_checks: List[str]
    

@dataclass
class SkillConfig:
    """完整的技能配置。"""
    
    name: str = ""
    description: str = ""
    methodology_summary: str = ""
    workflow_patterns: List[str] = field(default_factory=list)
    diagnostic_rules: Dict[str, float] = field(default_factory=dict)
    thresholds: Dict[str, ThresholdRule] = field(default_factory=dict)
    diagnostic_rule_objects: List[DiagnosticRule] = field(default_factory=list)
    methodology: str = ""
    output_schema: Dict[str, Any] = field(default_factory=dict)


def parse_skill_md(skill_path: Path) -> SkillConfig:
    """解析 SKILL.md 文件，提取规则、工作流和阈值配置。
    
    Args:
        skill_path: SKILL.md 文件路径
        
    Returns:
        SkillConfig 对象，包含所有解析的配置
    """
    if not skill_path.exists():
        return SkillConfig()
    
    content = skill_path.read_text(encoding="utf-8")
    config = SkillConfig()
    
    # 提取 Workflow Patterns
    workflow_match = re.search(
        r"##\s*Workflow\s*Patterns?\s*\n+(.*?)(?=^##|\Z)",
        content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    if workflow_match:
        section = workflow_match.group(1)
        patterns = re.findall(r"^[\s]*[-•*]\s*(.+)$", section, re.MULTILINE)
        config.workflow_patterns = [
            WorkflowPattern(pattern_type="workflow", description=p.strip())
            for p in patterns
        ]
    
    # 提取 Diagnostic Rules
    diag_match = re.search(
        r"##\s*Diagnostic\s*Rules?(?:\s+\([^)]*\))?[^#]*\n+(.*?)(?=^##|\Z)",
        content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    if diag_match:
        section = diag_match.group(1)
        # 匹配如 "- High Risk (>20ms)" 这样的行
        threshold_lines = re.findall(
            r"^\s*[-•*]\s*(\w+)\s*[:(].*?[>(]([\d.]+\s*(?:ms|us|%)).*?$",
            section,
            re.MULTILINE | re.IGNORECASE
        )
        for metric, value in threshold_lines:
            config.thresholds[metric.lower()] = ThresholdRule(
                metric_name=metric,
                condition=f">{value}",
                severity="high",
                raw_value=value
            )
    
    # 提取 Methodology
    method_match = re.search(
        r"(?:^|\n)\s*Methodology:\s*(.*?)(?=\n\s*\w+:|$)",
        content,
        re.DOTALL | re.IGNORECASE
    )
    if method_match:
        config.methodology = method_match.group(1).strip()
    
    return config


def get_default_thresholds() -> Dict[str, float]:
    """获取默认阈值配置（当 SKILL.md 不可用时）。"""
    return {
        "prelaunch_gap_high": 5.0,      # ms
        "tail_gap_medium": 3.0,         # ms
        "tail_gap_high": 10.0,          # ms
        "underfeed_critical": 0.7,      # ratio
        "underfeed_high": 0.3,          # ratio
        "internal_bubble_medium": 10.0, # ms
        "internal_bubble_high": 30.0,   # ms
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
    thresholds = get_default_thresholds()
    
    # 如果从 SKILL.md 中解析到了具体阈值，可以覆盖默认值
    # 这里可以根据实际需要扩展解析逻辑
    
    return thresholds
