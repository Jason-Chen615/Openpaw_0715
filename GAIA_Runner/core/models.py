# -*- coding: utf-8 -*-
"""GAIA数据模型定义"""

from dataclasses import dataclass, field, asdict
from typing import Any, Optional, List
from enum import Enum
import time
import json


class EventType(str, Enum):
    """事件类型枚举"""
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    CONTEXT_CHANGE = "context_change"
    GATE_CHECK = "gate_check"
    MEMORY_UPDATE = "memory_update"


@dataclass
class TraceEvent:
    """单个trace事件"""
    timestamp: float
    event_type: str
    iteration: int
    case_id: str
    level: int
    data: dict[str, Any] = field(default_factory=dict)
    iso_timestamp: str = ""  # ISO格式的时间戳，便于阅读

    def __post_init__(self):
        """初始化后自动生成ISO时间戳"""
        if not self.iso_timestamp:
            from datetime import datetime
            self.iso_timestamp = datetime.fromtimestamp(self.timestamp).isoformat()

    def to_json(self) -> str:
        """转换为JSON行"""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, line: str) -> "TraceEvent":
        """从JSON行创建"""
        d = json.loads(line)
        return cls(**d)


@dataclass
class GAIACase:
    """GAIA单个案例"""
    task_id: str
    level: int  # 1, 2, 3
    question: str
    final_answer: str
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    annotator_metadata: dict = field(default_factory=dict)

    def has_attachment(self) -> bool:
        """是否有附件"""
        return self.file_path is not None


@dataclass
class TurnMetrics:
    """单个turn的指标"""
    iteration: int
    turn_start_time: float
    turn_end_time: float
    context_size_before: int
    context_size_after: int
    tools_called: List[str] = field(default_factory=list)
    tool_call_count: int = 0
    gate_decisions: List[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        """持续时间（秒）"""
        return self.turn_end_time - self.turn_start_time

    @property
    def context_delta(self) -> int:
        """context大小变化"""
        return self.context_size_after - self.context_size_before


@dataclass
class ToolUsageMetrics:
    """工具使用指标"""
    tool_name: str
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    total_result_size: int = 0

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.call_count == 0:
            return 0.0
        return self.success_count / self.call_count


@dataclass
class ContextMetrics:
    """上下文指标"""
    peak_size: int = 0
    avg_size: int = 0
    compaction_count: int = 0
    total_compressed_size: int = 0
    avg_compression_rate: float = 0.0
    max_compression_rate: float = 0.0


@dataclass
class TaskDifficultyMetrics:
    """任务难度指标"""
    iteration_count: int = 0
    tool_diversity: int = 0
    avg_context_pressure: float = 0.0
    decision_complexity: float = 0.0
    difficulty_score: float = 0.0


@dataclass
class ExecutionTrace:
    """完整的执行轨迹"""
    case_id: str
    level: int
    start_time: float
    end_time: float
    events: List[TraceEvent] = field(default_factory=list)
    turn_metrics: List[TurnMetrics] = field(default_factory=list)
    tool_metrics: dict[str, ToolUsageMetrics] = field(default_factory=dict)
    context_metrics: ContextMetrics = field(default_factory=ContextMetrics)
    difficulty_metrics: TaskDifficultyMetrics = field(default_factory=TaskDifficultyMetrics)
    success: bool = False
    final_answer: Optional[str] = None
    error: Optional[str] = None

    @property
    def duration(self) -> float:
        """总执行时间"""
        return self.end_time - self.start_time

    @property
    def total_iterations(self) -> int:
        """总迭代次数"""
        return len(self.turn_metrics)

    def add_event(self, event: TraceEvent) -> None:
        """添加事件"""
        self.events.append(event)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "case_id": self.case_id,
            "level": self.level,
            "duration": self.duration,
            "total_iterations": self.total_iterations,
            "success": self.success,
            "final_answer": self.final_answer,
            "error": self.error,
            "events_count": len(self.events),
            "tool_metrics": {k: asdict(v) for k, v in self.tool_metrics.items()},
            "context_metrics": asdict(self.context_metrics),
            "difficulty_metrics": asdict(self.difficulty_metrics),
        }


@dataclass
class AnalysisResult:
    """分析结果"""
    case_id: str
    level: int
    difficulty_score: float = 0.0
    tool_diversity: float = 0.0
    tool_reuse_rate: float = 0.0
    tool_failure_rate: float = 0.0
    peak_context: int = 0
    avg_context: int = 0
    compression_count: int = 0
    compression_rate: float = 0.0

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)


@dataclass
class Metrics:
    """聚合指标"""
    total_cases: int = 0
    successful_cases: int = 0
    success_rate: float = 0.0
    avg_difficulty: float = 0.0
    total_events: int = 0
    total_duration: float = 0.0

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)
