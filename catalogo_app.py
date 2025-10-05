import streamlit as st
import pandas as pd
import gspread 
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- Configuração da Página ---
st.set_page_config(
    page_title="Admin | Gestão de Catálogo",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Função de Cache para Carregar os Dados ---
# Usamos a mesma lógica de conexão do catalogo_app.py
@st.cache_data(ttl=5) # Cache de apenas 5 segundos para refletir mudanças rapidamente
def load_data():
    try:
        # 1. AUTENTICAÇÃO E PREPARAÇÃO DA CHAVE SECRETA
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
        
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        
        # 2. ABRIR A PLANILHA DE PRODUTOS E DE PEDIDOS
        # Planilha 1: Catálogo de Produtos
        spreadsheet_catalogo = client.open_by_url(st.secrets["gsheets"]["sheets_url"])
        worksheet_catalogo = spreadsheet_catalogo.worksheet("Sheet1") # Lembre-se de corrigir o nome da aba se não for 'Sheet1'
        df_catalogo = pd.DataFrame(worksheet_catalogo.get_all_records())
        
        # Planilha 2: Relatório de Pedidos
        spreadsheet_pedidos = client.open_by_url(st.secrets["gsheets"]["pedidos_url"])
        worksheet_pedidos = spreadsheet_pedidos.worksheet("Pedidos")
        df_pedidos = pd.DataFrame(worksheet_pedidos.get_all_records())
        
        # Converte tipos para uso interno
        if not df_catalogo.empty:
            df_catalogo['ID'] = df_catalogo['ID'].astype(str)
            
        return df_catalogo, worksheet_catalogo, df_pedidos, worksheet_pedidos
        
    except Exception as e:
        st.error(f"Erro ao carregar dados. Verifique secrets.toml, permissões (Editor) e o nome das abas. Detalhe: {e}")
        return pd.DataFrame(), None, pd.DataFrame(), None 

# Carrega os dados
df_produtos, ws_produtos, df_pedidos, ws_pedidos = load_data()

# --- Funções de Gestão (CRUD) ---

def cadastrar_produto(nome, preco, curta, longa, link_imagem, disponivel):
    if ws_produtos is None:
        st.error("Não foi possível conectar à planilha de produtos.")
        return False
    
    # Gera um novo ID simples (pode ser melhorado para IDs únicos)
    novo_id = str(len(df_produtos) + 1).zfill(4) 
    
    nova_linha = [
        novo_id,
        nome,
        preco,
        curta,
        longa,
        link_imagem,
        disponivel
    ]
    
    try:
        ws_produtos.append_row(nova_linha)
        st.success(f"Produto '{nome}' cadastrado com sucesso! ID: {novo_id}")
        st.cache_data.clear() # Limpa o cache para recarregar os dados na próxima vez
        st.experimental_rerun()
    except Exception as e:
        st.error(f"Erro ao salvar produto. Verifique se o formato da linha está correto. Detalhe: {e}")

def deletar_produto(row_index, nome):
    if ws_produtos is None:
        st.error("Não foi possível conectar à planilha de produtos.")
        return False
        
    # O gspread usa índice 1 (linha 2 da planilha, pois a 1 é o cabeçalho)
    # Row index do Pandas (0-based) + 2 = Linha real do Sheets (1-based + cabeçalho)
    sheet_row_index = row_index + 2
    
    try:
        ws_produtos.delete_row(sheet_row_index)
        st.warning(f"Produto '{nome}' deletado com sucesso.")
        st.cache_data.clear()
        st.experimental_rerun()
    except Exception as e:
        st.error(f"Erro ao deletar produto. Detalhe: {e}")

# --- Layout do Painel de Admin ---

st.title("Administração 🛠️ Doce&Bella")
st.markdown("Bem-vinda ao painel de controle do seu Catálogo de Produtos.")

tab_produtos, tab_pedidos = st.tabs(["📋 Gestão de Produtos", "📦 Relatório de Pedidos"])

# --- TAB: GESTÃO DE PRODUTOS ---
with tab_produtos:
    st.header("Cadastro e Edição de Produtos")
    
    # Formulário de Cadastro de Novo Produto
    with st.expander("➕ Cadastrar Novo Produto", expanded=False):
        with st.form("form_cadastro"):
            col1, col2 = st.columns(2)
            
            nome = col1.text_input("Nome do Produto:")
            preco = col2.number_input("Preço (R$):", min_value=0.01, format="%.2f")
            
            link_imagem = st.text_input("Link da Imagem (URL Completo):", 
                                        placeholder="Ex: https://imgur.com/seulink.jpg")
            
            curta = st.text_area("Descrição Curta (para o Card):", max_chars=100)
            longa = st.text_area("Descrição Longa (para o Zoom):")
            
            disponivel = st.selectbox("Disponibilidade:", ["Sim", "Não"])
            
            if st.form_submit_button("SALVAR NOVO PRODUTO", type="primary"):
                if nome and preco and link_imagem and curta:
                    cadastrar_produto(nome, preco, curta, longa, link_imagem, disponivel)
                else:
                    st.error("Preencha todos os campos obrigatórios (Nome, Preço, Link, Curta).")

    st.markdown("---")
    st.subheader("Catálogo Ativo")

    if not df_produtos.empty:
        # Exibe o catálogo atual com a opção de deletar
        st.dataframe(df_produtos, use_container_width=True)
        
        st.caption("Selecione um produto abaixo para deletá-lo.")
        
        # Lógica de exclusão
        produtos_ativos = df_produtos.apply(lambda row: f"{row['ID']} - {row['NOME']}", axis=1).tolist()
        produto_selecionado = st.selectbox("Produto para Excluir:", ["Selecione..."] + produtos_ativos)
        
        if produto_selecionado != "Selecione...":
            produto_id = produto_selecionado.split(" - ")[0]
            linha_para_deletar = df_produtos[df_produtos['ID'] == produto_id]
            
            if not linha_para_deletar.empty:
                nome_deletar = linha_para_deletar['NOME'].iloc[0]
                index_deletar = linha_para_deletar.index[0]
                
                if st.button(f"🔴 CONFIRMAR EXCLUSÃO: {nome_deletar}", type="danger"):
                    deletar_produto(index_deletar, nome_deletar)

    else:
        st.info("Nenhum produto cadastrado no momento. Use o formulário acima para começar.")

# --- TAB: RELATÓRIO DE PEDIDOS ---
with tab_pedidos:
    st.header("Pedidos Recebidos")
    st.markdown("Estes são os pedidos que suas clientes finalizaram no catálogo.")
    
    if not df_pedidos.empty:
        # Exibe os pedidos, ordenados pelo mais recente
        df_pedidos_exibicao = df_pedidos.sort_values(by=df_pedidos.columns[0], ascending=False)
        st.dataframe(df_pedidos_exibicao, use_container_width=True)
    else:
        st.info("Nenhum pedido foi recebido ainda.")
