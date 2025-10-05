import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json # Importa a biblioteca para "ler" o JSON

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos"
SHEET_NAME_PEDIDOS = "pedidos"

# --- Conexão com Google Sheets ---
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
        # Converte a coluna de valor para número para ordenação
        df['VALOR_TOTAL'] = pd.to_numeric(df['VALOR_TOTAL'].str.replace(',', '.'), errors='coerce')
        return df
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Erro: A aba '{sheet_name}' não foi encontrada na sua planilha.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar os dados: {e}")
        return pd.DataFrame()

def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel):
    """Adiciona uma nova linha de produto na planilha."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_CATALOGO)
        
        all_data = worksheet.get_all_values()
        if len(all_data) > 1:
            last_id = max([int(row[0]) for row in all_data[1:] if row[0].isdigit()])
            novo_id = last_id + 1
        else:
            novo_id = 1

        nova_linha = [
            novo_id, nome, str(preco).replace('.', ','),
            desc_curta, desc_longa, link_imagem, disponivel
        ]
        
        worksheet.append_row(nova_linha)
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

with tab_pedidos:
    st.header("📋 Pedidos Recebidos")
    if st.button("Recarregar Pedidos"):
        st.cache_data.clear()
        st.rerun()

    df_pedidos = carregar_dados(SHEET_NAME_PEDIDOS)
    
    if df_pedidos.empty:
        st.info("Nenhum pedido foi encontrado na planilha.")
    else:
        # Ordena os pedidos do mais recente para o mais antigo
        df_pedidos = df_pedidos.sort_values(by="DATA_HORA", ascending=False)
        
        # --- NOVA VISUALIZAÇÃO DE PEDIDOS ---
        for index, row in df_pedidos.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns(3)
                col1.metric("Cliente", row['NOME_CLIENTE'])
                col2.metric("Data", row['DATA_HORA'].split(" ")[0]) # Pega só a data
                col3.metric("Valor Total", f"R$ {row['VALOR_TOTAL']:.2f}")

                with st.expander("Ver Detalhes do Pedido"):
                    try:
                        # Tenta "ler" o texto dos itens como um objeto de dados
                        itens_dict = json.loads(row['ITENS_PEDIDO'])
                        itens_df = pd.DataFrame(itens_dict['itens'])

                        st.write(f"**Contato:** {row['CONTATO_CLIENTE']}")
                        st.write("**Itens:**")
                        
                        # Mostra a tabela de itens formatada
                        st.dataframe(
                            itens_df[['quantidade', 'nome', 'preco']],
                            column_config={
                                "quantidade": "Qtd.",
                                "nome": "Produto",
                                "preco": st.column_config.NumberColumn("Preço Unit.", format="R$ %.2f")
                            },
                            hide_index=True,
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error("Não foi possível decodificar os itens deste pedido.")
                        st.write("Dados brutos:")
                        st.code(row['ITENS_PEDIDO'])


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
        
    df_produtos = carregar_dados(SHEET_NAME_CATALOGO)
    if df_produtos.empty:
        st.warning("Nenhum produto encontrado no catálogo.")
    else:
        st.dataframe(df_produtos, use_container_width=True)

