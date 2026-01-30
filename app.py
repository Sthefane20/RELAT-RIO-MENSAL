import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
from datetime import datetime
import hashlib
import os
import unicodedata
import plotly.graph_objects as go

# --- CONFIGURAÇÃO DA PÁGINA ---

st.set_page_config(page_title="Gestão de Entregas", layout="wide")

# --- CONSTANTES DE PERFIS ---

COLABORADOR_IGNORADO = "Tecnologia e Inovação - Contas Contabilidade"
PERFIL_FISCAL = "Departamento Fiscal"
PERFIL_PESSOAL = "Departamento Pessoal"
PERFIL_RH = "RH"
PERFIL_ADMIN = "Administrador"
DISPLAY_NOME_PERFIL = {

    PERFIL_FISCAL: "Fiscal",
    PERFIL_PESSOAL: "Pessoal",
    PERFIL_RH: "Recursos Humanos",
    PERFIL_ADMIN: "Administrador",
}
# palavras-chave que definem fiscal e pessoal

FISCAL_DEPARTAMENTOS = {

    "FISCAL",
    "SETOR FISCAL - REGULARIZACAO",
    "FISCAL-CONTABIL",
    "FISCAL - CONTABIL",
    "FISCAL - REGULARIZACAO"

}

PESSOAL_TERMS = [

    "PESSOAL",
    "ADMISSAO",
    "FERIAS",
    "FOLHA",
    "FOLHA COMPLEMENTAR",
    "RECALCULO DP",
    "REGULARIZACAO - DP",
    "RESCISAO",
    "ANALITICO DA RESCISAO",
    "GFD RESCISORIA",
    "SOLICITACAO DE AVISO",
    "RESCISAO DE ESTAGIARIO",
    "SIMULACAO DE RESCISAO",

]
# --- FUNÇÕES DE NORMALIZAÇÃO (RESOLVE O KEYERROR) ---

def normalizar_texto(texto):

    """Remove acentos, espaços extras e converte para maiúsculas."""

    if not isinstance(texto, str):

        return str(texto)

    nksel = unicodedata.normalize('NFKD', texto)

    sem_acentos = "".join([c for c in nksel if not unicodedata.combining(c)])

    return sem_acentos.strip().upper()



def classificar_departamento(tarefa, departamento_manual=None):

    if departamento_manual:

        valor_dep = normalizar_texto(departamento_manual)

        if valor_dep in FISCAL_DEPARTAMENTOS or "FISCAL" in valor_dep:

            return "Fiscal"

        return "Pessoal (DP)"



    dp = PESSOAL_TERMS

    t = normalizar_texto(tarefa)

    if any(x in t for x in dp):

        return "Pessoal (DP)"

    return "Fiscal"



def normalizar_status(valor):

    v = normalizar_texto(valor)

    if "ATRAS" in v: return "Atrasada"

    if "JUST" in v: return "Justificada"

    return "No prazo"



# --- UTILITÁRIOS DE SENHA ---

def hash_password(senha):

    """Gera o hash SHA256 de uma senha."""

    return hashlib.sha256(senha.encode("utf-8")).hexdigest()



def init_password_table():

    conn = sqlite3.connect("gestao_entregas.db")

    conn.execute("""

        CREATE TABLE IF NOT EXISTS perfis (

            perfil TEXT PRIMARY KEY,

            senha_hash TEXT NOT NULL

        )

    """)

    conn.commit()

    conn.close()



def obter_hash_senha(perfil):

    conn = sqlite3.connect("gestao_entregas.db")

    cursor = conn.execute("SELECT senha_hash FROM perfis WHERE perfil = ?", (perfil,))

    linha = cursor.fetchone()

    conn.close()

    return linha[0] if linha else None



def salvar_senha(perfil, senha):

    if not senha:

        return False

    conn = sqlite3.connect("gestao_entregas.db")

    conn.execute(

        "INSERT OR REPLACE INTO perfis (perfil, senha_hash) VALUES (?, ?)",

        (perfil, hash_password(senha.strip()))

    )

    conn.commit()

    conn.close()

    return True



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

init_password_table()



# --- PROCESSAMENTO DE ARQUIVO ---

def salvar_no_banco(df, substituir=False):

    colunas_originais = {c: normalizar_texto(c) for c in df.columns}

    df = df.rename(columns=colunas_originais)

    

    COL_DATA = "DATA DA ENTREGA"

    COL_RESP = "RESPONSAVEL ENTREGA"

    COL_TAREFA = "OBRIGACAO / TAREFA"

    COL_STATUS = "STATUS"



    cols_necessarias = [COL_DATA, COL_RESP, COL_TAREFA, COL_STATUS]

    missing = [c for c in cols_necessarias if c not in df.columns]

    

    if missing:

        st.error(f"Erro: Colunas não encontradas. O arquivo precisa ter as colunas: {', '.join(cols_necessarias)}")

        st.write("Colunas detectadas (normalizadas):", list(df.columns))

        return



    df[COL_DATA] = pd.to_datetime(df[COL_DATA], dayfirst=True, errors="coerce")

    df = df.dropna(subset=[COL_DATA])

    COL_DEPARTAMENTO = "DEPARTAMENTO"



    if COL_DEPARTAMENTO in df.columns:

        departamentos_raw = df[COL_DEPARTAMENTO].fillna("").astype(str)

    else:

        departamentos_raw = pd.Series([""] * len(df), index=df.index)

    

    if df.empty:

        st.warning("Nenhuma data válida encontrada na coluna 'DATA DA ENTREGA'.")

        return



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

    df_final["departamento"] = [

        classificar_departamento(tarefa, dep)

        for tarefa, dep in zip(df_final["tarefa"], departamentos_raw)

    ]

    df_final["data_upload"] = datetime.now()



    conn = sqlite3.connect("gestao_entregas.db")

    df_final.to_sql("entregas", conn, if_exists="append", index=False)

    conn.close()

    st.success(f"Sucesso! {len(df_final)} registros processados.")



# --- CSS ESTILO "CLEAN CORPORATE" ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Montserrat:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    .stApp { background-color: #F3F3F3 !important; }

    /* 1. SIDEBAR */
    section[data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: none !important;
    }

    /* 2. INPUTS (FILTROS DA SIDEBAR) - TEXTO PRETO FORÇADO */
    .stMultiSelect div[data-baseweb="select"] > div,
    .stSelectbox div[data-baseweb="select"] > div {
        background-color: #E0E0E0 !important;
        border: none !important;
        border-radius: 8px !important;
    }
    
    /* Hover no input */
    .stMultiSelect div[data-baseweb="select"] > div:hover,
    .stSelectbox div[data-baseweb="select"] > div:hover {
        background-color: #D6D6D6 !important;
    }

    /* FORÇA BRUTA: Cor do texto (Placeholder e Valor Selecionado) */
    div[data-baseweb="select"] div, 
    div[data-baseweb="select"] span,
    div[data-baseweb="select"] {
        color: #000000 !important;             /* Cor padrão */
        -webkit-text-fill-color: #000000 !important; /* Força para Webkit/Chrome */
        font-weight: 600 !important;           /* Negrito para destacar */
        fill: #000000 !important;              /* Para ícones SVG */
    }
    
    /* Garante que a setinha também fique preta */
    div[data-baseweb="select"] svg { 
        fill: #000000 !important;
        color: #000000 !important;
    }
    
    /* Estilo das Tags (itens selecionados no MultiSelect) */
    span[data-baseweb="tag"] {
        background-color: #FFFFFF !important;
        border-radius: 4px !important;
    }
    span[data-baseweb="tag"] span {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
    }

    /* Esconde os labels originais (Meses, Deptos...) se quiser o visual limpo */
    .stMultiSelect label, .stSelectbox label { display: none; }

    /* 3. BOTÕES */
    button[kind="primaryFormSubmit"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        border: 1px solid #CCCCCC !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        box-shadow: none !important;
        padding-top: 0.5rem; padding-bottom: 0.5rem;
    }
    button[kind="primaryFormSubmit"]:hover {
        background-color: #F5F5F5 !important;
        border-color: #BBBBBB !important;
    }
    div[data-testid="stSidebarUserContent"] { padding-top: 20px; }

    /* 4. FORMULÁRIO */
    [data-testid="stForm"] { border: none !important; box-shadow: none !important; padding: 0 !important; }

    /* 7. EXPANDER (Painel de Controle) */
    div[data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 8px !important;
    }
    div[data-testid="stExpander"] > details > summary {
        background-color: #FFFFFF !important;
        border-radius: 8px !important;
        padding-left: 10px !important;
        color: #111827 !important;
    }
    div[data-testid="stExpander"] > details > summary p {
        font-family: 'Montserrat', sans-serif !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        color: #111827 !important;
        margin: 0 !important;
    }
    div[data-testid="stExpander"] > details > summary svg {
        fill: #111827 !important;
        color: #111827 !important;
        margin-right: 10px;
    }
    div[data-testid="stExpander"] > details > div { background-color: #FFFFFF !important; color: #111827 !important; }

    /* 8. CARDS (MÉTRICAS) - COMPACTO E FONTE 48px */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        padding: 10px 15px !important;
        border-radius: 16px !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
        min-height: 110px !important;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-family: 'Montserrat', sans-serif !important;
        width: 100%;
        white-space: nowrap !important;
    }
    div[data-testid="stMetric"] label {
        font-weight: 500 !important;
        color: #6B7280 !important;
        font-size: 13px !important;
        margin-bottom: -8px !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-weight: 700 !important;
        color: #111827 !important;
        font-size: 40px !important;
        line-height: 1.1 !important;
    }

    /* 9. ESTILO DO CARD (CONTAINER COM BORDA) - FINAL E FORÇADO */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 16px !important;
        /* Sombra exata dos cards de métrica (item 8) */
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
        padding: 20px !important;
    }
    /* FORÇA FUNDO BRANCO EM CONTAINERS COM BORDA (st.container(border=True)) */
    div[data-testid="stContainer"] {
    background-color: #FFFFFF !important;
    border-radius: 16px !important;
}
    header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)
\


# --- SIDEBAR E FILTROS ---

if "autenticado_admin" not in st.session_state:
    st.session_state.autenticado_admin = False
if "autenticado_pessoal" not in st.session_state:
    st.session_state.autenticado_pessoal = False
if "autenticado_fiscal" not in st.session_state:
    st.session_state.autenticado_fiscal = False
if "autenticado_rh" not in st.session_state:
    st.session_state.autenticado_rh = False

if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)

if "perfil_em_uso" not in st.session_state:
    st.session_state.perfil_em_uso = None

admin_hash = obter_hash_senha(PERFIL_ADMIN)
pessoal_hash = obter_hash_senha(PERFIL_PESSOAL)
fiscal_hash = obter_hash_senha(PERFIL_FISCAL)
rh_hash = obter_hash_senha(PERFIL_RH)

if st.session_state.perfil_em_uso is None:
    st.sidebar.markdown("### Perfil de Acesso")
    st.sidebar.caption("Selecione o perfil e informe a senha para liberar o acesso.")
    perfil = st.sidebar.selectbox(
        "Perfil de Acesso",
        [PERFIL_FISCAL, PERFIL_PESSOAL, PERFIL_RH, PERFIL_ADMIN],
        key="perfil_select"
    )

    if perfil == PERFIL_ADMIN:
        if admin_hash is None:
            st.sidebar.warning("Defina uma nova senha do Administrador antes de continuar.")
            nova_senha_admin = st.sidebar.text_input("Nova senha (Administrador)", type="password", key="nova_senha_admin")
            if st.sidebar.button("Salvar senha do Administrador", key="btn_salvar_admin"):
                if salvar_senha(PERFIL_ADMIN, nova_senha_admin):
                    st.sidebar.success("Senha gravada com sucesso. Faça login abaixo.")
                    st.rerun()
                else:
                    st.sidebar.error("Informe uma senha válida.")
            st.stop()

        if not st.session_state.autenticado_admin:
            senha = st.sidebar.text_input("Senha", type="password", key="login_admin")
            if st.sidebar.button("Entrar", key="btn_login_admin"):
                if hash_password(senha or "") == admin_hash:
                    st.session_state.autenticado_admin = True
                    st.session_state.perfil_em_uso = PERFIL_ADMIN
                    st.rerun()
                else:
                    st.sidebar.error("Senha incorreta")
    elif perfil == PERFIL_RH:
        if rh_hash is None:
            st.sidebar.warning("Senha do perfil RH ainda não configurada. Configure-a no painel Administrativo.")
            st.stop()
        st.sidebar.info("Esse perfil visualiza os dados completos de Fiscal e Pessoal.")
        if not st.session_state.autenticado_rh:
            senha_rh = st.sidebar.text_input("Senha RH", type="password", key="login_rh")
            if st.sidebar.button("Entrar", key="btn_login_rh"):
                if hash_password(senha_rh or "") == rh_hash:
                    st.session_state.autenticado_rh = True
                    st.session_state.perfil_em_uso = PERFIL_RH
                    st.rerun()
                else:
                    st.sidebar.error("Senha incorreta")
    elif perfil == PERFIL_PESSOAL:
        if pessoal_hash is None:
            st.sidebar.warning("Senha do perfil Pessoal ainda não configurada. Configure-a no painel Administrativo.")
            st.stop()
        st.sidebar.info("Esse perfil acessa apenas os dados de Pessoal (DP).")
        if not st.session_state.autenticado_pessoal:
            senha_pessoal = st.sidebar.text_input("Senha Pessoal", type="password", key="login_pessoal")
            if st.sidebar.button("Entrar", key="btn_login_pessoal"):
                if hash_password(senha_pessoal or "") == pessoal_hash:
                    st.session_state.autenticado_pessoal = True
                    st.session_state.perfil_em_uso = PERFIL_PESSOAL
                    st.rerun()
                else:
                    st.sidebar.error("Senha incorreta")
    elif perfil == PERFIL_FISCAL:
        if fiscal_hash is None:
            st.sidebar.warning("Senha do perfil Fiscal ainda não configurada. Configure-a no painel Administrativo.")
            st.stop()
        st.sidebar.info("Esse perfil acessa apenas os dados de Fiscal.")
        if not st.session_state.autenticado_fiscal:
            senha_fiscal = st.sidebar.text_input("Senha Fiscal", type="password", key="login_fiscal")
            if st.sidebar.button("Entrar", key="btn_login_fiscal"):
                if hash_password(senha_fiscal or "") == fiscal_hash:
                    st.session_state.autenticado_fiscal = True
                    st.session_state.perfil_em_uso = PERFIL_FISCAL
                    st.rerun()
                else:
                    st.sidebar.error("Senha incorreta")
    st.stop()
else:
    perfil = st.session_state.perfil_em_uso

dashboard_liberado = bool(st.session_state.perfil_em_uso)

if not dashboard_liberado:
    st.stop()

departamento_opcoes = ["Fiscal", "Pessoal (DP)"]
if perfil == PERFIL_FISCAL:
    departamento_opcoes = ["Fiscal"]
elif perfil == PERFIL_PESSOAL:
    departamento_opcoes = ["Pessoal (DP)"]

conn = sqlite3.connect("gestao_entregas.db")
try:
    meses_opcoes = pd.read_sql("SELECT DISTINCT mes_referencia FROM entregas ORDER BY mes_referencia DESC", conn)["mes_referencia"].tolist()
    colabs_opcoes = pd.read_sql(
    "SELECT DISTINCT colaborador FROM entregas ORDER BY colaborador ASC",
    conn
)["colaborador"].tolist()

# Remove colaborador ignorado do filtro
    if COLABORADOR_IGNORADO in colabs_opcoes:
        colabs_opcoes.remove(COLABORADOR_IGNORADO)
    
except:
    meses_opcoes, colabs_opcoes = [], []
conn.close()

st.sidebar.markdown("<div style='height: 50px'></div>", unsafe_allow_html=True)

# --- FILTROS ---
with st.sidebar.form("filtros"):
    sel_meses = st.multiselect(
        "", 
        options=meses_opcoes,
        placeholder="Meses"
    )
    
    sel_deps = st.multiselect(
        "", 
        options=departamento_opcoes, 
        default=departamento_opcoes,
        placeholder="Departamentos"
    )
    
    sel_colabs = st.multiselect(
        "", 
        options=colabs_opcoes,
        placeholder="Colaboradores"
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    btn_filtrar = st.form_submit_button("Aplicar Filtros")

# --- LÓGICA DE CARREGAMENTO DE DADOS ---
conn = sqlite3.connect("gestao_entregas.db")
if not sel_meses:
    df = pd.read_sql("SELECT * FROM entregas", conn)
else:
    placeholders = ', '.join(['?'] * len(sel_meses))
    query = f"SELECT * FROM entregas WHERE mes_referencia IN ({placeholders})"
    df = pd.read_sql(query, conn, params=sel_meses)
conn.close()

# --- FILTRO GLOBAL ---
if not df.empty:
    df = df[df["colaborador"] != COLABORADOR_IGNORADO]

if not df.empty:
    if sel_deps: df = df[df["departamento"].isin(sel_deps)]
    if sel_colabs: df = df[df["colaborador"].isin(sel_colabs)]
    if perfil == PERFIL_FISCAL:
        df = df[df["departamento"] == "Fiscal"]
    elif perfil == PERFIL_PESSOAL:
        df = df[df["departamento"] == "Pessoal (DP)"]

# --- CABEÇALHO ---
if st.session_state.perfil_em_uso:
    nome_perfil = DISPLAY_NOME_PERFIL.get(st.session_state.perfil_em_uso, "Usuário")
    c_espaco, c_nome, c_sair = st.columns([7, 2, 1])
    with c_nome:
        st.markdown(
            f"<div style='text-align:right; font-weight:600; color:#333; padding-top: 10px;'>{nome_perfil}</div>", 
            unsafe_allow_html=True
        )
    with c_sair:
        if st.button("Sair", key="btn_top_logout"):
            st.session_state.autenticado_admin = False
            st.session_state.autenticado_rh = False
            st.session_state.autenticado_fiscal = False
            st.session_state.autenticado_pessoal = False
            st.session_state.perfil_em_uso = None
            st.rerun()

# --- DASHBOARD PRINCIPAL ---
st.markdown("""
<div style="
    border-left: 6px solid #111827; 
    padding-left: 15px; 
    margin-bottom: 20px;
    font-family: 'Montserrat', sans-serif;
">
    <p style="
        font-size: 32px; 
        font-weight: 700; 
        color: #111827; 
        margin: 0; 
        line-height: 1.1;
    ">Entregas Mensais</p>
    <p style="
        font-size: 18px; 
        font-weight: 400; 
        color: #4B5563; 
        margin: 0;
    ">Acessórias</p>
</div>
""", unsafe_allow_html=True)

if perfil == PERFIL_ADMIN and st.session_state.autenticado_admin:
    with st.expander("Painel de Controle", expanded=False):
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
            st.markdown("**Gerenciar Senhas dos Perfis**")
            perfil_para_atualizar = st.selectbox(
                "Escolha um perfil",
                options=[PERFIL_PESSOAL, PERFIL_FISCAL, PERFIL_RH, PERFIL_ADMIN],
                key="perfil_select_atualizar"
            )
            nova_senha_perfil = st.text_input("Nova senha", type="password", key="senha_perfil_atualizar")
            if st.button("Atualizar senha selecionada", key="btn_atualizar_perfil"):
                if salvar_senha(perfil_para_atualizar, nova_senha_perfil):
                    st.success(f"Senha do {perfil_para_atualizar} atualizada.")
                else:
                    st.error("Informe uma senha válida.")

if df.empty:
    st.info("Não há dados para exibir. Por favor, faça o upload de uma planilha no modo Administrador.")
else:
    # --- 1. CARDS DE MÉTRICAS (4 na mesma linha) ---
    c1, c2, c3, c4 = st.columns(4, gap="medium")
    
    with c1:
        st.metric("Total", len(df))
    with c2:
        st.metric("No Prazo", len(df[df["status"]=="No prazo"]))
    with c3:
        st.metric("Atrasadas", len(df[df["status"]=="Atrasada"]))
    with c4:
        st.metric("Justificadas", len(df[df["status"]=="Justificada"]))

    st.markdown("<br>", unsafe_allow_html=True)

    # --- 2. GRÁFICOS (Pizza e Barras) ---
    col_g1, col_g2 = st.columns([1, 1.2]) 

    with col_g1:
        # Card Status (Pizza) - ESTE É O CARD QUE DEVE FICAR BRANCO
        with st.container(border=True):
            st.markdown("<h5 style='font-family: Montserrat; font-weight: 700; color: #575555; margin-top:0; margin-bottom:10px;'>Status de Entregas</h5>", unsafe_allow_html=True)
            
            status_counts = df["status"].value_counts().reset_index()
            status_counts.columns = ["status","total"]
            
            fig_pie = px.pie(
                status_counts,
                names="status",
                values="total",
                hole=0.6,
                color="status",
                color_discrete_map={
                    "No prazo":"#80C4A8",
                    "Atrasada":"#03155A",
                    "Justificada":"#E9B84E"
                }
            )
            # Fundo transparente para o gráfico, para mostrar o branco do card
            fig_pie.update_layout(
                margin=dict(t=0, b=0, l=0, r=0), 
                legend=dict(orientation="h", y=-0.1),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    with col_g2:
        with st.container(border=True):
            st.markdown("<h5 style='font-family: Montserrat; font-weight: 700; color: #575555; margin-top:0; margin-bottom:10px;'>Top 10 Obrigações</h5>", unsafe_allow_html=True)
            
            top = df["tarefa"].value_counts().head(10).reset_index()
            top.columns = ["tarefa","total"]
            
            fig_bar = px.bar(
                top,
                x="total",
                y="tarefa",
                orientation="h",
                color="total",
                color_continuous_scale=["#03155A", "#0455A2"] 
            )
            fig_bar.update_traces(marker_cornerradius=20)
            fig_bar.update_layout(
                margin=dict(t=0, b=0, l=0, r=0), 
                yaxis={'categoryorder':'total ascending'},
                coloraxis_showscale=False,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    # --- 3. TABELA (Desempenho) ---
    with st.container(border=True):
        
        # Título dentro do card (ajustei a margem para ficar bonito)
        st.markdown("<h5 style='font-family: Montserrat; font-weight: 700; color: #575555; margin-top:0; margin-bottom:15px;'>Desempenho por Colaborador</h5>", unsafe_allow_html=True)
        
        # Lógica da tabela
        resumo = df.groupby(["colaborador","status"]).size().unstack(fill_value=0)
        for s in ["No prazo", "Atrasada", "Justificada"]:
            if s not in resumo.columns:
                resumo[s] = 0
                
        resumo["Total"] = resumo.sum(axis=1)
        
        # Exibe a tabela
        st.dataframe(resumo.sort_values("Total", ascending=False), use_container_width=True)