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
SHEET_NAME_PROMOCOES = "promocoes"

# --- Funções de Conexão e Carregamento (Sem alterações) ---
@st.cache_resource(ttl=None)
def get_gspread_client():
    try:
        gcp_sa_credentials = { "type": st.secrets["gsheets"]["type"], "project_id": st.secrets["gsheets"]["project_id"], "private_key_id": st.secrets["gsheets"]["private_key_id"], "private_key": st.secrets["gsheets"]["private_key"], "client_email": st.secrets["gsheets"]["client_email"], "client_id": st.secrets["gsheets"]["client_id"], "auth_uri": st.secrets["gsheets"]["auth_uri"], "token_uri": st.secrets["gsheets"]["token_uri"], "auth_provider_x509_cert_url": st.secrets["gsheets"]["auth_provider_x509_cert_url"], "client_x509_cert_url": st.secrets["gsheets"]["client_x509_cert_url"] }
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
    except gspread.exceptions.WorksheetNotFound:
        st.warning(f"Atenção: A aba '{sheet_name}' não foi encontrada na sua planilha. Algumas funcionalidades podem não funcionar.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar os dados de '{sheet_name}': {e}")
        return pd.DataFrame()

# --- Funções de Pedido ---
def atualizar_status_pedido(id_pedido, novo_status):
    try:
        sh = get_gspread_client(); worksheet = sh.worksheet(SHEET_NAME_PEDIDOS); cell = worksheet.find(id_pedido, in_column=1)
        if not cell: return False
        headers = worksheet.row_values(1);
        if 'STATUS' not in headers: return False
        status_col_index = headers.index('STATUS') + 1; worksheet.update_cell(cell.row, status_col_index, novo_status); st.cache_data.clear(); return True
    except Exception: return False
def excluir_pedido(id_pedido):
    try:
        sh = get_gspread_client(); worksheet = sh.worksheet(SHEET_NAME_PEDIDOS); cell = worksheet.find(id_pedido, in_column=1)
        if cell: worksheet.delete_rows(cell.row); st.cache_data.clear(); return True
        return False
    except Exception as e: st.error(f"Erro ao excluir o pedido: {e}"); return False
def exibir_itens_pedido(pedido_json, df_catalogo):
    try:
        detalhes_pedido = json.loads(pedido_json)
        for item in detalhes_pedido.get('itens', []):
            link_imagem = "https://via.placeholder.com/150?text=Sem+Imagem"
            if not df_catalogo.empty and not df_catalogo[df_catalogo['ID'] == item['id']].empty: link_imagem = df_catalogo[df_catalogo['ID'] == item['id']].iloc[0]['LINKIMAGEM']
            col_img, col_detalhes = st.columns([1, 4]); col_img.image(link_imagem, width=100)
            quantidade = item.get('qtd', item.get('quantidade', 0)); preco_unitario = float(item.get('preco', 0.0)); subtotal = item.get('subtotal')
            if subtotal is None: subtotal = preco_unitario * quantidade
            col_detalhes.markdown(f"**Produto:** {item.get('nome', 'N/A')}\n\n**Quantidade:** {quantidade}\n\n**Subtotal:** R$ {subtotal:.2f}"); st.markdown("---")
    except Exception as e: st.error(f"Erro ao processar itens do pedido: {e}")

# --- FUNÇÃO ADICIONAR_PRODUTO CORRIGIDA ---
def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel):
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_CATALOGO)
        all_values = worksheet.get_all_values()
        
        # Define explicitamente a próxima linha como o final da planilha
        next_row_index = len(all_values) + 1
        
        ids_existentes = [int(row[1]) for row in all_values[1:] if len(row) > 1 and row[1].isdigit()]
        novo_id = max(ids_existentes) + 1 if ids_existentes else 1
        
        nova_linha = ["", novo_id, nome, str(preco).replace('.', ','), desc_curta, desc_longa, link_imagem, disponivel]
        
        # Usa insert_row para adicionar na linha exata, em vez de append_row
        worksheet.insert_row(nova_linha, next_row_index, value_input_option='USER_ENTERED')
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Ocorreu um erro ao adicionar o produto: {e}")
        return False

# --- Funções de Promoção ---
def criar_promocao(id_produto, nome_produto, preco_original, preco_promocional, data_inicio, data_fim):
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_PROMOCOES)
        nova_linha = [str(id_produto), nome_produto, str(preco_original), str(preco_promocional), "Ativa", data_inicio, data_fim]
        worksheet.append_row(nova_linha, value_input_option='USER_ENTERED')
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Ocorreu um erro ao criar a promoção: {e}")
        return False
def desativar_promocao(id_produto):
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_PROMOCOES)
        cells = worksheet.findall(str(id_produto), in_column=1)
        if not cells: return False
        cell = cells[-1] 
        worksheet.update_acell(f'E{cell.row}', "Inativa")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Ocorreu um erro ao desativar a promoção: {e}")
        return False

# --- Layout do Aplicativo Admin ---
st.set_page_config(page_title="Admin Doce&Bella", layout="wide")
st.title("⭐ Painel de Administração | Doce&Bella")
tab_pedidos, tab_produtos, tab_promocoes = st.tabs(["Relatório de Pedidos", "Gerenciar Produtos", "🔥 Promoções"])

with tab_pedidos:
    # (código da aba de pedidos, sem alterações)
    st.header("📋 Pedidos Recebidos")
    if st.button("Recarregar Pedidos"): st.cache_data.clear(); st.rerun()
    df_pedidos_raw = carregar_dados(SHEET_NAME_PEDIDOS); df_catalogo_pedidos = carregar_dados(SHEET_NAME_CATALOGO)
    if df_pedidos_raw.empty: st.info("Nenhum pedido foi encontrado na planilha.")
    else:
        df_pedidos_raw['DATA_HORA'] = pd.to_datetime(df_pedidos_raw['DATA_HORA'], errors='coerce'); st.subheader("🔍 Filtrar Pedidos")
        col_filtro1, col_filtro2 = st.columns(2); data_filtro = col_filtro1.date_input("Filtrar por data:"); texto_filtro = col_filtro2.text_input("Buscar por cliente ou produto:")
        df_filtrado = df_pedidos_raw.copy()
        if data_filtro: df_filtrado = df_filtrado[df_filtrado['DATA_HORA'].dt.date == data_filtro]
        if texto_filtro.strip():
            texto_filtro = texto_filtro.lower(); df_filtrado = df_filtrado[df_filtrado['NOME_CLIENTE'].str.lower().str.contains(texto_filtro) | df_filtrado['ITENS_PEDIDO'].str.lower().str.contains(texto_filtro)]
        st.markdown("---"); pedidos_pendentes = df_filtrado[df_filtrado['STATUS'] != 'Finalizado']; pedidos_finalizados = df_filtrado[df_filtrado['STATUS'] == 'Finalizado']
        st.header("⏳ Pedidos Pendentes")
        if pedidos_pendentes.empty: st.info("Nenhum pedido pendente encontrado.")
        else:
            for index, pedido in pedidos_pendentes.iloc[::-1].iterrows():
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M')} - Total: R$ {pedido['VALOR_TOTAL']}"
                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{pedido['ID_PEDIDO']}`")
                    if st.button("✅ Finalizar Pedido", key=f"finalizar_{pedido['ID_PEDIDO']}"):
                        if atualizar_status_pedido(pedido['ID_PEDIDO'], novo_status="Finalizado"): st.success(f"Pedido {pedido['ID_PEDIDO']} finalizado!"); st.rerun()
                    st.markdown("---"); exibir_itens_pedido(pedido['ITENS_PEDIDO'], df_catalogo_pedidos)
        st.header("✅ Pedidos Finalizados")
        if pedidos_finalizados.empty: st.info("Nenhum pedido finalizado encontrado.")
        else:
             for index, pedido in pedidos_finalizados.iloc[::-1].iterrows():
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M')} - Total: R$ {pedido['VALOR_TOTAL']}"
                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{pedido['ID_PEDIDO']}`")
                    col_reverter, col_excluir = st.columns(2)
                    with col_reverter:
                        if st.button("↩️ Reverter para Pendente", key=f"reverter_{pedido['ID_PEDIDO']}", use_container_width=True):
                            if atualizar_status_pedido(pedido['ID_PEDIDO'], novo_status=""): st.success(f"Pedido {pedido['ID_PEDIDO']} revertido."); st.rerun()
                    with col_excluir:
                        if st.button("🗑️ Excluir Pedido", type="primary", key=f"excluir_{pedido['ID_PEDIDO']}", use_container_width=True):
                            if excluir_pedido(pedido['ID_PEDIDO']): st.success(f"Pedido {pedido['ID_PEDIDO']} excluído!"); st.rerun()
                    st.markdown("---"); exibir_itens_pedido(pedido['ITENS_PEDIDO'], df_catalogo_pedidos)

with tab_produtos:
    # (código da aba de produtos, sem alterações)
    st.header("🛍️ Gerenciamento de Produtos")
    with st.form("form_novo_produto", clear_on_submit=True):
        st.subheader("Cadastrar Novo Produto"); col1, col2 = st.columns(2); nome_prod = col1.text_input("Nome do Produto*"); preco_prod = col1.number_input("Preço (R$)*", min_value=0.0, format="%.2f", step=0.50); link_imagem_prod = col1.text_input("URL da Imagem do Produto"); desc_curta_prod = col2.text_input("Descrição Curta"); desc_longa_prod = col2.text_area("Descrição Longa/Detalhada"); disponivel_prod = col2.selectbox("Disponível para venda?", ("Sim", "Não"))
        if st.form_submit_button("Cadastrar Produto"):
            if not nome_prod or preco_prod <= 0: st.warning("Preencha o Nome e o Preço.")
            elif adicionar_produto(nome_prod, preco_prod, desc_curta_prod, desc_longa_prod, link_imagem_prod, disponivel_prod): st.success("Produto cadastrado!"); st.rerun()
            else: st.error("Falha ao cadastrar o produto.")
    st.markdown("---"); st.subheader("Catálogo Atual");
    if st.button("Recarregar Catálogo"): st.cache_data.clear(); st.rerun()
    df_produtos_display = carregar_dados(SHEET_NAME_CATALOGO)
    if df_produtos_display.empty: st.warning("Nenhum produto encontrado.")
    else: st.dataframe(df_produtos_display, use_container_width=True)

with tab_promocoes:
    # (código da aba de promoções, sem alterações)
    st.header("🔥 Gerenciador de Promoções")
    st.markdown("Crie e gerencie promoções com data de início e fim para produtos do seu catálogo.")
    df_catalogo_promo = carregar_dados(SHEET_NAME_CATALOGO)
    df_promocoes = carregar_dados(SHEET_NAME_PROMOCOES)
    if df_catalogo_promo.empty:
        st.warning("Você precisa ter produtos cadastrados no catálogo para criar uma promoção.")
    else:
        with st.form("form_nova_promocao", clear_on_submit=True):
            st.subheader("Criar Nova Promoção")
            df_catalogo_promo['PRECO'] = pd.to_numeric(df_catalogo_promo['PRECO'].str.replace(',', '.'), errors='coerce')
            opcoes_produtos = {f"{row['NOME']} (R$ {row['PRECO']:.2f})": row['ID'] for index, row in df_catalogo_promo.iterrows()}
            produto_selecionado_nome = st.selectbox("Escolha o produto:", options=opcoes_produtos.keys())
            preco_promocional = st.number_input("Novo Preço Promocional (R$)", min_value=0.01, format="%.2f", step=0.50)
            col_data1, col_data2 = st.columns(2)
            with col_data1:
                data_inicio = st.date_input("Data de Início", value=datetime.now())
            with col_data2:
                sem_data_fim = st.checkbox("Não tem data para acabar")
                data_fim = None
                if not sem_data_fim:
                    data_fim = st.date_input("Data de Fim", min_value=data_inicio)
            submitted = st.form_submit_button("Lançar Promoção")
            if submitted:
                id_produto_selecionado = opcoes_produtos[produto_selecionado_nome]
                produto_info = df_catalogo_promo[df_catalogo_promo['ID'] == id_produto_selecionado].iloc[0]
                if preco_promocional >= produto_info['PRECO']:
                    st.error("O preço promocional deve ser menor que o preço original.")
                else:
                    data_inicio_str = data_inicio.strftime('%Y-%m-%d')
                    data_fim_str = "" if sem_data_fim else data_fim.strftime('%Y-%m-%d')
                    if criar_promocao(id_produto_selecionado, produto_info['NOME'], produto_info['PRECO'], preco_promocional, data_inicio_str, data_fim_str):
                        st.success(f"Promoção para '{produto_info['NOME']}' criada com sucesso!")
                        st.rerun()
                    else:
                        st.error("Falha ao criar a promoção.")
        st.markdown("---")
        st.subheader("Visão Geral das Promoções")
        if df_promocoes.empty:
            st.info("Nenhuma promoção foi criada ainda.")
        else:
            hoje = pd.to_datetime(datetime.now().date())
            df_promocoes['DATA_INICIO'] = pd.to_datetime(df_promocoes['DATA_INICIO'], errors='coerce')
            df_promocoes['DATA_FIM'] = pd.to_datetime(df_promocoes['DATA_FIM'], errors='coerce')
            promocoes_ativas_hoje = df_promocoes[
                (df_promocoes['STATUS'] == 'Ativa') &
                (df_promocoes['DATA_INICIO'] <= hoje) &
                (df_promocoes['DATA_FIM'].isna() | (df_promocoes['DATA_FIM'] >= hoje))
            ]
            st.markdown("#### Promoções Ativas Hoje")
            if promocoes_ativas_hoje.empty:
                st.info("Nenhuma promoção está ativa para a data de hoje.")
            else:
                for index, promo in promocoes_ativas_hoje.iterrows():
                    fim_str = "sem data para acabar" if pd.isna(promo['DATA_FIM']) else promo['DATA_FIM'].strftime('%d/%m/%Y')
                    st.markdown(f"- **{promo['NOME_PRODUTO']}** por R$ {promo['PRECO_PROMOCIONAL']} (Válido até: {fim_str})")
            st.markdown("---")
            st.markdown("#### Todas as Promoções Criadas (Ativas e Inativas)")
            st.dataframe(df_promocoes, use_container_width=True)
