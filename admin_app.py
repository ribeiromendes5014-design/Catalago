# admin_app.py
import streamlit as st
import pandas as pd
import json
from datetime import datetime, date
import time
import requests 
import base64
import numpy as np 
import random
from io import StringIO

# --- Configurações de Dados (AJUSTADO) ---
SHEET_NAME_CATALOGO = "produtos_estoque" # <<< NOVO NOME DO ARQUIVO
SHEET_NAME_PEDIDOS = "pedidos"
SHEET_NAME_PROMOCOES = "promocoes"
# === NOVO: ARQUIVO DE CASHBACK E CONSTANTES ===
SHEET_NAME_CLIENTES_CASH = "clientes_cash"
CASHBACK_LANCAMENTOS_CSV = "lancamentos.csv" # Opcional: Se quiser registrar lançamentos
BONUS_INDICACAO_PERCENTUAL = 0.03 
CASHBACK_INDICADO_PRIMEIRA_COMPRA = 0.05
# ============================================

# --- Configurações do Repositório de Pedidos Externo (NOVO) ---
PEDIDOS_REPO_FULL = "ribeiromendes5014-design/fluxo"
PEDIDOS_BRANCH = "main" 

# --- Controle de Cache para forçar o reload do GitHub ---
if 'data_version' not in st.session_state:
    st.session_state['data_version'] = 0

# --- Configurações do GitHub (Lendo do st.secrets) ---
try:
    GITHUB_TOKEN = st.secrets["github"]["token"]
    REPO_NAME_FULL = st.secrets["github"]["repo_name"] 
    BRANCH = st.secrets["github"]["branch"] 
    
    # URLs de API (Base URL é para o repositório principal, mas será ajustado nas funções)
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
    
    # --- Repositório único (todos os CSVs estão no mesmo repo) ---
    repo_to_use = REPO_NAME_FULL
    branch_to_use = BRANCH

    api_url = f"https://api.github.com/repos/{repo_to_use}/contents/{csv_filename}?ref={branch_to_use}"


        # --- LÓGICA ROBUSTA PARA LER CSV COM CAMPOS COMPLEXOS (JSON) ---
        try:
            df = pd.read_csv(
                StringIO(content),  
                sep=",",  
                engine='python',  # Crucial para lidar com o JSON complexo no pedidos.csv
                on_bad_lines='warn'
            )
        except Exception as read_error:
            # Captura o erro na leitura para dar um feedback mais útil
            st.error(f"Erro de leitura do CSV de {csv_filename}. Causa: {read_error}. O arquivo pode estar vazio ou mal formatado.")
            return pd.DataFrame()
        # -------------------------------------------------------------

        df.columns = df.columns.str.strip().str.upper().str.replace(' ', '_')

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
        st.error(f"Erro geral ao carregar dados de '{csv_filename}': {e}")
        return pd.DataFrame()


# Função auxiliar para o app usar o nome antigo e passar a versão
def carregar_dados(sheet_name):
    # Passa o contador de versão para a função em cache
    return fetch_github_data_v2(sheet_name, st.session_state['data_version'])

# Função para obter o SHA e fazer o PUT (commit)
def write_csv_to_github(df, sheet_name, commit_message):
    """Obtém o SHA do arquivo e faz o commit do novo DataFrame no GitHub."""
    
    csv_filename = f"{sheet_name}.csv"
        
    if sheet_name == SHEET_NAME_PEDIDOS or sheet_name == SHEET_NAME_CLIENTES_CASH:
        repo_to_write = PEDIDOS_REPO_FULL
        branch_to_write = PEDIDOS_BRANCH
    else:
        repo_to_write = REPO_NAME_FULL
        branch_to_write = BRANCH
        
    GITHUB_API_BASE_URL_WRITE = f"https://api.github.com/repos/{repo_to_write}/contents"
    api_url = f"{GITHUB_API_BASE_URL_WRITE}/{csv_filename}"
    
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

    # 2. Preparar o novo conteúdo CSV (FORÇANDO UPPERCASE E UNDERSCORE PARA GRAVAÇÃO)
    df_to_save = df.copy()
    df_to_save.columns = df_to_save.columns.str.strip().str.upper().str.replace(' ', '_')
    
    csv_content = df_to_save.fillna('').to_csv(index=False, sep=',').replace('\n\n', '\n')
    
    # 3. Codificar o conteúdo em Base64
    content_base64 = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')

    # 4. Enviar a requisição PUT (Commit)
    payload = {
        "message": commit_message,
        "content": content_base64,
        "branch": branch_to_write
    }
    if sha:
        payload["sha"] = sha 
    
    put_response = requests.put(api_url, headers=HEADERS, json=payload)
    
    if put_response.status_code in [200, 201]:
        # Força a limpeza do cache de leitura após o sucesso da escrita
        fetch_github_data_v2.clear() 
        return True
    else:
        error_message = put_response.json().get('message', 'Erro desconhecido')
        st.error(f"Falha no Commit: {put_response.status_code} - {error_message}")
        return False
# --- FIM DA SUBSTITUIÇÃO DE write_csv_to_github ---


# --- SUBSTITUA A FUNÇÃO fetch_github_data_v2 COMPLETA ---
@st.cache_data(ttl=5)
def fetch_github_data_v2(sheet_name, version_control):
    """Carrega dados de um CSV do GitHub via API (sem cache da CDN)."""
    
    csv_filename = f"{sheet_name}.csv"
    
    # --- Lógica para Repositório Externo ---
    if sheet_name == SHEET_NAME_PEDIDOS or sheet_name == SHEET_NAME_CLIENTES_CASH:
        repo_to_use = PEDIDOS_REPO_FULL
        branch_to_use = PEDIDOS_BRANCH
    else:
        repo_to_use = REPO_NAME_FULL
        branch_to_use = BRANCH
        
    api_url = f"https://api.github.com/repos/{repo_to_use}/contents/{csv_filename}?ref={branch_to_use}"

    try:
        response = requests.get(api_url, headers=HEADERS)
        if response.status_code != 200:
            if sheet_name != SHEET_NAME_CLIENTES_CASH:
                st.warning(f"Erro ao buscar '{csv_filename}': Status {response.status_code}. Repositório: {repo_to_use}")
            return pd.DataFrame()

        content = base64.b64decode(response.json()["content"]).decode("utf-8")

        # --- LÓGICA ROBUSTA PARA LER CSV COM CAMPOS COMPLEXOS (JSON) ---
        try:
            df = pd.read_csv(
                StringIO(content),  
                sep=",",  
                engine='python', 
                on_bad_lines='warn'
            )
        except Exception as read_error:
            st.error(f"Erro de leitura do CSV de {csv_filename}. Causa: {read_error}. O arquivo pode estar vazio ou mal formatado.")
            return pd.DataFrame()
        # -------------------------------------------------------------

        # GARANTINDO O PADRÃO PARA BUSCA DE COLUNAS
        df.columns = df.columns.str.strip().str.upper().str.replace(' ', '_')

        if "COLUNA" in df.columns:
            df.drop(columns=["COLUNA"], inplace=True)

        if "PRECO" in df.columns:
            df["PRECO"] = df["PRECO"].astype(str).str.replace(".", ",", regex=False)

        if sheet_name == SHEET_NAME_PEDIDOS and "STATUS" not in df.columns:
            df["STATUS"] = ""
            
        if sheet_name == SHEET_NAME_PEDIDOS and "ID_PEDIDO" in df.columns:
            # Garante que ID_PEDIDO é uma string para evitar problemas de merge/lookup
            df['ID_PEDIDO'] = df['ID_PEDIDO'].astype(str)

        if sheet_name == SHEET_NAME_CATALOGO and "ID" in df.columns:
            df["ID"] = pd.to_numeric(df["ID"], errors="coerce")
            df.dropna(subset=["ID"], inplace=True)
            df["ID"] = df["ID"].astype(int)

        return df

    except Exception as e:
        st.error(f"Erro geral ao carregar dados de '{csv_filename}': {e}")
        return pd.DataFrame()

# --------------------------------------------------------------------------------
# --- FUNÇÕES DE LÓGICA DE CASHBACK (INTEGRADO AO ADMIN) ---
# --------------------------------------------------------------------------------

@st.cache_data(ttl=5)
def carregar_clientes_cashback():
    """Carrega e padroniza o DataFrame de clientes de cashback."""
    df = carregar_dados(SHEET_NAME_CLIENTES_CASH).copy()
    if df.empty:
        # Colunas padrão do cashback_system.py
        cols = ['NOME', 'APELIDO/DESCRIÇÃO', 'TELEFONE', 'CASHBACK_DISPONÍVEL', 'GASTO_ACUMULADO', 'NIVEL_ATUAL', 'INDICADO_POR', 'PRIMEIRA_COMPRA_FEITA']
        df = pd.DataFrame(columns=[c.upper().replace(' ', '_') for c in cols])
        df['TELEFONE'] = df['TELEFONE'].astype(str) # Garante que a coluna de telefone existe
        return df

    # Renomeia e padroniza as colunas conforme o schema do cashback_system.py
    df.rename(columns={
        'TELEFONE': 'TELEFONE', 
        'CASHBACK_DISPONIVEL': 'CASHBACK_DISPONIVEL',
        'NIVEL_ATUAL': 'NIVEL_ATUAL'
    }, inplace=True, errors='ignore')

    # Limpa o telefone para ser usado como chave única
    df['CONTATO_LIMPO'] = df['TELEFONE'].astype(str).str.replace(r'\D', '', regex=True).str.strip()
    df['CASHBACK_DISPONIVEL'] = pd.to_numeric(df['CASHBACK_DISPONIVEL'], errors='coerce').fillna(0.0)
    df['GASTO_ACUMULADO'] = pd.to_numeric(df['GASTO_ACUMULADO'], errors='coerce').fillna(0.0)
    df['NIVEL_ATUAL'] = df['NIVEL_ATUAL'].fillna('Prata')
    
    return df

def cadastrar_cliente_cashback(df_clientes, nome, contato, nivel='Prata'):
    """Adiciona um novo cliente ao DF de clientes (com status de primeira compra)."""
    novo_cliente = {
        'NOME': nome, 
        'APELIDO/DESCRIÇÃO': '', 
        'TELEFONE': contato,
        'CASHBACK_DISPONIVEL': 0.00, 
        'GASTO_ACUMULADO': 0.00, 
        'NIVEL_ATUAL': nivel,
        'INDICADO_POR': '', 
        'PRIMEIRA_COMPRA_FEITA': 'FALSE',
        'CONTATO_LIMPO': contato
    }
    return pd.concat([df_clientes, pd.DataFrame([novo_cliente])], ignore_index=True)

def calcular_nivel_e_beneficios(gasto_acumulado: float):
    # Lógica de níveis simplificada (Mantenha a lógica completa do cashback_system.py aqui se for preciso)
    if gasto_acumulado >= 1000.01: nivel, cb_normal = 'Diamante', 0.15
    elif gasto_acumulado >= 200.01: nivel, cb_normal = 'Ouro', 0.07
    else: nivel, cb_normal = 'Prata', 0.03
    return nivel, cb_normal

def lancar_venda_cashback(nome: str, contato: str, valor_venda: float):
    """Lança a venda, cadastra o cliente se novo, credita o cashback e persiste o DF."""
    df_clientes = carregar_clientes_cashback()
    contato_limpo = str(contato).replace('(', '').replace(')', '').replace('-', '').replace(' ', '').strip()
    valor_venda = float(valor_venda)
    
    # 1. Busca Cliente (Pelo Contato Limpo)
    cliente_idx = df_clientes[df_clientes['CONTATO_LIMPO'] == contato_limpo].index
    
    # Flags iniciais
    is_new_customer = cliente_idx.empty
    
    if is_new_customer:
        # 1.1. Cadastro Automático
        df_clientes = cadastrar_cliente_cashback(df_clientes, nome, contato_limpo, nivel='Prata')
        cliente_idx = df_clientes[df_clientes['CONTATO_LIMPO'] == contato_limpo].index
        idx = cliente_idx[0]
        st.toast(f"Cliente '{nome}' cadastrado automaticamente.", icon='👤')
    else:
        idx = cliente_idx[0]
    
    # 2. Cálculo do Cashback
    cliente = df_clientes.loc[idx].copy()
    gasto_antigo = cliente['GASTO_ACUMULADO']
    nivel_antigo = cliente['NIVEL_ATUAL']
    
    nivel_atual, cb_normal_rate = calcular_nivel_e_beneficios(gasto_antigo)
    taxa_final = cb_normal_rate
    
    # Se for a primeira compra E não tiver indicador, ou for novo, usa taxa de primeira compra
    if cliente['PRIMEIRA_COMPRA_FEITA'].upper() == 'FALSE' or is_new_customer:
        taxa_final = CASHBACK_INDICADO_PRIMEIRA_COMPRA # 5% na primeira compra (mesmo sem indicador)
        
    cashback_credito = round(valor_venda * taxa_final, 2)

    # 3. Atualiza Saldos
    df_clientes.loc[idx, 'CASHBACK_DISPONIVEL'] = round(cliente['CASHBACK_DISPONIVEL'] + cashback_credito, 2)
    df_clientes.loc[idx, 'GASTO_ACUMULADO'] = round(cliente['GASTO_ACUMULADO'] + valor_venda, 2)
    df_clientes.loc[idx, 'PRIMEIRA_COMPRA_FEITA'] = 'TRUE'
    
    # Recalcula Nível
    novo_nivel, _ = calcular_nivel_e_beneficios(df_clientes.loc[idx, 'GASTO_ACUMULADO'])
    df_clientes.loc[idx, 'NIVEL_ATUAL'] = novo_nivel
    
    # 4. Persiste o DataFrame de Clientes
    if write_csv_to_github(df_clientes, SHEET_NAME_CLIENTES_CASH, f"CRÉDITO CASHBACK: {nome} (R$ {cashback_credito:.2f})"):
        st.toast(f"Cashback creditado com sucesso! +R$ {cashback_credito:.2f}", icon='💵')
        st.toast(f"Novo Nível: {novo_nivel.upper()}", icon='⭐')
        return True
    else:
        st.error("Falha CRÍTICA ao salvar o crédito de Cashback no GitHub.")
        return False
        
# --------------------------------------------------------------------------------
# --- FIM DAS FUNÇÕES DE LÓGICA DE CASHBACK ---
# --------------------------------------------------------------------------------


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


def exibir_itens_pedido(id_pedido, pedido_json, df_catalogo):
    """
    Exibe os itens do pedido com um checkbox de separação e retorna
    a porcentagem de itens separados (com imagem do próprio JSON se disponível).
    """
    try:
        # A lógica para a coluna ITENS_JSON pode vir com aspas duplas,
        # então tentamos decodificar como JSON.
        if pd.isna(pedido_json) or not str(pedido_json).strip():
            st.warning(f"Pedido {id_pedido} não possui detalhes de itens para exibir.")
            return 0

        # Tenta carregar o JSON (assumindo que está com aspas duplas escapadas)
        try:
            detalhes_pedido = json.loads(pedido_json)
        except json.JSONDecodeError:
            # Tenta limpar as aspas duplas extras que podem ter vindo da serialização do CSV
            pedido_json_limpo = pedido_json.strip().replace('""', '"').strip('"')
            detalhes_pedido = json.loads(pedido_json_limpo)
            
        itens = detalhes_pedido.get('itens', [])

        if not itens:
            st.warning(f"Pedido {id_pedido} não possui uma lista de itens válida.")
            return 0

        total_itens = len(itens)
        itens_separados = 0

        key_progress = f'pedido_{id_pedido}_itens_separados'
        if key_progress not in st.session_state:
            st.session_state[key_progress] = [False] * total_itens

        for i, item in enumerate(itens):
            # 🖼️ 1️⃣ Prioriza a imagem do próprio JSON
            link_imagem = item.get('imagem', '').strip()

            # 🖼️ 2️⃣ Se não tiver, tenta achar no catálogo
            if not link_imagem and not df_catalogo.empty:
                item_id = pd.to_numeric(item.get('id'), errors='coerce')
                if not pd.isna(item_id):
                    match = df_catalogo[df_catalogo['ID'] == int(item_id)]
                    if not match.empty:
                        link_catalogo = str(match.iloc[0].get('LINKIMAGEM', '')).strip()
                        if link_catalogo.lower() != 'nan' and link_catalogo:
                            link_imagem = link_catalogo

            # 🖼️ 3️⃣ Fallback se continuar sem imagem
            if not link_imagem or link_imagem.lower() == 'nan':
                link_imagem = "https://via.placeholder.com/150?text=Sem+Imagem"

            # Layout
            col_check, col_img, col_detalhes = st.columns([0.5, 1, 3.5])

            checked = col_check.checkbox(
                label="Separado",
                value=st.session_state[key_progress][i],
                key=f"check_{id_pedido}_{i}",
            )
            if checked != st.session_state[key_progress][i]:
                st.session_state[key_progress][i] = checked
                st.rerun()

            # 🖼️ Exibe a imagem real do produto
            col_img.image(link_imagem, width=100)

            quantidade = item.get('quantidade', item.get('qtd', 0))
            preco_unitario = float(item.get('preco', 0.0))
            subtotal = item.get('subtotal') or preco_unitario * quantidade

            col_detalhes.markdown(
                f"**Produto:** {item.get('nome', 'N/A')}\n\n"
                f"**Quantidade:** {quantidade}\n\n"
                f"**Subtotal:** R$ {subtotal:.2f}"
            )
            st.markdown("---")

            if st.session_state[key_progress][i]:
                itens_separados += 1

        progresso = int((itens_separados / total_itens) * 100) if total_itens > 0 else 0
        return progresso

    except json.JSONDecodeError:
        st.error(f"Erro ao processar itens do pedido {id_pedido}: O formato dos dados dos itens é inválido. [JSON Decode Error]")
        return 0
    except Exception as e:
        st.error(f"Erro inesperado ao processar itens do pedido {id_pedido}: {e}")
        return 0
        
# --- FUNÇÕES CRUD PARA PRODUTOS (ESCRITA HABILITADA) ---
# ... (Funções CRUD para Produtos e Promoções permanecem inalteradas) ...

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

    df = df[df['ID'] != id_produto]
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
    st.header("📋 Pedidos Recebidos")

    if st.button("Recarregar Pedidos"):
        # Limpa o estado de separação dos itens ao recarregar
        keys_to_delete = [k for k in st.session_state if k.startswith('pedido_') and k.endswith('_itens_separados')]
        for k in keys_to_delete:
            del st.session_state[k]
        st.session_state['data_version'] += 1
        st.rerun()

    df_pedidos_raw = carregar_dados(SHEET_NAME_PEDIDOS)
    df_catalogo_pedidos = carregar_dados(SHEET_NAME_CATALOGO)

    if df_pedidos_raw.empty:
        st.info("Nenhum pedido foi encontrado na planilha.")
    else:
        df_pedidos_raw['DATA_HORA'] = pd.to_datetime(df_pedidos_raw['DATA_HORA'], errors='coerce')

        st.subheader("🔍 Filtrar Pedidos")
        col_filtro1, col_filtro2 = st.columns(2)
        data_filtro = col_filtro1.date_input("Filtrar por data:", value=None)
        texto_filtro = col_filtro2.text_input("Buscar por cliente ou produto:")

        df_filtrado = df_pedidos_raw.copy()
        if data_filtro:
            df_filtrado = df_filtrado[df_filtrado['DATA_HORA'].dt.date == data_filtro]
        if texto_filtro.strip():
            texto_filtro = texto_filtro.lower()
            df_filtrado = df_filtrado[
                df_filtrado['NOME_CLIENTE'].astype(str).str.lower().str.contains(texto_filtro)
                | df_filtrado['ITENS_PEDIDO'].astype(str).str.lower().str.contains(texto_filtro)
            ]

        st.markdown("---")
        # Pedidos PENDENTES são aqueles com status 'PENDENTE' (do novo fluxo)
        pedidos_pendentes = df_filtrado[df_filtrado['STATUS'] == 'PENDENTE']
        pedidos_finalizados = df_filtrado[df_filtrado['STATUS'] == 'Finalizado']
        pedidos_separacao = df_filtrado[df_filtrado['STATUS'].isin(['', 'Separacao', 'SEPARACAO'])] # Pedidos mais antigos ou em separação

        # Combina pedidos de separação e pendentes para a fila de trabalho
        pedidos_a_trabalhar = pd.concat([pedidos_separacao, pedidos_pendentes]).drop_duplicates(subset=['ID_PEDIDO'])
        
        # ======================
        # PEDIDOS PENDENTES (AGUARDANDO CRÉDITO)
        # ======================
        st.header("⏳ Pedidos Pendentes / Em Separação")
        if pedidos_a_trabalhar.empty:
            st.info("Nenhum pedido pendente ou em separação encontrado.")
        else:
            for index, pedido in pedidos_a_trabalhar.iloc[::-1].iterrows():
                id_pedido = pedido['ID_PEDIDO']
                data_hora_str = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indisponível"
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {data_hora_str} - Total: R$ {pedido['VALOR_TOTAL']}"

                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{id_pedido}`")
                    st.markdown(f"**Status Atual:** `{pedido['STATUS']}`")

                    # ✅ Usa a coluna correta (ITENS_JSON)
                    progresso_separacao = exibir_itens_pedido(id_pedido, pedido['ITENS_JSON'], df_catalogo_pedidos)

                    st.markdown(f"**Progresso de Separação:** {progresso_separacao}%")
                    st.progress(progresso_separacao / 100)

                    pode_finalizar = progresso_separacao == 100
                    
                    # --- NOVO FLUXO DE FINALIZAÇÃO COM CASHBACK ---
                    if st.button("✅ Finalizar Pedido e Creditar Cashback", key=f"finalizar_{id_pedido}", disabled=not pode_finalizar):
                        
                        nome_cliente = pedido['NOME_CLIENTE']
                        contato_cliente = pedido['CONTATO_CLIENTE']
                        valor_venda = float(pedido['VALOR_TOTAL']) 
                        
                        # 1. Lança o Cashback (Cadastra se novo, credita se existente)
                        if lancar_venda_cashback(nome_cliente, contato_cliente, valor_venda):
                            # 2. Cashback SUCESSO: Agora finaliza o pedido (muda status para Finalizado)
                            if atualizar_status_pedido(id_pedido, novo_status="Finalizado"):
                                st.success(f"Pedido {id_pedido} FINALIZADO e Cashback CREDITADO!")
                                # Limpa estado e força reload de tudo
                                st.session_state['data_version'] += 1 
                                st.cache_data.clear() # Limpa o cache de clientes de cashback para ver o novo saldo
                                st.rerun()
                            else:
                                st.error("Falha ao finalizar pedido no pedidos.csv. O Cashback foi creditado, verifique o arquivo!")
                        else:
                            # 3. Cashback FALHA: Não finaliza o pedido
                            st.error(f"❌ Falha CRÍTICA: O Cashback não foi creditado. Pedido {id_pedido} mantido como PENDENTE.")
                    
                    # --- FIM NOVO FLUXO DE FINALIZAÇÃO ---


        # ======================
        # PEDIDOS FINALIZADOS
        # ======================
        st.header("✅ Pedidos Finalizados")
        if pedidos_finalizados.empty:
            st.info("Nenhum pedido finalizado encontrado.")
        else:
            for index, pedido in pedidos_finalizados.iloc[::-1].iterrows():
                data_hora_str = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indisponível"
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {data_hora_str} - Total: R$ {pedido['VALOR_TOTAL']}"

                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{pedido['ID_PEDIDO']}`")

                    col_reverter, col_excluir = st.columns(2)
                    with col_reverter:
                        if st.button("↩️ Reverter para Pendente", key=f"reverter_{pedido['ID_PEDIDO']}", use_container_width=True):
                            # Reverte o status para PENDENTE (novo status de trabalho)
                            if atualizar_status_pedido(pedido['ID_PEDIDO'], novo_status="PENDENTE"): 
                                st.success(f"Pedido {pedido['ID_PEDIDO']} revertido para PENDENTE.")
                                st.session_state['data_version'] += 1
                                st.rerun()
                            else:
                                st.error("Falha ao reverter status do pedido.")
                    with col_excluir:
                        if st.button("🗑️ Excluir Pedido", type="primary", key=f"excluir_{pedido['ID_PEDIDO']}", use_container_width=True):
                            if excluir_pedido(pedido['ID_PEDIDO']):
                                st.success(f"Pedido {pedido['ID_PEDIDO']} excluído!")
                                st.session_state['data_version'] += 1
                                st.rerun()
                            else:
                                st.error("Falha ao excluir o pedido.")

                    st.markdown("---")
                    # ✅ Também usa a coluna ITENS_JSON aqui
                    exibir_itens_pedido(pedido['ID_PEDIDO'], pedido['ITENS_JSON'], df_catalogo_pedidos)


# --- FUNÇÕES CRUD PARA PRODUTOS (ESCRITA HABILITADA) ---
# ... (Restante do código CRUD de Produtos e Promoções permanece inalterado) ...
# O código continua aqui, mas não é repetido para brevidade.



with tab_promocoes:
    st.header("🔥 Gerenciador de Promoções")
    with st.expander("➕ Criar Nova Promoção", expanded=False):
        df_catalogo_promo = carregar_dados(SHEET_NAME_CATALOGO)
        
        # --- INÍCIO DA CORREÇÃO 2 ---
        if df_catalogo_promo.empty:
            st.warning("Cadastre produtos antes de criar uma promoção.")
        # Adiciona uma verificação para garantir que a coluna 'PRECO' existe
        elif 'PRECO' not in df_catalogo_promo.columns:
            st.error("ERRO: O arquivo 'produtos.csv' não contém uma coluna chamada 'PRECO'. Verifique seu arquivo no GitHub.")
        # --- FIM DA CORREÇÃO 2 ---
        else:
            with st.form("form_nova_promocao", clear_on_submit=True):
                # Esta linha agora é segura, pois já verificamos a existência da coluna
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
                    # --- CORREÇÃO DA CHAVE DO FORMULÁRIO DE PROMOÇÃO (FEITA NA CORREÇÃO ANTERIOR) ---
                    promo_form_key = f"edit_promo_{promo.get('ID_PROMOCAO', index)}_{index}_tab_promo"
                    
                    with st.form(promo_form_key, clear_on_submit=True):
                        st.markdown(f"Editando: **{promo.get('NOME_PRODUTO', 'N/A')}**")
                        
                        preco_promo_val_str = str(promo.get('PRECO_PROMOCIONAL', '0')).replace(',','.')
                        try:
                             preco_promo_val = float(preco_promo_val_str)
                        except ValueError:
                             preco_promo_val = 0.0

                        preco_promo_edit = st.number_input("Preço Promocional", value=preco_promo_val, format="%.2f")
                        
                        # --- CORREÇÃO DO ERRO DE TYPE ERROR (Já aplicada na versão anterior) ---
                        
                        di_val_str = str(promo.get('DATA_INICIO', '')).strip()
                        if di_val_str and len(di_val_str) >= 10:
                            di_val = datetime.strptime(di_val_str, '%Y-%m-%d').date()
                        else:
                            di_val = datetime.now().date()
                            
                        df_val_str = str(promo.get('DATA_FIM', '')).strip()
                        if df_val_str and len(df_val_str) >= 10:
                            df_val = datetime.strptime(df_val_str, '%Y-%m-%d').date()
                        else:
                            df_val = di_val 

                        data_inicio_edit = st.date_input("Data de Início", value=di_val, key=f"di_{promo.get('ID_PROMOCAO', index)}")
                        data_fim_edit = st.date_input("Data de Fim", value=df_val, min_value=data_inicio_edit, key=f"df_{promo.get('ID_PROMOCAO', index)}")
                        
                        status_edit = st.selectbox("Status", ["Ativa", "Inativa"], index=["Ativa", "Inativa"].index(promo.get('STATUS', 'Ativa')), key=f"st_{promo.get('ID_PROMOCAO', index)}")
                        
                        if st.form_submit_button("Salvar"):
                            data_fim_para_salvar = ""
                            # Salva a data de fim apenas se ela não era vazia ou se foi alterada para um valor válido
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











