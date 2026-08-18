import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from db import get_connection

st.set_page_config(page_title="Code Review vs Instabilidade Arquitetural", layout="wide")
st.title("Code Review & Instabilidade Arquitetural — MVP")
st.markdown("""
**Objetivo do estudo:** verificar se repositórios com maior taxa de revisão de código (code review)
tendem a apresentar menor crescimento de instabilidade arquitetural ao longo do tempo.

As métricas abaixo foram coletadas trimestralmente para repositórios Python e Java de grande porte no GitHub.
""")

@st.cache_data
def load_data():
    with get_connection() as conn:
        repos = pd.read_sql_query("SELECT * FROM repos", conn)
        quarters = pd.read_sql_query("SELECT * FROM quarters", conn)
        metrics = pd.read_sql_query("SELECT * FROM metrics", conn)
    return repos, quarters, metrics

repos, quarters, metrics = load_data()

if repos.empty:
    st.warning("Nenhum dado encontrado. Execute `python collect.py` e depois `python analyze.py`.")
    st.stop()

merged = (
    quarters
    .merge(metrics, on=["repo_id", "quarter"], how="inner")
    .merge(repos[["id", "name", "language", "stars"]], left_on="repo_id", right_on="id")
    .sort_values(["repo_id", "quarter"])
)

# --- Section 1: Sample overview ---
st.header("1. Visão Geral da Amostra")
st.markdown("""
Esta tabela resume os repositórios analisados. Cada linha representa um projeto open-source,
com as médias das métricas ao longo de todos os trimestres coletados.

- **valid_quarters:** número de trimestres com dados completos (PR + análise estática)
- **avg_review_ratio:** média da taxa de revisão — proporção de PRs que receberam pelo menos um "Approve" de alguém que não é o autor
- **avg_instability:** média da instabilidade arquitetural (métrica de Martin) — valores próximos de 1 indicam módulos mais instáveis (muito dependentes de outros, pouco depended upon)
""")
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
st.header("2. Evolução Temporal por Repositório")
st.markdown("""
Mostra como a **instabilidade arquitetural** (linha vermelha) e a **taxa de revisão** (linha azul)
evoluíram trimestre a trimestre em cada repositório.

- **Instabilidade (I):** calculada pela fórmula de Robert C. Martin — `I = Ce / (Ce + Ca)`, onde:
  - `Ce` (Efferent Coupling) = número de módulos que **este módulo importa**
  - `Ca` (Afferent Coupling) = número de módulos que **importam este módulo**
  - Quanto mais um módulo importa e menos é importado, mais instável ele é (I próximo de 1)
  - O valor exibido é a **média de I por módulo** do repositório naquele trimestre
- **Review Ratio:** proporção dos PRs mergeados naquele trimestre que tiveram aprovação formal de um revisor externo ao autor

Selecione o repositório na barra lateral para explorar.
""")
selected_repo = st.sidebar.selectbox("Repositório", sorted(merged["name"].unique()))
repo_data = merged[merged["name"] == selected_repo]

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=repo_data["quarter"], y=repo_data["instability"],
    name="Instabilidade (I)", line=dict(color="crimson")
))
fig.add_trace(go.Scatter(
    x=repo_data["quarter"], y=repo_data["review_ratio"],
    name="Review Ratio", line=dict(color="steelblue"), yaxis="y2"
))
fig.update_layout(
    title=selected_repo,
    yaxis=dict(title="Instabilidade (I)", range=[0, 1]),
    yaxis2=dict(title="Review Ratio", overlaying="y", side="right", range=[0, 1]),
    legend=dict(x=0, y=1.1, orientation="h"),
)
st.plotly_chart(fig, use_container_width=True)

# --- Section 3: Association scatter plot ---
st.header("3. Associação: Review Ratio vs ΔInstabilidade")
st.markdown("""
Este é o **gráfico central da hipótese**. Cada ponto representa um trimestre de um repositório.

- **Eixo X — Review Ratio no trimestre t:** quão revisado foi o código naquele período
- **Eixo Y — ΔInstabilidade (t → t+1):** quanto a instabilidade **mudou** no trimestre seguinte
  - Valores negativos = instabilidade **diminuiu** (arquitetura melhorou)
  - Valores positivos = instabilidade **aumentou** (arquitetura piorou)
  - Zero = sem mudança

**O que a hipótese prevê:** a linha de tendência (OLS) deveria ser **descendente** — ou seja,
trimestres com mais review deveriam ser seguidos de menor crescimento (ou redução) de instabilidade.

A linha tracejada horizontal em y=0 serve de referência para separar melhora de piora.
""")
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
        "review_ratio": "Review Ratio no trimestre t",
        "delta_instability": "ΔInstabilidade (t → t+1)",
    },
    title="Maior taxa de revisão precede menor crescimento de instabilidade?",
)
fig2.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
st.plotly_chart(fig2, use_container_width=True)

# --- Section 4: Raw data ---
st.header("4. Dados Brutos")
st.markdown("""
Tabela completa com todas as métricas coletadas por repositório e trimestre.

| Coluna | Descrição |
|--------|-----------|
| `review_ratio` | Proporção de PRs com aprovação de revisor externo |
| `author_entropy` | Entropia de Shannon dos autores de commits — mede diversidade de contribuidores (alto = mais distribuído) |
| `total_prs` | Total de PRs mergeados no trimestre |
| `instability` | Média da instabilidade de Martin (I) por módulo |
| `ce` | Média de Ce (efferent coupling) por módulo |
| `ca` | Média de Ca (afferent coupling) por módulo |
| `num_files` | Número de arquivos analisados no snapshot |
| `delta_instability` | Variação da instabilidade em relação ao trimestre seguinte |
""")
display_cols = [
    "name", "language", "quarter", "review_ratio", "author_entropy",
    "total_prs", "instability", "ce", "ca", "num_files", "delta_instability"
]
st.dataframe(scatter_data[display_cols].round(4), use_container_width=True)
csv = scatter_data[display_cols].to_csv(index=False)
st.download_button("Baixar CSV", csv, "mvp_data.csv", "text/csv")
