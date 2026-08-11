# GAIA_Runner: GAIA-QwenPaw 实验框架

一个完整的实验框架，用于在QwenPaw上测试和分析GAIA数据集中的Agent行为。

## 快速开始

### 目标
- ✅ 从三个代表性case开始验证框架
- ✅ 采集300+细粒度事件/case
- ✅ 四维度分析（难度、工具、内存、上下文）
- ✅ 无缝扩展到450+个case

### 框架结构

```
GAIA_Runner/
├── core/                      # 核心模块 (~1000行)
│   ├── models.py              # 数据模型定义
│   ├── case_loader.py         # GAIA parquet加载
│   └── trace_collector.py     # Trace事件采集
│
├── runner/                    # 执行框架 (~600行)
│   ├── agent_runner.py        # Agent执行主类
│   ├── execution_env.py       # 执行环境管理
│   └── trace_hooks.py         # Hook注册和集成
│
├── analysis/                  # 分析模块 (~900行)
│   ├── analyzer.py            # 四维度分析器
│   ├── metrics.py             # 指标计算函数
│   └── report_gen.py          # 报告生成
│
├── config/                    # 配置文件
│   └── default_config.py      # 默认配置
│
├── scripts/                   # 运行脚本 (~280行)
│   ├── run_single_case.py     # 运行单个case
│   ├── run_three_cases.py     # 运行三个代表case
│   └── generate_report.py     # 生成分析报告
│
├── tests/                     # 单元测试 (~120行)
│   └── test_*.py
│
├── outputs/                   # 输出目录
│   ├── traces/                # JSONL轨迹文件
│   ├── reports/               # 分析报告
│   └── metrics.json           # 汇总指标
│
└── IMPLEMENTATION_PLAN.md     # 详细实现方案
```

## 核心设计

### 采集四层事件

| 层级 | 采集点 | 事件数 | 内容 |
|-----|------|------|-----|
| **Turn** | Agent.reply()前后 | ~50 | 问题、回复、context大小 |
| **Tool** | ToolHookRegistry hooks | ~100-200 | 工具名、参数、结果、耗时 |
| **Context** | compress_context() | ~5-20 | 压缩前后大小、压缩率 |
| **Gate** | StopGate.check() | ~5-10 | gate类型、迭代数、决策 |
| **总计** | | **300+** | JSON Lines格式 |

### 多维度分析

1. **任务难度维度**
   - 迭代次数、工具多样性、context压力、决策复杂度
   - Level 1: 难度评分 0.2-0.4
   - Level 2: 难度评分 0.4-0.6
   - Level 3: 难度评分 0.6-1.0

2. **工具调用维度**
   - 工具多样性、重用率、失败率、耗时、调用序列

3. **内存动态维度**
   - 峰值context、平均context、压缩次数、压缩率

4. **上下文演变维度**
   - 质量趋势、噪声积累、关键信息保留率、冗余比例

### 与QwenPaw集成

| 集成点 | 位置 | 方式 | 采集内容 |
|------|------|------|--------|
| Turn事件 | Agent.reply() | Middleware | question, response, context_size |
| 工具调用 | ToolHookRegistry | before/after hooks | tool_name, args, result, duration |
| Context变化 | compress_context() | 包装方法 | size_before, size_after, rate |
| Gate决策 | StopGate.check() | 继承/hook | gate_type, iteration, decision |

## 三个代表性Case

### Level 1 - 纯文本推理
- **特征**: 无附件，纯文本理解
- **预期**: 1-3次迭代，0-2次工具调用，难度评分 0.2-0.4

### Level 2 - 文档处理
- **特征**: PDF/XLSX附件，表格提取和分析
- **预期**: 4-8次迭代，5-15次工具调用，难度评分 0.4-0.6

### Level 3 - 复杂多步骤
- **特征**: 多工具组合，长期推理链
- **预期**: 8-15次迭代，15-30次工具调用，难度评分 0.6-1.0

## 实现时间表

### Week 1: 框架基础构建
**目标**: 验证框架可行性，三个case可执行

- Day 1-2: Case Loader（加载GAIA parquet）
- Day 2: 数据模型定义（models.py）
- Day 3-4: TraceCollector基础（Turn-level events采集）
- Day 5: 单case测试验证

**交付**: 三个case可执行，100+基础events，JSONL生成正确

### Week 2: 详细跟踪增强
**目标**: 完整采集所有四层事件

- Day 1-2: Tool-level hooks集成（ToolHookRegistry）
- Day 3: Context压缩跟踪（compress_context()）
- Day 4: Gate决策跟踪（StopGate.check()）
- Day 5: 性能测试和优化

**交付**: 300+细粒度events/case，trace overhead < 10%

### Week 3: 分析和可视化
**目标**: 完整的分析和报告生成

- Day 1-2: Analyzer实现（四维度分析器）
- Day 3: 指标计算（metrics.py）
- Day 4: 报告生成（report_gen.py）
- Day 5: 文档完善和验证

**交付**: 分析报告（JSON）、对比分析报告、使用文档

## 技术决策说明

### 为什么选JSON Lines？
✅ 流式处理，边执行边写入，无需全部加载
✅ 易于分析，pandas兼容，可直接转DataFrame
✅ 易于扩展，无schema限制，可随意添加字段
✅ 可视化友好，易于分享和查看

### 为什么选Middleware + Hook混合？
✅ Middleware用于Turn-level的宏观事件
✅ Hook用于Tool/Context/Gate的细节事件
✅ 零侵入，无需修改QwenPaw源码
✅ 灵活性强，可动态启用/禁用采集

### 为什么采集四层事件？
✅ Turn层 - 宏观视图，追踪整体进度
✅ Tool层 - 微观视图，理解工具使用
✅ Context层 - 内存管理，压缩策略分析
✅ Gate层 - 控制流，迭代终止条件

## 无缝扩展路径

### 从3个case到450+个case

核心模块的逻辑完全相同，只需改变配置和加载模式：

```python
# 现在：三个代表性case
representative_cases = loader.find_representative_cases()
for case in representative_cases:
    runner.execute(case)

# 扩展后：全部450+个case（核心逻辑完全相同）
all_cases = loader.load_all_cases()
for case in all_cases:
    runner.execute(case)  # 执行逻辑完全相同

# 聚合分析框架（Week 4-5）
all_traces = [collector.load_trace(f) for f in trace_files]
aggregated = analyzer.aggregate(all_traces)  # Analyzer逻辑不变
report = reporter.generate_comparison(aggregated)
```

## 成功标准

### Phase 1（Week 1）- 框架可行性 ✅
- [ ] 三个case成功加载
- [ ] JSONL轨迹文件生成正确
- [ ] 每个case 100+基础events
- [ ] 事件序列化/反序列化无误

### Phase 2（Week 2）- 数据完整性 ✅
- [ ] Tool-level events 100%采集
- [ ] Context-level events完整捕获
- [ ] Gate-level events记录准确
- [ ] 总events 300+/case
- [ ] Trace overhead < 10%

### Phase 3（Week 3）- 分析可用性 ✅
- [ ] 四维度分析JSON完整
- [ ] 对比报告清晰展示level差异
- [ ] 工具使用分析准确
- [ ] 难度评分合理

## 风险评估

| 风险 | 概率 | 影响 | 缓解方案 |
|-----|------|------|--------|
| Hook未被触发 | 低 | 中 | 添加日志验证hook是否被调用 |
| JSONL文件过大 | 低 | 低 | 分批写入或压缩 |
| Context大小计算不准 | 低 | 低 | 使用token count替代 |
| Agent执行失败 | 中 | 中 | 添加错误处理和重试机制 |

## 文件代码量预期

| 模块 | 代码行数 | 说明 |
|-----|--------|-----|
| core/ | ~1000 | 核心模块 |
| runner/ | ~600 | 执行框架 |
| analysis/ | ~900 | 分析模块 |
| scripts/ | ~280 | 运行脚本 |
| tests/ | ~120 | 单元测试 |
| **总计** | **~3000** | 完整框架 |

## 部署和运行

### 环境准备
```bash
pip install pandas pyarrow matplotlib plotly
pip install -e /path/to/QwenPaw
```

### 运行单个case
```bash
python scripts/run_single_case.py --case_id <case_id> --output_dir outputs/
```

### 运行三个代表case
```bash
python scripts/run_three_cases.py --output_dir outputs/ --report_output report.html
```

### 生成分析报告
```bash
python scripts/generate_report.py --traces_dir outputs/traces/ --output_file outputs/report.json
```

## 后续研究方向

### 短期（Week 4-5）
- 扩展到450+个case
- 按level进行聚合分析
- 识别失败案例的模式

### 中期（Week 6-8）
- 工具选择优化建议
- Context管理策略改进
- Agent提示词微调建议

### 长期（Week 9+）
- 跨模型对比分析
- 工具库优化设计
- 自适应策略研究

## 总结

这个框架具有以下特点：

1. **可行性强** - 基于QwenPaw现有架构，无需大规模改动
2. **快速验证** - 3周内完成框架基础构建
3. **无缝扩展** - 从3个到450+个case无需改变架构
4. **数据完整** - 四层采集，每个case 300+事件
5. **分析深度** - 四维度全面分析agent行为
6. **工程规范** - 模块化设计，易于测试和维护

**建议立即启动Week 1的开发工作，预计第一周末能完成框架基础验证。**

---

详见 `IMPLEMENTATION_PLAN.md` 获取完整的实现方案。
