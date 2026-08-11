# -*- coding: utf-8 -*-
"""Hook注册和集成"""

import time
from typing import Callable, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class HookRegistry:
    """Hook注册表"""

    def __init__(self):
        """初始化Hook注册表"""
        self.hooks: Dict[str, list[Callable]] = {
            'tool_before': [],
            'tool_after': [],
            'context_before': [],
            'context_after': [],
            'turn_start': [],
            'turn_end': [],
            'gate_check': [],
        }
        self.enabled = True

    def register(self, hook_type: str, callback: Callable) -> None:
        """
        注册Hook
        
        Args:
            hook_type: Hook类型
            callback: 回调函数
        """
        if hook_type not in self.hooks:
            raise ValueError(f"Unknown hook type: {hook_type}")
        self.hooks[hook_type].append(callback)
        logger.debug(f"已注册 {hook_type} hook")

    def unregister(self, hook_type: str, callback: Callable) -> None:
        """注销Hook"""
        if hook_type in self.hooks and callback in self.hooks[hook_type]:
            self.hooks[hook_type].remove(callback)
            logger.debug(f"已注销 {hook_type} hook")

    def trigger(self, hook_type: str, *args, **kwargs) -> None:
        """触发Hook"""
        if not self.enabled or hook_type not in self.hooks:
            return
        
        for callback in self.hooks[hook_type]:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Hook执行失败 ({hook_type}): {str(e)}")

    def enable(self) -> None:
        """启用所有Hook"""
        self.enabled = True

    def disable(self) -> None:
        """禁用所有Hook"""
        self.enabled = False


# 全局Hook注册表
_global_registry = HookRegistry()


def get_hook_registry() -> HookRegistry:
    """获取全局Hook注册表"""
    return _global_registry


def register_hook(hook_type: str, callback: Callable) -> None:
    """注册全局Hook"""
    get_hook_registry().register(hook_type, callback)


def trigger_hook(hook_type: str, *args, **kwargs) -> None:
    """触发全局Hook"""
    get_hook_registry().trigger(hook_type, *args, **kwargs)


class ToolHookWrapper:
    """工具调用Hook包装器"""

    def __init__(self, tool_func: Callable, tool_name: str):
        """
        初始化包装器
        
        Args:
            tool_func: 原始工具函数
            tool_name: 工具名称
        """
        self.tool_func = tool_func
        self.tool_name = tool_name

    def __call__(self, *args, **kwargs) -> Any:
        """调用包装后的工具"""
        start_time = time.time()
        
        # Before hook
        trigger_hook('tool_before', self.tool_name, args, kwargs)
        
        try:
            # 执行工具
            result = self.tool_func(*args, **kwargs)
            duration = time.time() - start_time
            
            # After hook
            trigger_hook('tool_after', self.tool_name, result, duration, 'success', None)
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            
            # After hook with error
            trigger_hook('tool_after', self.tool_name, None, duration, 'error', str(e))
            
            raise


class ContextCompressionHook:
    """上下文压缩Hook"""

    def __init__(self, compress_func: Callable):
        """
        初始化压缩Hook
        
        Args:
            compress_func: 原始压缩函数
        """
        self.compress_func = compress_func

    def __call__(self, context: Any, **kwargs) -> Any:
        """调用包装后的压缩函数"""
        size_before = len(str(context))
        
        # Before hook
        trigger_hook('context_before', size_before)
        
        result = self.compress_func(context, **kwargs)
        
        size_after = len(str(result))
        
        # After hook
        trigger_hook('context_after', size_before, size_after)
        
        return result
