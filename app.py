import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
from datetime import datetime
import os
import unicodedata

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão de Entregas", layout="wide")

# --- FUNÇÕES DE NORMALIZAÇÃO (RESOLVE O KEYERROR) ---
def normalizar_texto(texto):
    """Remove acentos, espaços extras e converte para maiúsculas."""
    if not isinstance(texto, str):
        return str(texto)
    # Remove acentos
    nksel = unicodedata.normalize('NFKD', texto)
    sem_acentos = "".join([c for c in nksel if not unicodedata.combining(c)])
    # Limpa espaços e coloca em maiúsculo
    return sem_acentos.strip().upper()

def classificar_departamento(tarefa):
    dp = ["ADMISSAO", "FERIAS", "FOLHA", "RECALCULO", "RESCISAO"]
    t = normalizar_texto(tarefa)
    if any(x in t for x in dp): 
        return "Pessoal (DP)"
    return "Fiscal"

def normalizar_status(valor):
    v = normalizar_texto(valor)
    if "ATRAS" in v: return "Atrasada"
    if "JUST" in v: return "Justificada"
    return "No prazo"

# --- BANCO DE DADOS ---
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
    if not mes: return
    conn = sqlite3.connect("gestao_entregas.db")
    conn.execute("DELETE FROM entregas WHERE mes_referencia = ?", (mes,))
    conn.commit()
    conn.close()
    st.info(f"Dados do mês {mes} removidos com sucesso.")

init_db()

# --- PROCESSAMENTO DE ARQUIVO ---
def salvar_no_banco(df, substituir=False):
    # 1. Normalizar nomes das colunas originais do arquivo
    colunas_originais = {c: normalizar_texto(c) for c in df.columns}
    df = df.rename(columns=colunas_originais)
    
    # 2. Colunas que o sistema espera (após normalização)
    COL_DATA = "DATA DA ENTREGA"
    COL_RESP = "RESPONSAVEL ENTREGA"
    COL_TAREFA = "OBRIGACAO / TAREFA"
    COL_STATUS = "STATUS"

    # 3. Verificação de existência
    cols_necessarias = [COL_DATA, COL_RESP, COL_TAREFA, COL_STATUS]
    faltando = [c for c in cols_necessarias if c not in df.columns]
    
    if faltando:
        st.error(f"Erro: Colunas não encontradas. O arquivo precisa ter as colunas: {', '.join(cols_necessarias)}")
        st.write("Colunas detectadas (normalizadas):", list(df.columns))
        return

    # 4. Tratamento de Datas
    df[COL_DATA] = pd.to_datetime(df[COL_DATA], dayfirst=True, errors="coerce")
    df = df.dropna(subset=[COL_DATA])
    
    if df.empty:
        st.warning("Nenhuma data válida encontrada na coluna 'DATA DA ENTREGA'.")
        return

    # 5. Preparação para o Banco
    df_final = pd.DataFrame()
    df_final["data_entrega"] = df[COL_DATA].dt.strftime("%d/%m/%Y")
    df_final["mes_referencia"] = df[COL_DATA].dt.strftime("%Y-%m")
    
    if substituir:
        meses_para_limpar = df_final["mes_referencia"].unique()
        conn = sqlite3.connect("gestao_entregas.db")
        for m in meses_para_limpar:
            conn.execute("DELETE FROM entregas WHERE mes_referencia = ?", (m,))
        conn.commit()
        conn.close()

    df_final["colaborador"] = df[COL_RESP].fillna("Não informado")
    df_final["tarefa"] = df[COL_TAREFA].fillna("Sem tarefa")
    df_final["status"] = df[COL_STATUS].apply(normalizar_status)
    df_final["departamento"] = df_final["tarefa"].apply(classificar_departamento)
    df_final["data_upload"] = datetime.now()

    conn = sqlite3.connect("gestao_entregas.db")
    df_final.to_sql("entregas", conn, if_exists="append", index=False)
    conn.close()
    st.success(f"Sucesso! {len(df_final)} registros processados.")

# --- CSS INTEGRADO ---
st.markdown("""
<style>
    :root { --bg-page: #F9FAFB; --radius: 12px; }
    .stApp { background-color: #F9FAFB; }
    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #E5E7EB;
        padding: 15px !important;
        border-radius: 12px !important;
    }
    button[kind="primaryFormSubmit"] {
        background-color: #000000 !important;
        color: white !important;
        border-radius: 8px !important;
        width: 100% !important;
    }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR E FILTROS ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)

perfil = st.sidebar.selectbox("Perfil de Acesso", ["Visualização", "Administrador"])

if perfil == "Administrador" and not st.session_state.autenticado:
    senha = st.sidebar.text_input("Senha", type="password")
    if st.sidebar.button("Entrar"):
        if senha == "admin123":
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.sidebar.error("Senha incorreta")
elif perfil == "Administrador" and st.session_state.autenticado:
    if st.sidebar.button("Sair do Modo Admin"):
        st.session_state.autenticado = False
        st.rerun()

st.sidebar.divider()

# Carregar opções para os filtros
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

# --- LÓGICA DE CARREGAMENTO DE DADOS ---
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

# --- DASHBOARD PRINCIPAL ---
st.title("Entregas Mensais - Acessórias")

if perfil == "Administrador" and st.session_state.autenticado:
    with st.expander("Painel de Controle Administrativo", expanded=False):
        col_adm1, col_adm2 = st.columns(2)
        with col_adm1:
            st.markdown("**Upload de Novos Dados**")
            arquivo = st.file_uploader("Carregar planilha (Excel ou CSV)", type=["xlsx", "csv"])
            sub = st.checkbox("Substituir dados dos meses contidos no arquivo")
            if st.button("Processar Arquivo") and arquivo:
                if arquivo.name.endswith("xlsx"):
                    df_up = pd.read_excel(arquivo)
                else:
                    df_up = pd.read_csv(arquivo)
                salvar_no_banco(df_up, sub)
                st.rerun()
        
        with col_adm2:
            st.markdown("**Gerenciar Períodos**")
            mes_del = st.selectbox("Selecionar mês para exclusão", options=meses_opcoes, key="del_mes")
            if st.button("Remover Registros"):
                limpar_banco_mes(mes_del)
                st.rerun()

st.divider()

if df.empty:
    st.info("Não há dados para exibir. Por favor, faça o upload de uma planilha no modo Administrador.")
else:
    # Métricas
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total de Tarefas", len(df))
    m2.metric("No Prazo", len(df[df["status"]=="No prazo"]))
    m3.metric("Atrasadas", len(df[df["status"]=="Atrasada"]))
    m4.metric("Justificadas", len(df[df["status"]=="Justificada"]))

    # Gráficos
    col_g1, col_g2 = st.columns([1, 1.2])
    
    with col_g1:
        st.markdown("### Status das Entregas")
        status_counts = df["status"].value_counts().reset_index()
        status_counts.columns = ["status","total"]
        fig_pie = px.pie(status_counts, names="status", values="total", hole=0.6,
                         color="status",
                         color_discrete_map={"No prazo":"#10B981","Atrasada":"#EF4444","Justificada":"#F59E0B"})
        fig_pie.update_layout(margin=dict(t=30, b=0, l=0, r=0), legend=dict(orientation="h", y=-0.1))
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_g2:
        st.markdown("### Top 10 Obrigações")
        top = df["tarefa"].value_counts().head(10).reset_index()
        top.columns = ["tarefa","total"]
        fig_bar = px.bar(top, x="total", y="tarefa", orientation="h",
                         color_discrete_sequence=["#0C50BD"])
        fig_bar.update_layout(margin=dict(t=30, b=0, l=0, r=0), yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("### Desempenho por Colaborador")
    resumo = df.groupby(["colaborador","status"]).size().unstack(fill_value=0)
    # Garantir que todas as colunas de status existam no dataframe de resumo
    for s in ["No prazo", "Atrasada", "Justificada"]:
        if s not in resumo.columns: 
            resumo[s] = 0
    
    resumo["Total"] = resumo.sum(axis=1)
    st.dataframe(resumo.sort_values("Total", ascending=False), use_container_width=True)