# admin_app.py
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos"
SHEET_NAME_PEDIDOS = "pedidos"

# --- Conexão com Google Sheets (Sem alterações) ---
@st.cache_resource(ttl=None)
def get_gspread_client():
    """Cria um cliente GSpread autenticado."""
    try:
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
        st.error(f"Erro na autenticação com o Google Sheets: {e}")
        st.stop()

@st.cache_data(ttl=60)
def carregar_dados(sheet_name):
    """Carrega dados de uma aba, garantindo que a coluna STATUS exista."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_values()
        if len(data) < 2:
            return pd.DataFrame()
        
        df = pd.DataFrame(data[1:], columns=data[0])
        
        if sheet_name == SHEET_NAME_PEDIDOS and 'STATUS' not in df.columns:
            df['STATUS'] = ''
        
        if sheet_name == SHEET_NAME_CATALOGO and 'ID' in df.columns:
            df['ID'] = pd.to_numeric(df['ID'], errors='coerce')
        
        return df
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Erro: A aba '{sheet_name}' não foi encontrada.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar os dados: {e}")
        return pd.DataFrame()

def atualizar_status_pedido(id_pedido, novo_status="Finalizado"):
    """Encontra um pedido pelo ID e atualiza seu status na coluna 'STATUS'."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_PEDIDOS)
        
        cell = worksheet.find(id_pedido, in_column=1)
        if not cell:
            st.error(f"ID do Pedido {id_pedido} não encontrado na planilha.")
            return False

        headers = worksheet.row_values(1)
        if 'STATUS' not in headers:
            st.error("A coluna 'STATUS' não foi encontrada na sua planilha de pedidos.")
            return False
        
        status_col_index = headers.index('STATUS') + 1
        
        worksheet.update_cell(cell.row, status_col_index, novo_status)
        st.cache_data.clear()
        return True

    except Exception as e:
        st.error(f"Erro ao atualizar o status do pedido: {e}")
        return False

# --- Funções de Produto (Sem alterações) ---
def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel):
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_CATALOGO)
        
        all_data = worksheet.get_all_records()
        if all_data:
            last_id = max([int(row['ID']) for row in all_data if str(row.get('ID')).isdigit()])
            novo_id = last_id + 1
        else:
            novo_id = 1

        nova_linha = [novo_id, nome, str(preco).replace('.', ','), desc_curta, desc_longa, link_imagem, disponivel]
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

with tab_pedidos:
    st.header("📋 Pedidos Recebidos")
    if st.button("Recarregar Pedidos"):
        st.cache_data.clear()
        st.rerun()

    df_pedidos_raw = carregar_dados(SHEET_NAME_PEDIDOS)
    df_catalogo = carregar_dados(SHEET_NAME_CATALOGO)

    if df_pedidos_raw.empty:
        st.info("Nenhum pedido foi encontrado na planilha.")
    else:
        df_pedidos_raw['DATA_HORA'] = pd.to_datetime(df_pedidos_raw['DATA_HORA'], errors='coerce')
        
        st.subheader("🔍 Filtrar Pedidos")
        col_filtro1, col_filtro2 = st.columns(2)
        with col_filtro1:
            data_filtro = st.date_input("Filtrar por data:")
        with col_filtro2:
            texto_filtro = st.text_input("Buscar por cliente ou produto:", placeholder="Digite o nome do cliente ou do produto")

        df_filtrado = df_pedidos_raw.copy()

        if data_filtro:
            df_filtrado = df_filtrado[df_filtrado['DATA_HORA'].dt.date == data_filtro]

        if texto_filtro.strip():
            texto_filtro = texto_filtro.lower()
            df_filtrado = df_filtrado[
                df_filtrado['NOME_CLIENTE'].str.lower().str.contains(texto_filtro) |
                df_filtrado['ITENS_PEDIDO'].str.lower().str.contains(texto_filtro)
            ]
        
        st.markdown("---")

        pedidos_pendentes = df_filtrado[df_filtrado['STATUS'] != 'Finalizado']
        pedidos_finalizados = df_filtrado[df_filtrado['STATUS'] == 'Finalizado']

        st.header("⏳ Pedidos Pendentes")
        if pedidos_pendentes.empty:
            st.info("Nenhum pedido pendente encontrado (com os filtros aplicados).")
        else:
            for index, pedido in pedidos_pendentes.iloc[::-1].iterrows():
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M')} - Total: R$ {pedido['VALOR_TOTAL']}"
                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID do Pedido:** `{pedido['ID_PEDIDO']}`")
                    
                    if st.button("✅ Finalizar Pedido", key=f"finalizar_{pedido['ID_PEDIDO']}"):
                        if atualizar_status_pedido(pedido['ID_PEDIDO']):
                            st.success(f"Pedido {pedido['ID_PEDIDO']} finalizado com sucesso!")
                            st.rerun()
                        else:
                            st.error("Não foi possível finalizar o pedido.")
                    
                    st.markdown("---")
                    
                    try:
                        detalhes_pedido = json.loads(pedido['ITENS_PEDIDO'])
                        for item in detalhes_pedido.get('itens', []):
                            link_imagem = "https://via.placeholder.com/150?text=Sem+Imagem"
                            if not df_catalogo.empty:
                                produto_no_catalogo = df_catalogo[df_catalogo['ID'] == item['id']]
                                if not produto_no_catalogo.empty:
                                    link_imagem = produto_no_catalogo.iloc[0]['LINKIMAGEM']
                            
                            col_img, col_detalhes = st.columns([1, 4])
                            with col_img:
                                if link_imagem: st.image(link_imagem, width=100)
                            with col_detalhes:
                                quantidade = item.get('qtd', item.get('quantidade', 0))
                                st.markdown(f"**Produto:** {item['nome']}")
                                st.markdown(f"**Quantidade:** {quantidade}")
                                st.markdown(f"**Preço Unitário:** R$ {item.get('preco', 0):.2f}")
                                st.markdown(f"**Subtotal:** R$ {item.get('subtotal', 0):.2f}")
                            st.markdown("---")
                    except Exception as e:
                        st.error(f"Erro ao processar itens do pedido: {e}")

        # --- SEÇÃO DE PEDIDOS FINALIZADOS (MODIFICADA) ---
        st.header("✅ Pedidos Finalizados")
        if pedidos_finalizados.empty:
            st.info("Nenhum pedido finalizado encontrado (com os filtros aplicados).")
        else:
             # Loop para exibir cada pedido finalizado com detalhes, igual aos pendentes
             for index, pedido in pedidos_finalizados.iloc[::-1].iterrows():
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M')} - Total: R$ {pedido['VALOR_TOTAL']}"
                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID do Pedido:** `{pedido['ID_PEDIDO']}`")
                    st.markdown("---")
                    
                    try:
                        detalhes_pedido = json.loads(pedido['ITENS_PEDIDO'])
                        for item in detalhes_pedido.get('itens', []):
                            link_imagem = "https://via.placeholder.com/150?text=Sem+Imagem"
                            if not df_catalogo.empty:
                                produto_no_catalogo = df_catalogo[df_catalogo['ID'] == item['id']]
                                if not produto_no_catalogo.empty:
                                    link_imagem = produto_no_catalogo.iloc[0]['LINKIMAGEM']
                            
                            col_img, col_detalhes = st.columns([1, 4])
                            with col_img:
                                if link_imagem: st.image(link_imagem, width=100)
                            with col_detalhes:
                                quantidade = item.get('qtd', item.get('quantidade', 0))
                                st.markdown(f"**Produto:** {item['nome']}")
                                st.markdown(f"**Quantidade:** {quantidade}")
                                st.markdown(f"**Preço Unitário:** R$ {item.get('preco', 0):.2f}")
                                st.markdown(f"**Subtotal:** R$ {item.get('subtotal', 0):.2f}")
                            st.markdown("---")
                    except Exception as e:
                        st.error(f"Erro ao processar itens do pedido: {e}")

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
        if st.form_submit_button("Cadastrar Produto"):
            if not nome_prod or preco_prod <= 0:
                st.warning("Preencha pelo menos o Nome e o Preço.")
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
