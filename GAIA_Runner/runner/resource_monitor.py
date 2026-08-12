# -*- coding: utf-8 -*-
"""Docker容器资源监控"""

import json
import csv
import subprocess
import threading
import time
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """监控Docker容器的CPU和内存占用"""
    
    def __init__(self, container_name: str, case_id: str, output_dir: Path):
        """
        初始化资源监控
        
        Args:
            container_name: 容器名称（如qwenpaw_gaia）
            case_id: case ID
            output_dir: 输出目录
        """
        self.container_name = container_name
        self.case_id = case_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.samples: List[Dict] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.error: Optional[str] = None
    
    def start(self) -> None:
        """启动监控线程"""
        self.start_time = datetime.now()
        self.monitoring = True
        self.samples = []
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f"启动资源监控: {self.container_name}")
    
    def stop(self) -> None:
        """停止监控"""
        self.monitoring = False
        self.end_time = datetime.now()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info(f"停止资源监控: 采集了{len(self.samples)}个样本")
    
    def _monitor_loop(self) -> None:
        """监控循环"""
        elapsed_time = 0
        
        while self.monitoring:
            try:
                # 运行docker stats命令
                cmd = [
                    'docker', 'stats',
                    '--no-stream',
                    '--format', '{{json .}}',
                    self.container_name
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode != 0:
                    if not self.error:
                        error_msg = result.stderr.strip() or "Unknown error"
                        self.error = f"docker stats失败: {error_msg}"
                        logger.error(f"资源监控错误: {self.error}")
                    time.sleep(1)
                    continue
                
                # 解析JSON输出
                stats_data = json.loads(result.stdout)
                
                # 提取数据
                cpu_str = stats_data.get('CPUPerc', '0%').rstrip('%')
                memory_str = stats_data.get('MemUsage', '0B')
                memory_percent_str = stats_data.get('MemPerc', '0%').rstrip('%')
                
                try:
                    cpu_percent = float(cpu_str)
                except ValueError:
                    cpu_percent = 0.0
                
                try:
                    memory_percent = float(memory_percent_str)
                except ValueError:
                    memory_percent = 0.0
                
                # 解析内存大小（如"256MiB"）
                memory_usage = self._parse_memory(memory_str)
                
                # 记录样本
                sample = {
                    'timestamp': elapsed_time,
                    'case_id': self.case_id,
                    'cpu_percent': cpu_percent,
                    'memory_usage': memory_usage,
                    'memory_percent': memory_percent
                }
                
                self.samples.append(sample)
                logger.debug(f"[{elapsed_time}s] CPU: {cpu_percent}% MEM: {memory_usage}MB")
                
                time.sleep(1)
                elapsed_time += 1
                
            except subprocess.TimeoutExpired:
                if not self.error:
                    self.error = "docker stats命令超时"
                time.sleep(1)
            except json.JSONDecodeError as e:
                if not self.error:
                    self.error = f"JSON解析错误: {str(e)}"
                time.sleep(1)
            except Exception as e:
                if not self.error:
                    self.error = f"监控异常: {str(e)}"
                    logger.error(self.error, exc_info=True)
                time.sleep(1)
    
    @staticmethod
    def _parse_memory(memory_str: str) -> float:
        """解析内存字符串为MB"""
        memory_str = memory_str.split('/')[0].strip()
        
        try:
            if memory_str.endswith('GiB'):
                return float(memory_str[:-3]) * 1024
            elif memory_str.endswith('MiB'):
                return float(memory_str[:-3])
            elif memory_str.endswith('KiB'):
                return float(memory_str[:-3]) / 1024
            elif memory_str.endswith('B'):
                return float(memory_str[:-1]) / (1024 * 1024)
            else:
                return 0.0
        except ValueError:
            return 0.0
    

    
    def save_results(self) -> Dict:
        """保存采集结果为JSON和CSV"""
        if not self.samples:
            logger.warning("没有采集到资源数据")
            return {}
        
        # 计算统计指标
        cpu_values = [s['cpu_percent'] for s in self.samples]
        memory_values = [s['memory_usage'] for s in self.samples]
        
        stats = {
            'case_id': self.case_id,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': len(self.samples),
            'sample_count': len(self.samples),
            'error': self.error,
            'metrics': {
                'cpu': {
                    'avg': round(sum(cpu_values) / len(cpu_values), 2),
                    'max': round(max(cpu_values), 2),
                    'min': round(min(cpu_values), 2),
                },
                'memory': {
                    'avg': round(sum(memory_values) / len(memory_values), 2),
                    'max': round(max(memory_values), 2),
                    'min': round(min(memory_values), 2),
                    'growth': round(memory_values[-1] - memory_values[0], 2),
                }
            },
            'samples': self.samples
        }
        
        # 找到CPU峰值出现的时间
        if cpu_values:
            max_cpu_idx = cpu_values.index(max(cpu_values))
            max_cpu_time = self.samples[max_cpu_idx]['timestamp']
            stats['cpu_peak_at_second'] = max_cpu_time
        
        # 保存为JSON
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_path = self.output_dir / f"qwenpaw_gaia_resources_{self.case_id}_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        logger.info(f"资源监控JSON已保存: {json_path}")
        
        # 保存为CSV
        csv_path = self.output_dir / f"qwenpaw_gaia_resources_{self.case_id}_{timestamp}.csv"
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['timestamp', 'case_id', 'cpu_percent', 'memory_usage', 'memory_percent']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.samples)
        logger.info(f"资源监控CSV已保存: {csv_path}")
        
        return stats

