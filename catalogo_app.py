import streamlit as st
import pandas as pd

# --- Configuração da Página ---
st.set_page_config(
    page_title="Catálogo de Produtos | Doce&Bella",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Função de Cache para Carregar os Dados ---
# Esta função garante que os dados da planilha sejam lidos
# rapidamente e apenas quando necessário.
@st.cache_data(ttl=600) # O Streamlit relê a cada 10 minutos (600 segundos)
def load_data():
    try:
        # AQUI O STREAMLIT SE CONECTA USANDO AS CHAVES SECRETAS
        conn = st.connection("gsheets", type=st.secrets["gsheets"]["type"])
        
        # Pega os dados da primeira aba da planilha (sheet=0)
        df = conn.read(spreadsheet=st.secrets["gsheets"]["sheets_url"], 
                       worksheet="Sheet1") 
                       
        # Filtra apenas os produtos que estão 'Disponivel' como 'Sim'
        df = df[df['DISPONIVEL'].str.lower() == 'sim'].copy()
        
        # Converte o Preço para um formato numérico para cálculos
        df['PRECO'] = pd.to_numeric(df['PRECO'], errors='coerce')
        
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados da planilha. Verifique a conexão e as credenciais. Detalhe: {e}")
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