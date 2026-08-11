#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成分析报告的脚本
"""

import sys
import logging
from pathlib import Path
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.default_config import OUTPUT_DIR, LOG_FILE, LOG_LEVEL
from core.trace_collector import TraceCollector
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
    parser = argparse.ArgumentParser(description='生成分析报告')
    parser.add_argument('--traces-dir', default=Path(OUTPUT_DIR) / 'traces', help='轨迹文件目录')
    parser.add_argument('--output-dir', default=Path(OUTPUT_DIR) / 'reports', help='报告输出目录')
    args = parser.parse_args()
    
    setup_logging(LOG_FILE, LOG_LEVEL)
    logger = logging.getLogger(__name__)
    
    logger.info("生成分析报告")
    
    try:
        traces_dir = Path(args.traces_dir)
        if not traces_dir.exists():
            logger.error(f"轨迹目录不存在: {traces_dir}")
            return 1
        
        # 加载所有轨迹
        logger.info(f"从 {traces_dir} 加载轨迹...")
        collector = TraceCollector(OUTPUT_DIR)
        
        # 查找所有meta文件
        meta_files = list(traces_dir.glob('*_meta.json'))
        logger.info(f"找到 {len(meta_files)} 个轨迹")
        
        if not meta_files:
            logger.warning("未找到任何轨迹文件")
            return 1
        
        analyzer = Analyzer()
        for meta_file in meta_files:
            # 从meta文件名解析case_id和level
            name = meta_file.stem.replace('_meta', '')
            parts = name.rsplit('_level', 1)
            if len(parts) == 2:
                case_id, level = parts
                level = int(level)
                try:
                    trace = collector.load_trace(case_id, level)
                    analyzer.add_trace(trace)
                    logger.debug(f"加载轨迹: {case_id} (Level {level})")
                except Exception as e:
                    logger.warning(f"加载轨迹失败 {case_id}: {str(e)}")
        
        logger.info(f"已加载 {len(analyzer.traces)} 个轨迹")
        
        # 分析
        logger.info("执行分析...")
        analyzer.analyze_all()
        
        # 生成报告
        logger.info(f"生成报告到 {args.output_dir}...")
        reporter = ReportGenerator(args.output_dir)
        
        json_report = reporter.generate_json_report(analyzer, 'analysis_report.json')
        logger.info(f"JSON报告: {json_report}")
        
        html_report = reporter.generate_html_report(analyzer, 'analysis_report.html')
        logger.info(f"HTML报告: {html_report}")
        
        summary = analyzer.get_summary()
        logger.info(f"分析摘要:")
        logger.info(f"  总案例: {summary['total_cases']}")
        logger.info(f"  成功: {summary['successful_cases']}")
        logger.info(f"  成功率: {summary['success_rate']*100:.1f}%")
        
        return 0
        
    except Exception as e:
        logger.error(f"生成报告失败: {str(e)}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
