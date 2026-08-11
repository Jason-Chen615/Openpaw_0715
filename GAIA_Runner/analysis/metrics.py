# -*- coding: utf-8 -*-
"""指标计算函数"""

from typing import List, Dict, Any
from collections import defaultdict
from ..core.models import ExecutionTrace, EventType


def calculate_tool_metrics(trace: ExecutionTrace) -> Dict[str, Any]:
    """
    计算工具使用指标
    
    Args:
        trace: 执行轨迹
        
    Returns:
        工具使用指标字典
    """
    tool_calls = defaultdict(lambda: {'count': 0, 'success': 0, 'errors': 0})
    
    for event in trace.events:
        if event.event_type == EventType.TOOL_CALL.value:
            tool_name = event.data.get('tool_name')
            tool_calls[tool_name]['count'] += 1
        elif event.event_type == EventType.TOOL_RESULT.value:
            tool_name = event.data.get('tool_name')
            status = event.data.get('status', 'success')
            if status == 'success':
                tool_calls[tool_name]['success'] += 1
            else:
                tool_calls[tool_name]['errors'] += 1
    
    # 计算聚合指标
    total_tools = len(tool_calls)
    total_calls = sum(t['count'] for t in tool_calls.values())
    unique_tools = total_tools
    total_errors = sum(t['errors'] for t in tool_calls.values())
    
    tool_diversity = unique_tools / max(total_calls, 1)
    
    return {
        'total_tool_calls': total_calls,
        'unique_tools': unique_tools,
        'tool_diversity': tool_diversity,
        'tool_failure_rate': total_errors / max(total_calls, 1),
        'tools_detail': dict(tool_calls),
    }


def calculate_context_metrics(trace: ExecutionTrace) -> Dict[str, Any]:
    """
    计算上下文相关指标
    
    Args:
        trace: 执行轨迹
        
    Returns:
        上下文指标字典
    """
    context_changes = []
    max_size = 0
    total_size = 0
    size_count = 0
    
    for event in trace.events:
        if event.event_type == EventType.TURN_START.value:
            size = event.data.get('context_size', 0)
            if size > max_size:
                max_size = size
            total_size += size
            size_count += 1
        elif event.event_type == EventType.CONTEXT_CHANGE.value:
            context_changes.append({
                'size_before': event.data.get('size_before', 0),
                'size_after': event.data.get('size_after', 0),
                'compression_rate': event.data.get('compression_rate', 0.0),
            })
    
    avg_size = total_size // max(size_count, 1)
    avg_compression = sum(c['compression_rate'] for c in context_changes) / max(len(context_changes), 1)
    
    return {
        'peak_context_size': max_size,
        'avg_context_size': avg_size,
        'compression_count': len(context_changes),
        'avg_compression_rate': avg_compression,
    }


def calculate_difficulty_score(trace: ExecutionTrace) -> float:
    """
    计算任务难度评分
    
    公式：难度 = 0.3*迭代数 + 0.25*工具多样性 + 0.25*context压力 + 0.2*决策复杂度
    
    Args:
        trace: 执行轨迹
        
    Returns:
        难度评分 (0.0 - 1.0)
    """
    # 计算迭代数
    turns = [e for e in trace.events if e.event_type == EventType.TURN_END.value]
    iteration_count = len(turns)
    iteration_score = min(iteration_count / 15.0, 1.0)  # 归一化
    
    # 计算工具多样性
    tool_metrics = calculate_tool_metrics(trace)
    tool_diversity = tool_metrics.get('tool_diversity', 0.0)
    
    # 计算context压力
    context_metrics = calculate_context_metrics(trace)
    peak_context = context_metrics.get('peak_context_size', 0)
    context_pressure = min(peak_context / 10000.0, 1.0)  # 归一化
    
    # 计算决策复杂度
    gates = [e for e in trace.events if e.event_type == EventType.GATE_CHECK.value]
    decision_complexity = len(gates) / max(iteration_count, 1) / 10.0
    
    # 加权求和
    difficulty_score = (
        0.3 * iteration_score +
        0.25 * tool_diversity +
        0.25 * context_pressure +
        0.2 * decision_complexity
    )
    
    return min(difficulty_score, 1.0)


def calculate_all_metrics(trace: ExecutionTrace) -> Dict[str, Any]:
    """计算所有指标"""
    return {
        'tool_metrics': calculate_tool_metrics(trace),
        'context_metrics': calculate_context_metrics(trace),
        'difficulty_score': calculate_difficulty_score(trace),
        'total_events': len(trace.events),
        'total_iterations': trace.total_iterations,
        'duration': trace.duration,
    }
