import streamlit as st
import pandas as pd
import gspread # Biblioteca principal para interagir com o Google Sheets
import math
from oauth2client.service_account import ServiceAccountCredentials # Para autenticação

# --- Configuração da Página ---
st.set_page_config(
    page_title="Catálogo de Produtos | Doce&Bella",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Função de Cache para Carregar os Dados ---
@st.cache_data(ttl=600)
def load_data():
    try:
        # 1. AUTENTICAÇÃO E PREPARAÇÃO DA CHAVE SECRETA
        # Recriamos a estrutura do JSON a partir dos segredos guardados no secrets.toml
        creds_json = {
            "type": st.secrets["gsheets"]["creds"]["type"],
            "project_id": st.secrets["gsheets"]["creds"]["project_id"],
            "private_key_id": st.secrets["gsheets"]["creds"]["private_key_id"],
            "private_key": st.secrets["gsheets"]["creds"]["private_key"],
            "client_email": st.secrets["gsheets"]["creds"]["client_email"],
            "client_id": st.secrets["gsheets"]["creds"]["client_id"],
            "auth_uri": st.secrets["gsheets"]["creds"]["auth_uri"],
            "token_uri": st.secrets["gsheets"]["creds"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gsheets"]["creds"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gsheets"]["creds"]["client_x509_cert_url"],
        }
        
        # 2. CONEXÃO COM O GOOGLE
        # O escopo (scope) define o que o aplicativo pode fazer (acessar planilhas)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        # Usamos from_service_account_info que é a função correta para dicionários
        # E passamos as credenciais (creds_json) e o escopo (scope)
        creds = ServiceAccountCredentials.from_service_account_info(creds_json, scope)
        client = gspread.authorize(creds)
        
        # 3. ABRIR A PLANILHA E LER OS DADOS
        spreadsheet = client.open_by_url(st.secrets["gsheets"]["sheets_url"])
        worksheet = spreadsheet.worksheet("Sheet1") # O nome da sua primeira aba de produtos
        
        # 4. CONVERTER PARA DATAFRAME
        df = pd.DataFrame(worksheet.get_all_records())
                       
        # (Lógica de limpeza e filtro permanece a mesma)
        df = df[df['DISPONIVEL'].astype(str).str.lower() == 'sim'].copy()
        df['PRECO'] = pd.to_numeric(df['PRECO'], errors='coerce')
        df['ID'] = df['ID'].astype(str) 
        
        return df
    except Exception as e:
        # Mensagem de erro mais clara em caso de falha de autenticação/conexão
        st.error(f"Erro Crítico de Conexão. ❌ Verifique se o e-mail da Service Account está como 'Editor' na Planilha e se o secrets.toml está correto. Detalhe: {e}")
        return pd.DataFrame()

# Carrega os dados
df_produtos = load_data()

# --- Exibir Mensagem de Erro se o Catálogo estiver vazio ---
if df_produtos.empty:
    st.error("⚠️ O catálogo está vazio ou houve um erro de conexão. Por favor, verifique a planilha e o painel Admin.")
else:
    # --- Continuação no Próximo Passo: Montar o Layout ---
    st.title("💖 Nossas Novidades")

    # Layout em colunas (3 produtos por linha)
    cols = st.columns(3)

    # Itera sobre os produtos e exibe no layout
    for index, row in df_produtos.iterrows():
        col = cols[index % 3] # Distribui o produto na coluna 0, 1 ou 2
        
        with col:
            st.image(row['LINKIMAGEM'], use_column_width=True)
            st.markdown(f"**{row['NOME']}**")
            st.markdown(f"R$ {row['PRECO']:.2f}")
            
            # Placeholder para a funcionalidade de adicionar/detalhes
            col.button(f"Ver Detalhes/Comprar", key=f"btn_{row['ID']}")
            st.divider()


    st.success(f"Catálogo Carregado com Sucesso! Total de {len(df_produtos)} produtos disponíveis.")



