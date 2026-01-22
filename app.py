import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
from datetime import datetime
import os

# Configuração da página
st.set_page_config(page_title="Gestão de Entregas", layout="wide")

# Inicializar estado de login se não existir
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
    st.success(f"🚨 Todos os relatórios do mês {mes} foram apagados!")

init_db()

# ---------------- FUNÇÕES DE APOIO ----------------
def classificar_departamento(tarefa):
    dp = ["admissão","admissao","ferias","férias","folha complementar","recalculo dp","rescisão","rescisao"]
    fiscal = ["fiscal","fiscal-contábil","fiscal-contabil","setor fiscal-regularização"]
    t = str(tarefa).lower().strip()
    if any(x in t for x in dp): return "Pessoal (DP)"
    if any(x in t for x in fiscal): return "Fiscal"
    return "Fiscal"

def normalizar_status(valor):
    v = str(valor).upper()
    if "ATRAS" in v: return "Atrasada"
    if "JUST" in v: return "Justificada"
    return "No prazo"

def salvar_no_banco(df, substituir=False):
    if substituir:
        limpar_banco_mes(mes_selecionado)


    df.columns = [c.strip().upper() for c in df.columns]
    COL_DATA, COL_RESP, COL_TAREFA, COL_STATUS = "DATA DA ENTREGA", "RESPONSÁVEL ENTREGA", "OBRIGAÇÃO / TAREFA", "STATUS"
    
    df[COL_DATA] = pd.to_datetime(df[COL_DATA], format="%d/%m/%Y", errors="coerce")
    df = df.dropna(subset=[COL_DATA])
    df = df[df[COL_RESP].astype(str).str.strip() != "Tecnologia e Inovação - Contas Contabilidade"]

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
    st.success("✅ Importado com sucesso!")

# ---------------- SIDEBAR / LOGIN ----------------
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)

perfil = st.sidebar.selectbox("Perfil", ["Visualização", "Administrador"])

# Lógica de Login para Administrador
if perfil == "Administrador":
    if not st.session_state.autenticado:
        senha = st.sidebar.text_input("Senha", type="password")
        if st.sidebar.button("ENTRAR"):
            if senha == "admin123":
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta")
    else:
        if st.sidebar.button("Sair do Admin"):
            st.session_state.autenticado = False
            st.rerun()
else:
    # Se mudar para Visualização, desloga por segurança (opcional)
    st.session_state.autenticado = False

# ---------------- FORMULÁRIO DE FILTROS ----------------
st.sidebar.divider()
with st.sidebar.form("filtros"):
    st.markdown("### Filtros")
    conn = sqlite3.connect("gestao_entregas.db")
    try:
        meses_opcoes = pd.read_sql("SELECT DISTINCT mes_referencia FROM entregas ORDER BY mes_referencia DESC", conn)["mes_referencia"].tolist()
        colabs_opcoes = pd.read_sql("SELECT DISTINCT colaborador FROM entregas ORDER BY colaborador ASC", conn)["colaborador"].tolist()
    except:
        meses_opcoes, colabs_opcoes = [], []
    conn.close()

    sel_meses = st.multiselect("Meses", options=meses_opcoes, placeholder="Todos (Geral)")
    sel_deps = st.multiselect("Departamentos", options=["Fiscal", "Pessoal (DP)"], default=["Fiscal", "Pessoal (DP)"])
    sel_colabs = st.multiselect("Colaboradores", options=colabs_opcoes, placeholder="Todos")
    
    btn_filtrar = st.form_submit_button("APLICAR FILTROS")

# ---------------- ÁREA ADMIN (Só aparece se autenticado) ----------------
if perfil == "Administrador" and st.session_state.autenticado:
    st.markdown("---")
    st.header("🛠 Painel Administrativo")
    
    col_adm1, col_adm2 = st.columns(2)
    
    with col_adm1:
        st.subheader("📤 Upload de Dados")
        arquivo = st.file_uploader("Subir Planilha", type=["xlsx", "csv"])
        sub = st.checkbox("Substituir tudo ao processar")
        if st.button("🚀 Processar Upload") and arquivo:
            df_up = pd.read_excel(arquivo) if arquivo.name.endswith("xlsx") else pd.read_csv(arquivo)
            salvar_no_banco(df_up, sub)
            st.rerun()
            
    with col_adm2:
        st.subheader("🗑 Gerenciar Relatórios")
        st.markdown("Selecione o mês para apagar os dados:")
        mes_selecionado = st.selectbox("Selecione o Mês", options=meses_opcoes)
        if st.button(f"Apagar Dados de {mes_selecionado}"):
            limpar_banco_mes(mes_selecionado)
            st.rerun()

# ---------------- LÓGICA DE CARREGAMENTO ----------------
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

# ---------------- DASHBOARD ----------------
st.title("📊 Relatório de Entregas")

if df.empty:
    st.info("Nenhum dado disponível. Faça login como Administrador e suba uma planilha.")
else:
    # Cards de Métricas
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de Tarefas", len(df))
    c2.metric("No Prazo ✅", len(df[df["status"]=="No prazo"]))
    c3.metric("Atrasadas 🚨", len(df[df["status"]=="Atrasada"]))
    c4.metric("Justificadas ⚠️", len(df[df["status"]=="Justificada"]))

    st.markdown("---")
    # Gráficos
    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.subheader("Performance Geral")
        status_counts = df["status"].value_counts().reset_index()
        status_counts.columns = ["status","count"]
        fig_pie = px.pie(status_counts, names="status", values="count", hole=0.6,
                         color="status", color_discrete_map={"No prazo":"#000000","Atrasada":"#E5E7EB","Justificada":"#6B7280"})
        fig_pie.update_traces(rotation=90, textinfo="percent")
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_graf2:
        st.subheader("Top 10 Obrigações")
        top = df["tarefa"].value_counts().head(10).reset_index()
        top.columns = ["tarefa","count"]
        fig_bar = px.bar(top, x="count", y="tarefa", orientation="h", color_discrete_sequence=["#000000"])
        st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader("Desempenho por Colaborador")
    resumo = df.groupby(["colaborador","status"]).size().unstack(fill_value=0)
    for s in ["No prazo","Atrasada","Justificada"]:
        if s not in resumo.columns: resumo[s] = 0
    resumo["Total"] = resumo.sum(axis=1)
    st.dataframe(resumo.sort_values("Total", ascending=False), use_container_width=True)
