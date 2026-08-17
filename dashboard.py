import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from db import get_connection

st.set_page_config(page_title="Code Review vs Architectural Instability", layout="wide")
st.title("Code Review & Architectural Instability — MVP")

@st.cache_data
def load_data():
    with get_connection() as conn:
        repos = pd.read_sql_query("SELECT * FROM repos", conn)
        quarters = pd.read_sql_query("SELECT * FROM quarters", conn)
        metrics = pd.read_sql_query("SELECT * FROM metrics", conn)
    return repos, quarters, metrics

repos, quarters, metrics = load_data()

if repos.empty:
    st.warning("No data found. Run `python collect.py` then `python analyze.py` first.")
    st.stop()

merged = (
    quarters
    .merge(metrics, on=["repo_id", "quarter"], how="inner")
    .merge(repos[["id", "name", "language", "stars"]], left_on="repo_id", right_on="id")
    .sort_values(["repo_id", "quarter"])
)

# --- Section 1: Sample overview ---
st.header("1. Sample Overview")
overview = (
    merged
    .groupby(["name", "language", "stars"])
    .agg(
        valid_quarters=("quarter", "count"),
        avg_review_ratio=("review_ratio", "mean"),
        avg_instability=("instability", "mean"),
    )
    .reset_index()
    .round(3)
)
st.dataframe(overview, use_container_width=True)

# --- Section 2: Time series per repository ---
st.header("2. Time Series by Repository")
selected_repo = st.sidebar.selectbox("Repository", sorted(merged["name"].unique()))
repo_data = merged[merged["name"] == selected_repo]

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=repo_data["quarter"], y=repo_data["instability"],
    name="Instability (I)", line=dict(color="crimson")
))
fig.add_trace(go.Scatter(
    x=repo_data["quarter"], y=repo_data["review_ratio"],
    name="Review Ratio", line=dict(color="steelblue"), yaxis="y2"
))
fig.update_layout(
    title=selected_repo,
    yaxis=dict(title="Instability (I)", range=[0, 1]),
    yaxis2=dict(title="Review Ratio", overlaying="y", side="right", range=[0, 1]),
    legend=dict(x=0, y=1.1, orientation="h"),
)
st.plotly_chart(fig, use_container_width=True)

# --- Section 3: Association scatter plot ---
st.header("3. Association: Review Ratio (t) vs ΔInstability (t→t+1)")
df = merged.copy().sort_values(["repo_id", "quarter"])
df["delta_instability"] = df.groupby("repo_id")["instability"].diff().shift(-1)
scatter_data = df.dropna(subset=["delta_instability"])

fig2 = px.scatter(
    scatter_data,
    x="review_ratio",
    y="delta_instability",
    color="language",
    hover_data=["name", "quarter"],
    trendline="ols",
    labels={
        "review_ratio": "Review Ratio at t",
        "delta_instability": "ΔInstability (t → t+1)",
    },
    title="Does higher review ratio precede lower instability growth?",
)
fig2.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
st.plotly_chart(fig2, use_container_width=True)

# --- Section 4: Raw data ---
st.header("4. Raw Data")
display_cols = [
    "name", "language", "quarter", "review_ratio", "author_entropy",
    "total_prs", "instability", "ce", "ca", "num_files", "delta_instability"
]
st.dataframe(scatter_data[display_cols].round(4), use_container_width=True)
csv = scatter_data[display_cols].to_csv(index=False)
st.download_button("Download CSV", csv, "mvp_data.csv", "text/csv")
