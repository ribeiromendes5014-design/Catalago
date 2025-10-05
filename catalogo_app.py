import streamlit as st
import pandas as pd
import math
# Precisamos importar a biblioteca gspread-streamlit para a conexão
from gspread_streamlit import get_worksheet 

# ... (restante do código: st.set_page_config, etc.) ...

# --- Função de Cache para Carregar os Dados ---
# ATENÇÃO: É preciso instalar a biblioteca gspread-streamlit no ambiente (requirements.txt)
@st.cache_data(ttl=600)
def load_data():
    try:
        # AQUI USAMOS O GET_WORKSHEET DA BIBLIOTECA gspread-streamlit
        # Ele lê as credenciais do seu secrets.toml automaticamente!
        worksheet = get_worksheet(
            spreadsheet_title=None, # Título não é necessário se usar a URL
            # A URL da planilha vem do seu secrets.toml
            spreadsheet_url=st.secrets["gsheets"]["sheets_url"],
            worksheet_name="Sheet1" # O nome da sua primeira aba
        )
        
        # Converte a planilha lida para um DataFrame do Pandas
        df = pd.DataFrame(worksheet.get_all_records())
                       
        # Filtra apenas os produtos que estão 'Disponivel' como 'Sim'
        df = df[df['DISPONIVEL'].astype(str).str.lower() == 'sim'].copy()
        
        # Converte o Preço para um formato numérico para cálculos
        df['PRECO'] = pd.to_numeric(df['PRECO'], errors='coerce')
        
        # Garante que as colunas críticas existam, caso a planilha esteja vazia
        if df.empty or 'ID' not in df.columns:
             st.warning("A planilha foi carregada, mas está vazia ou faltando colunas!")
             return pd.DataFrame()
             
        df['ID'] = df['ID'].astype(str)
        return df
    except Exception as e:
        # st.error(f"Erro ao carregar dados da planilha. Detalhe: {e}")
        return pd.DataFrame() # Retorna um DataFrame vazio em caso de erro

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

