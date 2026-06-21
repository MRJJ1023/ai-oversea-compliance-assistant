# AI 出海合规管理与法案预警助手 v02

本项目是面向 AI 出海业务、经营分析、销售、法务和产品团队的轻量合规工作台，用于快速定位各地区 AI / 数据 / 隐私 / 跨境相关法规或官方指南原文，识别目标市场风险点，沉淀客户合规响应材料，并通过 GitHub Actions 定时监控官方来源疑似更新。

## v02 新增能力

- 新增 `scripts/law_update_checker.py`：读取法规来源库，检查官方链接的 Last-Modified、ETag、HTTP 状态和正文 hash。
- 新增 `.github/workflows/check_law_updates.yml`：每周自动运行一次，也支持在 GitHub Actions 页面手动触发。
- 新增 `data/law_monitor_snapshot.csv`：保存每个官方来源的监控快照。
- 发现疑似变化时，自动追加写入 `data/law_update_log.csv`，并提交回 GitHub。

## 重要边界

本工具只做合规信息检索、风险提示和疑似更新预警，不构成正式法律意见。对于自动监控发现的变化，必须打开官方来源进行人工复核。

## 本地运行

```bash
cd ai_oversea_compliance_assistant_v02
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## 本地测试监控脚本

第一次建立监控基线：

```bash
python scripts/law_update_checker.py --mode initialize --timeout 30
```

后续检查疑似更新：

```bash
python scripts/law_update_checker.py --mode check --timeout 30
```

## 部署说明

1. 将本项目上传到 GitHub 仓库根目录。
2. 确认仓库包含：`app.py`、`requirements.txt`、`data/`、`.streamlit/`、`scripts/`、`.github/workflows/`。
3. Streamlit Cloud 的入口文件填写 `app.py`。
4. 在 GitHub 仓库的 Actions 页面启用工作流，并可手动运行 `Check law source updates` 建立第一轮监控快照。
