# -*- coding: utf-8 -*-
"""报告生成"""

import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from analysis.analyzer import Analyzer
from core.models import ExecutionTrace


class ReportGenerator:
    """报告生成器"""

    def __init__(self, output_dir: str | Path):
        """初始化报告生成器"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_json_report(
        self,
        analyzer: Analyzer,
        output_filename: str = "analysis_report.json"
    ) -> Path:
        """
        生成JSON格式的分析报告
        
        Args:
            analyzer: 分析器对象
            output_filename: 输出文件名
            
        Returns:
            报告文件路径
        """
        summary = analyzer.get_summary()
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': summary,
            'analysis_results': [r.to_dict() for r in analyzer.analysis_results],
            'level_statistics': analyzer.get_level_statistics(),
        }
        
        output_path = self.output_dir / output_filename
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return output_path

    def generate_html_report(
        self,
        analyzer: Analyzer,
        output_filename: str = "analysis_report.html"
    ) -> Path:
        """
        生成HTML格式的分析报告
        
        Args:
            analyzer: 分析器对象
            output_filename: 输出文件名
            
        Returns:
            报告文件路径
        """
        summary = analyzer.get_summary()
        level_stats = analyzer.get_level_statistics()
        
        html_content = self._generate_html(summary, level_stats)
        
        output_path = self.output_dir / output_filename
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path

    def _generate_html(self, summary: Dict[str, Any], level_stats: Dict[int, Dict[str, Any]]) -> str:
        """生成HTML内容"""
        total = summary['total_cases']
        successful = summary['successful_cases']
        success_rate = summary['success_rate']
        
        level_rows = ""
        for level in sorted(level_stats.keys()):
            stats = level_stats[level]
            level_rows += f"""
            <tr>
                <td>Level {level}</td>
                <td>{stats['count']}</td>
                <td>{stats['successful']}</td>
                <td>{stats['successful']/max(stats['count'],1)*100:.1f}%</td>
                <td>{stats['avg_difficulty']:.2f}</td>
                <td>{stats['avg_tools']:.2f}</td>
                <td>{stats['avg_context']:.0f}</td>
            </tr>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>GAIA测试分析报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .summary {{ background-color: #f9f9f9; padding: 10px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <h1>GAIA测试分析报告</h1>
            <div class="summary">
                <p><strong>总案例数:</strong> {total}</p>
                <p><strong>成功案例:</strong> {successful}</p>
                <p><strong>成功率:</strong> {success_rate*100:.1f}%</p>
                <p><strong>总事件数:</strong> {summary['total_events']}</p>
                <p><strong>总耗时:</strong> {summary['total_duration']:.2f}s</p>
            </div>
            
            <h2>按Level统计</h2>
            <table>
                <tr>
                    <th>Level</th>
                    <th>总数</th>
                    <th>成功</th>
                    <th>成功率</th>
                    <th>平均难度</th>
                    <th>平均工具多样性</th>
                    <th>平均Context大小</th>
                </tr>
                {level_rows}
            </table>
        </body>
        </html>
        """
        
        return html

    def generate_comparison_report(
        self,
        traces_by_level: Dict[int, List[ExecutionTrace]],
        output_filename: str = "comparison_report.json"
    ) -> Path:
        """
        生成对比分析报告
        
        Args:
            traces_by_level: 按level分组的轨迹
            output_filename: 输出文件名
            
        Returns:
            报告文件路径
        """
        report = {
            'timestamp': datetime.now().isoformat(),
            'level_comparisons': {},
        }
        
        for level, traces in traces_by_level.items():
            analyzer = Analyzer()
            for trace in traces:
                analyzer.add_trace(trace)
            analyzer.analyze_all()
            
            report['level_comparisons'][level] = analyzer.get_summary()
        
        output_path = self.output_dir / output_filename
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return output_path
