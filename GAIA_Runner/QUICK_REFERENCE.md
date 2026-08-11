# GAIA_Runner 快速参考

## 🎯 一句话说明
在QwenPaw上运行GAIA数据集的三个代表性case（各Level各一个），采集300+细粒度事件，进行四维度分析。

---

## ⚡ 最快启动（3步）

### 1️⃣ 本地打包
```bash
cd /path/to/QwenPaw
tar -czf GAIA_Runner.tar.gz GAIA_Runner/
```

### 2️⃣ 服务器部署
```bash
scp GAIA_Runner.tar.gz user@server:/home/user/
ssh user@server
cd /path/to/QwenPaw
tar -xzf /home/user/GAIA_Runner.tar.gz
docker compose --env-file .env up -d
sleep 60
```

### 3️⃣ 运行
```bash
python3 -m venv gaia_env
source gaia_env/bin/activate
pip install -r GAIA_Runner/requirements.txt

python GAIA_Runner/scripts/run_three_cases.py \
  --output-dir GAIA_Runner/outputs \
  --dataset-root dataset/GAIA
```

---

## 📂 文件结构

```
GAIA_Runner/
├── core/          # 数据加载和采集
├── runner/        # Agent执行框架
├── analysis/      # 四维度分析
├── config/        # 配置管理
├── scripts/       # 运行脚本
├── outputs/       # 输出目录
└── docs/          # 文档
```

---

## 🔧 常用命令

| 任务 | 命令 |
|-----|------|
| 运行三个case | `python GAIA_Runner/scripts/run_three_cases.py --output-dir outputs --dataset-root dataset/GAIA` |
| 运行单个case | `python GAIA_Runner/scripts/run_single_case.py --level 2` |
| 生成报告 | `python GAIA_Runner/scripts/generate_report.py --traces-dir outputs/traces --output-dir outputs/reports` |
| 查看日志 | `tail -f GAIA_Runner/outputs/gaia_runner.log` |
| 查看报告 | `cat GAIA_Runner/outputs/reports/analysis_report.json \| python3 -m json.tool` |

---

## 🎯 四层事件

| 层 | 采集点 | 事件数 | 内容 |
|----|------|------|-----|
| Turn | Agent.reply() | ~50 | 问题、回复、context |
| Tool | ToolHookRegistry | ~100-200 | 工具、参数、结果 |
| Context | compress_context() | ~5-20 | 压缩大小、压缩率 |
| Gate | StopGate.check() | ~5-10 | 决策、原因 |
| **总计** | | **300+** | - |

---

## 📊 三个代表性Case

| Level | 特征 | 迭代 | 工具 | 难度 |
|------|------|------|------|------|
| 1 | 纯文本 | 1-3 | 0-2 | 0.2-0.4 |
| 2 | 文档 | 4-8 | 5-15 | 0.4-0.6 |
| 3 | 多工具 | 8-15 | 15-30 | 0.6-1.0 |

---

## 📋 四维度分析

1. **难度**: 0.3×迭代 + 0.25×工具 + 0.25×context + 0.2×复杂度
2. **工具**: 多样性、重用率、失败率、耗时
3. **内存**: 峰值、平均、压缩次数、压缩率
4. **质量**: 质量趋势、噪声、关键信息保留、冗余

---

## 🚨 故障排除

| 问题 | 症状 | 解决 |
|-----|------|------|
| 连接失败 | ConnectionError | `docker ps \| grep qwenpaw` |
| 找不到数据集 | FileNotFoundError | `ls dataset/GAIA/2023/test/` |
| 内存不足 | MemoryError | `docker update --memory=16g` |
| 权限问题 | PermissionError | `chmod -R 755 outputs/` |

---

## 📞 如何获取帮助

| 问题 | 文档 |
|-----|------|
| 项目是什么？ | README.md |
| 怎么部署？ | OPENEULER_DEPLOYMENT.md |
| 怎么使用？ | DEPLOYMENT_GUIDE.md |
| 实现细节？ | IMPLEMENTATION_PLAN.md |
| 有什么功能？ | PROJECT_DELIVERY.md |

---

## ⏱️ 时间参考

- 单个case: 5-30秒
- 三个case: 15-90秒
- 报告生成: <2秒
- 总耗时: 20-100秒

---

## ✨ 关键特性

✅ 四层细粒度事件采集  
✅ 四维度深度分析  
✅ 无需改源码集成  
✅ JSONL流式处理  
✅ 支持450+个case扩展  
✅ 详细OpenEuler部署指南  

---

## 🎁 输出文件

- **轨迹**: `outputs/traces/*.jsonl` (JSONL格式)
- **元数据**: `outputs/traces/*_meta.json` (case信息)
- **报告**: `outputs/reports/analysis_report.json` (分析结果)
- **HTML**: `outputs/reports/analysis_report.html` (可视化)
- **日志**: `outputs/gaia_runner.log` (执行日志)

---

## 🚀 下一步

1. **阅读**: README.md
2. **部署**: OPENEULER_DEPLOYMENT.md
3. **运行**: `run_three_cases.py`
4. **分析**: 查看报告

**Let's go!** 🎯
