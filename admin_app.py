import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos"
SHEET_NAME_PEDIDOS = "PEDIDOS"

# --- Conexão com Google Sheets (mesma função do app do catálogo) ---
@st.cache_resource(ttl=None)
def get_gspread_client():
    """Cria um cliente GSpread autenticado usando o service account do st.secrets."""
    try:
        gcp_sa_credentials = {
            "type": st.secrets["gsheets"]["type"],
            "project_id": st.secrets["gsheets"]["project_id"],
            "private_key_id": st.secrets["gsheets"]["private_key_id"],
            "private_key": st.secrets["gsheets"]["private_key"],
            "client_email": st.secrets["gsheets"]["client_email"],
            "client_id": st.secrets["gsheets"]["client_id"],
            "auth_uri": st.secrets["gsheets"]["auth_uri"],
            "token_uri": st.secrets["gsheets"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gsheets"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gsheets"]["client_x509_cert_url"]
        }
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(gcp_sa_credentials, scope)
        client = gspread.authorize(creds)
        sh = client.open_by_url(st.secrets["gsheets"]["sheet_url"])
        return sh
    except Exception as e:
        st.error(f"Erro na autenticação com o Google Sheets. Verifique seu `secrets.toml`. Detalhe: {e}")
        st.stop()

@st.cache_data(ttl=60) # Cache de 1 minuto para dados do admin
def carregar_dados(sheet_name):
    """Carrega todos os dados de uma aba específica."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records() # get_all_records lê os dados como dicionários
        if not data:
            return pd.DataFrame()
        return pd.DataFrame(data)
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Erro: A aba '{sheet_name}' não foi encontrada na sua planilha.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar os dados: {e}")
        return pd.DataFrame()

# --- Layout do Aplicativo Admin ---
st.set_page_config(
    page_title="Admin Doce&Bella",
    layout="wide"
)

st.title("⭐ Painel de Administração | Doce&Bella")
st.markdown("Use este painel para gerenciar os pedidos e o catálogo de produtos.")

# --- Abas para Organização ---
tab_pedidos, tab_produtos = st.tabs(["Relatório de Pedidos", "Gerenciar Produtos"])

with tab_pedidos:
    st.header("📋 Pedidos Recebidos")
    df_pedidos = carregar_dados(SHEET_NAME_PEDIDOS)
    if df_pedidos.empty:
        st.info("Nenhum pedido foi encontrado na planilha.")
    else:
        st.dataframe(df_pedidos, use_container_width=True)

with tab_produtos:
    st.header("🛍️ Gerenciamento de Produtos")
    st.write("Aqui você poderá adicionar, editar e excluir produtos do seu catálogo.")
    st.markdown("---")

    st.subheader("Catálogo Atual")
    df_produtos = carregar_dados(SHEET_NAME_CATALOGO)

    if df_produtos.empty:
        st.warning("Nenhum produto encontrado no catálogo.")
    else:
        st.dataframe(df_produtos, use_container_width=True)