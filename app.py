import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
from datetime import datetime
import os

# Configuracao da pagina
st.set_page_config(page_title="Gestao de Entregas", layout="wide")

# Inicializar estado de login
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

# ---------------- CSS ----------------
def local_css(file_name):
    if os.path.exists(file_name):
        with open(file_name, encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css("style.css")

# ---------------- BANCO DE DADOS ----------------
def init_db():
    conn = sqlite3.connect("gestao_entregas.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador TEXT, tarefa TEXT, status TEXT, 
            departamento TEXT, mes_referencia TEXT, 
            data_entrega TEXT, data_upload TIMESTAMP
        )
    """)
    conn.close()

def limpar_banco_mes(mes):
    conn = sqlite3.connect("gestao_entregas.db")
    conn.execute("DELETE FROM entregas WHERE mes_referencia = ?", (mes,))
    conn.commit()
    conn.close()
    st.info(f"Dados do mes {mes} removidos com sucesso.")

init_db()

# ---------------- FUNCOES DE APOIO ----------------
def classificar_departamento(tarefa):
    dp = ["admissao", "ferias", "folha", "recalculo", "rescisao"]
    t = str(tarefa).lower().strip()
    if any(x in t for x in dp): return "Pessoal (DP)"
    return "Fiscal"

def normalizar_status(valor):
    v = str(valor).upper()
    if "ATRAS" in v: return "Atrasada"
    if "JUST" in v: return "Justificada"
    return "No prazo"

def salvar_no_banco(df, substituir=False, mes_ref=None):
    if substituir and mes_ref:
        limpar_banco_mes(mes_ref)

    df.columns = [c.strip().upper() for c in df.columns]
    COL_DATA, COL_RESP, COL_TAREFA, COL_STATUS = "DATA DA ENTREGA", "RESPONSAVEL ENTREGA", "OBRIGACAO / TAREFA", "STATUS"
    
    df[COL_DATA] = pd.to_datetime(df[COL_DATA], format="%d/%m/%Y", errors="coerce")
    df = df.dropna(subset=[COL_DATA])
    
    df_final = pd.DataFrame()
    df_final["data_entrega"] = df[COL_DATA].dt.strftime("%d/%m/%Y")
    df_final["mes_referencia"] = df[COL_DATA].dt.strftime("%Y-%m")
    df_final["colaborador"] = df[COL_RESP].fillna("Nao informado")
    df_final["tarefa"] = df[COL_TAREFA].fillna("Sem tarefa")
    df_final["status"] = df[COL_STATUS].apply(normalizar_status)
    df_final["departamento"] = df_final["tarefa"].apply(classificar_departamento)
    df_final["data_upload"] = datetime.now()

    conn = sqlite3.connect("gestao_entregas.db")
    df_final.to_sql("entregas", conn, if_exists="append", index=False)
    conn.close()
    st.success("Dados importados com sucesso.")

# ---------------- SIDEBAR ----------------
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)

perfil = st.sidebar.selectbox("Perfil de Acesso", ["Visualizacao", "Administrador"])

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
        if st.sidebar.button("Sair do Modo Admin"):
            st.session_state.autenticado = False
            st.rerun()

st.sidebar.divider()

# Carregar opcoes para os filtros
conn = sqlite3.connect("gestao_entregas.db")
try:
    meses_opcoes = pd.read_sql("SELECT DISTINCT mes_referencia FROM entregas ORDER BY mes_referencia DESC", conn)["mes_referencia"].tolist()
    colabs_opcoes = pd.read_sql("SELECT DISTINCT colaborador FROM entregas ORDER BY colaborador ASC", conn)["colaborador"].tolist()
except:
    meses_opcoes, colabs_opcoes = [], []
conn.close()

with st.sidebar.form("filtros"):
    st.markdown("**Filtros de Pesquisa**")
    sel_meses = st.multiselect("Meses", options=meses_opcoes)
    sel_deps = st.multiselect("Departamentos", options=["Fiscal", "Pessoal (DP)"], default=["Fiscal", "Pessoal (DP)"])
    sel_colabs = st.multiselect("Colaboradores", options=colabs_opcoes)
    btn_filtrar = st.form_submit_button("Aplicar Filtros")

# ---------------- LOGICA DE DADOS ----------------
conn = sqlite3.connect("gestao_entregas.db")
if not sel_meses:
    query = "SELECT * FROM entregas"
    df = pd.read_sql(query, conn)
else:
    placeholders = ', '.join(['?'] * len(sel_meses))
    query = f"SELECT * FROM entregas WHERE mes_referencia IN ({placeholders})"
    df = pd.read_sql(query, conn, params=sel_meses)
conn.close()

if not df.empty:
    if sel_deps: df = df[df["departamento"].isin(sel_deps)]
    if sel_colabs: df = df[df["colaborador"].isin(sel_colabs)]

# ---------------- CONTEUDO PRINCIPAL ----------------
st.title("Entregas Mensais - Acessórias")
st.markdown("Esse gráficos correspondem as entregas mensais de obrigações do sistema Acessórias realizadas pelos colaboradores. Considerando o primeiro e último dia de cada mês.")

if perfil == "Administrador" and st.session_state.autenticado:
    with st.expander("Painel de Controle Administrativo", expanded=False):
        col_adm1, col_adm2 = st.columns(2)
        with col_adm1:
            st.markdown("**Upload de Novos Dados**")
            arquivo = st.file_uploader("Carregar planilha", type=["xlsx", "csv"])
            sub = st.checkbox("Substituir dados existentes")
            if st.button("Processar Arquivo") and arquivo:
                df_up = pd.read_excel(arquivo) if arquivo.name.endswith("xlsx") else pd.read_csv(arquivo)
                salvar_no_banco(df_up, sub, mes_ref=None)
                st.rerun()
        
        with col_adm2:
            st.markdown("**Gerenciar Periodos**")
            mes_del = st.selectbox("Selecionar mes para exclusao", options=meses_opcoes, key="del_mes")
            if st.button("Remover Registros"):
                limpar_banco_mes(mes_del)
                st.rerun()

st.divider()

if df.empty:
    st.info("Nao ha dados para exibir com os filtros selecionados.")
else:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total de Tarefas", len(df))
    m2.metric("No Prazo", len(df[df["status"]=="No prazo"]))
    m3.metric("Atrasadas", len(df[df["status"]=="Atrasada"]))
    m4.metric("Justificadas", len(df[df["status"]=="Justificada"]))

    col_g1, col_g2 = st.columns([1, 1.2])
    
    with col_g1:
        st.markdown("### Dados Gerais")
        status_counts = df["status"].value_counts().reset_index()
        status_counts.columns = ["status","total"]
        fig_pie = px.pie(status_counts, names="status", values="total", hole=0.6,
                         color="status",
                         color_discrete_map={"No prazo":"#10B981","Atrasada":"#EF4444","Justificada":"#F59E0B"})
        fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0), legend=dict(orientation="h", y=-0.1))
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_g2:
        st.markdown("### Top 10 Obrigacões")
        top = df["tarefa"].value_counts().head(10).reset_index()
        top.columns = ["tarefa","total"]
        fig_bar = px.bar(top, x="total", y="tarefa", orientation="h",
                         color_discrete_sequence=["#0C50BD"])
        fig_bar.update_layout(margin=dict(t=0, b=0, l=0, r=0), yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("### Desempenho por Colaborador")
    resumo = df.groupby(["colaborador","status"]).size().unstack(fill_value=0)
    
    for s in ["No prazo", "Atrasada", "Justificada"]:
        if s not in resumo.columns: 
            resumo[s] = 0
    
    resumo["Total"] = resumo.sum(axis=1)
    
    st.dataframe(
        resumo.sort_values("Total", ascending=False), 
        use_container_width=True
    )