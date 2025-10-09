# admin_app.py
import streamlit as st
import pandas as pd
import json
from datetime import datetime
import time
import requests 

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos_estoque"
SHEET_NAME_PEDIDOS = "pedidos"
SHEET_NAME_PROMOCOES = "promocoes"

# --- Configurações do GitHub ---
GITHUB_RAW_BASE_URL = "https://raw.githubusercontent.com/ribeiromendes5014-design/fluxo/main"

# --- Conexão e Carregamento de Dados (CORRIGIDO E NORMALIZADO) ---

@st.cache_data(ttl=60)
def carregar_dados(sheet_name):
    """Carrega dados de um CSV do GitHub."""
    csv_filename = f"{sheet_name}.csv"
    url = f"{GITHUB_RAW_BASE_URL}/{csv_filename}"
    
    try:
        # Usando sep=',' para delimitador de vírgula
        df = pd.read_csv(url, sep=',') 
        
        # Limpeza e Normalização dos Nomes das Colunas
        df.columns = df.columns.str.strip().str.upper() 

        # Remove a coluna 'COLUNA' (se existir) que parece ser um índice extra.
        if 'COLUNA' in df.columns:
            df.drop(columns=['COLUNA'], inplace=True)

        # Adicionar colunas ausentes para compatibilidade, como antes
        if sheet_name == SHEET_NAME_PEDIDOS and 'STATUS' not in df.columns: df['STATUS'] = ''
        if sheet_name == SHEET_NAME_CATALOGO and 'ID' in df.columns: 
            # Garante que ID é numérico
            df['ID'] = pd.to_numeric(df['ID'], errors='coerce') 
            df.dropna(subset=['ID'], inplace=True) 
            df['ID'] = df['ID'].astype(int)

        return df
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            st.warning(f"Arquivo CSV '{csv_filename}' não encontrado na URL: {url}"); return pd.DataFrame()
        else:
            st.error(f"Erro HTTP ao carregar dados de '{csv_filename}': {e}"); return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao carregar dados de '{csv_filename}': {e}"); return pd.DataFrame()


# --- Funções de Pedidos (DESABILITADAS PARA ESCRITA) ---

def atualizar_status_pedido(id_pedido, novo_status):
    st.error("Funcionalidade de escrita desabilitada. Configure a API do GitHub para escrita."); return False
    
def excluir_pedido(id_pedido):
    st.error("Funcionalidade de escrita desabilitada. Configure a API do GitHub para escrita."); return False

def exibir_itens_pedido(pedido_json, df_catalogo):
    try:
        detalhes_pedido = json.loads(pedido_json)
        for item in detalhes_pedido.get('itens', []):
            link_imagem = "https://via.placeholder.com/150?text=Sem+Imagem"
            item_id = pd.to_numeric(item.get('id'), errors='coerce')
            
            if not df_catalogo.empty and not pd.isna(item_id) and not df_catalogo[df_catalogo['ID'] == int(item_id)].empty: 
                 # CORREÇÃO: Trata o link como string e verifica se é 'nan'
                 link_na_tabela = str(df_catalogo[df_catalogo['ID'] == int(item_id)].iloc[0].get('LINKIMAGEM', link_imagem)).strip()
                 
                 if link_na_tabela.lower() != 'nan' and link_na_tabela:
                     link_imagem = link_na_tabela

            col_img, col_detalhes = st.columns([1, 4]); col_img.image(link_imagem, width=100)
            quantidade = item.get('qtd', item.get('quantidade', 0)); preco_unitario = float(item.get('preco', 0.0)); subtotal = item.get('subtotal')
            if subtotal is None: subtotal = preco_unitario * quantidade
            col_detalhes.markdown(f"**Produto:** {item.get('nome', 'N/A')}\n\n**Quantidade:** {quantidade}\n\n**Subtotal:** R$ {subtotal:.2f}"); st.markdown("---")
    except Exception as e: st.error(f"Erro ao processar itens do pedido: {e}")

# --- FUNÇÕES CRUD PARA PRODUTOS (DESABILITADAS PARA ESCRITA) ---

def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel):
    st.error("Funcionalidade de escrita desabilitada. Configure a API do GitHub para escrita."); return False

def excluir_produto(id_produto):
    st.error("Funcionalidade de escrita desabilitada. Configure a API do GitHub para escrita."); return False

def atualizar_produto(id_produto, nome, preco, desc_curta, desc_longa, link_imagem, disponivel):
    st.error("Funcionalidade de escrita desabilitada. Configure a API do GitHub para escrita."); return False

# --- FUNÇÕES CRUD PARA PROMOÇÕES (DESABILITADAS PARA ESCRITA) ---

def criar_promocao(id_produto, nome_produto, preco_original, preco_promocional, data_inicio, data_fim):
    st.error("Funcionalidade de escrita desabilitada. Configure a API do GitHub para escrita."); return False

def excluir_promocao(id_promocao):
    st.error("Funcionalidade de escrita desabilitada. Configure a API do GitHub para escrita."); return False

def atualizar_promocao(id_promocao, preco_promocional, data_inicio, data_fim, status):
    st.error("Funcionalidade de escrita desabilitada. Configure a API do GitHub para escrita."); return False


# --- LAYOUT DO APP ---
st.set_page_config(page_title="Admin Doce&Bella", layout="wide")
st.title("⭐ Painel de Administração | Doce&Bella")
tab_pedidos, tab_produtos, tab_promocoes = st.tabs(["Pedidos", "Produtos", "🔥 Promoções"])

with tab_pedidos:
    st.header("📋 Pedidos Recebidos"); 
    if st.button("Recarregar Pedidos"): st.cache_data.clear(); st.rerun()
    df_pedidos_raw = carregar_dados(SHEET_NAME_PEDIDOS); 
    df_catalogo_pedidos = carregar_dados(SHEET_NAME_CATALOGO)
    if df_pedidos_raw.empty: st.info("Nenhum pedido foi encontrado na planilha.")
    else:
        df_pedidos_raw['DATA_HORA'] = pd.to_datetime(df_pedidos_raw['DATA_HORA'], errors='coerce'); st.subheader("🔍 Filtrar Pedidos")
        col_filtro1, col_filtro2 = st.columns(2); data_filtro = col_filtro1.date_input("Filtrar por data:"); texto_filtro = col_filtro2.text_input("Buscar por cliente ou produto:")
        df_filtrado = df_pedidos_raw.copy()
        if data_filtro: df_filtrado = df_filtrado[df_filtrado['DATA_HORA'].dt.date == data_filtro]
        if texto_filtro.strip():
            texto_filtro = texto_filtro.lower(); df_filtrado = df_filtrado[df_filtrado['NOME_CLIENTE'].astype(str).str.lower().str.contains(texto_filtro) | df_filtrado['ITENS_PEDIDO'].astype(str).str.lower().str.contains(texto_filtro)]
        st.markdown("---"); pedidos_pendentes = df_filtrado[df_filtrado['STATUS'] != 'Finalizado']; pedidos_finalizados = df_filtrado[df_filtrado['STATUS'] == 'Finalizado']
        st.header("⏳ Pedidos Pendentes")
        if pedidos_pendentes.empty: st.info("Nenhum pedido pendente encontrado.")
        else:
            for index, pedido in pedidos_pendentes.iloc[::-1].iterrows():
                data_hora_str = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indisponível"
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {data_hora_str} - Total: R$ {pedido['VALOR_TOTAL']}"
                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{pedido['ID_PEDIDO']}`")
                    if st.button("✅ Finalizar Pedido", key=f"finalizar_{pedido['ID_PEDIDO']}"):
                        if atualizar_status_pedido(pedido['ID_PEDIDO'], novo_status="Finalizado"): st.success(f"Pedido {pedido['ID_PEDIDO']} finalizado!"); st.rerun()
                    st.markdown("---"); exibir_itens_pedido(pedido['ITENS_PEDIDO'], df_catalogo_pedidos)
        st.header("✅ Pedidos Finalizados")
        if pedidos_finalizados.empty: st.info("Nenhum pedido finalizado encontrado.")
        else:
             for index, pedido in pedidos_finalizados.iloc[::-1].iterrows():
                data_hora_str = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indisponível"
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {data_hora_str} - Total: R$ {pedido['VALOR_TOTAL']}"
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
    st.header("🛍️ Gerenciamento de Produtos")
    with st.expander("➕ Cadastrar Novo Produto", expanded=False):
        with st.form("form_novo_produto", clear_on_submit=True):
            col1, col2 = st.columns(2); nome_prod = col1.text_input("Nome do Produto*"); preco_prod = col1.number_input("Preço (R$)*", min_value=0.0, format="%.2f", step=0.50); link_imagem_prod = col1.text_input("URL da Imagem"); desc_curta_prod = col2.text_input("Descrição Curta"); desc_longa_prod = col2.text_area("Descrição Longa"); disponivel_prod = col2.selectbox("Disponível?", ("Sim", "Não"))
            if st.form_submit_button("Cadastrar Produto"):
                if not nome_prod or preco_prod <= 0: st.warning("Preencha Nome e Preço.")
                elif adicionar_produto(nome_prod, preco_prod, desc_curta_prod, desc_longa_prod, link_imagem_prod, disponivel_prod):
                    st.success("Produto cadastrado!"); st.rerun()
                else: st.error("Falha ao cadastrar.")
    
    st.markdown("---")
    st.subheader("Catálogo Atual")
    df_produtos = carregar_dados(SHEET_NAME_CATALOGO)
    if df_produtos.empty:
        st.warning("Nenhum produto encontrado.")
    else:
        for index, produto in df_produtos.iterrows():
            with st.container(border=True):
                col1, col2 = st.columns([1, 4])
                
                link_imagem_produto = str(produto.get("LINKIMAGEM")).strip() 
                
                with col1:
                    # ✅ CORREÇÃO APLICADA AQUI
                    if link_imagem_produto.lower() in ['nan', 'none'] or not link_imagem_produto:
                         img_url = "https://via.placeholder.com/150?text=Sem+Imagem"
                    else:
                         img_url = link_imagem_produto
                         
                    st.image(img_url, width=100)
                    
                with col2:
                    st.markdown(f"**{produto.get('NOME', 'N/A')}** (ID: {produto.get('ID', 'N/A')})")
                    st.markdown(f"**Preço:** R$ {produto.get('PRECO', 'N/A')}")
                    with st.popover("📝 Editar"):
                        with st.form(f"edit_form_{produto.get('ID')}_{index}", clear_on_submit=True):
                            st.markdown(f"Editando: **{produto.get('NOME', 'N/A')}**")
                            preco_val = float(str(produto.get('PRECO', '0')).replace(',','.'))
                            nome_edit = st.text_input("Nome", value=produto.get('NOME', ''))
                            preco_edit = st.number_input("Preço", value=preco_val, format="%.2f")
                            link_edit = st.text_input("Link Imagem", value=produto.get('LINKIMAGEM', ''))
                            curta_edit = st.text_input("Desc. Curta", value=produto.get('DESCRICAOCURTA', ''))
                            longa_edit = st.text_area("Desc. Longa", value=produto.get('DESCRICAOLONGA', ''))
                            
                            disponivel_val = produto.get('DISPONIVEL', 'Sim')
                            if isinstance(disponivel_val, str):
                                disponivel_val = disponivel_val.strip().title()
                            else:
                                disponivel_val = 'Sim' 
                            
                            try:
                                default_index = ["Sim", "Não"].index(disponivel_val)
                            except ValueError:
                                default_index = 0
                                
                            disponivel_edit = st.selectbox("Disponível", ["Sim", "Não"], index=default_index)

                            if st.form_submit_button("Salvar Alterações"):
                                if atualizar_produto(produto['ID'], nome_edit, preco_edit, curta_edit, longa_edit, link_edit, disponivel_edit):
                                    st.success("Produto atualizado!"); st.rerun()
                                else: st.error("Falha ao atualizar.")

                    if st.button("🗑️ Excluir", key=f"del_{produto.get('ID', index)}", type="primary"):
                        if excluir_produto(produto['ID']):
                            st.success("Produto excluído!"); st.rerun()
                        else: st.error("Falha ao excluir.")


with tab_promocoes:
    st.header("🔥 Gerenciador de Promoções")
    with st.expander("➕ Criar Nova Promoção", expanded=False):
        df_catalogo_promo = carregar_dados(SHEET_NAME_CATALOGO)
        if df_catalogo_promo.empty:
            st.warning("Cadastre produtos antes de criar uma promoção.")
        else:
            with st.form("form_nova_promocao", clear_on_submit=True):
                df_catalogo_promo['PRECO_FLOAT'] = pd.to_numeric(df_catalogo_promo['PRECO'].astype(str).str.replace(',', '.'), errors='coerce') 
                opcoes_produtos = {f"{row['NOME']} (R$ {row['PRECO_FLOAT']:.2f})": row['ID'] for _, row in df_catalogo_promo.dropna(subset=['PRECO_FLOAT', 'ID']).iterrows()}
                
                if not opcoes_produtos:
                    st.warning("Nenhum produto com preço válido encontrado no catálogo.")
                else:
                    produto_selecionado_nome = st.selectbox("Escolha o produto:", options=opcoes_produtos.keys())
                    preco_promocional = st.number_input("Novo Preço Promocional (R$)", min_value=0.01, format="%.2f")
                    col_data1, col_data2 = st.columns(2)
                    data_inicio = col_data1.date_input("Data de Início", value=datetime.now())
                    sem_data_fim = col_data2.checkbox("Não tem data para acabar")
                    data_fim = col_data2.date_input("Data de Fim", min_value=data_inicio) if not sem_data_fim else None
                    if st.form_submit_button("Lançar Promoção"):
                        id_produto = opcoes_produtos[produto_selecionado_nome]
                        produto_info = df_catalogo_promo[df_catalogo_promo['ID'] == id_produto].iloc[0]
                        data_fim_str = "" if sem_data_fim or data_fim is None else data_fim.strftime('%Y-%m-%d')
                        if criar_promocao(id_produto, produto_info['NOME'], produto_info['PRECO_FLOAT'], preco_promocional, data_inicio.strftime('%Y-%m-%d'), data_fim_str):
                            st.success("Promoção criada!"); st.rerun()

    st.markdown("---")
    st.subheader("Promoções Criadas")
    df_promocoes = carregar_dados(SHEET_NAME_PROMOCOES)
    if df_promocoes.empty:
        st.info("Nenhuma promoção foi criada ainda.")
    else:
        for index, promo in df_promocoes.iterrows():
            with st.container(border=True):
                st.markdown(f"**{promo.get('NOME_PRODUTO', 'N/A')}** | De R$ {promo.get('PRECO_ORIGINAL', 'N/A')} por **R$ {promo.get('PRECO_PROMOCIONAL', 'N/A')}**")
                st.caption(f"Status: {promo.get('STATUS', 'N/A')} | ID da Promoção: {promo.get('ID_PROMOCAO', 'N/A')}")
                
                with st.popover("📝 Editar Promoção"):
                    with st.form(f"edit_promo_{promo.get('ID_PROMOCAO', index)}", clear_on_submit=True):
                        st.markdown(f"Editando: **{promo.get('NOME_PRODUTO', 'N/A')}**")
                        preco_promo_val = float(str(promo.get('PRECO_PROMOCIONAL', '0')).replace(',','.'))
                        preco_promo_edit = st.number_input("Preço Promocional", value=preco_promo_val, format="%.2f")
                        
                        di_val = datetime.strptime(promo['DATA_INICIO'], '%Y-%m-%d') if promo.get('DATA_INICIO') and len(promo['DATA_INICIO']) >= 10 else datetime.now()
                        df_val = datetime.strptime(promo['DATA_FIM'], '%Y-%m-%d') if promo.get('DATA_FIM') and len(promo['DATA_FIM']) >= 10 else di_val
                        
                        data_inicio_edit = st.date_input("Data de Início", value=di_val, key=f"di_{promo.get('ID_PROMOCAO', index)}")
                        data_fim_edit = st.date_input("Data de Fim", value=df_val, min_value=data_inicio_edit, key=f"df_{promo.get('ID_PROMOCAO', index)}")
                        status_edit = st.selectbox("Status", ["Ativa", "Inativa"], index=["Ativa", "Inativa"].index(promo.get('STATUS', 'Ativa')), key=f"st_{promo.get('ID_PROMOCAO', index)}")
                        
                        if st.form_submit_button("Salvar"):
                            if atualizar_promocao(promo['ID_PROMOCAO'], preco_promo_edit, data_inicio_edit.strftime('%Y-%m-%d'), data_fim_edit.strftime('%Y-%m-%d'), status_edit):
                                st.success("Promoção atualizada!"); st.rerun()

                if st.button("🗑️ Excluir Promoção", key=f"del_promo_{promo.get('ID_PROMOCAO', index)}", type="primary"):
                    if excluir_promocao(promo['ID_PROMOCAO']):
                        st.success("Promoção excluída!"); st.rerun()

