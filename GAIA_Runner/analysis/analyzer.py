# -*- coding: utf-8 -*-
"""四维度分析器"""

from typing import List, Dict, Any
from collections import defaultdict
from .metrics import calculate_all_metrics
from ..core.models import ExecutionTrace, AnalysisResult


class Analyzer:
    """执行轨迹分析器"""

    def __init__(self):
        """初始化分析器"""
        self.traces: List[ExecutionTrace] = []
        self.analysis_results: List[AnalysisResult] = []

    def add_trace(self, trace: ExecutionTrace) -> None:
        """添加轨迹"""
        self.traces.append(trace)

    def analyze_single(self, trace: ExecutionTrace) -> AnalysisResult:
        """
        分析单个轨迹
        
        Args:
            trace: 执行轨迹
            
        Returns:
            分析结果
        """
        metrics = calculate_all_metrics(trace)
        
        result = AnalysisResult(
            case_id=trace.case_id,
            level=trace.level,
            difficulty_score=metrics['difficulty_score'],
            tool_diversity=metrics['tool_metrics'].get('tool_diversity', 0.0),
            tool_reuse_rate=1.0 - metrics['tool_metrics'].get('tool_diversity', 0.0),
            tool_failure_rate=metrics['tool_metrics'].get('tool_failure_rate', 0.0),
            peak_context=metrics['context_metrics'].get('peak_context_size', 0),
            avg_context=metrics['context_metrics'].get('avg_context_size', 0),
            compression_count=metrics['context_metrics'].get('compression_count', 0),
            compression_rate=metrics['context_metrics'].get('avg_compression_rate', 0.0),
        )
        
        self.analysis_results.append(result)
        return result

    def analyze_all(self) -> List[AnalysisResult]:
        """分析所有轨迹"""
        self.analysis_results = []
        for trace in self.traces:
            self.analyze_single(trace)
        return self.analysis_results

    def get_level_statistics(self) -> Dict[int, Dict[str, Any]]:
        """获取按level分组的统计"""
        stats = defaultdict(lambda: {
            'count': 0,
            'successful': 0,
            'avg_difficulty': 0.0,
            'avg_iterations': 0.0,
            'avg_tools': 0.0,
            'avg_context': 0.0,
        })
        
        for trace in self.traces:
            level = trace.level
            stats[level]['count'] += 1
            if trace.success:
                stats[level]['successful'] += 1
        
        for result in self.analysis_results:
            level = result.level
            stats[level]['avg_difficulty'] += result.difficulty_score
            stats[level]['avg_tools'] += result.tool_diversity
            stats[level]['avg_context'] += result.peak_context
        
        for level in stats:
            count = max(stats[level]['count'], 1)
            stats[level]['avg_difficulty'] /= count
            stats[level]['avg_tools'] /= count
            stats[level]['avg_context'] /= count
        
        return dict(stats)

    def get_summary(self) -> Dict[str, Any]:
        """获取分析摘要"""
        total = len(self.traces)
        successful = sum(1 for t in self.traces if t.success)
        
        level_stats = self.get_level_statistics()
        
        return {
            'total_cases': total,
            'successful_cases': successful,
            'success_rate': successful / max(total, 1),
            'level_statistics': level_stats,
            'total_events': sum(len(t.events) for t in self.traces),
            'total_duration': sum(t.duration for t in self.traces),
        }
