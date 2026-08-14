#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行八个代表性case的脚本"""

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
from runner.resource_monitor import ResourceMonitor
from analysis.analyzer import Analyzer
from analysis.report_gen import ReportGenerator

EIGHT_CASES = [
    {"task_type": "calculation", "task_id": "f8ee2934-7981-4cd4-8abc-e91239c50c97"},
    {"task_type": "coding", "task_id": "83692c1b-eab1-49f1-9ef4-151708310689"},
    {"task_type": "document_understanding", "task_id": "7a770333-8c1b-4008-b630-9d3cb4f0c171"},
    {"task_type": "multi_hop_reasoning", "task_id": "967ad395-7b16-43a2-83e7-41df7cd6401a"},
    {"task_type": "multimodal", "task_id": "0c393561-dd13-4b7c-ac49-20ac469aa276"},
    {"task_type": "reasoning", "task_id": "c68c0db6-1929-4194-8602-56dce5ddbd29"},
    {"task_type": "spreadsheet_analysis", "task_id": "943255a6-8c56-4cf8-9faf-c74743960097"},
    {"task_type": "web_research", "task_id": "088d34d3-8b99-4928-ba26-9a0c6098a616"},
]

def setup_logging(log_file: str, log_level: str):
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()]
    )

def main():
    parser = argparse.ArgumentParser(description='运行GAIA八个代表性case')
    parser.add_argument('--output-dir', default=OUTPUT_DIR)
    parser.add_argument('--dataset-root', default=GAIA_DATASET_ROOT)
    parser.add_argument('--qwenpaw-url', default=QWENPAW_BASE_URL)
    parser.add_argument('--api-user', default=QWENPAW_API_USER)
    parser.add_argument('--api-pass', default=QWENPAW_API_PASS)
    parser.add_argument('--agent-id', default='qwenpaw_gaia')
    parser.add_argument('--container-name', default='qwenpaw_gaia')
    args = parser.parse_args()
    
    setup_logging(LOG_FILE, LOG_LEVEL)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("启动GAIA Runner - 八个代表性case")
    logger.info("=" * 60)
    
    try:
        env = ExecutionEnvironment(
            qwenpaw_base_url=args.qwenpaw_url,
            api_username=args.api_user,
            api_password=args.api_pass,
            dataset_root=args.dataset_root,
            agent_id=args.agent_id
        )
        if hasattr(env, 'setup_session'):
            env.setup_session()
        logger.info("环境配置已就绪")
        
        loader = GAIACaseLoader(args.dataset_root)
        task_ids = [c["task_id"] for c in EIGHT_CASES]
        cases_dict = loader.load_cases_by_task_ids(task_ids)
        
        if not cases_dict:
            logger.error("未找到任何案例")
            return 1
        
        logger.info(f"找到 {len(cases_dict)} 个案例")
        global_analyzer = Analyzer()
        
        for case_info in EIGHT_CASES:
            task_id = case_info["task_id"]
            task_type = case_info["task_type"]
            
            if task_id not in cases_dict:
                logger.warning(f"跳过 {task_id}")
                continue
            
            case = cases_dict[task_id]
            case_output_dir = Path(args.output_dir) / task_id
            case_output_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"\n执行: {task_type} ({task_id})")
            
            collector = TraceCollector(case_output_dir, task_id=task_id)
            runner = AgentRunner(env, collector)
            resource_monitor = ResourceMonitor(args.container_name, task_id, case_output_dir)
            resource_monitor.start()
            
            try:
                trace = runner.execute_case(case)
                logger.info(f"成功: {trace.success}, 耗时: {trace.duration:.2f}s")
                global_analyzer.add_trace(trace)
            finally:
                resource_monitor.stop()
                resource_monitor.save_results()
        
        logger.info("\n" + "=" * 60)
        logger.info("进行全局分析...")
        global_analyzer.analyze_all()
        summary = global_analyzer.get_summary()
        logger.info(f"总案例: {summary['total_cases']}, 成功: {summary['successful_cases']}, 成功率: {summary['success_rate']*100:.1f}%")
        
        logger.info("生成全局报告...")
        reporter = ReportGenerator(Path(args.output_dir) / 'reports')
        reporter.generate_json_report(global_analyzer)
        reporter.generate_html_report(global_analyzer)
        
        logger.info("=" * 60)
        logger.info("执行完成！")
        logger.info("=" * 60)
        return 0
        
    except Exception as e:
        logger.error(f"执行失败: {str(e)}", exc_info=True)
        return 1

if __name__ == '__main__':
    sys.exit(main())
