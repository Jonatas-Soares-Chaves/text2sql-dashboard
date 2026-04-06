import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import get_settings
from core.text2sql import ask, QueryResult
from db.connection import check_connection, get_schema_description, init_db

settings = get_settings()

st.set_page_config(
    page_title="Text-to-SQL · IA para Dados",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .sql-block { background:#1e1e2e; color:#cdd6f4; border-radius:8px;
                 padding:1rem; font-family:monospace; font-size:13px;
                 white-space:pre-wrap; overflow-x:auto; }
    .metric-row { display:flex; gap:12px; margin-bottom:1rem; }
    .answer-box { background:#f0f4ff; border-left:4px solid #4361ee;
                  border-radius:0 8px 8px 0; padding:.85rem 1.1rem;
                  font-size:15px; line-height:1.65; }
    .tag { display:inline-block; background:#e8f4fd; color:#1a6fa8;
           border-radius:4px; padding:2px 8px; font-size:12px;
           margin:2px; cursor:pointer; }
</style>
""", unsafe_allow_html=True)

if "history" not in st.session_state:
    st.session_state.history: list[QueryResult] = []

if "db_ready" not in st.session_state:
    st.session_state.db_ready = False


with st.sidebar:
    st.title(" Text-to-SQL")
    st.caption("Pergunte sobre seus dados em português")

    st.divider()

    st.subheader("Status")
    if check_connection():
        st.success("PostgreSQL conectado", icon="✅")
        if not st.session_state.db_ready:
            init_db()
            st.session_state.db_ready = True
    else:
        st.error("Banco não conectado", icon="❌")
        st.info("Configure DATABASE_URL no .env ou nos Secrets do HF Spaces.")
        st.stop()

    st.divider()

    with st.expander(" Schema do banco"):
        st.code(get_schema_description(), language="text")

    st.divider()

    st.subheader("Configurações")
    show_sql = st.toggle("Mostrar SQL gerado", value=True)
    show_chart = st.toggle("Gráfico automático", value=True)
    model_info = st.empty()
    model_info.caption(f"Modelo: `{settings.groq_model}`")

    st.divider()

    if st.session_state.history:
        st.subheader(f"Histórico ({len(st.session_state.history)})")
        for i, r in enumerate(reversed(st.session_state.history[-5:])):
            icon = "✅" if r.success else "❌"
            if st.button(
                f"{icon} {r.question[:35]}...",
                key=f"hist_{i}",
                use_container_width=True,
            ):
                st.session_state.current_result = r
                st.rerun()

        if st.button("Limpar histórico", use_container_width=True):
            st.session_state.history = []
            st.rerun()


st.title(" Text-to-SQL com IA")
st.caption(
    "Digite uma pergunta sobre os dados de e-commerce em português. "
    "O sistema converte para SQL, executa e explica o resultado."
)

EXAMPLES = [
    "Qual o total de receita por mês em 2024",
    "Top 5 produtos mais vendidos por quantidade?",
    "Qual estado tem mais clientes VIP?",
    "Qual a taxa de cancelamento por canal de venda?",
    "Quais categorias têm maior margem de lucro?",
    "Quantos pedidos foram feitos por semana em 2023?",
    "Qual o ticket médio por segmento de cliente?",
    "Quais produtos estão com estoque zerado?",
    "Compare receita de 2023 vs 2024 por trimestre",
    "Qual vendedor (canal) tem maior taxa de entrega?",
]

cols = st.columns(3)

for i, ex in enumerate(EXAMPLES):
    if cols[i % 3].button(
        ex,
        key=f"ex_{i}",
        use_container_width=True
    ):
        st.session_state.pending_question = ex

question = st.text_area(
    "Sua pergunta:",
    value=st.session_state.get("pending_question", ""),
    height=100,
    placeholder="Ex: Qual foi a receita total por categoria em 2024?",
    key="question_input",
)

if "pending_question" in st.session_state:
    del st.session_state["pending_question"]

col_run, col_clear = st.columns([1, 5])
run_clicked = col_run.button("▶ Executar", type="primary", use_container_width=True)
if col_clear.button("Limpar", use_container_width=True):
    st.rerun()

if run_clicked and question.strip():
    with st.spinner("Consultando o LLM e executando SQL..."):
        result = ask(question.strip())
        st.session_state.history.append(result)
        st.session_state.current_result = result

result: QueryResult | None = st.session_state.get("current_result")

if result:
    st.divider()

    if not result.success:
        st.error(f"**Erro:** {result.error}")
    else:

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Linhas retornadas", len(result.df))
        m2.metric("Colunas", len(result.df.columns))
        m3.metric("Tempo total", f"{result.execution_time_ms}ms")
        m4.metric("Cache", "Sim ♻️" if result.cached else "Não 🔄")

        st.markdown("### Resposta")
        st.markdown(
            f'<div class="answer-box">{result.answer}</div>',
            unsafe_allow_html=True,
        )

        if show_sql:
            st.markdown("### SQL gerado")
            st.markdown(
                f'<div class="sql-block">{result.sql}</div>',
                unsafe_allow_html=True,
            )
            st.button(
                " Copiar SQL",
                on_click=lambda: st.write(
                    f"<script>navigator.clipboard.writeText(`{result.sql}`)</script>",
                    unsafe_allow_html=True,
                ),
            )

        st.markdown("### Resultado")
        if result.df.empty:
            st.info("Nenhum resultado retornado para esta consulta.")
        else:
            st.dataframe(result.df, use_container_width=True, hide_index=True)

            csv = result.df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Exportar CSV",
                csv,
                "resultado.csv",
                "text/csv",
            )

def auto_chart(df):
    import streamlit as st

    if df is None or df.empty:
        st.warning("Sem dados para exibir.")
        return

    st.subheader(" Visualização automática")

    numeric_cols = df.select_dtypes(include="number").columns

    if len(numeric_cols) > 0:
        st.line_chart(df[numeric_cols])
    else:
        st.dataframe(df)

        # Visualização automática
        if show_chart and not result.df.empty:
            st.markdown("### Visualização automática")
            auto_chart(result.df)


def auto_chart(df: pd.DataFrame) -> None:
    """
    Tenta gerar o gráfico mais adequado automaticamente
    com base nos tipos de colunas.
    """
    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()

    if not num_cols:
        st.info("Nenhuma coluna numérica para visualizar.")
        return

    period_col = next(
        (c for c in cat_cols if any(
            kw in c.lower() for kw in ["mes", "mês", "semana", "trimestre", "ano", "data", "date"]
        )),
        None,
    )

    if period_col and num_cols:

        fig = px.line(
            df, x=period_col, y=num_cols[0],
            markers=True,
            labels={num_cols[0]: num_cols[0].replace("_", " ").title()},
            color_discrete_sequence=["#4361ee"],
        )
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    elif cat_cols and num_cols and len(df) <= 30:

        fig = px.bar(
            df.sort_values(num_cols[0], ascending=False),
            x=cat_cols[0], y=num_cols[0],
            color=num_cols[0],
            color_continuous_scale="Blues",
            labels={
                cat_cols[0]: cat_cols[0].replace("_", " ").title(),
                num_cols[0]: num_cols[0].replace("_", " ").title(),
            },
        )
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            coloraxis_showscale=False,
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    elif len(num_cols) >= 2:

        fig = px.scatter(
            df, x=num_cols[0], y=num_cols[1],
            color=cat_cols[0] if cat_cols else None,
            labels={
                num_cols[0]: num_cols[0].replace("_", " ").title(),
                num_cols[1]: num_cols[1].replace("_", " ").title(),
            },
        )
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Estrutura dos dados não se encaixa em um gráfico automático — use os dados exportados.")


st.divider()
st.caption(
    "**Stack Completa** · "
    "Groq (llama-3.3-70b) · LangChain · PostgreSQL · Streamlit · Python"
)
