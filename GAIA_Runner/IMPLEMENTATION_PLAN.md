# GAIA-QwenPaw 实验框架实现方案

## 1. 总体架构

### 1.1 目标
- 从三个代表性case开始验证框架可行性
- 采集完整的Agent执行轨迹（300+事件/case）
- 进行四维度分析（任务难度、工具调用、内存、上下文）
- 无缝扩展到450+个case（不改架构）

### 1.2 核心采集策略
- **采集方式**：JSON Lines格式（流式写入）
- **细粒度事件**：四层采集（Turn、Tool、Context、Gate）
- **数据量**：每个case 300-500个事件

## 2. 框架模块设计

### 2.1 目录结构
```
GAIA_Runner/
├── core/                    # 核心模块
│   ├── models.py            # 数据模型
│   ├── case_loader.py       # GAIA加载器
│   └── trace_collector.py   # Trace采集
├── runner/                  # 执行框架
│   ├── agent_runner.py      # Agent执行
│   ├── execution_env.py     # 环境管理
│   └── trace_hooks.py       # Hook集成
├── analysis/                # 分析模块
│   ├── analyzer.py          # 四维度分析
│   ├── metrics.py           # 指标计算
│   └── report_gen.py        # 报告生成
├── scripts/                 # 脚本
│   ├── run_single_case.py
│   ├── run_three_cases.py
│   └── generate_report.py
├── tests/                   # 测试
└── outputs/                 # 输出目录
```

**代码量**：~3000行

## 3. 数据模型

- **GAIACase**: 案例（task_id, level, question, final_answer, file_path）
- **TraceEvent**: 事件（timestamp, event_type, iteration, case_id, level, data）
- **EventType**: turn_start/end, tool_call/result, context_change, gate_check
- **ExecutionTrace**: 完整轨迹（events, metrics, success）

## 4. 采集四层事件

| 层级 | 采集点 | 事件类型 | 数量 |
|-----|------|--------|------|
| Turn | Agent.reply() | turn_start/end | ~50 |
| Tool | ToolHookRegistry | tool_call/result | ~100-200 |
| Context | compress_context() | context_change | ~5-20 |
| Gate | StopGate.check() | gate_check | ~5-10 |
| **总计** | | | **300+** |

## 5. 多维度分析

### 5.1 任务难度维度
```
难度评分 = 0.3*迭代数 + 0.25*工具多样性 + 
           0.25*context压力 + 0.2*决策复杂度
```

Level预期值：
- Level 1: 1-3迭代，得分 0.2-0.4
- Level 2: 4-8迭代，得分 0.4-0.6
- Level 3: 8-15迭代，得分 0.6-1.0

### 5.2 工具调用维度
指标：工具多样性、重用率、失败率、耗时、调用序列

### 5.3 内存动态维度
指标：峰值context、平均context、压缩次数、压缩率

### 5.4 上下文演变维度
指标：质量趋势、噪声积累、关键信息保留率、冗余比例

## 6. QwenPaw集成

### 6.1 集成点
| 集成点 | 位置 | 方式 | 内容 |
|------|------|------|-----|
| Turn | Agent.reply() | Middleware | question, response, context_size |
| 工具 | ToolHookRegistry | before/after hooks | tool_name, args, result, duration |
| Context | compress_context() | 包装 | size_before, size_after, rate |
| Gate | StopGate.check() | 继承 | gate_type, iteration, decision |

### 6.2 集成方式
**Middleware**：Turn-level宏观事件
**Hook**：Tool/Context/Gate细节事件

## 7. 三个代表性Case

| Level | 特征 | 预期迭代 | 预期工具 | 难度评分 |
|------|------|--------|--------|--------|
| 1 | 纯文本推理，无附件 | 1-3 | 0-2 | 0.2-0.4 |
| 2 | 文档处理，PDF/XLSX | 4-8 | 5-15 | 0.4-0.6 |
| 3 | 多工具组合，长推理 | 8-15 | 15-30 | 0.6-1.0 |

## 8. 实现时间表

### Week 1：框架基础（Day 1-5）
- Day 1-2：Case Loader（加载GAIA parquet）
- Day 2：数据模型定义
- Day 3-4：TraceCollector基础（Turn-level）
- Day 5：单case测试

交付：三个case可执行，100+基础events

### Week 2：详细跟踪（Day 1-5）
- Day 1-2：Tool-level hooks集成
- Day 3：Context压缩跟踪
- Day 4：Gate决策跟踪
- Day 5：性能优化

交付：300+细粒度events/case，overhead < 10%

### Week 3：分析可视化（Day 1-5）
- Day 1-2：Analyzer实现
- Day 3：指标计算
- Day 4：报告生成
- Day 5：文档验证

交付：分析报告、对比分析、使用文档

## 9. 文件清单

| 模块 | 文件 | 行数 | 说明 |
|-----|------|------|-----|
| core | models.py | 300 | 数据模型 |
| core | case_loader.py | 150 | GAIA加载 |
| core | trace_collector.py | 300 | 采集存储 |
| runner | agent_runner.py | 250 | 执行框架 |
| runner | execution_env.py | 150 | 环境管理 |
| runner | trace_hooks.py | 200 | Hook集成 |
| analysis | analyzer.py | 400 | 四维度分析 |
| analysis | metrics.py | 200 | 指标计算 |
| analysis | report_gen.py | 250 | 报告生成 |
| scripts | *.py | 280 | 脚本脚本 |
| tests | test_*.py | 120 | 单元测试 |
| **总计** | | **~3000** | |

## 10. 关键技术决策

### 10.1 JSON Lines
✅ 流式处理，无需全部加载
✅ 易于分析，pandas兼容
✅ 易于扩展，无schema限制

### 10.2 Middleware + Hook混合
✅ Middleware用于Turn-level
✅ Hook用于Tool/Context/Gate细节
✅ 零侵入，无需改QwenPaw源码

### 10.3 四层事件采集
✅ Turn层-宏观进度
✅ Tool层-工具使用
✅ Context层-内存管理
✅ Gate层-控制流

## 11. 无缝扩展路径

### 从3到450+的扩展
核心模块逻辑完全相同，只需改配置：

```python
# 现在
representative_cases = loader.find_representative_cases()

# 扩展后（逻辑完全相同）
all_cases = loader.load_all_cases()

for case in all_cases:
    runner.execute(case)
    trace = collector.end_case(...)
```

### 聚合分析（Week 4-5）
```python
all_traces = [collector.load_trace(f) for f in trace_files]
aggregated = analyzer.aggregate(all_traces)
report = reporter.generate_comparison(aggregated)
```

## 12. 成功标准

### Phase 1（Week 1）框架可行性
- [ ] 三个case成功加载
- [ ] JSONL轨迹生成正确
- [ ] 100+基础events/case
- [ ] 序列化无误

### Phase 2（Week 2）数据完整性
- [ ] Tool-level events 100%
- [ ] Context-level events完整
- [ ] Gate-level events准确
- [ ] 300+细粒度events/case
- [ ] Overhead < 10%

### Phase 3（Week 3）分析可用性
- [ ] 四维度分析JSON完整
- [ ] 对比报告清晰
- [ ] 工具分析准确
- [ ] 难度评分合理

## 13. 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|-----|------|------|-----|
| Hook未触发 | 低 | 中 | 日志验证 |
| JSONL过大 | 低 | 低 | 分批/压缩 |
| Context计算 | 低 | 低 | token count |
| Agent失败 | 中 | 中 | 错误处理 |

## 14. 后续方向

### 短期（Week 4-5）
- 扩展到450+case
- 按level聚合分析
- 失败案例识别

### 中期（Week 6-8）
- 工具优化建议
- Context策略改进
- 提示词微调

### 长期（Week 9+）
- 跨模型对比
- 工具库优化
- 自适应策略

## 总结

### 方案特点
✅ 可行性强（基于现有架构）
✅ 快速验证（3周完成）
✅ 无缝扩展（无改架构）
✅ 数据完整（300+事件/case）
✅ 分析深度（四维度）
✅ 工程规范（模块化）

### 建议
立即启动Week 1开发，预计第一周末完成框架验证。
