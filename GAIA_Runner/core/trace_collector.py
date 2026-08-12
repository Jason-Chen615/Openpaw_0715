# -*- coding: utf-8 -*-
"""执行轨迹采集器"""

import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import defaultdict
from datetime import datetime
from core.models import TraceEvent, EventType, ExecutionTrace, GAIACase


class TraceCollector:
    """采集和存储执行轨迹"""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.traces_dir = self.output_dir / "traces"
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        self.current_trace: Optional[ExecutionTrace] = None
        self.all_traces: List[ExecutionTrace] = []
        self.raw_sse_file: Optional[Path] = None  # 原始SSE流文件句柄

    def start_case(self, case_id: str, level: int, case: GAIACase) -> ExecutionTrace:
        """开始记录一个case"""
        self.current_trace = ExecutionTrace(
            case_id=case_id,
            level=level,
            start_time=time.time(),
            end_time=0.0
        )
        return self.current_trace

    def record_event(self, event_type, iteration: int, data: Dict[str, Any]) -> None:
        """记录一个事件（支持EventType枚举或字符串）"""
        if self.current_trace is None:
            raise RuntimeError("未启动case记录")
        
        # 支持EventType枚举或字符串类型
        if isinstance(event_type, EventType):
            event_type_str = event_type.value
        else:
            event_type_str = str(event_type)
        
        event = TraceEvent(
            timestamp=time.time(),
            event_type=event_type_str,
            iteration=iteration,
            case_id=self.current_trace.case_id,
            level=self.current_trace.level,
            data=data
        )
        self.current_trace.add_event(event)

    def record_turn_start(self, iteration: int, question: str, context_size: int) -> None:
        """记录Turn开始"""
        self.record_event(
            EventType.TURN_START,
            iteration,
            {'question': question, 'context_size': context_size}
        )

    def record_turn_end(
        self, 
        iteration: int, 
        response: str, 
        context_size: int,
        duration: float
    ) -> None:
        """记录Turn结束"""
        self.record_event(
            EventType.TURN_END,
            iteration,
            {'response': response, 'context_size': context_size, 'duration': duration}
        )

    def record_tool_call(
        self,
        iteration: int,
        tool_name: str,
        args: Dict[str, Any],
        duration: float = 0.0
    ) -> None:
        """记录工具调用"""
        self.record_event(
            EventType.TOOL_CALL,
            iteration,
            {'tool_name': tool_name, 'args': args, 'duration': duration}
        )

    def record_tool_result(
        self,
        iteration: int,
        tool_name: str,
        result: Any,
        status: str = "success",
        error: Optional[str] = None
    ) -> None:
        """记录工具结果"""
        self.record_event(
            EventType.TOOL_RESULT,
            iteration,
            {
                'tool_name': tool_name,
                'result': str(result)[:500],
                'status': status,
                'error': error,
            }
        )

    def record_context_change(
        self,
        iteration: int,
        size_before: int,
        size_after: int,
        method: str = "default"
    ) -> None:
        """记录上下文变化"""
        rate = 1.0 - (size_after / size_before) if size_before > 0 else 0.0
        self.record_event(
            EventType.CONTEXT_CHANGE,
            iteration,
            {
                'size_before': size_before,
                'size_after': size_after,
                'compression_rate': rate,
                'method': method,
            }
        )

    def record_gate_check(
        self,
        iteration: int,
        gate_type: str,
        decision: str,
        reason: Optional[str] = None
    ) -> None:
        """记录Gate检查"""
        self.record_event(
            EventType.GATE_CHECK,
            iteration,
            {
                'gate_type': gate_type,
                'decision': decision,
                'reason': reason,
            }
        )

    def init_raw_sse_file(self) -> None:
        """初始化原始SSE流文件"""
        if self.current_trace is None:
            raise RuntimeError("未启动case记录")
        
        self.raw_sse_file = self.traces_dir / f"{self.current_trace.case_id}_level{self.current_trace.level}_raw_sse.txt"
        # 如果文件已存在则覆盖
        with open(self.raw_sse_file, 'w', encoding='utf-8') as f:
            f.write(f"=== Raw SSE Stream for case {self.current_trace.case_id} (Level {self.current_trace.level}) ===\n")
            f.write(f"Started at: {datetime.now().isoformat()}\n")
            f.write("=" * 80 + "\n\n")

    def record_raw_sse(self, sse_line: str) -> None:
        """记录原始SSE流中的一条消息"""
        if self.raw_sse_file is None:
            self.init_raw_sse_file()
        
        # 添加时间戳标记每条SSE消息
        timestamp = datetime.now().isoformat()
        with open(self.raw_sse_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {sse_line}\n")

    def end_case(
        self,
        success: bool = False,
        final_answer: Optional[str] = None,
        error: Optional[str] = None
    ) -> ExecutionTrace:
        """结束case记录并保存"""
        if self.current_trace is None:
            raise RuntimeError("未启动case记录")
        
        self.current_trace.end_time = time.time()
        self.current_trace.success = success
        self.current_trace.final_answer = final_answer
        self.current_trace.error = error
        
        self._save_trace(self.current_trace)
        self.all_traces.append(self.current_trace)
        
        # 关闭SSE文件
        if self.raw_sse_file is not None:
            with open(self.raw_sse_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"Ended at: {datetime.now().isoformat()}\n")
                f.write(f"Duration: {self.current_trace.duration:.2f}s\n")
                f.write(f"Success: {success}\n")
            self.raw_sse_file = None
        
        trace = self.current_trace
        self.current_trace = None
        return trace

    def _save_trace(self, trace: ExecutionTrace) -> None:
        """保存轨迹到JSONL文件"""
        trace_file = self.traces_dir / f"{trace.case_id}_level{trace.level}.jsonl"
        
        with open(trace_file, 'w', encoding='utf-8') as f:
            for event in trace.events:
                f.write(event.to_json() + '\n')
        
        meta_file = self.traces_dir / f"{trace.case_id}_level{trace.level}_meta.json"
        meta = {
            'case_id': trace.case_id,
            'level': trace.level,
            'success': trace.success,
            'duration': trace.duration,
            'total_events': len(trace.events),
            'total_iterations': trace.total_iterations,
            'error': trace.error,
        }
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    def load_trace(self, case_id: str, level: int) -> ExecutionTrace:
        """加载保存的轨迹"""
        trace_file = self.traces_dir / f"{case_id}_level{level}.jsonl"
        
        if not trace_file.exists():
            raise FileNotFoundError(f"找不到轨迹文件: {trace_file}")
        
        trace = ExecutionTrace(
            case_id=case_id,
            level=level,
            start_time=0.0,
            end_time=0.0
        )
        
        with open(trace_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    event = TraceEvent.from_json(line)
                    trace.add_event(event)
        
        return trace

    def get_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        summary = {
            'total_cases': len(self.all_traces),
            'successful_cases': sum(1 for t in self.all_traces if t.success),
            'by_level': {},
            'total_events': sum(len(t.events) for t in self.all_traces),
            'total_duration': sum(t.duration for t in self.all_traces),
        }
        
        for level in [1, 2, 3]:
            level_traces = [t for t in self.all_traces if t.level == level]
            summary['by_level'][level] = {
                'total': len(level_traces),
                'successful': sum(1 for t in level_traces if t.success)
            }
        
        return summary

        
