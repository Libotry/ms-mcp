"""Profiling Anomaly Analysis MCP Tool

为 MCP Server 提供的性能异常分析工具函数。
"""

from pathlib import Path
import json


def register_profiling_anomaly_tool(mcp):
    """向 MCP 实例注册 profiling anomaly 分析工具"""
    
    @mcp.tool()
    def analyze_profiling_anomaly(profiling_dir: str, output_report: bool = True) -> str:
        """深度分析昇腾 Profiling 数据，检测性能异常和气泡问题，生成架构级分析报告。

        基于参考脚本的分析方法，对 step_trace_time.csv 和其他 profiling 数据进行深入分析，
        识别以下类型的性能问题:
        
        - 预启动间隙 (Prelaunch Gap): Host 侧数据预处理慢于 Device 执行速度
        - 尾部间隙 (Tail Gap): 最后一个 Kernel 结束后到 Step 结束的闲置时间
        - 内部气泡 (Internal Bubbles): Stream 内多个 Kernel 之间的碎片化间隔
        - 设备欠载 (Device Underfeed): AI Core/AI Vector Core 利用率不足
        - 迭代不稳定：不同 Step 之间耗时差异过大
        
        分析流程:
        1. 解析 step_trace_time.csv 获取每个 iteration 的时间边界
        2. 从 op_statistic_0.csv 等文件提取设备执行区间
        3. 计算每个 Step 的气泡指标和服务时间
        4. 识别健康度风险等级 (low/medium/high/critical)
        5. 汇总关键发现和生成优化建议
        6. 可选导出详细 JSON 报告
        
        Args:
            profiling_dir: Profiling 数据目录路径 (应包含 step_trace_time.csv 等文件)
            output_report: 是否导出详细 JSON 报告到 analyzing_result.json，默认 True
        
        Returns:
            JSON 格式的分析摘要，包含总体风险评估、关键发现和优化建议
        """
        from skills.profiling_analyzer import ProfilingAnalyzer
        
        try:
            profiler = ProfilingAnalyzer(Path(profiling_dir))
            report = profiler.analyze()
            
            # 导出详细报告
            if output_report:
                report_path = Path(profiling_dir) / "analyzing_result.json"
                profiler.export_report(report_path)
            
            result = {
                "summary": {
                    "total_steps": report.total_steps,
                    "overall_risk_level": report.overall_risk_level,
                    "key_findings": report.key_findings,
                    "recommendations": report.recommendations,
                },
                "step_statistics": {
                    "avg_duration_ms": sum(s.duration_ms for s in report.analyzed_steps) / max(1, len(report.analyzed_steps)),
                    "risk_distribution": {},
                },
                "detailed_report_path": str(report_path) if output_report else None,
            }
            
            # 统计风险分布
            risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
            for step in report.analyzed_steps:
                risk_dist[step.risk_level] += 1
            result["step_statistics"]["risk_distribution"] = risk_dist
            
            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except FileNotFoundError as e:
            return json.dumps({"error": f"Profiling 数据文件缺失：{e}"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"分析失败：{type(e).__name__}: {e}"}, ensure_ascii=False)
    
    return analyze_profiling_anomaly
