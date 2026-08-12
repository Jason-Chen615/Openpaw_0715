# -*- coding: utf-8 -*-
"""执行环境管理"""

from typing import Optional, Dict, Any
from pathlib import Path
import os


class ExecutionEnvironment:
    """QwenPaw执行环境管理"""

    def __init__(
        self,
        qwenpaw_base_url: str = "http://127.0.0.1:8088/api",
        api_username: str = "admin",
        api_password: str = "password",
        dataset_root: Optional[str] = None,
        agent_id: str = "qwenpaw_gaia"
    ):
        """
        初始化执行环境
        
        Args:
            qwenpaw_base_url: QwenPaw API基础URL
            api_username: API用户名
            api_password: API密码
            dataset_root: 数据集根目录
        """
        self.qwenpaw_base_url = qwenpaw_base_url
        self.api_username = api_username
        self.api_password = api_password
        self.agent_id = agent_id
        
        # 优先级：命令行参数 > 环境变量 > 默认值
        # 检查是否传入了非默认参数，如果是则使用参数值，否则读取环境变量
        if qwenpaw_base_url != "http://127.0.0.1:8088/api":
            self.qwenpaw_base_url = qwenpaw_base_url
        else:
            self.qwenpaw_base_url = os.getenv('QWENPAW_BASE_URL', qwenpaw_base_url)
        
        if api_username != "admin":
            self.api_username = api_username
        else:
            self.api_username = os.getenv('QWENPAW_API_USER', api_username)
        
        if api_password != "password":
            self.api_password = api_password
        else:
            self.api_password = os.getenv('QWENPAW_API_PASS', api_password)
        
        if agent_id != "qwenpaw_gaia":
            self.agent_id = agent_id
        else:
            self.agent_id = os.getenv('QWENPAW_AGENT_ID', agent_id)
        
        if dataset_root is None:
            dataset_root = os.getenv('GAIA_DATASET_ROOT', 'dataset/GAIA')
        self.dataset_root = Path(dataset_root)
        
        self.bearer_token: Optional[str] = None

    def is_available(self) -> bool:
        """检查环境是否可用"""
        return (
            self.qwenpaw_base_url
            and self.api_username
            and self.api_password
        )

    def get_healthz_url(self) -> str:
        """获取健康检查URL"""
        return f"{self.qwenpaw_base_url}/../healthz"

    def get_auth_headers(self) -> Dict[str, str]:
        """获取认证请求头 - 使用Bearer Token"""
        if self.bearer_token:
            return {'Authorization': f'Bearer {self.bearer_token}'}
        return {}
    
    def set_bearer_token(self, token: str) -> None:
        """设置Bearer token"""
        self.bearer_token = token

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'qwenpaw_base_url': self.qwenpaw_base_url,
            'api_username': self.api_username,
            'agent_id': self.agent_id,
            'dataset_root': str(self.dataset_root),
        }
