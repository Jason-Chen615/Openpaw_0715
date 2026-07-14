# How to Run LoCoMo Evaluation on QwenPaw

## 第一步：上传文件到服务器

```bash
scp locomo10_small_dataset/* user@your-server:~/qwenpaw-eval/
```

## 第二步：在服务器上创建 .env 文件

```bash
cd ~/qwenpaw-eval
cat > .env << EOF
QWENPAW_AUTH_USERNAME=admin
QWENPAW_AUTH_PASSWORD=your_password
DASHSCOPE_API_KEY=sk-xxxxxxxx
EOF
```

## 第三步：启动 QwenPaw

```bash
mkdir -p eval_results
docker compose --env-file .env up -d
```

等 60 秒后验证是否启动：

```bash
curl -u admin:your_password http://127.0.0.1:8088/healthz
# 返回 {"status": "ok"} 即可
```

## 第四步：在浏览器配置模型

打开 `http://your-server:8088`，进入 **设置 → 模型**，启用对应模型。

> 如需公网访问，先配置 Nginx，见 DEPLOYMENT.md §5。

## 第五步：安装评测脚本依赖

```bash
python3 -m venv eval_env
source eval_env/bin/activate
pip install -r requirements.txt
```

## 第六步：运行评测

```bash
export QWENPAW_BASE_URL=http://127.0.0.1:8088/api
export QWENPAW_API_USER=admin
export QWENPAW_API_PASS=your_password

python eval_locomo.py \
  --data locomo_small.json \
  --agent-id locomo_eval \
  --output eval_results/results.json
```

## 第七步：查看结果

```bash
cat eval_results/results.json
```

指标示例：
```
Cat1 Factual     4/ 6 = 66.7%
Cat2 Temporal    6/11 = 54.5%
Cat4 General QA 19/27 = 70.4%
Overall         32/52 = 61.5%
```

---

> ⚠️ 当前 `got` 字段返回占位符 `[PENDING...]`，需实现消息拉取后才能得到真实回答。详见 DEPLOYMENT.md §7。