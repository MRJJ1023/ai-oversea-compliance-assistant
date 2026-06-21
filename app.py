from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable, List

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"

st.set_page_config(
    page_title="AI 出海合规管理与法案预警助手",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    .main .block-container {padding-top: 1.4rem; max-width: 1480px;}
    .hero {
        padding: 1.4rem 1.6rem;
        border-radius: 22px;
        background: linear-gradient(135deg, #eff6ff 0%, #ffffff 50%, #f8fafc 100%);
        border: 1px solid #dbeafe;
        box-shadow: 0 14px 36px rgba(15, 23, 42, 0.08);
        margin-bottom: 1rem;
    }
    .hero-title {font-size: 2.1rem; font-weight: 800; color: #0f172a; margin-bottom: .35rem;}
    .hero-sub {font-size: 1rem; color: #475569; line-height: 1.65;}
    .notice {
        border-left: 5px solid #2563eb;
        background: #eff6ff;
        color: #0f172a;
        padding: .85rem 1rem;
        border-radius: 14px;
        margin: .7rem 0 1rem 0;
        line-height: 1.65;
    }
    .risk-high {border-left: 6px solid #dc2626; background: #fff7ed;}
    .risk-mid {border-left: 6px solid #f59e0b; background: #fffbeb;}
    .risk-low {border-left: 6px solid #2563eb; background: #eff6ff;}
    .card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        padding: 1rem 1.1rem;
        box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
        min-height: 126px;
    }
    .card h4 {font-size: 1rem; margin: 0 0 .35rem 0; color: #0f172a;}
    .card p {font-size: .92rem; line-height: 1.55; color: #475569; margin: 0;}
    .small-muted {font-size: .88rem; color: #64748b; line-height: 1.55;}
    .section-title {font-size: 1.3rem; font-weight: 750; color: #0f172a; margin: 1.2rem 0 .25rem 0;}
    .section-desc {color:#64748b; font-size:.95rem; line-height:1.6; margin-bottom:.7rem;}
    .stMetric {background: white; border-radius: 16px; padding: .8rem; border:1px solid #e2e8f0; box-shadow: 0 8px 18px rgba(15,23,42,.05);}
    div[data-baseweb="tag"] {background-color: #dbeafe !important; color:#1d4ed8 !important;}
    footer {visibility: hidden;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    df = pd.read_csv(path)
    df = df.fillna("")
    return df


law_df = load_csv("law_source_registry.csv")
risk_df = load_csv("risk_rule_library.csv")
case_df = load_csv("case_warning_library.csv")
update_df = load_csv("law_update_log.csv")
try:
    snapshot_df = load_csv("law_monitor_snapshot.csv")
except Exception:
    snapshot_df = pd.DataFrame()


def unique_sorted(series: pd.Series, include_all: bool = False) -> List[str]:
    values = sorted([str(x) for x in series.dropna().unique() if str(x).strip()])
    return (["全部"] + values) if include_all else values


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    t = str(text).lower()
    return any(str(k).lower() in t for k in keywords if str(k).strip())


def search_df(df: pd.DataFrame, query: str, cols: List[str]) -> pd.DataFrame:
    q = query.strip().lower()
    if not q:
        return df
    mask = pd.Series(False, index=df.index)
    for col in cols:
        if col in df.columns:
            mask |= df[col].astype(str).str.lower().str.contains(re.escape(q), na=False)
    return df[mask]


def level_rank(level: str) -> int:
    mapping = {"高": 3, "中高": 2, "中": 1, "低": 0}
    return mapping.get(str(level).strip(), 0)


def risk_level_class(level: str) -> str:
    if "高" == str(level).strip():
        return "risk-high"
    if "中高" in str(level) or "中" in str(level):
        return "risk-mid"
    return "risk-low"


def match_rule_field(value: str, selected: str) -> bool:
    """Treat '全部' in either side as wildcard and allow contains matching."""
    v = str(value)
    s = str(selected)
    if not s or s == "全部":
        return True
    if not v or v == "全部":
        return True
    return s in v or v in s


def filter_risk_rules(
    df: pd.DataFrame,
    jurisdiction: str,
    industry: str,
    product_type: str,
    deployment_mode: str,
    data_activities: List[str],
    keyword: str,
) -> pd.DataFrame:
    out = df.copy()
    if jurisdiction != "全部":
        out = out[out["jurisdiction"].astype(str).apply(lambda x: x == jurisdiction or x == "全球/通用")]
    out = out[out["industry"].astype(str).apply(lambda x: match_rule_field(x, industry))]
    out = out[out["product_type"].astype(str).apply(lambda x: match_rule_field(x, product_type))]
    out = out[out["deployment_mode"].astype(str).apply(lambda x: match_rule_field(x, deployment_mode))]
    if data_activities:
        out = out[out["data_activity"].astype(str).apply(lambda x: any(match_rule_field(x, a) for a in data_activities))]
    out = search_df(out, keyword, ["scenario", "data_activity", "risk_point", "trigger_condition", "suggested_action", "legal_basis"])
    if not out.empty:
        out = out.assign(_rank=out["risk_level"].apply(level_rank)).sort_values(["_rank", "sla_days"], ascending=[False, True]).drop(columns=["_rank"])
    return out


def make_action_summary(rules: pd.DataFrame) -> str:
    if rules.empty:
        return "当前筛选条件下暂无明确高风险规则命中，可先查看法规原文检索模块，并由业务 / 法务进一步复核。"
    top = rules.iloc[0]
    high_count = (rules["risk_level"].astype(str).str.contains("高")).sum()
    legal_count = (rules["need_legal"].astype(str) == "是").sum()
    product_count = (rules["need_product"].astype(str) == "是").sum()
    return (
        f"当前筛选条件下命中 {len(rules)} 条合规风险规则，其中高/中高风险 {high_count} 条。"
        f"优先关注“{top['risk_point']}”，建议动作：{top['suggested_action']}"
        f"本轮共 {legal_count} 条需要法务介入，{product_count} 条需要产品确认。"
    )


RESPONSE_LIBRARY = [
    {
        "question_type": "客户数据是否用于模型训练",
        "standard_response": "优先准备客户数据使用边界说明，明确客户输入、知识库数据、日志数据是否会被用于模型训练；如需训练或优化，应说明授权、退出机制和合同约定。",
        "materials": "数据使用说明；DPA补充条款；客户FAQ；产品数据流说明",
        "legal_path": "涉及个人数据、客户业务数据或训练授权时，需要法务确认合同与告知口径。",
        "product_path": "需要产品确认数据是否进入训练链路、日志是否隔离、客户是否可配置。",
    },
    {
        "question_type": "日志留存",
        "standard_response": "优先说明日志类型、留存周期、访问控制、审计导出能力和客户可配置边界，避免承诺超出产品能力。",
        "materials": "日志留存说明；审计能力说明；安全控制说明；客户可配置清单",
        "legal_path": "涉及监管留痕或跨境日志访问时，需要法务确认留存义务和数据处理边界。",
        "product_path": "需要产品确认日志字段、保存周期、导出能力和权限控制。",
    },
    {
        "question_type": "DPA / 数据处理协议",
        "standard_response": "优先准备标准DPA模板、数据处理角色说明、处理目的、数据类别、子处理者、跨境传输和删除机制。",
        "materials": "DPA模板；数据处理说明；子处理者清单；合同条款风险提示",
        "legal_path": "DPA属于法务主导事项，条款偏离标准版本时需升级复核。",
        "product_path": "需要产品提供实际数据处理链路、存储区域、删除机制和权限控制说明。",
    },
    {
        "question_type": "第三方模型调用",
        "standard_response": "优先说明是否调用第三方模型、数据是否会传递给第三方、第三方是否保留或训练数据，以及可选替代方案。",
        "materials": "第三方模型调用说明；供应商安全说明；数据流向图；客户可选方案",
        "legal_path": "涉及第三方处理者或跨境传输时需法务确认合同责任和告知义务。",
        "product_path": "需要产品确认调用链路、供应商接口、日志保存和可替代模型能力。",
    },
    {
        "question_type": "数据跨境 / 数据不出境",
        "standard_response": "优先说明数据存储区域、访问路径、跨境传输场景和可选部署方案；不能简单承诺“绝不出境”，需要结合部署模式确认。",
        "materials": "数据流向说明；部署模式对比；跨境传输说明；本地化部署可行性评估",
        "legal_path": "跨境传输涉及地区法规和合同责任边界，需要法务确认。",
        "product_path": "需要产品确认存储区域、访问路径、备份和运维支持边界。",
    },
    {
        "question_type": "内容安全与输出审核",
        "standard_response": "优先说明模型输出审核机制、风险过滤、人机协同复核、客户侧责任边界和高风险场景限制。",
        "materials": "内容安全说明；人工复核机制；风险过滤说明；客户责任边界说明",
        "legal_path": "涉及用户权益、高风险输出或监管敏感行业时需法务评估。",
        "product_path": "需要产品确认安全策略、审核能力、黑白名单和日志追踪能力。",
    },
]
response_df = pd.DataFrame(RESPONSE_LIBRARY)

# Sidebar filters
with st.sidebar:
    st.markdown("### 🧭 检索与预警条件")
    jurisdiction_sel = st.selectbox("目标地区 / 国家", unique_sorted(risk_df["jurisdiction"], include_all=True), index=0)
    industry_values = sorted(set("全部".split() + risk_df["industry"].astype(str).unique().tolist()))
    industry_sel = st.selectbox("客户行业", unique_sorted(risk_df["industry"], include_all=True), index=0)
    product_sel = st.selectbox("产品类型", unique_sorted(risk_df["product_type"], include_all=True), index=0)
    deploy_sel = st.selectbox("部署方式", unique_sorted(risk_df["deployment_mode"], include_all=True), index=0)
    data_activity_sel = st.multiselect("数据活动 / 处理对象", unique_sorted(risk_df["data_activity"]), default=[])
    keyword_sel = st.text_input("关键词搜索", placeholder="如：模型训练、DPA、跨境、日志、未成年人")
    st.divider()
    st.markdown("### 📌 使用说明")
    st.caption("v02 用于法规检索、风险预警和材料准备，并接入 GitHub Actions 定时监控官方来源疑似更新。")

matched_rules = filter_risk_rules(
    risk_df,
    jurisdiction_sel,
    industry_sel,
    product_sel,
    deploy_sel,
    data_activity_sel,
    keyword_sel,
)

st.markdown(
    """
    <div class="hero">
      <div class="hero-title">AI 出海合规管理与法案预警助手</div>
      <div class="hero-sub">
      面向 AI 出海业务、经营分析、销售、法务和产品团队的轻量合规工作台：
      快速定位官方法规/指南原文，识别目标市场风险点，沉淀客户合规响应材料，并并接入后台定时监控官方来源疑似更新。
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="notice">
    <b>当前关键判断：</b>{make_action_summary(matched_rules)}
    </div>
    """,
    unsafe_allow_html=True,
)

m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("法规/指南来源", f"{len(law_df)}")
with m2:
    st.metric("风险规则", f"{len(risk_df)}")
with m3:
    st.metric("案例/事件", f"{len(case_df)}")
with m4:
    high_rules = (risk_df["risk_level"].astype(str).str.contains("高")).sum()
    st.metric("高/中高风险规则", f"{high_rules}")
with m5:
    st.metric("更新台账", f"{len(update_df)}")

cards = st.columns(4)
card_contents = [
    ("法规原文检索", "先找到官方来源，再做业务解读，避免只凭二手材料判断合规义务。"),
    ("目标市场预警", "把地区、行业、产品、部署和数据活动映射到风险规则，提前识别客户落地风险。"),
    ("标准材料沉淀", "围绕训练数据、日志留存、DPA、第三方模型和数据跨境沉淀销售/法务/产品协同材料。"),
    ("更新监控接口", "v02 接入 GitHub Actions 定时检查官方来源页面，并将疑似更新写入台账。"),
]
for col, (title, body) in zip(cards, card_contents):
    with col:
        st.markdown(f"<div class='card'><h4>{title}</h4><p>{body}</p></div>", unsafe_allow_html=True)

# Prepare tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "① 法规原文检索",
    "② 目标市场风险预警",
    "③ 案例警示",
    "④ 法规更新台账",
    "⑤ 响应材料库",
])

with tab1:
    st.markdown("<div class='section-title'>法规原文检索</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-desc'>用于快速定位各地区 AI、数据、隐私和跨境相关法规或官方指南原文，并查看适用场景与风险关键词。</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.8])
    with c1:
        law_jur = st.selectbox("法规地区", unique_sorted(law_df["jurisdiction"], include_all=True), key="law_jur")
    with c2:
        law_type = st.selectbox("法规类型", unique_sorted(law_df["law_type"], include_all=True), key="law_type")
    with c3:
        law_status = st.selectbox("法律状态", unique_sorted(law_df["legal_status"], include_all=True), key="law_status")
    with c4:
        law_query = st.text_input("法规关键词", placeholder="如：AI Act、GDPR、生成式AI、跨境、DPA", key="law_query")

    law_view = law_df.copy()
    if law_jur != "全部":
        law_view = law_view[law_view["jurisdiction"] == law_jur]
    if law_type != "全部":
        law_view = law_view[law_view["law_type"] == law_type]
    if law_status != "全部":
        law_view = law_view[law_view["legal_status"] == law_status]
    law_view = search_df(law_view, law_query, ["law_name", "summary", "key_obligations", "applicable_scenarios", "risk_keywords"])

    chart_col, table_col = st.columns([0.9, 1.4])
    with chart_col:
        if not law_view.empty:
            count_df = law_view.groupby("jurisdiction", as_index=False).size().rename(columns={"size": "count"})
            fig = px.bar(count_df, x="count", y="jurisdiction", orientation="h", title="法规/指南来源分布")
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10), xaxis_title="数量", yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
    with table_col:
        show_cols = ["jurisdiction", "law_name", "law_type", "legal_status", "official_source_name", "official_url", "summary", "risk_keywords", "last_checked_date", "monitoring_method"]
        st.dataframe(
            law_view[show_cols],
            use_container_width=True,
            height=380,
            column_config={"official_url": st.column_config.LinkColumn("官方链接")},
        )
    st.download_button("下载当前法规检索结果", data=law_view.to_csv(index=False).encode("utf-8-sig"), file_name="law_search_result.csv", mime="text/csv")

with tab2:
    st.markdown("<div class='section-title'>目标市场风险预警</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-desc'>基于左侧选择的地区、行业、产品、部署方式和数据活动，匹配风险规则库，输出风险点、依据来源和建议动作。</div>", unsafe_allow_html=True)

    if matched_rules.empty:
        st.info("当前筛选条件下暂无规则命中。建议放宽地区、行业、产品或数据活动条件，或回到法规原文检索模块查看官方来源。")
    else:
        st.markdown("#### 命中风险规则")
        for _, row in matched_rules.head(8).iterrows():
            cls = risk_level_class(row["risk_level"])
            st.markdown(
                f"""
                <div class="notice {cls}">
                <b>{row['risk_point']}</b>｜风险等级：<b>{row['risk_level']}</b><br>
                <span class="small-muted">场景：{row['scenario']}｜触发条件：{row['trigger_condition']}</span><br>
                <b>建议动作：</b>{row['suggested_action']}<br>
                <span class="small-muted">依据：{row['legal_basis']}｜法务介入：{row['need_legal']}｜产品确认：{row['need_product']}｜建议 SLA：{row['sla_days']} 天</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.dataframe(
            matched_rules[["rule_id", "jurisdiction", "scenario", "industry", "product_type", "deployment_mode", "data_activity", "risk_point", "risk_level", "legal_basis", "source_url", "suggested_action", "need_legal", "need_product", "owner_team", "sla_days"]],
            use_container_width=True,
            height=360,
            column_config={"source_url": st.column_config.LinkColumn("来源链接")},
        )
        c1, c2 = st.columns(2)
        with c1:
            level_count = matched_rules.groupby("risk_level", as_index=False).size().rename(columns={"size": "count"})
            fig = px.bar(level_count, x="risk_level", y="count", title="命中风险等级分布", text="count")
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10), xaxis_title="风险等级", yaxis_title="规则数量")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            team_count = matched_rules.groupby("owner_team", as_index=False).size().rename(columns={"size": "count"})
            fig = px.bar(team_count, x="count", y="owner_team", orientation="h", title="建议牵头/协同团队", text="count")
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10), xaxis_title="规则数量", yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
        st.download_button("下载当前风险预警清单", data=matched_rules.to_csv(index=False).encode("utf-8-sig"), file_name="market_risk_warning_result.csv", mime="text/csv")

with tab3:
    st.markdown("<div class='section-title'>案例警示</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-desc'>用于查看公开监管事件或典型风险场景，帮助业务在目标市场落地前形成风险预警意识。</div>", unsafe_allow_html=True)
    case_query = st.text_input("案例关键词", placeholder="如：训练、跨境、隐私、未成年人、内容安全", key="case_query")
    case_view = case_df.copy()
    if jurisdiction_sel != "全部":
        case_view = case_view[case_view["jurisdiction"].astype(str).str.contains(jurisdiction_sel, na=False) | case_view["jurisdiction"].astype(str).str.contains("全球", na=False)]
    case_view = search_df(case_view, case_query or keyword_sel, ["case_title", "related_risk", "summary", "lesson_learned", "industry"])
    if case_view.empty:
        st.info("当前筛选条件下暂无案例，可放宽地区或关键词条件。")
    else:
        for _, row in case_view.iterrows():
            st.markdown(
                f"""
                <div class="card" style="margin-bottom:.8rem;">
                <h4>{row['case_title']}</h4>
                <p><b>地区：</b>{row['jurisdiction']}｜<b>类型：</b>{row['case_type']}｜<b>关联风险：</b>{row['related_risk']}</p>
                <p><b>摘要：</b>{row['summary']}</p>
                <p><b>业务警示：</b>{row['lesson_learned']}</p>
                <p><a href="{row['source_url']}" target="_blank">查看来源</a></p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.download_button("下载案例警示结果", data=case_view.to_csv(index=False).encode("utf-8-sig"), file_name="case_warning_result.csv", mime="text/csv")

with tab4:
    st.markdown("<div class='section-title'>法规更新台账</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-desc'>v02 已接入 GitHub Actions 自动监控框架：定时检查官方来源页面，通过 Last-Modified、ETag 或正文 hash 判断疑似更新，并写入更新台账。</div>", unsafe_allow_html=True)
    if not snapshot_df.empty:
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            st.metric("监控来源数", f"{len(snapshot_df)}")
        with s2:
            changed_count = (snapshot_df.get("change_detected", pd.Series(dtype=str)).astype(str) == "是").sum()
            st.metric("本轮疑似变化", f"{changed_count}")
        with s3:
            error_count = snapshot_df.get("fetch_error", pd.Series(dtype=str)).astype(str).str.strip().ne("").sum()
            st.metric("访问异常", f"{error_count}")
        with s4:
            latest_check = snapshot_df.get("checked_at", pd.Series([""])).astype(str).replace("", np.nan).dropna()
            st.metric("最近自动检查", latest_check.iloc[0] if len(latest_check) else "未运行")
        with st.expander("查看法规来源监控快照", expanded=False):
            snapshot_cols = [c for c in ["jurisdiction", "law_name", "official_url", "checked_at", "http_status", "last_modified", "etag", "change_detected", "change_fields", "fetch_error"] if c in snapshot_df.columns]
            st.dataframe(snapshot_df[snapshot_cols], use_container_width=True, height=300, column_config={"official_url": st.column_config.LinkColumn("官方链接")})
    else:
        st.info("尚未生成 law_monitor_snapshot.csv。部署到 GitHub 后，可在 Actions 中手动运行一次 Check law source updates 建立监控基线。")
    u1, u2 = st.columns([1, 2])
    with u1:
        impact_count = update_df.groupby("impact_level", as_index=False).size().rename(columns={"size": "count"})
        fig = px.pie(impact_count, names="impact_level", values="count", title="更新影响等级")
        fig.update_layout(height=340, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with u2:
        st.dataframe(
            update_df[["update_id", "jurisdiction", "law_name", "source_url", "detected_date", "change_type", "change_summary", "impact_level", "affected_scenarios", "suggested_review_action", "status"]],
            use_container_width=True,
            height=340,
            column_config={"source_url": st.column_config.LinkColumn("来源链接")},
        )
    st.markdown(
        """
        <div class="notice">
        <b>v02 自动监控机制预留：</b>后续新增 law_update_checker.py 与 GitHub Actions 定时任务，定期读取法规来源库中的官方链接，
        通过 API、Last-Modified、ETag 或网页正文 hash 判断是否疑似更新。发现变化后写入 law_update_log.csv，并提示人工复核。
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.download_button("下载法规更新台账", data=update_df.to_csv(index=False).encode("utf-8-sig"), file_name="law_update_log.csv", mime="text/csv")

with tab5:
    st.markdown("<div class='section-title'>客户合规响应材料库</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-desc'>用于将客户常见合规问题转化为标准材料、法务确认路径和产品确认路径，降低重复沟通成本。</div>", unsafe_allow_html=True)
    q_type = st.selectbox("客户问题类型", response_df["question_type"].tolist())
    selected = response_df[response_df["question_type"] == q_type].iloc[0]
    left, right = st.columns([1.1, 1])
    with left:
        st.markdown(
            f"""
            <div class="card">
            <h4>{selected['question_type']}</h4>
            <p><b>标准响应方向：</b>{selected['standard_response']}</p>
            <p><b>建议准备材料：</b>{selected['materials']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            f"""
            <div class="card">
            <h4>协同处理路径</h4>
            <p><b>法务路径：</b>{selected['legal_path']}</p>
            <p><b>产品路径：</b>{selected['product_path']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("#### 响应材料总表")
    st.dataframe(response_df, use_container_width=True, height=300)
    st.download_button("下载客户合规响应材料库", data=response_df.to_csv(index=False).encode("utf-8-sig"), file_name="response_material_library.csv", mime="text/csv")

st.divider()
st.markdown(
    """
    <div class="small-muted">
    <b>边界说明：</b>本工具用于合规信息检索、风险提示和业务前置准备，不构成正式法律意见；具体客户项目落地仍需由法务或外部律师复核。
    v02 已加入 GitHub Actions 定时监控框架；监控结果仅作为疑似更新提示，具体法律变化仍需人工复核。
    </div>
    """,
    unsafe_allow_html=True,
)
