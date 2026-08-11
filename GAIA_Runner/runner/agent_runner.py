# -*- coding: utf-8 -*-
"""Agent执行器"""

import time
import logging
from typing import Optional
from .execution_env import ExecutionEnvironment
from ..core.models import GAIACase, ExecutionTrace
from ..core.trace_collector import TraceCollector

logger = logging.getLogger(__name__)


class AgentRunner:
    """在QwenPaw中执行Agent"""

    def __init__(self, env: ExecutionEnvironment, collector: TraceCollector):
        """
        初始化Agent执行器
        
        Args:
            env: 执行环境
            collector: 轨迹采集器
        """
        self.env = env
        self.collector = collector
        self.session = None

    def setup_session(self) -> None:
        """设置HTTP会话"""
        try:
            import requests
            self.session = requests.Session()
            headers = self.env.get_auth_headers()
            self.session.headers.update(headers)
            logger.info(f"已连接到 {self.env.qwenpaw_base_url}")
        except ImportError:
            logger.error("需要安装 requests 库")
            raise

    def execute_case(self, case: GAIACase) -> ExecutionTrace:
        """
        执行单个case
        
        Args:
            case: GAIA案例
            
        Returns:
            执行轨迹
        """
        logger.info(f"开始执行case: {case.task_id} (Level {case.level})")
        
        # 开始记录
        trace = self.collector.start_case(case.task_id, case.level, case)
        
        try:
            # 这里实现实际的Agent执行逻辑
            # 目前是模拟执行
            success = self._simulate_execution(case, trace)
            
            trace = self.collector.end_case(
                success=success,
                final_answer=case.final_answer if success else None,
                error=None if success else "执行失败"
            )
            
            logger.info(
                f"case执行完成: {case.task_id} "
                f"成功={success} 耗时={trace.duration:.2f}s"
            )
            
            return trace
            
        except Exception as e:
            logger.error(f"执行case失败: {case.task_id}: {str(e)}")
            trace = self.collector.end_case(
                success=False,
                error=str(e)
            )
            return trace

    def _simulate_execution(self, case: GAIACase, trace: ExecutionTrace) -> bool:
        """
        模拟执行（用于测试）
        
        Args:
            case: 案例
            trace: 轨迹对象
            
        Returns:
            是否成功
        """
        iteration = 1
        max_iterations = 3 if case.level == 1 else (8 if case.level == 2 else 15)
        
        # 记录Turn开始
        self.collector.record_turn_start(
            iteration,
            case.question,
            len(case.question) * 4
        )
        
        time.sleep(0.5)  # 模拟处理时间
        
        # 记录Tool调用（如果有附件）
        if case.has_attachment():
            self.collector.record_tool_call(
                iteration,
                "file_reader",
                {"file_path": case.file_path}
            )
            time.sleep(0.2)
            self.collector.record_tool_result(
                iteration,
                "file_reader",
                "File content extracted",
                "success"
            )
        
        # 记录Turn结束
        self.collector.record_turn_end(
            iteration,
            "Generated response",
            len(case.question) * 4 + 100,
            0.7
        )
        
        return True

    def close(self) -> None:
        """关闭会话"""
        if self.session:
            self.session.close()
            logger.info("会话已关闭")
