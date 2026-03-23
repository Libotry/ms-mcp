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
    """单个阈值规�?"""
    
    metric_name: str
    condition: str  # e.g., ">20ms", "<5%", ">=10"
    severity: str   # "low", "medium", "high", "critical"
    raw_value: str  # original matched string
    
    
@dataclass  
class WorkflowPattern:
    """工作流程模式."""
    
    pattern_type: str
    description: str
    sequence: List[str] = field(default_factory=list)


@dataclass
class DiagnosticRule:
    """诊断规则."""
    
    rule_id: str
    symptom: str
    causes: List[str]
    evidence_patterns: List[str]
    recommendations: List[str]
    

@dataclass
class SkillConfig:
    """完整的技能配�?"""
    
    workflow_patterns: List[WorkflowPattern] = field(default_factory=list)
    thresholds: List[ThresholdRule] = field(default_factory=list)
    diagnostic_rules: Dict[str, DiagnosticRule] = field(default_factory=dict)
    methodology: str = ""
    output_schema: Dict[str, Any] = field(default_factory=dict)
    
    
def parse_skill_md(skill_path: Path) -> SkillConfig:
    """解析 SKILL.md 文件，提取所有规则和配置�?
    
    Args:
        skill_path: SKILL.md 文件路径
        
    Returns:
        SkillConfig 对象，包含所有解析出的配�?
    """
    if not skill_path.exists():
        return SkillConfig()
    
    content = skill_path.read_text(encoding="utf-8")
    config = SkillConfig()
    
    # 解析各个部分
    config.methodology = _extract_methodology(content)
    config.workflow_patterns = _extract_workflow_patterns(content)
    config.thresholds = _extract_thresholds(content)
    config.diagnostic_rules = _extract_diagnostic_rules(content)
    config.output_schema = _extract_output_schema(content)
    
    return config


def _extract_section(content: str, section_title: str) -> str:
    """提取指定章节的内�?"""
    # 支持多种标题格式
    patterns = [
        rf"^##\s*{re.escape(section_title)}\s*$",
        rf"^###\s*{re.escape(section_title)}\s*$",
        rf"^####\s*{re.escape(section_title)}\s*$",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
        if match:
            start_pos = match.end()
            # 找到下一个同级或上级标题
            next_header = re.search(r"^#{1,4}\s+", content[start_pos:], re.MULTILINE)
            if next_header:
                return content[start_pos:start_pos + next_header.start()]
            else:
                return content[start_pos:]
    
    return ""


def _extract_methodology(content: str) -> str:
    """提取方法论描�?"""
    # 查找 Methodology 关键�?
    method_match = re.search(
        r"(?:^|\n)\s*(?:Methodology|分析方法)[:：]\s*(.*?)(?=\n\s*\w+[:：]|$)",
        content,
        re.DOTALL | re.IGNORECASE
    )
    if method_match:
        return method_match.group(1).strip()
    
    # 或者从简介中提取
    intro = _extract_section(content, "Introduction") or _extract_section(content, "简�?)
    return intro.strip() if intro else ""


def _extract_workflow_patterns(content: str) -> List[WorkflowPattern]:
    """提取工作流程模式."""
    patterns = []
    
    workflow_section = _extract_section(content, "Workflow Patterns") or \
                       _extract_section(content, "工作流程") or \
                       _extract_section(content, "工作�?)
    
    if not workflow_section:
        return patterns
    
    # 匹配列表�?
    lines = workflow_section.split("\n")
    current_pattern: Optional[WorkflowPattern] = None
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
            
        # 检测是否是新的模式（通常有编号或特殊标记�?
        pattern_marker = re.match(r"^[-�?]\s*(\d+\.?\s*)?[A-Z][a-z]+:", line)
        if pattern_marker:
            if current_pattern:
                patterns.append(current_pattern)
            
            desc = line.split(":", 1)[1].strip() if ":" in line else line.lstrip("-�? ").strip()
            current_pattern = WorkflowPattern(
                pattern_type=f"pattern_{len(patterns)+1}",
                description=desc
            )
        elif current_pattern and (line.startswith("-") or line.startswith("*")):
            # 子步�?
            step = line.lstrip("-�? ").strip()
            current_pattern.sequence.append(step)
    
    if current_pattern:
        patterns.append(current_pattern)
    
    return patterns


def _extract_thresholds(content: str) -> List[ThresholdRule]:
    """提取阈值规�?"""
    thresholds = []
    
    # �?Diagnostic Rules 部分查找阈�?
    diag_section = _extract_section(content, "Diagnostic Rules") or \
                   _extract_section(content, "诊断规则")
    
    if not diag_section:
        return thresholds
    
    # 匹配各种阈值表示方�?
    threshold_patterns = [
        # "- High Risk (>20ms)"
        r"^\s*[-�?]\s*(High\s*Risk|Critical|Warning):\s*\(>([\d.]+)\s*(ms|us|%)\)",
        # "- >20ms: Critical"
        r"^\s*[-�?]\s*>([\d.]+)\s*(ms|us|%):\s*(\w+)",
        # "Gap > 5ms �?High Risk"
        r"\b(Gap|Bubble|Underfeed)\s*>\s*([\d.]+)\s*(ms|us|%)\s*[→\->]+\s*(\w+)",
    ]
    
    for pattern in threshold_patterns:
        matches = re.finditer(pattern, diag_section, re.MULTILINE | re.IGNORECASE)
        for match in matches:
            groups = match.groups()
            
            # 根据不同模式解析
            if len(groups) == 3 and groups[0].replace(" ", "").lower() in ["highrisk", "critical", "warning"]:
                severity_map = {"high risk": "high", "critical": "critical", "warning": "medium"}
                thresholds.append(ThresholdRule(
                    metric_name="unspecified",
                    condition=f">{groups[1]}{groups[2]}",
                    severity=severity_map.get(groups[0].lower(), "medium"),
                    raw_value=match.group(0)
                ))
            elif len(groups) >= 3:
                thresholds.append(ThresholdRule(
                    metric_name="metric",
                    condition=f"{groups[0]}{groups[1]}" if groups[0] else f">{groups[1]}{groups[2]}",
                    severity=groups[-1].lower() if groups[-1].lower() in ["low", "medium", "high", "critical"] else "medium",
                    raw_value=match.group(0)
                ))
    
    return thresholds


def _extract_diagnostic_rules(content: str) -> Dict[str, DiagnosticRule]:
    """提取诊断规则."""
    rules = {}
    
    diag_section = _extract_section(content, "Diagnostic Rules") or \
                   _extract_section(content, "诊断规则")
    
    if not diag_section:
        return rules
    
    # 尝试识别独立的诊断规则块
    # 格式可能是："Symptom: ... Causes: ... Evidence: ..."
    rule_blocks = re.split(r"\n(?=[A-Z][a-z]+:\s*$|\*\*[A-Z])", diag_section)
    
    for i, block in enumerate(rule_blocks):
        if not block.strip():
            continue
            
        symptom_match = re.search(r"Symptom[:：]\s*(.+)", block, re.IGNORECASE)
        if symptom_match:
            rule = DiagnosticRule(
                rule_id=f"rule_{i}",
                symptom=symptom_match.group(1).strip(),
                causes=_extract_list(block, "Causes"),
                evidence_patterns=_extract_list(block, "Evidence"),
                recommendations=_extract_list(block, "Recommendations") or _extract_list(block, "Solution")
            )
            rules[rule.rule_id] = rule
    
    return rules


def _extract_output_schema(content: str) -> Dict[str, Any]:
    """提取输出 Schema 定义."""
    schema_section = _extract_section(content, "Output Schema") or \
                     _extract_section(content, "Schema") or \
                     _extract_section(content, "JSONSchema")
    
    if not schema_section:
        return {}
    
    # 尝试提取 JSON Schema
    json_match = re.search(r"```(?:json)?\s*({.*?})\s*```", schema_section, re.DOTALL)
    if json_match:
        try:
            import json
            return json.loads(json_match.group(1))
        except Exception:
            pass
    
    # 简单的键值对提取
    schema = {}
    for line in schema_section.split("\n"):
        kv_match = re.match(r"^\s*(\w+)\s*[:：]\s*(.+)$", line)
        if kv_match:
            schema[kv_match.group(1)] = kv_match.group(2)
    
    return schema


def _extract_list(text: str, section_name: str) -> List[str]:
    """从文本中提取列表内容."""
    items = []
    
    # 查找 Section
    section_match = re.search(
        rf"{section_name}[:：]\s*\n?(.*?)(?={section_name}[:：]|^[A-Z]|\Z)",
        text,
        re.DOTALL | re.MULTILINE | re.IGNORECASE
    )
    
    if section_match:
        section_content = section_match.group(1)
        # 提取列表�?
        list_items = re.findall(r"^\s*[-�?]\s*(.+)$", section_content, re.MULTILINE)
        items.extend([item.strip() for item in list_items])
    
    return items


def get_default_thresholds() -> Dict[str, float]:
    """获取默认阈值配置（�?SKILL.md 不存在时使用）�?""
    return {
        "prelaunch_gap_warning_ms": 5.0,
        "prelaunch_gap_critical_ms": 20.0,
        "tail_gap_warning_ms": 3.0,
        "tail_gap_critical_ms": 10.0,
        "underfeed_ratio_warning": 0.3,
        "underfeed_ratio_critical": 0.6,
        "internal_bubble_warning_ms": 10.0,
        "internal_bubble_critical_ms": 30.0,
        "bubble_count_warning": 5,
    }


def load_skill_config(profiling_dir: Path) -> tuple[SkillConfig, Dict[str, float]]:
    """加载技能配置和阈值�?
    
    按优先级搜索 SKILL.md:
    1. profiling_dir/SKILL.md
    2. skills/ascend-profiling-anomaly/SKILL.md
    
    Returns:
        (SkillConfig, thresholds_dict) 元组
    """
    skill_paths = [
        profiling_dir / "SKILL.md",
        Path(__file__).parent / "ascend-profiling-anomaly" / "SKILL.md",
    ]
    
    for sp in skill_paths:
        if sp.exists():
            config = parse_skill_md(sp)
            thresholds = _build_thresholds_from_config(config)
            return config, thresholds
    
    # 回退到默认配�?
    return SkillConfig(), get_default_thresholds()


def _build_thresholds_from_config(config: SkillConfig) -> Dict[str, float]:
    """�?SkillConfig 构建阈值的字典。�?"
    thresholds = get_default_thresholds()
    
    # 如果�?SKILL.md 中解析到了具体阈值，可以覆盖默认�?
    # 这里可以根据实际需要扩展解析逻辑
    
    return thresholds
