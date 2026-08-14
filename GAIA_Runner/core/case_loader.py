# -*- coding: utf-8 -*-
"""GAIA数据集加载器"""

import os
import pandas as pd
from typing import List, Optional
from pathlib import Path
from core.models import GAIACase


class GAIACaseLoader:
    """加载GAIA parquet文件中的案例"""

    def __init__(self, dataset_root: str | Path):
        """
        初始化加载器
        
        Args:
            dataset_root: GAIA数据集根目录 (dataset/GAIA/)
        """
        self.dataset_root = Path(dataset_root)
        self.test_dir = self.dataset_root / "2023" / "test"
        self.val_dir = self.dataset_root / "2023" / "validation"

    def load_cases_by_level(self, level: int, split: str = "test") -> List[GAIACase]:
        """
        按难度等级加载案例
        
        Args:
            level: 难度等级 (1, 2, 3)
            split: 数据集分割 ("test" 或 "validation")
            
        Returns:
            案例列表
        """
        if split == "test":
            parquet_path = self.test_dir / f"metadata.level{level}.parquet"
        else:
            parquet_path = self.val_dir / f"metadata.level{level}.parquet"

        if not parquet_path.exists():
            raise FileNotFoundError(f"找不到parquet文件: {parquet_path}")

        df = pd.read_parquet(str(parquet_path))
        cases = []

        for _, row in df.iterrows():
            case = GAIACase(
                task_id=row.get("task_id", ""),
                level=level,
                question=row.get("Question", ""),
                final_answer=row.get("Final answer", ""),
                file_path=row.get("file_path"),
                file_name=row.get("file_name"),
                annotator_metadata=row.get("Annotator Metadata", {}),
            )
            cases.append(case)

        return cases

    def load_all_cases(self, split: str = "test") -> dict[int, List[GAIACase]]:
        """
        加载所有难度等级的案例
        
        Args:
            split: 数据集分割
            
        Returns:
            按level分组的案例字典
        """
        cases_by_level = {}
        for level in [1, 2, 3]:
            try:
                cases_by_level[level] = self.load_cases_by_level(level, split)
            except FileNotFoundError:
                print(f"警告: 未找到level {level}的数据")
        return cases_by_level

    def get_case_file_path(self, case: GAIACase) -> Optional[Path]:
        """
        获取案例附件的完整路径
        
        Args:
            case: GAIA案例
            
        Returns:
            完整的文件路径，如果没有附件则返回None
        """
        if case.file_path:
            full_path = self.dataset_root / case.file_path
            if full_path.exists():
                return full_path
        return None

    def find_representative_cases(self) -> dict[int, GAIACase]:
        """
        找到三个代表性案例（每个level一个）
        
        Returns:
            按level分组的代表性案例
        """
        representative = {}

        for level in [1, 2, 3]:
            cases = self.load_cases_by_level(level, "test")
            if not cases:
                continue

            if level == 1:
                # Level 1: 选择无附件的纯文本推理案例
                text_cases = [c for c in cases if not c.has_attachment()]
                if text_cases:
                    representative[1] = text_cases[0]
            elif level == 2:
                # Level 2: 选择有文档附件的案例
                doc_cases = [
                    c for c in cases
                    if c.has_attachment()
                    and (c.file_path.endswith(".pdf") or c.file_path.endswith(".xlsx"))
                ]
                if doc_cases:
                    representative[2] = doc_cases[0]
            elif level == 3:
                # Level 3: 选择复杂的多工具案例
                if cases:
                    representative[3] = cases[0]

        return representative

    def load_cases_by_task_ids(self, task_ids: List[str], split: str = "test") -> dict[str, GAIACase]:
        """
        按task_id列表加载案例
        
        Args:
            task_ids: task_id列表
            split: 数据集分割 ("test" 或 "validation")
            
        Returns:
            按task_id分组的案例字典
        """
        result = {}
        
        # 加载所有难度等级的案例
        all_cases = self.load_all_cases(split)
        
        # 从所有案例中查找指定的task_id
        for level_cases in all_cases.values():
            for case in level_cases:
                if case.task_id in task_ids:
                    result[case.task_id] = case
        
        return result

    def get_case_by_task_id(self, task_id: str, split: str = "test") -> Optional[GAIACase]:
        """
        根据task_id获取单个案例
        
        Args:
            task_id: 案例ID
            split: 数据集分割
            
        Returns:
            案例对象，如果不存在则返回None
        """
        cases = self.load_cases_by_task_ids([task_id], split)
        return cases.get(task_id)


def create_test_case_loader(qwenpaw_root: str | Path) -> GAIACaseLoader:
    """创建测试用的案例加载器"""
    dataset_path = Path(qwenpaw_root) / "dataset" / "GAIA"
    return GAIACaseLoader(dataset_path)
