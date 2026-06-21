# AI 出海合规管理与法案预警助手 v01

这是一个基于 Streamlit 的 AI 出海合规辅助工具，用于法规原文检索、目标市场风险预警、案例警示、法规更新台账和客户合规响应材料整理。

> 说明：本工具用于合规信息检索、风险提示和业务前置准备，不构成正式法律意见；具体客户项目落地仍需由法务或外部律师复核。

## 本地运行

```bash
cd /d D:\tencent_resume_portfolio\07_AI出海合规管理助手\ai_oversea_compliance_assistant_v01
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## 项目结构

```text
ai_oversea_compliance_assistant_v01
├── app.py
├── requirements.txt
├── README.md
├── data
│   ├── law_source_registry.csv
│   ├── risk_rule_library.csv
│   ├── case_warning_library.csv
│   └── law_update_log.csv
└── .streamlit
    └── config.toml
```

## v01 功能

1. 法规原文检索：按地区、法规类型、法律状态、业务关键词检索官方法规/指南来源。
2. 目标市场风险预警：按地区、行业、产品类型、部署方式和数据活动匹配风险规则。
3. 案例警示：查看公开案例或典型风险事件，形成客户落地前预警。
4. 法规更新台账：展示法规/指南更新记录，为 v02 自动监控预留接口。
5. 客户合规响应材料库：围绕常见客户问题输出标准化材料建议和协同路径。

## v02 升级方向

新增 GitHub Actions + law_update_checker.py 定时检查官方来源链接，基于 API、Last-Modified、ETag 或网页正文 hash 判断疑似更新，并写入 law_update_log.csv。
