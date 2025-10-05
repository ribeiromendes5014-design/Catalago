# admin_app.py
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json # Importar a biblioteca JSON

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos"
SHEET_NAME_PEDIDOS = "pedidos"

# --- Conexão com Google Sheets (Sem alterações) ---
@st.cache_resource(ttl=None)
def get_gspread_client():
    """Cria um cliente GSpread autenticado usando o service account do st.secrets."""
    try:
        # Mantém a mesma lógica de autenticação que você já tem
        gcp_sa_credentials = {
            "type": st.secrets["gsheets"]["type"], "project_id": st.secrets["gsheets"]["project_id"],
            "private_key_id": st.secrets["gsheets"]["private_key_id"], "private_key": st.secrets["gsheets"]["private_key"],
            "client_email": st.secrets["gsheets"]["client_email"], "client_id": st.secrets["gsheets"]["client_id"],
            "auth_uri": st.secrets["gsheets"]["auth_uri"], "token_uri": st.secrets["gsheets"]["token_uri"],
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

@st.cache_data(ttl=60)
def carregar_dados(sheet_name):
    """Carrega todos os dados de uma aba específica."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_values()
        if len(data) < 2:
             return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=data[0])
        
        # Garante que a coluna 'ID' do catálogo seja do tipo correto para busca
        if sheet_name == SHEET_NAME_CATALOGO and 'ID' in df.columns:
            df['ID'] = pd.to_numeric(df['ID'], errors='coerce')

        return df
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Erro: A aba '{sheet_name}' não foi encontrada na sua planilha.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar os dados: {e}")
        return pd.DataFrame()

# --- Funções de Produto (Sem alterações) ---
def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel):
    """Adiciona uma nova linha de produto na planilha."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_CATALOGO)
        
        all_data = worksheet.get_all_records() # Usar get_all_records para facilitar
        if all_data:
            last_id = max([int(row['ID']) for row in all_data if str(row.get('ID')).isdigit()])
            novo_id = last_id + 1
        else:
            novo_id = 1

        nova_linha = [
            novo_id, nome, str(preco).replace('.', ','),
            desc_curta, desc_longa, link_imagem, disponivel
        ]
        
        worksheet.append_row(nova_linha, value_input_option='USER_ENTERED')
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Ocorreu um erro ao adicionar o produto: {e}")
        return False

# --- Layout do Aplicativo Admin ---
st.set_page_config(page_title="Admin Doce&Bella", layout="wide")

st.title("⭐ Painel de Administração | Doce&Bella")
st.markdown("Use este painel para gerenciar os pedidos e o catálogo de produtos.")

tab_pedidos, tab_produtos = st.tabs(["Relatório de Pedidos", "Gerenciar Produtos"])

# --- ABA DE PEDIDOS (MODIFICADA) ---
with tab_pedidos:
    st.header("📋 Pedidos Recebidos")
    if st.button("Recarregar Pedidos"):
        st.cache_data.clear()
        st.rerun()

    df_pedidos = carregar_dados(SHEET_NAME_PEDIDOS)
    df_catalogo = carregar_dados(SHEET_NAME_CATALOGO)

    if df_pedidos.empty:
        st.info("Nenhum pedido foi encontrado na planilha.")
    else:
        # Inverte a ordem para mostrar os mais recentes primeiro
        df_pedidos = df_pedidos.iloc[::-1]

        for index, pedido in df_pedidos.iterrows():
            # Título do Expander com as informações principais
            titulo_expander = f"Pedido de **{pedido['NOME_CLIENTE']}** - {pedido['DATA_HORA']} - Total: R$ {pedido['VALOR_TOTAL']}"
            
            with st.expander(titulo_expander):
                st.markdown(f"**Contato do Cliente:** `{pedido['CONTATO_CLIENTE']}`")
                st.markdown("---")
                
                try:
                    # Tenta "ler" o texto da coluna ITENS_PEDIDO como um JSON
                    detalhes_pedido = json.loads(pedido['ITENS_PEDIDO'])
                    itens = detalhes_pedido.get('itens', [])

                    if not itens:
                        st.warning("Não foi possível encontrar os itens neste pedido.")
                        continue

                    st.subheader("Itens do Pedido:")
                    
                    for item in itens:
                        # Para cada item, busca a imagem no catálogo
                        link_imagem = "https://via.placeholder.com/150?text=Sem+Imagem" # Imagem padrão
                        if not df_catalogo.empty:
                            produto_no_catalogo = df_catalogo[df_catalogo['ID'] == item['id']]
                            if not produto_no_catalogo.empty:
                                link_imagem = produto_no_catalogo.iloc[0]['LINKIMAGEM']

                        # Exibe os detalhes em colunas
                        col_img, col_detalhes = st.columns([1, 4])

                        with col_img:
                            if link_imagem:
                                st.image(link_imagem, width=100)
                        
                        with col_detalhes:
                            st.markdown(f"**Produto:** {item['nome']}")
                            st.markdown(f"**Quantidade:** {item['qtd']}")
                            st.markdown(f"**Preço Unitário:** R$ {item['preco']:.2f}")
                            st.markdown(f"**Subtotal:** R$ {item['subtotal']:.2f}")
                        
                        st.markdown("---")

                except json.JSONDecodeError:
                    st.error("O formato dos itens do pedido está inválido e não pôde ser lido.")
                    st.write("Conteúdo original:", pedido['ITENS_PEDIDO'])
                except Exception as e:
                    st.error(f"Ocorreu um erro inesperado ao processar os itens: {e}")


# --- ABA DE PRODUTOS (Sem alterações) ---
with tab_produtos:
    st.header("🛍️ Gerenciamento de Produtos")
    
    with st.form("form_novo_produto", clear_on_submit=True):
        st.subheader("Cadastrar Novo Produto")
        col1, col2 = st.columns(2)
        
        with col1:
            nome_prod = st.text_input("Nome do Produto*")
            preco_prod = st.number_input("Preço (R$)*", min_value=0.0, format="%.2f", step=0.50)
            link_imagem_prod = st.text_input("URL da Imagem do Produto")
            
        with col2:
            desc_curta_prod = st.text_input("Descrição Curta (Ex: Sabor chocolate, 250g)")
            desc_longa_prod = st.text_area("Descrição Longa/Detalhada")
            disponivel_prod = st.selectbox("Disponível para venda?", ("Sim", "Não"))

        submitted = st.form_submit_button("Cadastrar Produto")
        if submitted:
            if not nome_prod or preco_prod <= 0:
                st.warning("Por favor, preencha pelo menos o Nome e o Preço do produto.")
            else:
                if adicionar_produto(nome_prod, preco_prod, desc_curta_prod, desc_longa_prod, link_imagem_prod, disponivel_prod):
                    st.success("Produto cadastrado com sucesso!")
                    st.rerun()
                else:
                    st.error("Falha ao cadastrar o produto.")

    st.markdown("---")

    st.subheader("Catálogo Atual")
    if st.button("Recarregar Catálogo"):
        st.cache_data.clear()
        st.rerun()
        
    df_produtos_display = carregar_dados(SHEET_NAME_CATALOGO)
    if df_produtos_display.empty:
        st.warning("Nenhum produto encontrado no catálogo.")
    else:
        st.dataframe(df_produtos_display, use_container_width=True)
