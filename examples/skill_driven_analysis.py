#!/usr/bin/env python3
"""SKILL.md 驱动的 Profiling 分析示例

演示如何让 SKILL.md 从静态文档变成可执行的配置规则。
展示两种使用方式：
1. 直接使用 skill_parser 解析 SKILL.md
2. 通过 ProfilingAnalyzer 自动加载并使用 SKILL.md 配置
"""

from pathlib import Path

from skills.skill_parser import parse_skill_md, get_default_thresholds
from skills.profiling_analyzer import ProfilingAnalyzer


def demo_direct_parsing():
    """演示直接解析 SKILL.md 文件."""
    print("=" * 80)
    print("1. 直接解析 SKILL.md 配置文件")
    print("=" * 80)
    
    # 定位 SKILL.md 文件
    skill_path = Path(__file__).parent.parent / "skills" / "ascend-profiling-anomaly" / "SKILL.md"
    
    if not skill_path.exists():
        print(f"✗ SKILL.md 未找到：{skill_path}")
        print("\n说明：SKILL.md 当前位于 skills/ascend-profiling-anomaly/SKILL.md")
        return
    
    print(f"\n✓ 找到 SKILL.md: {skill_path}\n")
    
    # 解析配置
    config = parse_skill_md(skill_path)
    
    print(f"解析结果:")
    print(f"  - 工作流程模式数量：{len(config.workflow_patterns)}")
    print(f"  - 阈值规则数量：{len(config.thresholds)}")
    print(f"  - 诊断规则数量：{len(config.diagnostic_rules)}")
    print(f"  - 方法论摘要：{config.methodology[:50] if config.methodology else 'N/A'}...")
    
    if config.workflow_patterns:
        print(f"\n工作流程模式 (前 3 条):")
        for i, pattern in enumerate(config.workflow_patterns[:3], 1):
            print(f"  {i}. {pattern.description}")
    
    if config.thresholds:
        print(f"\n阈值配置:")
        for metric, rule in list(config.thresholds.items())[:3]:
            print(f"  - {rule.metric_name}: {rule.condition} ({rule.severity})")


def demo_auto_loading():
    """演示 ProfilingAnalyzer 自动加载 SKILL.md 配置."""
    print("\n" + "=" * 80)
    print("2. ProfilingAnalyzer 自动加载 SKILL.md 配置")
    print("=" * 80)
    
    # 使用测试数据目录
    test_data_dir = Path(__file__).parent.parent / "test_data"
    
    if not test_data_dir.exists():
        print(f"\n✗ 测试数据目录不存在：{test_data_dir}")
        return
    
    # 创建分析器（会自动查找并加载 SKILL.md）
    analyzer = ProfilingAnalyzer(test_data_dir)
    
    print(f"\n✓ 分析器已初始化")
    print(f"  - 数据目录：{test_data_dir}")
    print(f"  - SKILL.md 状态：{'已加载' if analyzer.skill_config.methodology else '使用默认配置'}")
    print(f"  - 阈值配置项数：{len(analyzer.thresholds)}")
    
    # 显示使用的阈值
    print(f"\n当前使用的阈值配置:")
    for key, value in sorted(analyzer.thresholds.items()):
        print(f"  - {key}: {value}")
    
    # 执行分析
    print("\n" + "-" * 80)
    print("正在执行 profiling 数据分析...")
    print("-" * 80)
    
    try:
        report = analyzer.analyze()
        
        print(f"\n✓ 分析完成!")
        print(f"\n报告摘要:")
        print(f"  - 总步骤数：{report.total_steps}")
        print(f"  - 整体风险等级：{report.overall_risk_level}")
        print(f"  - 关键发现数：{len(report.key_findings)}")
        print(f"  - 建议数：{len(report.recommendations)}")
        
        if report.key_findings:
            print(f"\n关键发现 (前 5 条):")
            for i, finding in enumerate(report.key_findings[:5], 1):
                print(f"  {i}. {finding}")
                
        if report.recommendations:
            print(f"\n优化建议:")
            for i, rec in enumerate(report.recommendations[:3], 1):
                print(f"  {i}. {rec}")
        
    except FileNotFoundError as e:
        print(f"\n✗ 数据文件缺失：{e}")
        print("\n提示：请确保 test_data 目录下包含必要的 profiling 数据文件")
    except Exception as e:
        print(f"\n✗ 分析失败：{e}")
        import traceback
        traceback.print_exc()


def compare_approaches():
    """对比有无 SKILL.md 的差异."""
    print("\n" + "=" * 80)
    print("3. SKILL.md vs 默认配置的差异")
    print("=" * 80)
    
    default_thresholds = get_default_thresholds()
    
    print("\n默认阈值配置（当 SKILL.md 不存在时使用）:")
    for key, value in sorted(default_thresholds.items()):
        print(f"  - {key}: {value}")
    
    print("\n💡 说明:")
    print("  - 如果 SKILL.md 存在且定义了阈值，将优先使用 SKILL.md 的配置")
    print("  - 这使得调整检测标准无需修改代码，只需编辑 SKILL.md 即可")
    print("  - SKILL.md 同时作为人类可读的文档和机器可执行的配置")


def main():
    """主函数."""
    print("\n" + "=" * 80)
    print("SKILL.md 驱动分析演示")
    print("=" * 80)
    print("\n本示例展示如何将 SKILL.md 从静态文档转变为可执行配置\n")
    
    # 演示三种用法
    demo_direct_parsing()
    demo_auto_loading()
    compare_approaches()
    
    print("\n" + "=" * 80)
    print("演示完成")
    print("=" * 80)
    print("\n下一步:")
    print("  1. 根据实际需求调整 skills/ascend-profiling-anomaly/SKILL.md 中的规则和阈值")
    print("  2. 运行此脚本验证新配置的效果")
    print("  3. 在生产环境中使用 ProfilingAnalyzer 进行自动化分析")
    print()


if __name__ == "__main__":
    main()
