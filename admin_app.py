# admin_app.py
import streamlit as st
import pandas as pd
import json
from datetime import datetime
import time
import requests 
import base64
import numpy as np 
import random
from io import StringIO

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos"
SHEET_NAME_PEDIDOS = "pedidos"
SHEET_NAME_PROMOCOES = "promocoes"

# --- Controle de Cache para forçar o reload do GitHub ---
if 'data_version' not in st.session_state:
    st.session_state['data_version'] = 0

# --- Configurações do GitHub (Lendo do st.secrets) ---
try:
    GITHUB_TOKEN = st.secrets["github"]["token"]
    REPO_NAME_FULL = st.secrets["github"]["repo_name"] 
    BRANCH = st.secrets["github"]["branch"] 
    
    # URLs de API
    GITHUB_RAW_BASE_URL = f"https://raw.githubusercontent.com/{REPO_NAME_FULL}/{BRANCH}"
    GITHUB_API_BASE_URL = f"https://api.github.com/repos/{REPO_NAME_FULL}/contents"
    
    HEADERS = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
except KeyError:
    st.error("Erro de configuração: As chaves 'token', 'repo_name' e 'branch' do GitHub precisam estar configuradas no secrets.toml."); st.stop()


# --- Funções Base do GitHub para Leitura e Escrita ---

@st.cache_data(ttl=5)
def fetch_github_data_v2(sheet_name, version_control):
    """Carrega dados de um CSV do GitHub via API (sem cache da CDN)."""
    csv_filename = f"{sheet_name}.csv"
    api_url = f"https://api.github.com/repos/{REPO_NAME_FULL}/contents/{csv_filename}?ref={BRANCH}"

    try:
        # Faz a requisição diretamente à API do GitHub
        response = requests.get(api_url, headers=HEADERS)
        if response.status_code != 200:
            st.warning(f"Erro ao buscar '{csv_filename}': {response.status_code}")
            return pd.DataFrame()

        # Decodifica o conteúdo base64 retornado pela API
        content = base64.b64decode(response.json()["content"]).decode("utf-8")

        # Converte o conteúdo em DataFrame
        from io import StringIO
        df = pd.read_csv(StringIO(content), sep=",")

        # Padroniza as colunas
        df.columns = df.columns.str.strip().str.upper()

        if "COLUNA" in df.columns:
            df.drop(columns=["COLUNA"], inplace=True)

        if "PRECO" in df.columns:
            df["PRECO"] = df["PRECO"].astype(str).str.replace(".", ",", regex=False)

        if sheet_name == SHEET_NAME_PEDIDOS and "STATUS" not in df.columns:
            df["STATUS"] = ""

        if sheet_name == SHEET_NAME_CATALOGO and "ID" in df.columns:
            df["ID"] = pd.to_numeric(df["ID"], errors="coerce")
            df.dropna(subset=["ID"], inplace=True)
            df["ID"] = df["ID"].astype(int)

        return df

    except Exception as e:
        st.error(f"Erro ao carregar dados de '{csv_filename}': {e}")
        return pd.DataFrame()


# Função auxiliar para o app usar o nome antigo e passar a versão
def carregar_dados(sheet_name):
    # Passa o contador de versão para a função em cache
    return fetch_github_data_v2(sheet_name, st.session_state['data_version'])

# Função para obter o SHA e fazer o PUT (commit)
def write_csv_to_github(df, sheet_name, commit_message):
    """Obtém o SHA do arquivo e faz o commit do novo DataFrame no GitHub."""
    csv_filename = f"{sheet_name}.csv"
    api_url = f"{GITHUB_API_BASE_URL}/{csv_filename}"
    
    # 1. Obter o SHA atual do arquivo
    response = requests.get(api_url, headers=HEADERS)
    if response.status_code != 200:
        if response.status_code == 404:
             sha = None
        else:
             st.error(f"Erro ao obter SHA: {response.status_code} - {response.json().get('message', 'Erro desconhecido')}")
             return False
    
    try:
        if response.status_code == 200:
            sha = response.json()['sha']
    except KeyError:
        st.error("Erro interno: SHA não encontrado na resposta do GitHub.")
        return False

    # 2. Preparar o novo conteúdo CSV
    csv_content = df.fillna('').to_csv(index=False, sep=',').replace('\n\n', '\n')
    
    # 3. Codificar o conteúdo em Base64
    content_base64 = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')

    # 4. Enviar a requisição PUT (Commit)
    payload = {
        "message": commit_message,
        "content": content_base64,
        "branch": BRANCH
    }
    if sha:
        payload["sha"] = sha 
    
    put_response = requests.put(api_url, headers=HEADERS, json=payload)
    
    if put_response.status_code in [200, 201]:
        return True
    else:
        error_message = put_response.json().get('message', 'Erro desconhecido')
        st.error(f"Falha no Commit: {put_response.status_code} - {error_message}")
        return False

# --- Funções de Pedidos (ESCRITA HABILITADA) ---

def atualizar_status_pedido(id_pedido, novo_status):
    df = carregar_dados(SHEET_NAME_PEDIDOS).copy()
    if df.empty: 
        st.error("Não há dados de pedidos para atualizar.")
        return False

    index_to_update = df[df['ID_PEDIDO'] == id_pedido].index
    if not index_to_update.empty:
        df.loc[index_to_update, 'STATUS'] = novo_status
        commit_msg = f"Atualizar status do pedido {id_pedido} para {novo_status}"
        return write_csv_to_github(df, SHEET_NAME_PEDIDOS, commit_msg)
    return False

def excluir_pedido(id_pedido):
    df = carregar_dados(SHEET_NAME_PEDIDOS).copy()
    if df.empty: return False

    df = df[df['ID_PEDIDO'] != id_pedido]
    commit_msg = f"Excluir pedido {id_pedido}"
    return write_csv_to_github(df, SHEET_NAME_PEDIDOS, commit_msg)


def exibir_itens_pedido(pedido_json, df_catalogo):
    try:
        detalhes_pedido = json.loads(pedido_json)
        for item in detalhes_pedido.get('itens', []):
            link_imagem = "https://via.placeholder.com/150?text=Sem+Imagem"
            item_id = pd.to_numeric(item.get('id'), errors='coerce')
            
            if not df_catalogo.empty and not pd.isna(item_id) and not df_catalogo[df_catalogo['ID'] == int(item_id)].empty: 
                link_na_tabela = str(df_catalogo[df_catalogo['ID'] == int(item_id)].iloc[0].get('LINKIMAGEM', link_imagem)).strip()
                
                if link_na_tabela.lower() != 'nan' and link_na_tabela:
                    link_imagem = link_na_tabela

            col_img, col_detalhes = st.columns([1, 4]); col_img.image(link_imagem, width=100)
            quantidade = item.get('qtd', item.get('quantidade', 0)); preco_unitario = float(item.get('preco', 0.0)); subtotal = item.get('subtotal')
            if subtotal is None: subtotal = preco_unitario * quantidade
            col_detalhes.markdown(f"**Produto:** {item.get('nome', 'N/A')}\n\n**Quantidade:** {quantidade}\n\n**Subtotal:** R$ {subtotal:.2f}"); st.markdown("---")
    except Exception as e: st.error(f"Erro ao processar itens do pedido: {e}")

# --- FUNÇÕES CRUD PARA PRODUTOS (ESCRITA HABILITADA) ---

def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel):
    df = carregar_dados(SHEET_NAME_CATALOGO).copy()
    
    df['ID'] = pd.to_numeric(df['ID'], errors='coerce')
    novo_id = df['ID'].max() + 1 if not df.empty and df['ID'].any() and not pd.isna(df['ID'].max()) else 1
    
    nova_linha = {
        'ID': novo_id, 
        'NOME': nome, 
        'PRECO': str(preco).replace('.', ','), 
        'DESCRICAOCURTA': desc_curta,
        'DESCRICAOLONGA': desc_longa,
        'LINKIMAGEM': link_imagem, 
        'DISPONIVEL': disponivel,
    }
    
    if not df.empty:
        df.loc[len(df)] = nova_linha
    else:
        df = pd.DataFrame([nova_linha])
        
    commit_msg = f"Adicionar produto: {nome} (ID: {novo_id})"
    return write_csv_to_github(df, SHEET_NAME_CATALOGO, commit_msg)


def excluir_produto(id_produto):
    df = carregar_dados(SHEET_NAME_CATALOGO).copy()
    if df.empty: return False

    df = df[df['ID'] != int(id_produto)]
    commit_msg = f"Excluir produto ID: {id_produto}"
    return write_csv_to_github(df, SHEET_NAME_CATALOGO, commit_msg)


def atualizar_produto(id_produto, nome, preco, desc_curta, desc_longa, link_imagem, disponivel):
    df = carregar_dados(SHEET_NAME_CATALOGO).copy()
    if df.empty: return False
    
    index_to_update = df[df['ID'] == int(id_produto)].index
    if not index_to_update.empty:
        idx = index_to_update[0]
        df.loc[idx, 'NOME'] = nome
        df.loc[idx, 'PRECO'] = str(preco).replace('.', ',') 
        df.loc[idx, 'DESCRICAOCURTA'] = desc_curta 
        df.loc[idx, 'DESCRICAOLONGA'] = desc_longa 
        df.loc[idx, 'LINKIMAGEM'] = link_imagem
        df.loc[idx, 'DISPONIVEL'] = disponivel
        
        commit_msg = f"Atualizar produto ID: {id_produto}"
        return write_csv_to_github(df, SHEET_NAME_CATALOGO, commit_msg)
    return False

# --- FUNÇÕES CRUD PARA PROMOÇÕES (ESCRITA HABILITADA) ---

def criar_promocao(id_produto, nome_produto, preco_original, preco_promocional, data_inicio, data_fim):
    df = carregar_dados(SHEET_NAME_PROMOCOES).copy()
    
    id_promocao = int(time.time()) 

    nova_linha = {
        'ID_PROMOCAO': id_promocao,
        'ID_PRODUTO': str(id_produto),
        'NOME_PRODUTO': nome_produto,
        'PRECO_ORIGINAL': str(preco_original),
        'PRECO_PROMOCIONAL': str(preco_promocional).replace('.', ','), 
        'STATUS': "Ativa",
        'DATA_INICIO': data_inicio,
        'DATA_FIM': data_fim
    }
    
    if not df.empty:
        df.loc[len(df)] = nova_linha
    else:
        df = pd.DataFrame([nova_linha])
    
    commit_msg = f"Criar promoção para {nome_produto}"
    return write_csv_to_github(df, SHEET_NAME_PROMOCOES, commit_msg)


def excluir_promocao(id_promocao):
    df = carregar_dados(SHEET_NAME_PROMOCOES).copy()
    if df.empty: return False
    
    df = df[df['ID_PROMOCAO'] != int(id_promocao)]
    commit_msg = f"Excluir promoção ID: {id_promocao}"
    return write_csv_to_github(df, SHEET_NAME_PROMOCOES, commit_msg)


def atualizar_promocao(id_promocao, preco_promocional, data_inicio, data_fim, status):
    df = carregar_dados(SHEET_NAME_PROMOCOES).copy()
    if df.empty: return False
    
    index_to_update = df[df['ID_PROMOCAO'] == int(id_promocao)].index
    if not index_to_update.empty:
        idx = index_to_update[0]
        df.loc[idx, 'PRECO_PROMOCIONAL'] = str(preco_promocional).replace('.', ',')
        df.loc[idx, 'DATA_INICIO'] = data_inicio
        df.loc[idx, 'DATA_FIM'] = data_fim
        df.loc[idx, 'STATUS'] = status
        
        commit_msg = f"Atualizar promoção ID: {id_promocao}"
        return write_csv_to_github(df, SHEET_NAME_PROMOCOES, commit_msg)
    return False


# --- LAYOUT DO APP ---
st.set_page_config(page_title="Admin Doce&Bella", layout="wide")
st.title("⭐ Painel de Administração | Doce&Bella")



# --- TABS DO SISTEMA ---
tab_pedidos, tab_produtos, tab_promocoes = st.tabs(["Pedidos", "Produtos", "🔥 Promoções"])

# --- VARIÁVEL DE CONTROLE DE VERSÃO JÁ ESTÁ NO TOPO ---

with tab_pedidos:
    st.header("📋 Pedidos Recebidos"); 
    if st.button("Recarregar Pedidos"): st.rerun() 
    
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
                        if atualizar_status_pedido(pedido['ID_PEDIDO'], novo_status="Finalizado"): 
                            st.success(f"Pedido {pedido['ID_PEDIDO']} finalizado!")
                            st.session_state['data_version'] += 1 
                            st.rerun() 
                        else: st.error("Falha ao finalizar pedido.")
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
                            if atualizar_status_pedido(pedido['ID_PEDIDO'], novo_status=""): 
                                st.success(f"Pedido {pedido['ID_PEDIDO']} revertido.")
                                st.session_state['data_version'] += 1 
                                st.rerun() 
                            else: st.error("Falha ao reverter status do pedido.")
                    with col_excluir:
                        if st.button("🗑️ Excluir Pedido", type="primary", key=f"excluir_{pedido['ID_PEDIDO']}", use_container_width=True):
                            if excluir_pedido(pedido['ID_PEDIDO']): 
                                st.success(f"Pedido {pedido['ID_PEDIDO']} excluído!")
                                st.session_state['data_version'] += 1 
                                st.rerun() 
                            else: st.error("Falha ao excluir o pedido.")
                    st.markdown("---"); exibir_itens_pedido(pedido['ITENS_PEDIDO'], df_catalogo_pedidos)


with tab_produtos:
    st.header("🛍️ Gerenciamento de Produtos")
    import time
    if int(time.time()) % 5 == 0:
        # A remoção do st.rerun() a cada 5 segundos é recomendada aqui,
        # pois pode causar recarregamento excessivo e problemas com o cache.
        # Caso o recarregamento imediato seja estritamente necessário para o fluxo de trabalho, mantenha,
        # mas para fins de estabilidade, esta linha foi removida.
        pass
        
    with st.expander("➕ Cadastrar Novo Produto", expanded=False):
        with st.form("form_novo_produto", clear_on_submit=True):
            col1, col2 = st.columns(2); nome_prod = col1.text_input("Nome do Produto*"); preco_prod = col1.number_input("Preço (R$)*", min_value=0.0, format="%.2f", step=0.50); link_imagem_prod = col1.text_input("URL da Imagem"); desc_curta_prod = col2.text_input("Descrição Curta"); desc_longa_prod = col2.text_area("Descrição Longa"); disponivel_prod = col2.selectbox("Disponível?", ("Sim", "Não"))
            
            # --- BLOCo ALTERADO ABAIXO ---
            if st.form_submit_button("Cadastrar Produto"):
                if not nome_prod or preco_prod <= 0: 
                    st.warning("Preencha Nome e Preço.")
                elif adicionar_produto(nome_prod, preco_prod, desc_curta_prod, desc_longa_prod, link_imagem_prod, disponivel_prod):
                    st.success("Produto cadastrado!")
                    st.session_state['data_version'] += 1  # Incrementa a versão
                    st.rerun()  # Força o Streamlit a recarregar e usar a nova versão
                else: 
                    st.error("Falha ao cadastrar.")
    
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
                    if link_imagem_produto.lower() == 'nan' or not link_imagem_produto:
                          img_url = "https://via.placeholder.com/150?text=Sem+Imagem"
                    else:
                          img_url = link_imagem_produto
                          
                    st.image(img_url, width=100)
                    
                with col2:
                    st.markdown(f"**{produto.get('NOME', 'N/A')}** (ID: {produto.get('ID', 'N/A')})")
                    st.markdown(f"**Preço:** R$ {produto.get('PRECO', 'N/A')}")
                    with st.popover("📝 Editar"):
                        with st.form(f"edit_form_{produto.get('ID', index)}", clear_on_submit=True):
                            st.markdown(f"Editando: **{produto.get('NOME', 'N/A')}**")
                            # Conversão segura do PRECO para float
                            preco_val_str = str(produto.get('PRECO', '0')).replace(',','.')
                            try:
                                preco_val = float(preco_val_str)
                            except ValueError:
                                preco_val = 0.0

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
                                    st.success("Produto atualizado!")
                                    st.session_state['data_version'] += 1 
                                    st.rerun() 
                                else: st.error("Falha ao atualizar.")

                    # Lógica de exclusão com atualização imediata (LÓGICA REQUISITADA)
                    if st.button("🗑️ Excluir", key=f"del_{produto.get('ID', index)}", type="primary"):
                        if excluir_produto(produto['ID']):
                            st.success("Produto excluído!")
                            st.session_state['data_version'] += 1 # 🔁 Força o reload do cache
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("Falha ao excluir.")


with tab_promocoes:
    st.header("🔥 Gerenciador de Promoções")
    with st.expander("➕ Criar Nova Promoção", expanded=False):
        df_catalogo_promo = carregar_dados(SHEET_NAME_CATALOGO)
        if df_catalogo_promo.empty:
            st.warning("Cadastre produtos antes de criar uma promoção.")
        else:
            with st.form("form_nova_promocao", clear_on_submit=True):
                # Conversão segura do PRECO para float
                df_catalogo_promo['PRECO_FLOAT'] = pd.to_numeric(df_catalogo_promo['PRECO'].astype(str).str.replace(',', '.'), errors='coerce') 
                opcoes_produtos = {f"{row['NOME']} (R$ {row['PRECO_FLOAT']:.2f})": row['ID'] for _, row in df_catalogo_promo.dropna(subset=['PRECO_FLOAT', 'ID']).iterrows()}
                
                if not opcoes_produtos:
                    st.warning("Nenhum produto com preço válido encontrado no catálogo.")
                else:
                    produto_selecionado_nome = st.selectbox("Escolha o produto:", options=opcoes_produtos.keys())
                    preco_promocional = st.number_input("Novo Preço Promocional (R$)", min_value=0.01, format="%.2f")
                    col_data1, col_data2 = st.columns(2)
                    data_inicio = col_data1.date_input("Data de Início", value=datetime.now().date()) 
                    sem_data_fim = col_data2.checkbox("Não tem data para acabar")
                    data_fim = col_data2.date_input("Data de Fim", min_value=data_inicio) if not sem_data_fim else None
                    if st.form_submit_button("Lançar Promoção"):
                        id_produto = opcoes_produtos[produto_selecionado_nome]
                        produto_info = df_catalogo_promo[df_catalogo_promo['ID'] == id_produto].iloc[0]
                        data_fim_str = "" if sem_data_fim or data_fim is None else data_fim.strftime('%Y-%m-%d')
                        if criar_promocao(id_produto, produto_info['NOME'], produto_info['PRECO_FLOAT'], preco_promocional, data_inicio.strftime('%Y-%m-%d'), data_fim_str):
                            st.success("Promoção criada!")
                            st.session_state['data_version'] += 1 
                            st.rerun()
                        else: st.error("Falha ao criar promoção.")

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
                        # Conversão segura do PRECO_PROMOCIONAL
                        preco_promo_val_str = str(promo.get('PRECO_PROMOCIONAL', '0')).replace(',','.')
                        try:
                             preco_promo_val = float(preco_promo_val_str)
                        except ValueError:
                             preco_promo_val = 0.0

                        preco_promo_edit = st.number_input("Preço Promocional", value=preco_promo_val, format="%.2f")
                        
                        # --- CORREÇÃO DO ERRO DE TYPE ERROR AQUI ---
                        
                        # Garante que DATA_INICIO é uma string válida para parsear
                        di_val_str = str(promo.get('DATA_INICIO', '')).strip()
                        if di_val_str and len(di_val_str) >= 10:
                            di_val = datetime.strptime(di_val_str, '%Y-%m-%d').date()
                        else:
                            di_val = datetime.now().date()
                            
                        # Garante que DATA_FIM é uma string válida para parsear
                        df_val_str = str(promo.get('DATA_FIM', '')).strip()
                        if df_val_str and len(df_val_str) >= 10:
                            df_val = datetime.strptime(df_val_str, '%Y-%m-%d').date()
                        else:
                            df_val = di_val # Se não houver data de fim, usa a data de início

                        data_inicio_edit = st.date_input("Data de Início", value=di_val, key=f"di_{promo.get('ID_PROMOCAO', index)}")
                        data_fim_edit = st.date_input("Data de Fim", value=df_val, min_value=data_inicio_edit, key=f"df_{promo.get('ID_PROMOCAO', index)}")
                        
                        # --- FIM DA CORREÇÃO ---

                        status_edit = st.selectbox("Status", ["Ativa", "Inativa"], index=["Ativa", "Inativa"].index(promo.get('STATUS', 'Ativa')), key=f"st_{promo.get('ID_PROMOCAO', index)}")
                        
                        if st.form_submit_button("Salvar"):
                            # Ajusta a data de fim para string vazia se for igual à data de início e a original era vazia
                            data_fim_para_salvar = ""
                            if df_val_str or data_fim_edit > data_inicio_edit:
                                data_fim_para_salvar = data_fim_edit.strftime('%Y-%m-%d')
                                
                            if atualizar_promocao(promo['ID_PROMOCAO'], preco_promo_edit, data_inicio_edit.strftime('%Y-%m-%d'), data_fim_para_salvar, status_edit):
                                st.success("Promoção atualizada!")
                                st.session_state['data_version'] += 1 
                                st.rerun()
                            else: st.error("Falha ao atualizar promoção.")

                if st.button("🗑️ Excluir Promoção", key=f"del_promo_{promo.get('ID_PROMOCAO', index)}", type="primary"):
                    if excluir_promocao(promo['ID_PROMOCAO']):
                        st.success("Promoção excluída!")
                        st.session_state['data_version'] += 1 
                        st.rerun()
                    else: st.error("Falha ao excluir promoção.")
