import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
from datetime import datetime
import os

with open("style.css", encoding="utf-8") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.set_page_config(page_title="Gestão de Entregas", layout="wide")

# ---------------- CSS ----------------
def local_css(file_name):
    if os.path.exists(file_name):
        with open(file_name, encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css("style.css")

# ---------------- SESSION ----------------
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

# ---------------- REGRAS ----------------
TAREFAS_DP = [
    "admissão","admissao","ferias","férias","folha complementar","recalculo dp",
    "rescisão","rescisao","analitico da rescisão","analitico da rescisao","gfd rescisória","gfd rescisoria",
    "solicitação de aviso","solicitacao de aviso","rescisão de estagiário","rescisao de estagiario",
    "simulação de rescisão","simulacao de rescisao"
]

TAREFAS_FISCAL = [
    "fiscal","fiscal-contábil","fiscal-contabil","setor fiscal-regularização","setor fiscal-regularizacao"
]

def classificar_departamento(tarefa):
    tarefa_limpa = str(tarefa).lower().strip()

    for termo in TAREFAS_DP:
        if termo in tarefa_limpa:
            return "Pessoal (DP)"

    for termo in TAREFAS_FISCAL:
        if termo in tarefa_limpa:
            return "Fiscal"

    # fallback obrigatório
    return "Fiscal"

def normalizar_status(valor):
    v = str(valor).upper()
    if "ATRAS" in v:
        return "Atrasada"
    if "JUST" in v:
        return "Justificada"
    return "No prazo"

# ---------------- BANCO ----------------
def init_db():
    conn = sqlite3.connect("gestao_entregas.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador TEXT,
            tarefa TEXT,
            status TEXT,
            departamento TEXT,
            mes_referencia TEXT,
            data_entrega TEXT,
            data_upload TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def limpar_banco():
    conn = sqlite3.connect("gestao_entregas.db")
    conn.execute("DELETE FROM entregas")
    conn.commit()
    conn.close()

def apagar_mes(mes):
    """
    Apaga todas as entregas de um mês específico no formato 'YYYY-MM'
    """
    conn = sqlite3.connect("gestao_entregas.db")
    c = conn.cursor()
    c.execute("DELETE FROM entregas WHERE mes_referencia = ?", (mes,))
    conn.commit()
    conn.close()
    st.success(f"🗑 Entregas do mês {mes} apagadas com sucesso!")

# ---------------- UPLOAD ----------------
def salvar_no_banco(df, substituir=False):
    if substituir:
        limpar_banco()

    df.columns = [c.strip().upper() for c in df.columns]

    COL_DATA = "DATA DA ENTREGA"
    COL_RESP = "RESPONSÁVEL ENTREGA"
    COL_TAREFA = "OBRIGAÇÃO / TAREFA"
    COL_STATUS = "STATUS"

    for col in [COL_DATA, COL_RESP, COL_TAREFA, COL_STATUS]:
        if col not in df.columns:
            st.error(f"Coluna obrigatória não encontrada: {col}")
            return

    # ---- IGNORAR ENTREGAS DE TECNOLOGIA E INOVAÇÃO ----
    NOME_IGNORADO = "Tecnologia e Inovação - Contas Contabilidade"
    total_antes = len(df)
    df = df[df[COL_RESP].astype(str).str.strip() != NOME_IGNORADO]
    removidas = total_antes - len(df)
    if removidas > 0:
        st.info(f"🚫 {removidas} entregas ignoradas ({NOME_IGNORADO})")

    # ---- DATA DD/MM/AAAA ----
    df[COL_DATA] = df[COL_DATA].astype(str).str.strip()
    def converter_data_br(valor):
        try:
            return pd.to_datetime(valor, format="%d/%m/%Y", errors="raise")
        except:
            return pd.NaT
    df[COL_DATA] = df[COL_DATA].apply(converter_data_br)
    invalidas = df[COL_DATA].isna().sum()
    if invalidas > 0:
        st.warning(f"⚠️ {invalidas} datas inválidas foram ignoradas")
    df = df.dropna(subset=[COL_DATA])

    # ---- DATAFRAME FINAL ----
    df_final = pd.DataFrame()
    df_final["data_entrega"] = df[COL_DATA].dt.strftime("%d/%m/%Y")
    df_final["mes_referencia"] = df[COL_DATA].dt.strftime("%Y-%m")
    df_final["colaborador"] = df[COL_RESP].fillna("Não informado")
    df_final["tarefa"] = df[COL_TAREFA].fillna("Sem tarefa")
    df_final["status"] = df[COL_STATUS].apply(normalizar_status)
    df_final["departamento"] = df_final["tarefa"].apply(classificar_departamento)
    df_final["data_upload"] = datetime.now()

    conn = sqlite3.connect("gestao_entregas.db")
    df_final.to_sql("entregas", conn, if_exists="append", index=False)
    conn.close()

    st.success(f"✅ {len(df_final)} entregas salvas com sucesso!")

# ---------------- INIT ----------------
init_db()

# ---------------- SIDEBAR ----------------
st.sidebar.image("logo.png", use_container_width=True)
perfil = st.sidebar.selectbox("Perfil", ["Visualização", "Administrador"])

if perfil == "Administrador":
    if not st.session_state.autenticado:
        senha = st.sidebar.text_input("Senha", type="password")
        if st.sidebar.button("Entrar"):
            if senha == "admin123":
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta")
    else:
        st.sidebar.success("Logado")
        if st.sidebar.button("Sair"):
            st.session_state.autenticado = False
            st.rerun()
else:
    st.session_state.autenticado = False

# ... (mantenha as funções de banco e regras iguais até chegar no Sidebar)

# ---------------- FILTROS ----------------
conn = sqlite3.connect("gestao_entregas.db")
try:
    meses = pd.read_sql(
        "SELECT DISTINCT mes_referencia FROM entregas ORDER BY mes_referencia DESC",
        conn
    )["mes_referencia"].tolist()
except:
    meses = []
conn.close()

st.sidebar.markdown("### 🔍 Filtros de Pesquisa")
mes = st.sidebar.selectbox("📅 Mês", meses if meses else ["Sem dados"])
deps = st.sidebar.multiselect(
    "🏢 Departamentos",
    ["Fiscal", "Pessoal (DP)"],
    default=["Fiscal", "Pessoal (DP)"]
)

# --- NOVA LÓGICA PARA BUSCA DE COLABORADORES ---
colaboradores_selecionados = []
if mes != "Sem dados":
    # Buscamos os nomes disponíveis para preencher o filtro de busca
    conn = sqlite3.connect("gestao_entregas.db")
    df_nomes = pd.read_sql(f"SELECT DISTINCT colaborador FROM entregas WHERE mes_referencia = '{mes}'", conn)
    conn.close()
    
    lista_nomes = sorted(df_nomes["colaborador"].unique().tolist())
    colaboradores_selecionados = st.sidebar.multiselect(
        "👤 Buscar Colaborador",
        options=lista_nomes,
        placeholder="Digite o nome..."
    )

# ---------------- ADMIN ----------------

# ---------------- DASHBOARD ----------------
st.title("Relatório de Entregas")

if mes != "Sem dados":
    conn = sqlite3.connect("gestao_entregas.db")
    df = pd.read_sql(f"SELECT * FROM entregas WHERE mes_referencia = '{mes}'", conn)
    conn.close()

    if not df.empty:
        # Aplicar Filtro de Departamento
        df = df[df["departamento"].isin(deps)]
        
        # --- APLICAR FILTRO DE NOME (SE SELECIONADO) ---
        if colaboradores_selecionados:
            df = df[df["colaborador"].isin(colaboradores_selecionados)]

        # Verificar se após os filtros ainda há dados
        if df.empty:
            st.warning("Nenhum dado encontrado para os filtros selecionados.")
        else:
            # Métricas
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total", len(df))
            c2.metric("No prazo", len(df[df["status"] == "No prazo"]))
            c3.metric("Atrasadas", len(df[df["status"] == "Atrasada"]))
            c4.metric("Justificadas", len(df[df["status"] == "Justificada"]))

            st.divider()

            col1, col2 = st.columns(2)
            with col1:
                fig = px.pie(
                    df, names="status", hole=0.5, color="status",
                    color_discrete_map={
                        "No prazo": "#0DDB3A",
                        "Atrasada": "#DB3F0D",
                        "Justificada": "#DB960D"
                    }
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                top = df["tarefa"].value_counts().head(10).reset_index()
                top.columns = ["Tarefa", "Qtd"]
                fig2 = px.bar(top, x="Qtd", y="Tarefa", orientation="h", title="Top 10 Obrigações / Tarefas")
                st.plotly_chart(fig2, use_container_width=True)

            st.subheader("Colaboradores")
            resumo = df.groupby(["colaborador", "status"]).size().unstack(fill_value=0)
            if "Total" not in resumo.columns:
                resumo["Total"] = resumo.sum(axis=1)
            
            st.dataframe(resumo.sort_values("Total", ascending=False), use_container_width=True)

    else:
        st.warning("Sem dados para este período")
else:
    st.info("Faça o upload da primeira planilha")
