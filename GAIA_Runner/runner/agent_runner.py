# -*- coding: utf-8 -*-
"""Agent执行器"""

import time
import logging
import json
from typing import Optional
from pathlib import Path
from .execution_env import ExecutionEnvironment
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
            # 执行实际的Agent请求
            success, final_answer = self._simulate_execution(case, trace)
            
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
        
        # 构建消息内容
        content = []
        
        # 添加文本
        content.append({
            "type": "text",
            "text": case.question
        })
        
        # 如果有附件，添加文件
        if case.has_attachment():
            host_file_path = self.env.dataset_root / case.file_path
            if host_file_path.exists():
                logger.info(f"附件存在: {host_file_path}")
                
                # 容器内的文件路径（发送给QwenPaw）
                # 因为挂载是 ../dataset/GAIA:/data/gaia:ro
                # 需要将Windows路径转换为Unix路径
                container_file_path = f"/data/gaia/{str(case.file_path).replace(chr(92), '/')}"
                logger.info(f"容器内路径: {container_file_path}")
                
                try:
                    with open(host_file_path, 'rb') as f:
                        file_content = f.read()
                    
                    logger.info(f"文件大小: {len(file_content)} bytes")
                    
                    # 根据文件类型添加
                    if host_file_path.suffix.lower() in ['.pdf', '.txt', '.md', '.xlsx', '.csv']:
                        content.append({
                            "type": "file",
                            "file_name": host_file_path.name,
                            "file_path": container_file_path
                        })
                        logger.info(f"添加附件: {host_file_path.name}")
                except Exception as e:
                    logger.warning(f"处理文件失败: {e}")
            else:
                logger.warning(f"附件不存在: {host_file_path}")
        
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
            logger.info(f"问题: {case.question[:100]}...")
            
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
            
            for line in response.iter_lines():
                if not line:
                    continue
                
                line = line.decode('utf-8') if isinstance(line, bytes) else line
                
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
                                self.collector.record_tool_call(
                                    iteration,
                                    plugin_name,
                                    plugin_args,
                                    duration=0.0
                                )
                            
                            # plugin_call_output - 工具结果
                            elif event_type == 'plugin_call_output':
                                plugin_name = event_data.get('plugin_name', 'unknown')
                                output = event_data.get('output', '')
                                status = 'success' if not event_data.get('error') else 'failure'
                                error_msg = event_data.get('error')
                                logger.info(f"[工具结果] {plugin_name} - {status}")
                                self.collector.record_tool_result(
                                    iteration,
                                    plugin_name,
                                    output,
                                    status=status,
                                    error=error_msg
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
            
            # 检查是否与预期答案匹配（简单的字符串包含检查）
            expected_answer = case.final_answer.lower()
            actual_answer = full_response.lower()
            
            success = expected_answer in actual_answer or actual_answer in expected_answer
            
            return success, full_response
            
        except Exception as e:
            logger.error(f"执行请求失败: {str(e)}", exc_info=True)
            return False, None

    def close(self) -> None:
        """关闭会话"""
        if self.session:
            self.session.close()
            logger.info("会话已关闭")
