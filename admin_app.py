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
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_values()
        if len(data) < 2: return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=data[0])
        if sheet_name == SHEET_NAME_PEDIDOS and 'STATUS' not in df.columns: df['STATUS'] = ''
        if sheet_name == SHEET_NAME_CATALOGO and 'ID' in df.columns: df['ID'] = pd.to_numeric(df['ID'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar os dados: {e}")
        return pd.DataFrame()

def atualizar_status_pedido(id_pedido, novo_status):
    """Atualiza o status de um pedido para qualquer valor (ex: "Finalizado", "")."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_PEDIDOS)
        cell = worksheet.find(id_pedido, in_column=1)
        if not cell: return False
        headers = worksheet.row_values(1)
        if 'STATUS' not in headers: return False
        status_col_index = headers.index('STATUS') + 1
        worksheet.update_cell(cell.row, status_col_index, novo_status)
        st.cache_data.clear()
        return True
    except Exception:
        return False

# --- NOVA FUNÇÃO PARA EXCLUIR PEDIDO ---
def excluir_pedido(id_pedido):
    """Encontra um pedido pelo ID e exclui a linha inteira."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_PEDIDOS)
        cell = worksheet.find(id_pedido, in_column=1)
        if cell:
            worksheet.delete_rows(cell.row)
            st.cache_data.clear()
            return True
        return False
    except Exception as e:
        st.error(f"Erro ao excluir o pedido: {e}")
        return False

# --- Funções de Produto (Sem alterações) ---
def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel):
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_CATALOGO)
        all_data = worksheet.get_all_records()
        novo_id = max([int(row['ID']) for row in all_data if str(row.get('ID')).isdigit()]) + 1 if all_data else 1
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
        data_filtro = col_filtro1.date_input("Filtrar por data:")
        texto_filtro = col_filtro2.text_input("Buscar por cliente ou produto:")
        
        df_filtrado = df_pedidos_raw.copy()
        if data_filtro: df_filtrado = df_filtrado[df_filtrado['DATA_HORA'].dt.date == data_filtro]
        if texto_filtro.strip():
            texto_filtro = texto_filtro.lower()
            df_filtrado = df_filtrado[df_filtrado['NOME_CLIENTE'].str.lower().str.contains(texto_filtro) | df_filtrado['ITENS_PEDIDO'].str.lower().str.contains(texto_filtro)]
        st.markdown("---")

        pedidos_pendentes = df_filtrado[df_filtrado['STATUS'] != 'Finalizado']
        pedidos_finalizados = df_filtrado[df_filtrado['STATUS'] == 'Finalizado']

        st.header("⏳ Pedidos Pendentes")
        if pedidos_pendentes.empty:
            st.info("Nenhum pedido pendente encontrado.")
        else:
            for index, pedido in pedidos_pendentes.iloc[::-1].iterrows():
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M')} - Total: R$ {pedido['VALOR_TOTAL']}"
                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{pedido['ID_PEDIDO']}`")
                    if st.button("✅ Finalizar Pedido", key=f"finalizar_{pedido['ID_PEDIDO']}"):
                        if atualizar_status_pedido(pedido['ID_PEDIDO'], novo_status="Finalizado"):
                            st.success(f"Pedido {pedido['ID_PEDIDO']} finalizado!")
                            st.rerun()
                    st.markdown("---")
                    # Lógica para exibir itens (sem alteração)
                    try:
                        detalhes_pedido = json.loads(pedido['ITENS_PEDIDO'])
                        for item in detalhes_pedido.get('itens', []):
                            # ... (código de exibição de item)
                            link_imagem = "https://via.placeholder.com/150?text=Sem+Imagem"
                            if not df_catalogo.empty and not df_catalogo[df_catalogo['ID'] == item['id']].empty:
                                link_imagem = df_catalogo[df_catalogo['ID'] == item['id']].iloc[0]['LINKIMAGEM']
                            col_img, col_detalhes = st.columns([1, 4])
                            col_img.image(link_imagem, width=100)
                            quantidade = item.get('qtd', item.get('quantidade', 0))
                            col_detalhes.markdown(f"**Produto:** {item['nome']}\n\n**Quantidade:** {quantidade}\n\n**Subtotal:** R$ {item.get('subtotal', 0):.2f}")
                            st.markdown("---")
                    except Exception as e: st.error(f"Erro ao processar itens: {e}")

        st.header("✅ Pedidos Finalizados")
        if pedidos_finalizados.empty:
            st.info("Nenhum pedido finalizado encontrado.")
        else:
             for index, pedido in pedidos_finalizados.iloc[::-1].iterrows():
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M')} - Total: R$ {pedido['VALOR_TOTAL']}"
                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{pedido['ID_PEDIDO']}`")
                    
                    # --- NOVOS BOTÕES AQUI ---
                    col_reverter, col_excluir = st.columns(2)
                    with col_reverter:
                        if st.button("↩️ Reverter para Pendente", key=f"reverter_{pedido['ID_PEDIDO']}", use_container_width=True):
                            if atualizar_status_pedido(pedido['ID_PEDIDO'], novo_status=""):
                                st.success(f"Pedido {pedido['ID_PEDIDO']} revertido.")
                                st.rerun()
                    with col_excluir:
                        if st.button("🗑️ Excluir Pedido", type="primary", key=f"excluir_{pedido['ID_PEDIDO']}", use_container_width=True):
                            if excluir_pedido(pedido['ID_PEDIDO']):
                                st.success(f"Pedido {pedido['ID_PEDIDO']} excluído!")
                                st.rerun()
                    
                    st.markdown("---")
                    # Lógica para exibir itens (sem alteração)
                    try:
                        detalhes_pedido = json.loads(pedido['ITENS_PEDIDO'])
                        for item in detalhes_pedido.get('itens', []):
                            # ... (código de exibição de item)
                            link_imagem = "https://via.placeholder.com/150?text=Sem+Imagem"
                            if not df_catalogo.empty and not df_catalogo[df_catalogo['ID'] == item['id']].empty:
                                link_imagem = df_catalogo[df_catalogo['ID'] == item['id']].iloc[0]['LINKIMAGEM']
                            col_img, col_detalhes = st.columns([1, 4])
                            col_img.image(link_imagem, width=100)
                            quantidade = item.get('qtd', item.get('quantidade', 0))
                            col_detalhes.markdown(f"**Produto:** {item['nome']}\n\n**Quantidade:** {quantidade}\n\n**Subtotal:** R$ {item.get('subtotal', 0):.2f}")
                            st.markdown("---")
                    except Exception as e: st.error(f"Erro ao processar itens: {e}")

with tab_produtos:
    st.header("🛍️ Gerenciamento de Produtos")
    with st.form("form_novo_produto", clear_on_submit=True):
        st.subheader("Cadastrar Novo Produto")
        col1, col2 = st.columns(2)
        nome_prod = col1.text_input("Nome do Produto*")
        preco_prod = col1.number_input("Preço (R$)*", min_value=0.0, format="%.2f", step=0.50)
        link_imagem_prod = col1.text_input("URL da Imagem do Produto")
        desc_curta_prod = col2.text_input("Descrição Curta")
        desc_longa_prod = col2.text_area("Descrição Longa/Detalhada")
        disponivel_prod = col2.selectbox("Disponível para venda?", ("Sim", "Não"))
        if st.form_submit_button("Cadastrar Produto"):
            if not nome_prod or preco_prod <= 0:
                st.warning("Preencha o Nome e o Preço.")
            elif adicionar_produto(nome_prod, preco_prod, desc_curta_prod, desc_longa_prod, link_imagem_prod, disponivel_prod):
                st.success("Produto cadastrado!")
                st.rerun()
            else:
                st.error("Falha ao cadastrar o produto.")
    st.markdown("---")
    st.subheader("Catálogo Atual")
    if st.button("Recarregar Catálogo"): st.cache_data.clear(); st.rerun()
    df_produtos_display = carregar_dados(SHEET_NAME_CATALOGO)
    if df_produtos_display.empty:
        st.warning("Nenhum produto encontrado.")
    else:
        st.dataframe(df_produtos_display, use_container_width=True)
