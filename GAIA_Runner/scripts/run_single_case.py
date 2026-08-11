#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行单个case的脚本
"""

import sys
import logging
from pathlib import Path
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.default_config import (
    QWENPAW_BASE_URL, QWENPAW_API_USER, QWENPAW_API_PASS,
    GAIA_DATASET_ROOT, OUTPUT_DIR, LOG_FILE, LOG_LEVEL
)
from core.case_loader import GAIACaseLoader
from core.trace_collector import TraceCollector
from runner.execution_env import ExecutionEnvironment
from runner.agent_runner import AgentRunner
from analysis.analyzer import Analyzer
from analysis.report_gen import ReportGenerator


def setup_logging(log_file: str, log_level: str):
    """设置日志"""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ]
    )


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='运行单个GAIA case')
    parser.add_argument('--level', type=int, required=True, choices=[1,2,3], help='难度等级')
    parser.add_argument('--case-id', help='案例ID（可选，不指定则用代表性案例）')
    parser.add_argument('--output-dir', default=OUTPUT_DIR, help='输出目录')
    parser.add_argument('--dataset-root', default=GAIA_DATASET_ROOT, help='数据集根目录')
    args = parser.parse_args()
    
    setup_logging(LOG_FILE, LOG_LEVEL)
    logger = logging.getLogger(__name__)
    
    logger.info(f"运行单个case - Level {args.level}")
    
    try:
        # 初始化
        env = ExecutionEnvironment(dataset_root=args.dataset_root)
        loader = GAIACaseLoader(args.dataset_root)
        collector = TraceCollector(args.output_dir)
        runner = AgentRunner(env, collector)
        
        # 加载案例
        if args.case_id:
            cases = loader.load_cases_by_level(args.level)
            case = next((c for c in cases if c.task_id == args.case_id), None)
            if not case:
                logger.error(f"找不到案例: {args.case_id}")
                return 1
        else:
            representative = loader.find_representative_cases()
            case = representative.get(args.level)
            if not case:
                logger.error(f"找不到Level {args.level}的代表性案例")
                return 1
        
        logger.info(f"案例: {case.task_id}")
        logger.info(f"问题: {case.question[:100]}...")
        
        # 执行
        trace = runner.execute_case(case)
        
        logger.info(f"执行完成: 成功={trace.success} 耗时={trace.duration:.2f}s")
        
        # 分析
        analyzer = Analyzer()
        analyzer.add_trace(trace)
        analyzer.analyze_all()
        
        # 报告
        reporter = ReportGenerator(Path(args.output_dir) / 'reports')
        json_report = reporter.generate_json_report(analyzer)
        logger.info(f"报告已生成: {json_report}")
        
        return 0
        
    except Exception as e:
        logger.error(f"执行失败: {str(e)}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
