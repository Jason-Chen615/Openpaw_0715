# -*- coding: utf-8 -*-
"""Agent执行器"""

import time
import logging
import json
from typing import Optional
from pathlib import Path
from datetime import datetime
from .execution_env import ExecutionEnvironment
from .resource_monitor import ResourceMonitor
from core.models import GAIACase, ExecutionTrace, EventType
from core.trace_collector import TraceCollector

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
        """设置HTTP会话，包括登录获取token"""
        try:
            import requests
            self.session = requests.Session()
            
            # 先尝试登录获取token
            login_url = f"{self.env.qwenpaw_base_url}/auth/login"
            login_data = {
                "username": self.env.api_username,
                "password": self.env.api_password,
                "expires_in": -1  # 永久token
            }
            
            logger.info(f"正在登录: {login_url}")
            response = self.session.post(login_url, json=login_data, timeout=10)
            
            if response.status_code == 200:
                token_response = response.json()
                token = token_response.get('token')
                if token:
                    self.env.set_bearer_token(token)
                    logger.info(f"登录成功，获得token: {token[:20]}...")
                else:
                    logger.warning("登录响应中没有token字段")
            else:
                logger.warning(f"登录失败: {response.status_code} {response.text}")
            
            # 设置认证头
            headers = self.env.get_auth_headers()
            self.session.headers.update(headers)
            self.session.headers['Content-Type'] = 'application/json'
            
            logger.info(f"已连接到 {self.env.qwenpaw_base_url}")
        except ImportError:
            logger.error("需要安装 requests 库")
            raise
        except Exception as e:
            logger.error(f"设置会话失败: {str(e)}", exc_info=True)
            raise

    def execute_case(self, case: GAIACase) -> ExecutionTrace:
        """
        执行单个case（带资源监控）
        
        Args:
            case: GAIA案例
            
        Returns:
            执行轨迹
        """
        logger.info(f"开始执行case: {case.task_id} (Level {case.level})")
        
        # 开始记录
        trace = self.collector.start_case(case.task_id, case.level, case)
        
        # 初始化资源监控
        monitor = ResourceMonitor(
            container_name='qwenpaw_gaia',
            case_id=case.task_id,
            output_dir=Path(self.collector.output_dir) / 'resources'
        )
        
        try:
            # 启动资源监控
            monitor.start()
            
            # 执行实际的Agent请求
            success, final_answer = self._simulate_execution(case, trace)
            
            # 停止资源监控
            monitor.stop()
            
            # 保存资源监控结果
            try:
                resource_stats = monitor.save_results()
                if monitor.error:
                    logger.warning(f"资源监控异常（但继续执行）: {monitor.error}")
            except Exception as e:
                logger.warning(f"保存资源监控结果失败: {str(e)}")
            
            trace = self.collector.end_case(
                success=success,
                final_answer=final_answer if success else None,
                error=None if success else "执行失败"
            )
            
            logger.info(
                f"case执行完成: {case.task_id} "
                f"成功={success} 耗时={trace.duration:.2f}s"
            )
            
            return trace
            
        except Exception as e:
            # 停止资源监控
            monitor.stop()
            
            logger.error(f"执行case失败: {case.task_id}: {str(e)}", exc_info=True)
            trace = self.collector.end_case(
                success=False,
                error=str(e)
            )
            return trace

    def _simulate_execution(self, case: GAIACase, trace: ExecutionTrace) -> tuple[bool, Optional[str]]:
        """
        通过QwenPaw API执行case
        
        Args:
            case: 案例
            trace: 轨迹对象
            
        Returns:
            (成功标志, 最终答案)
        """
        if not self.session:
            self.setup_session()
        
        # 准备请求
        session_id = f"gaia-{case.task_id}"
        
        # 构建问题文本
        question_text = case.question
        
        # 如果有附件，将文件路径作为文本上下文注入prompt
        if case.has_attachment():
            host_file_path = self.env.dataset_root / case.file_path
            if host_file_path.exists():
                logger.info(f"附件存在: {host_file_path}")
                
                # 容器内的文件路径
                container_file_path = f"/data/gaia/{str(case.file_path).replace(chr(92), '/')}"
                logger.info(f"容器内路径: {container_file_path}")
                
                # 将文件路径注入问题文本中，让Agent主动读取
                question_text += f"\n\nPlease read and analyze the file located at: {container_file_path}"
                logger.info(f"已将文件路径注入prompt")
            else:
                logger.warning(f"附件不存在: {host_file_path}")
        
        # 构建消息内容 - 只包含文本，不使用type=file
        content = [
            {
                "type": "text",
                "text": question_text
            }
        ]
        
        # 构建请求体
        request_body = {
            "input": [
                {
                    "role": "user",
                    "content": content
                }
            ],
            "session_id": session_id
        }
        
        # 发送请求到QwenPaw API
        chat_endpoint = f"{self.env.qwenpaw_base_url}/console/chat"

        
        try:
            logger.info(f"发送请求到: {chat_endpoint}")
            logger.info(f"Session ID: {session_id}")
            logger.info(f"问题: {question_text[:100]}...")
            
            response = self.session.post(
                chat_endpoint,
                json=request_body,
                stream=True,
                timeout=300
            )
            
            if response.status_code != 200:
                logger.error(f"API返回错误: {response.status_code}")
                logger.error(f"响应: {response.text}")
                return False, None
            
            # 处理SSE流 - 完整捕获Agent执行轨迹
            iteration = 1
            full_response = ""
            turn_start_time = time.time()
            
            self.collector.record_turn_start(iteration, case.question, len(json.dumps(request_body)))
            # 初始化raw_sse文件
            self.collector.init_raw_sse_file()

            
            for line in response.iter_lines():
                if not line:
                    continue
                
                line = line.decode('utf-8') if isinstance(line, bytes) else line
                
                # 记录原始SSE流（包含时间戳）
                self.collector.record_raw_sse(line)
                
                # 处理SSE格式: "data: {...}"
                if line.startswith('data: '):
                    try:
                        event_data = json.loads(line[6:])  # 移除 "data: " 前缀
                        obj_type = event_data.get('object')
                        event_type = event_data.get('type')
                        
                        # ===== 处理流式内容块 (object="content") =====
                        if obj_type == 'content':
                            # 文本块
                            if event_type == 'text':
                                text_chunk = event_data.get('text', '')
                                if text_chunk:
                                    full_response += text_chunk
                                    logger.debug(f"[文本] {text_chunk[:80]}")
                                    # 记录文本事件
                                    self.collector.record_event(
                                        'text_chunk',
                                        iteration,
                                        {
                                            'text': text_chunk,
                                            'sequence_number': event_data.get('sequence_number'),
                                            'delta': event_data.get('delta')
                                        }
                                    )
                            
                            # plugin_call - 工具调用开始
                            elif event_type == 'plugin_call':
                                plugin_name = event_data.get('plugin_name', 'unknown')
                                plugin_args = event_data.get('args', {})
                                logger.info(f"[工具调用] {plugin_name}")
                                self.collector.record_event(
                                    'plugin_call',
                                    iteration,
                                    {
                                        'plugin_name': plugin_name,
                                        'args': plugin_args
                                    }
                                )
                            
                            # plugin_call_output - 工具结果
                            elif event_type == 'plugin_call_output':
                                plugin_name = event_data.get('plugin_name', 'unknown')
                                output = event_data.get('output', '')
                                status = 'success' if not event_data.get('error') else 'failure'
                                error_msg = event_data.get('error')
                                logger.info(f"[工具结果] {plugin_name} - {status}")
                                self.collector.record_event(
                                    'plugin_call_output',
                                    iteration,
                                    {
                                        'plugin_name': plugin_name,
                                        'output': output,
                                        'status': status,
                                        'error': error_msg
                                    }
                                )
                        
                        # ===== 处理完整消息 (object="message") =====
                        elif obj_type == 'message':
                            # message类型 - 最终回复
                            if event_type == 'message':
                                content_list = event_data.get('content', [])
                                if isinstance(content_list, list):
                                    for content_item in content_list:
                                        if isinstance(content_item, dict):
                                            item_text = content_item.get('text', '')
                                            if item_text:
                                                full_response += item_text
                                                logger.debug(f"[消息] {item_text[:80]}")
                            
                            # reasoning类型 - 推理过程
                            elif event_type == 'reasoning':
                                reasoning_text = event_data.get('text', '')
                                if reasoning_text:
                                    logger.debug(f"[推理] {reasoning_text[:80]}")
                                    # 记录推理事件用于后续分析
                                    self.collector.record_event(
                                        'reasoning',
                                        iteration,
                                        {
                                            'text': reasoning_text,
                                            'msg_id': event_data.get('msg_id')
                                        }
                                    )
                        
                        # ===== 处理其他系统事件 =====
                        elif obj_type == 'response':
                            # 响应级别事件
                            resp_status = event_data.get('status')
                            if resp_status == 'completed':
                                logger.info(f"[响应完成] 耗时 {event_data.get('completed_at', 0) - event_data.get('created_at', 0)}ms")
                        
                        elif obj_type == 'turn_usage':
                            # 使用统计
                            logger.debug(f"[统计] {event_data}")
                        
                    except json.JSONDecodeError as e:
                        logger.debug(f"SSE解析失败: {line[:100]}")
                        continue
            
            # 记录Turn结束
            self.collector.record_turn_end(
                iteration,
                full_response,
                len(full_response),
                response.elapsed.total_seconds() if hasattr(response, 'elapsed') else 0
            )
            
            logger.info(f"收到完整响应，长度: {len(full_response)}")
            
            # 从响应中提取最终答案
            # 策略：取最后一条message事件中的最终回复（跳过reasoning）
            final_answer_text = ""
            for event in reversed(self.collector.current_trace.events):
                if event.event_type == 'message':
                    # 从content数组中提取最后一个非空文本块
                    content_list = event.data.get('content', [])
                    if isinstance(content_list, list):
                        for item in reversed(content_list):
                            if isinstance(item, dict):
                                text = item.get('text', '').strip()
                                if text:
                                    final_answer_text = text
                                    break
                    if final_answer_text:
                        break
            
            # 如果没找到最后的message事件，用full_response的最后部分
            if not final_answer_text:
                # 取最后1000个字符作为最终答案（通常最终回答在末尾）
                final_answer_text = full_response[-1000:] if len(full_response) > 1000 else full_response
            
            logger.info(f"提取的最终答案: {final_answer_text[:200]}")
            
            # 检查是否与预期答案匹配
            expected = case.final_answer.lower().strip()
            actual = final_answer_text.lower().strip()
            
            # 匹配策略：
            # 1. 精确匹配（忽略大小写）
            if expected == actual:
                success = True
                logger.info("✓ 精确匹配")
            # 2. 子串匹配（预期答案在实际回答中）
            elif expected in actual:
                success = True
                logger.info("✓ 子串匹配（预期in实际）")
            # 3. 反向子串匹配（实际回答在预期答案中）
            elif actual in expected:
                success = True
                logger.info("✓ 反向子串匹配（实际in预期）")
            # 4. 部分词汇匹配（关键词至少有80%在实际回答中）
            else:
                # 分词匹配：预期答案的词汇有多少比例出现在实际回答中
                expected_words = set(expected.split())
                actual_words = set(actual.split())
                if expected_words and actual_words:
                    match_ratio = len(expected_words & actual_words) / len(expected_words)
                    if match_ratio >= 0.8:
                        success = True
                        logger.info(f"✓ 词汇匹配 ({match_ratio:.1%})")
                    else:
                        success = False
                        logger.info(f"✗ 不匹配 (词汇匹配度: {match_ratio:.1%})")
                else:
                    success = False
                    logger.info("✗ 不匹配")
            
            logger.info(f"预期答案: {expected[:100]}")
            logger.info(f"实际答案: {actual[:100]}")
            logger.info(f"判断结果: {success}")
            
            return success, final_answer_text
            
        except Exception as e:
            logger.error(f"执行请求失败: {str(e)}", exc_info=True)
            return False, None

    def close(self) -> None:
        """关闭会话"""
        if self.session:
            self.session.close()
            logger.info("会话已关闭")

