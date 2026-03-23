"""
示例：使用 Ascend Profiling Anomaly Detection MCP 工具

本示例展示如何使用新增的 profiling 异常检测工具来分析昇腾 AI 处理器的性能数据。
"""

import asyncio
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# 方法 1: 作为独立分析器使用
def analyze_profiling_data():
    """直接使用 ProfilingAnalyzer 进行分析"""
    from skills.profiling_analyzer import ProfilingAnalyzer
    
    # 指定 profiling 数据目录
    # 注意：需要是实际的 Ascend Profiler 导出的数据格式
    # 标准格式应包含 step_trace_time.csv 文件，其中包含：
    # - Iteration Index
    # - Iteration Start Timestamp(ms)  
    # - Iteration End Timestamp(ms)
    profiling_dir = Path("./profiling_output")
    
    if not profiling_dir.exists():
        print(f"目录不存在：{profiling_dir}")
        print("请使用真实的 Ascend Profiler 导出数据进行测试")
        return
    
    # 创建分析器并执行分析
    analyzer = ProfilingAnalyzer(profiling_dir)
    report = analyzer.analyze()
    
    # 打印分析报告
    print("\n=== Profiling 分析报告 ===")
    print(f"总步数：{report.total_steps}")
    print(f"风险等级：{report.overall_risk_level}")
    print(f"\n关键发现 ({len(report.key_findings)}):")
    for finding in report.key_findings[:5]:  # 显示前 5 个
        print(f"  • {finding}")
    
    print(f"\n建议 ({len(report.recommendations)}):")
    for rec in report.recommendations[:3]:  # 显示前 3 个
        print(f"  • {rec}")


# 方法 2: 通过 MCP Server 使用
async def run_mcp_server_example():
    """运行集成后的 MCP Server"""
    from server import app
    
    print("启动 MCP Server...")
    print("可通过 stdio 或 SSE 连接到服务器")
    print("\n可用工具:")
    print("  - ascend_profiling_analysis: 自动分析 profiling 数据中的异常")
    print("\n参数说明:")
    print("  profiling_dir: Profiling 数据所在目录路径")
    print("  threshold_percentile: 异常阈值百分位数 (默认：90)")
    print("  min_duration_us: 最小关注时长 (微秒，默认：1000)")
    

# 方法 3: 在现有技能系统中使用
def integrate_with_skill_system():
    """将 profiling 分析与现有技能系统结合"""
    from skills.indexer import SkillIndexer
    from skills.retriever import SkillRetriever
    from skills.reranker import SkillReranker
    from skills.router import route_to_skill
    from skills.profiling_analyzer import ProfilingAnalyzer
    
    print("Profiling 分析已集成到技能系统!")
    print("\n工作流程:")
    print("1. 用户请求 -> router.route_to_skill()")
    print("2. 识别为性能分析类问题")
    print("3. 调用 ProfilingAnalyzer 进行深度分析")
    print("4. 生成架构报告和优化建议")
    print("\n支持的场景:")
    print("  • 训练速度慢诊断")
    print("  • 通信瓶颈识别")
    print("  • 算子性能优化")
    print("  • 流水线气泡分析")


if __name__ == "__main__":
    print("=" * 60)
    print("Ascend Profiling Anomaly Detection Tool Examples")
    print("=" * 60)
    
    # 选择要运行的示例
    print("\n请选择示例模式:")
    print("1. 直接分析 profiling 数据")
    print("2. 查看 MCP Server 信息")
    print("3. 了解技能系统集成")
    
    choice = input("\n输入选项 (1-3): ").strip()
    
    if choice == "1":
        analyze_profiling_data()
    elif choice == "2":
        asyncio.run(run_mcp_server_example())
    elif choice == "3":
        integrate_with_skill_system()
    else:
        print("无效选项")
