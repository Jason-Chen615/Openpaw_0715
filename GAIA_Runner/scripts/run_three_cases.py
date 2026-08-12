#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行三个代表性case的脚本
"""

import sys
import logging
from pathlib import Path
import argparse

# 添加GAIA_Runner到路径
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
    parser = argparse.ArgumentParser(description='运行GAIA三个代表性case')
    parser.add_argument('--output-dir', default=OUTPUT_DIR, help='输出目录')
    parser.add_argument('--dataset-root', default=GAIA_DATASET_ROOT, help='数据集根目录')
    parser.add_argument('--qwenpaw-url', default=QWENPAW_BASE_URL, help='QwenPaw API URL')
    parser.add_argument('--api-user', default=QWENPAW_API_USER, help='API用户名')
    parser.add_argument('--api-pass', default=QWENPAW_API_PASS, help='API密码')
    parser.add_argument('--agent-id', default='qwenpaw_gaia', help='QwenPaw Agent ID')
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(LOG_FILE, LOG_LEVEL)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("启动GAIA Runner - 三个代表性case")
    logger.info("=" * 60)
    
    try:
        # 1. 初始化环境
        env = ExecutionEnvironment(
            qwenpaw_base_url=args.qwenpaw_url,
            api_username=args.api_user,
            api_password=args.api_pass,
            dataset_root=args.dataset_root,
            agent_id=args.agent_id
        )
        env.setup_session() if hasattr(env, 'setup_session') else None
        logger.info(f"环境配置: {env.to_dict()}")
        
        # 2. 加载案例
        loader = GAIACaseLoader(args.dataset_root)
        representative_cases = loader.find_representative_cases()
        
        if not representative_cases:
            logger.error("未找到代表性案例")
            return 1
        
        logger.info(f"找到 {len(representative_cases)} 个代表性案例")
        for level, case in representative_cases.items():
            logger.info(f"  Level {level}: {case.task_id}")
        
        # 3. 创建采集器和执行器
        collector = TraceCollector(args.output_dir)
        runner = AgentRunner(env, collector)
        
        # 4. 执行案例
        traces = []
        for level in sorted(representative_cases.keys()):
            case = representative_cases[level]
            logger.info(f"\n开始执行 Level {level} 案例: {case.task_id}")
            logger.info(f"问题: {case.question[:100]}...")
            
            trace = runner.execute_case(case)
            traces.append(trace)
            
            logger.info(f"执行完成:")
            logger.info(f"  成功: {trace.success}")
            logger.info(f"  耗时: {trace.duration:.2f}s")
            logger.info(f"  事件数: {len(trace.events)}")
        
        # 5. 分析
        logger.info("\n开始分析...")
        analyzer = Analyzer()
        for trace in traces:
            analyzer.add_trace(trace)
        
        results = analyzer.analyze_all()
        summary = analyzer.get_summary()
        
        logger.info(f"分析完成:")
        logger.info(f"  总案例: {summary['total_cases']}")
        logger.info(f"  成功: {summary['successful_cases']}")
        logger.info(f"  成功率: {summary['success_rate']*100:.1f}%")
        
        # 6. 生成报告
        logger.info("\n生成报告...")
        reporter = ReportGenerator(Path(args.output_dir) / 'reports')
        
        json_report = reporter.generate_json_report(analyzer)
        logger.info(f"JSON报告: {json_report}")
        
        html_report = reporter.generate_html_report(analyzer)
        logger.info(f"HTML报告: {html_report}")
        
        logger.info("=" * 60)
        logger.info("执行完成！")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"执行失败: {str(e)}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
