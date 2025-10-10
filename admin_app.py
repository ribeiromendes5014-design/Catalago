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
import ast
import re

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos_estoque"
SHEET_NAME_PEDIDOS = "pedidos"
SHEET_NAME_PROMOCOES = "promocoes"
SHEET_NAME_CLIENTES_CASH = "clientes_cash"
SHEET_NAME_CUPONS = "cupons" # <-- NOVO: Adicionado para cupons
CASHBACK_LANCAMENTOS_CSV = "lancamentos.csv"
# Constantes de Cálculo (Baseado no fluxo cashback_system.py)
BONUS_INDICACAO_PERCENTUAL = 0.03
CASHBACK_INDICADO_PRIMEIRA_COMPRA = 0.05
# ==============================================

# --- Configurações do Repositório de Pedidos Externo ---
# Assumindo que os dados de Pedidos e Clientes Cashback estão aqui:
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
    
    # --- Lógica para Repositório Externo ---
    # MODIFICADO: Cupons e Clientes ficam no mesmo repo dos pedidos
    if sheet_name in [SHEET_NAME_PEDIDOS, SHEET_NAME_CLIENTES_CASH, SHEET_NAME_CUPONS]:
        repo_to_use = PEDIDOS_REPO_FULL
        branch_to_use = PEDIDOS_BRANCH
    else:
        repo_to_use = REPO_NAME_FULL
        branch_to_use = BRANCH
        
    api_url = f"https://api.github.com/repos/{repo_to_use}/contents/{csv_filename}?ref={branch_to_use}"

    try:
        response = requests.get(api_url, headers=HEADERS)
        if response.status_code != 200:
            # Não mostra aviso para arquivos que podem não existir inicialmente
            if sheet_name not in [SHEET_NAME_CLIENTES_CASH, SHEET_NAME_CUPONS]:
                st.warning(f"Erro ao buscar '{csv_filename}': Status {response.status_code}. Repositório: {repo_to_use}")
            return pd.DataFrame()

        content = base64.b64decode(response.json()["content"]).decode("utf-8")
        
        if not content.strip(): # Se o arquivo estiver vazio
            return pd.DataFrame()

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

        df.columns = df.columns.str.strip().str.upper().str.replace(' ', '_')

        if "COLUNA" in df.columns:
            df.drop(columns=["COLUNA"], inplace=True)

        if "PRECO" in df.columns:
            df["PRECO"] = df["PRECO"].astype(str).str.replace(".", ",", regex=False)

        if sheet_name == SHEET_NAME_PEDIDOS and "STATUS" not in df.columns:
            df["STATUS"] = ""
            
        if sheet_name == SHEET_NAME_PEDIDOS and "ID_PEDIDO" in df.columns:
            df['ID_PEDIDO'] = df['ID_PEDIDO'].astype(str)

        if sheet_name == SHEET_NAME_CATALOGO and "ID" in df.columns:
            df["ID"] = pd.to_numeric(df["ID"], errors="coerce")
            df.dropna(subset=["ID"], inplace=True)
            df["ID"] = df["ID"].astype(int)

        # === Padronização para Clientes Cashback (limpeza e types) ===
        if sheet_name == SHEET_NAME_CLIENTES_CASH:
             if 'CASHBACK_DISPONÍVEL' in df.columns:
                 df.rename(columns={'CASHBACK_DISPONÍVEL': 'CASHBACK_DISPONIVEL'}, inplace=True)
             if 'TELEFONE' in df.columns:
                 df.rename(columns={'TELEFONE': 'CONTATO'}, inplace=True)

             # Padroniza e limpa o campo de contato para busca
             if 'CONTATO' in df.columns:
                 # Cria 'CONTATO_LIMPO' para buscas
                 df['CONTATO_LIMPO'] = df['CONTATO'].astype(str).str.replace(r'\D', '', regex=True).str.strip() 
                 df['CASHBACK_DISPONIVEL'] = pd.to_numeric(df.get('CASHBACK_DISPONIVEL', 0.0), errors='coerce').fillna(0.0)
                 df['GASTO_ACUMULADO'] = pd.to_numeric(df.get('GASTO_ACUMULADO', 0.0), errors='coerce').fillna(0.0)
                 df['NIVEL_ATUAL'] = df['NIVEL_ATUAL'].fillna('Prata')
             
             for col in ['NOME', 'CONTATO', 'CASHBACK_DISPONIVEL', 'NIVEL_ATUAL', 'GASTO_ACUMULADO', 'CONTATO_LIMPO', 'PRIMEIRA_COMPRA_FEITA']:
                 if col not in df.columns: df[col] = '' if col not in ['CASHBACK_DISPONIVEL', 'GASTO_ACUMULADO'] else 0.0
             df.dropna(subset=['CONTATO_LIMPO'], inplace=True) # Usa o campo limpo para verificar dados válidos
        # ===================================================================

        return df

    except Exception as e:
        st.error(f"Erro ao carregar dados de '{csv_filename}': {e}")
        return pd.DataFrame()


# Função auxiliar para o app usar o nome antigo e passar a versão
def carregar_dados(sheet_name):
    # Passa o contador de versão para a função em cache
    return fetch_github_data_v2(sheet_name, st.session_state['data_version'])

# Função auxiliar para carregar o DataFrame de Clientes Cashback
def carregar_clientes_cashback():
    """Alias para carregar o DataFrame de clientes cashback."""
    # Garante que o DataFrame de Clientes Cashback seja carregado com a lógica de versionamento
    return carregar_dados(SHEET_NAME_CLIENTES_CASH) 

# Função para obter o SHA e fazer o PUT (commit)
def write_csv_to_github(df, sheet_name, commit_message):
    """Obtém o SHA do arquivo e faz o commit do novo DataFrame no GitHub."""
    
    csv_filename = f"{sheet_name}.csv"
        
    if sheet_name in [SHEET_NAME_PEDIDOS, SHEET_NAME_CLIENTES_CASH, SHEET_NAME_CUPONS]:
        repo_to_write = PEDIDOS_REPO_FULL
        branch_to_write = PEDIDOS_BRANCH
    else:
        repo_to_write = REPO_NAME_FULL
        branch_to_write = BRANCH
        
    GITHUB_API_BASE_URL_WRITE = f"https://api.github.com/repos/{repo_to_write}/contents"
    api_url = f"{GITHUB_API_BASE_URL_WRITE}/{csv_filename}"
    
    # 1. Obter o SHA atual do arquivo
    response = requests.get(api_url, headers=HEADERS)
    sha = None
    if response.status_code == 200:
        sha = response.json().get('sha')
    elif response.status_code != 404:
        st.error(f"Erro ao obter SHA: {response.status_code} - {response.json().get('message', 'Erro desconhecido')}")
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
        fetch_github_data_v2.clear() 
        return True
    else:
        error_message = put_response.json().get('message', 'Erro desconhecido')
        st.error(f"Falha no Commit: {put_response.status_code} - {error_message}")
        return False

# --------------------------------------------------------------------------------
# --- FUNÇÕES DE LÓGICA DE CASHBACK (INTEGRADO AO ADMIN) ---
# (O código existente de cashback continua aqui, sem alterações)
# --------------------------------------------------------------------------------

def calcular_nivel_e_beneficios(gasto_acumulado: float):
    if gasto_acumulado >= 1000.01: nivel, cb_normal = 'Diamante', 0.15
    elif gasto_acumulado >= 200.01: nivel, cb_normal = 'Ouro', 0.07
    else: nivel, cb_normal = 'Prata', 0.03
    return nivel, cb_normal

def cadastrar_cliente_cashback(df_clientes, nome, contato_limpo, nivel='Prata'):
    novo_cliente = {
        'NOME': nome, 
        'APELIDO/DESCRIÇÃO': '', 
        'CONTATO': contato_limpo,
        'CASHBACK_DISPONIVEL': 0.00, 
        'GASTO_ACUMULADO': 0.00, 
        'NIVEL_ATUAL': nivel,
        'INDICADO_POR': '', 
        'PRIMEIRA_COMPRA_FEITA': 'FALSE',
        'CONTATO_LIMPO': contato_limpo
    }
    return pd.concat([df_clientes, pd.DataFrame([novo_cliente])], ignore_index=True)

def lancar_venda_cashback(nome: str, contato: str, valor_cashback_credito: float):
    contato_limpo = str(contato).replace('(', '').replace(')', '').replace('-', '').replace(' ', '').strip()
    df_clientes = carregar_clientes_cashback()
    cliente_idx = df_clientes[df_clientes['CONTATO_LIMPO'] == contato_limpo].index
    
    is_new_customer = cliente_idx.empty
    if is_new_customer:
        df_clientes = cadastrar_cliente_cashback(df_clientes, nome, contato_limpo, nivel='Prata')
        cliente_idx = df_clientes[df_clientes['CONTATO_LIMPO'] == contato_limpo].index
        idx = cliente_idx[0]
        st.toast(f"Cliente '{nome}' cadastrado automaticamente.", icon='👤')
    else:
        idx = cliente_idx[0]
        
    cliente = df_clientes.loc[idx].copy()
    df_clientes.loc[idx, 'CASHBACK_DISPONIVEL'] = round(cliente['CASHBACK_DISPONIVEL'] + valor_cashback_credito, 2)
    df_clientes.loc[idx, 'PRIMEIRA_COMPRA_FEITA'] = 'TRUE'
    novo_nivel, _ = calcular_nivel_e_beneficios(df_clientes.loc[idx, 'GASTO_ACUMULADO'])
    df_clientes.loc[idx, 'NIVEL_ATUAL'] = novo_nivel
    
    if write_csv_to_github(df_clientes, SHEET_NAME_CLIENTES_CASH, f"CRÉDITO CASHBACK: {nome} (R$ {valor_cashback_credito:.2f})"):
        st.toast(f"Cashback creditado com sucesso! +R$ {valor_cashback_credito:.2f}", icon='💵')
        st.toast(f"Novo Nível: {novo_nivel.upper()}", icon='⭐')
        return True
    else:
        st.error("Falha CRÍTICA ao salvar o crédito de Cashback no GitHub.")
        return False

def calcular_cashback_a_creditar(pedido_json, df_catalogo):
    valor_cashback_total = 0.0
    pedido_str = str(pedido_json).strip()
    if not pedido_str or pedido_str.lower() in ('nan', '{}', ''):
        return 0.0
    try:
        try:
            detalhes_pedido = json.loads(pedido_str)
        except (json.JSONDecodeError, TypeError):
            detalhes_pedido = ast.literal_eval(pedido_str)
        itens = detalhes_pedido.get('itens', [])
        for item in itens:
            try:
                item_id = int(item.get('id', -1))
            except (TypeError, ValueError):
                continue
            cashback_percent_str = str(item.get('cashbackpercent', 0)).replace(',', '.')
            try:
                cashback_percent = float(cashback_percent_str)
            except ValueError:
                cashback_percent = 0.0
            if cashback_percent == 0.0 and not df_catalogo.empty:
                produto_catalogo = df_catalogo.loc[df_catalogo['ID'] == item_id]
                if not produto_catalogo.empty:
                    catalogo_cashback_str = str(produto_catalogo.iloc[0].get('CASHBACKPERCENT', 0)).replace(',', '.')
                    try:
                        cashback_percent = float(catalogo_cashback_str)
                    except ValueError:
                        pass
            if cashback_percent > 0:
                preco_unitario = float(item.get('preco', 0.0))
                try:
                    quantidade = int(item.get('quantidade', 0))
                except (TypeError, ValueError):
                    quantidade = 0
                valor_item = preco_unitario * quantidade
                valor_cashback_total += valor_item * (cashback_percent / 100)
    except Exception:
        return 0.0
    return round(valor_cashback_total, 2)

# --- FUNÇÕES DE PEDIDOS (O código existente continua aqui, sem alterações) ---

def atualizar_status_pedido(id_pedido, novo_status, df_catalogo):
    df = carregar_dados(SHEET_NAME_PEDIDOS).copy()
    if df.empty: 
        st.error("Não há dados de pedidos para atualizar.")
        return False
    index_to_update = df[df['ID_PEDIDO'] == str(id_pedido)].index
    if not index_to_update.empty:
        idx = index_to_update[0]
        if novo_status == 'Finalizado' and df.loc[idx, 'STATUS'] != 'Finalizado':
            pedido = df.loc[idx]
            pedido_json = pedido.get('ITENS_JSON') 
            contato_cliente = pedido.get('CONTATO_CLIENTE')
            nome_cliente_pedido = pedido.get('NOME_CLIENTE')
            valor_cashback_credito = calcular_cashback_a_creditar(pedido_json, df_catalogo)
            if pedido_json and contato_cliente and valor_cashback_credito > 0:
                if not lancar_venda_cashback(nome_cliente_pedido, contato_cliente, valor_cashback_credito):
                    st.warning("Falha ao lançar cashback. Pedido não será finalizado.")
                    return False
                df.loc[idx, 'VALOR_CASHBACK_CREDITADO'] = valor_cashback_credito
        df.loc[idx, 'STATUS'] = novo_status
        if novo_status != 'Finalizado':
            df.loc[idx, 'VALOR_CASHBACK_CREDITADO'] = 0.0
        commit_msg = f"Atualizar status do pedido {id_pedido} para {novo_status}"
        if write_csv_to_github(df, SHEET_NAME_PEDIDOS, commit_msg):
             return True
        else:
             st.error("Falha ao salvar o status do pedido no GitHub.")
             return False
    return False

def excluir_pedido(id_pedido):
    df = carregar_dados(SHEET_NAME_PEDIDOS).copy()
    if df.empty: return False
    df = df[df['ID_PEDIDO'] != str(id_pedido)]
    commit_msg = f"Excluir pedido {id_pedido}"
    return write_csv_to_github(df, SHEET_NAME_PEDIDOS, commit_msg)

def exibir_itens_pedido(id_pedido, pedido_json, df_catalogo):
    try:
        pedido_str = str(pedido_json).strip()
        if not pedido_str or pedido_str.lower() in ('nan', '{}', ''):
            st.warning("⚠️ Detalhes do pedido (JSON) não encontrados ou vazios.")
            return 0
        try:
            detalhes_pedido = json.loads(pedido_str)
        except json.JSONDecodeError:
            detalhes_pedido = ast.literal_eval(pedido_str)
        itens = detalhes_pedido.get('itens', [])
        total_itens = len(itens)
        itens_separados = 0
        key_progress = f'pedido_{id_pedido}_itens_separados'
        if key_progress not in st.session_state:
            st.session_state[key_progress] = [False] * total_itens
        for i, item in enumerate(itens):
            link_imagem = "https://via.placeholder.com/150?text=Sem+Imagem"
            item_id = pd.to_numeric(item.get('id'), errors='coerce')
            if not df_catalogo.empty and not pd.isna(item_id) and not df_catalogo[df_catalogo['ID'] == int(item_id)].empty: 
                link_na_tabela = str(df_catalogo[df_catalogo['ID'] == int(item_id)].iloc[0].get('LINKIMAGEM', link_imagem)).strip()
                if link_na_tabela.lower() != 'nan' and link_na_tabela:
                    link_imagem = link_na_tabela
            col_check, col_img, col_detalhes = st.columns([0.5, 1, 3.5])
            checked = col_check.checkbox(label="Separado", value=st.session_state[key_progress][i], key=f"check_{id_pedido}_{i}",)
            if checked != st.session_state[key_progress][i]:
                st.session_state[key_progress][i] = checked
                st.rerun() 
            col_img.image(link_imagem, width=100)
            quantidade = item.get('qtd', item.get('quantidade', 0))
            preco_unitario = float(item.get('preco', 0.0))
            subtotal = item.get('subtotal')
            if subtotal is None: subtotal = preco_unitario * quantidade
            col_detalhes.markdown(f"**Produto:** {item.get('nome', 'N/A')}\n\n**Quantidade:** {quantidade}\n\n**Subtotal:** R$ {subtotal:.2f}"); 
            st.markdown("---")
            if st.session_state[key_progress][i]:
                itens_separados += 1
        if total_itens > 0:
            progresso = int((itens_separados / total_itens) * 100)
            return progresso
        return 0
    except Exception as e: 
        st.error(f"Erro fatal ao processar itens do pedido. Verifique o JSON. Detalhe: {e}")
        return 0 

# --- FUNÇÕES CRUD (O código existente continua aqui, sem alterações) ---

def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel, cashback_percent_prod=0.0):
    df = carregar_dados(SHEET_NAME_CATALOGO).copy()
    df['ID'] = pd.to_numeric(df['ID'], errors='coerce')
    novo_id = df['ID'].max() + 1 if not df.empty and df['ID'].any() and not pd.isna(df['ID'].max()) else 1
    nova_linha = {
        'ID': novo_id, 'NOME': nome, 'PRECO': str(preco).replace('.', ','), 'DESCRICAOCURTA': desc_curta,
        'DESCRICAOLONGA': desc_longa, 'LINKIMAGEM': link_imagem, 'DISPONIVEL': disponivel,
        'CASHBACKPERCENT': str(cashback_percent_prod).replace('.', ',') 
    }
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    commit_msg = f"Adicionar produto: {nome} (ID: {novo_id})"
    return write_csv_to_github(df, SHEET_NAME_CATALOGO, commit_msg)

def atualizar_produto(id_produto, nome, preco, desc_curta, desc_longa, link_imagem, disponivel, cashback_percent_prod=0.0):
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
        df.loc[idx, 'CASHBACKPERCENT'] = str(cashback_percent_prod).replace('.', ',') 
        commit_msg = f"Atualizar produto ID: {id_produto}"
        return write_csv_to_github(df, SHEET_NAME_CATALOGO, commit_msg)
    return False

def excluir_produto(id_produto):
    df = carregar_dados(SHEET_NAME_CATALOGO).copy()
    if df.empty: return False
    df = df[df['ID'] != int(id_produto)]
    commit_msg = f"Excluir produto ID: {id_produto}"
    return write_csv_to_github(df, SHEET_NAME_CATALOGO, commit_msg)

def criar_promocao(id_produto, nome_produto, preco_original, preco_promocional, data_inicio, data_fim):
    df = carregar_dados(SHEET_NAME_PROMOCOES).copy()
    id_promocao = int(time.time()) 
    nova_linha = {
        'ID_PROMOCAO': id_promocao, 'ID_PRODUTO': str(id_produto), 'NOME_PRODUTO': nome_produto,
        'PRECO_ORIGINAL': str(preco_original), 'PRECO_PROMOCIONAL': str(preco_promocional).replace('.', ','), 
        'STATUS': "Ativa", 'DATA_INICIO': data_inicio, 'DATA_FIM': data_fim
    }
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
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

# --- NOVO: FUNÇÃO PARA CRIAR CUPOM ---
def criar_cupom(codigo, tipo_desconto, valor, data_validade, valor_minimo, limite_usos):
    df = carregar_dados(SHEET_NAME_CUPONS).copy()
    
    if not df.empty and codigo.upper() in df['CODIGO'].str.upper().tolist():
        st.error(f"O código de cupom '{codigo}' já existe!")
        return False

    nova_linha = {
        'CODIGO': codigo.upper(),
        'TIPO_DESCONTO': tipo_desconto,
        'VALOR': valor,
        'DATA_VALIDADE': str(data_validade) if data_validade else '',
        'VALOR_MINIMO_PEDIDO': valor_minimo,
        'LIMITE_USOS': limite_usos,
        'USOS_ATUAIS': 0,
        'STATUS': 'ATIVO'
    }

    df_nova = pd.DataFrame([nova_linha])
    df = pd.concat([df, df_nova], ignore_index=True)
    
    commit_msg = f"Criar novo cupom: {codigo.upper()}"
    return write_csv_to_github(df, SHEET_NAME_CUPONS, commit_msg)


# --- LAYOUT DO APP ---
st.set_page_config(page_title="Admin Doce&Bella", layout="wide")
st.title("⭐ Painel de Administração | Doce&Bella")

# --- TABS DO SISTEMA ---
# MODIFICADO: Adicionada a nova tab de cupons
tab_pedidos, tab_produtos, tab_promocoes, tab_cupons = st.tabs(["Pedidos", "Produtos", "🔥 Promoções", "🎟️ Cupons"])

def extract_customer_cashback(itens_json_string):
    if pd.isna(itens_json_string) or not itens_json_string:
        return 0.0
    s = str(itens_json_string).strip()
    match = re.search(r'\"cliente_saldo_cashback\"\s*:\s*([\d\.]+)', s)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    if s.startswith('"') and s.endswith('"'): s = s[1:-1]
    s = s.replace('""', '"').replace('\\"', '"') 
    try:
        data = json.loads(s)
        return data.get("cliente_saldo_cashback", 0.0)
    except Exception:
        try:
            data = ast.literal_eval(itens_json_string) 
            return data.get("cliente_saldo_cashback", 0.0)
        except Exception:
            return 0.0

with tab_pedidos:
    # (O código da aba de pedidos continua aqui, sem alterações)
    st.header("📋 Pedidos Recebidos")
    if st.button("Recarregar Pedidos"): 
        keys_to_delete = [k for k in st.session_state if k.startswith('pedido_') and k.endswith('_itens_separados')]
        for k in keys_to_delete:
            del st.session_state[k]
        st.session_state['data_version'] += 1 
        st.rerun() 
    
    df_pedidos_raw = carregar_dados(SHEET_NAME_PEDIDOS)
    df_catalogo_pedidos = carregar_dados(SHEET_NAME_CATALOGO)
    
    if not df_pedidos_raw.empty and 'ITENS_JSON' in df_pedidos_raw.columns:
        df_pedidos_raw['SALDO_CASHBACK_CLIENTE_PEDIDO'] = df_pedidos_raw['ITENS_JSON'].apply(extract_customer_cashback)
    else:
        df_pedidos_raw['SALDO_CASHBACK_CLIENTE_PEDIDO'] = 0.0
    
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
                df_filtrado['NOME_CLIENTE'].astype(str).str.lower().str.contains(texto_filtro) | 
                df_filtrado['ITENS_PEDIDO'].astype(str).str.lower().str.contains(texto_filtro) | 
                df_filtrado['ITENS_JSON'].astype(str).str.lower().str.contains(texto_filtro)
            ]
            
        st.markdown("---")
        pedidos_pendentes = df_filtrado[df_filtrado['STATUS'] != 'Finalizado']
        pedidos_finalizados = df_filtrado[df_filtrado['STATUS'] == 'Finalizado']
        st.header("⏳ Pedidos Pendentes")
        
        if pedidos_pendentes.empty: 
            st.info("Nenhum pedido pendente encontrado.")
        else:
            for index, pedido in pedidos_pendentes.iloc[::-1].iterrows():
                id_pedido = pedido['ID_PEDIDO']
                data_hora_str = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indisponível"
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {data_hora_str} - Total: R$ {pedido['VALOR_TOTAL']}"
                pedido_json_data = pedido.get('ITENS_JSON', pedido.get('ITENS_PEDIDO', '{}'))
                cashback_a_creditar = calcular_cashback_a_creditar(pedido_json_data, df_catalogo_pedidos)
                
                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{id_pedido}`")
                    saldo_anterior = pedido['SALDO_CASHBACK_CLIENTE_PEDIDO']
                    st.markdown(f"**Saldo Cashback do Cliente:** **R$ {saldo_anterior:.2f}**")
                    st.markdown("---")
                    if cashback_a_creditar > 0.00:
                        st.markdown(f"**💰 Cashback a ser Creditado:** **R$ {cashback_a_creditar:.2f}**")
                        st.info("Este valor será creditado ao cliente (no clientes_cash.csv) **após** a finalização deste pedido.")
                    else:
                        st.markdown("💰 **Cashback a ser Creditado:** R$ 0.00")
                        st.caption("Nenhum produto neste pedido está configurado com porcentagem de Cashback (CASHBACKPERCENT).")
                    progresso_separacao = exibir_itens_pedido(id_pedido, pedido_json_data, df_catalogo_pedidos)
                    st.markdown(f"**Progresso de Separação:** {progresso_separacao}%")
                    st.progress(progresso_separacao / 100)
                    pode_finalizar = progresso_separacao == 100
                    if st.button("✅ Finalizar Pedido", key=f"finalizar_{id_pedido}", disabled=not pode_finalizar):
                        if atualizar_status_pedido(id_pedido, novo_status="Finalizado", df_catalogo=df_catalogo_pedidos):
                            st.success(f"Pedido {id_pedido} finalizado!")
                            key_progress = f'pedido_{id_pedido}_itens_separados'
                            if key_progress in st.session_state: del st.session_state[key_progress]
                            st.session_state['data_version'] += 1 
                            st.rerun() 
                        else: st.error("Falha ao finalizar pedido.")
                        
        st.header("✅ Pedidos Finalizados")
        if pedidos_finalizados.empty: 
            st.info("Nenhum pedido finalizado encontrado.")
        else:
            for index, pedido in pedidos_finalizados.iloc[::-1].iterrows():
                data_hora_str = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indisponível"
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {data_hora_str} - Total: R$ {pedido['VALOR_TOTAL']}"
                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{pedido['ID_PEDIDO']}`")
                    saldo_anterior = pedido['SALDO_CASHBACK_CLIENTE_PEDIDO']
                    st.markdown(f"**Saldo Cashback do Cliente:** **R$ {saldo_anterior:.2f}**")
                    st.markdown("---")
                    col_reverter, col_excluir = st.columns(2)
                    with col_reverter:
                        if st.button("↩️ Reverter para Pendente", key=f"reverter_{pedido['ID_PEDIDO']}", use_container_width=True):
                            if atualizar_status_pedido(pedido['ID_PEDIDO'], novo_status="PENDENTE", df_catalogo=pd.DataFrame()): 
                                st.success(f"Pedido {pedido['ID_PEDIDO']} revertido para PENDENTE.")
                                st.session_state['data_version'] += 1; st.rerun()  
                            else: st.error("Falha ao reverter status do pedido.")
                    with col_excluir:
                        if st.button("🗑️ Excluir Pedido", type="primary", key=f"excluir_{pedido['ID_PEDIDO']}", use_container_width=True):
                            if excluir_pedido(pedido['ID_PEDIDO']): 
                                st.success(f"Pedido {pedido['ID_PEDIDO']} excluído!")
                                st.session_state['data_version'] += 1; st.rerun()  
                            else: st.error("Falha ao excluir o pedido.")
                    st.markdown("---")
                    exibir_itens_pedido(pedido['ID_PEDIDO'], pedido.get('ITENS_JSON', pedido.get('ITENS_PEDIDO', '{}')), df_catalogo_pedidos)

with tab_produtos:
    # (O código da aba de produtos continua aqui, sem alterações)
    st.header("🛍️ Gerenciamento de Produtos")
    df_produtos_catalogo = carregar_dados(SHEET_NAME_CATALOGO)
    with st.expander("➕ Adicionar Novo Produto"):
        with st.form("form_novo_produto", clear_on_submit=True):
            novo_nome = st.text_input("Nome do Produto")
            novo_preco = st.number_input("Preço (R$)", min_value=0.01, format="%.2f")
            novo_desc_curta = st.text_input("Descrição Curta")
            novo_desc_longa = st.text_area("Descrição Longa")
            novo_link_imagem = st.text_input("Link da Imagem")
            novo_cashback = st.number_input("Cashback (%)", min_value=0.0, max_value=100.0, format="%.2f")
            novo_disponivel = st.checkbox("Disponível para Venda", value=True)
            if st.form_submit_button("Salvar Novo Produto"):
                if novo_nome and novo_preco > 0:
                    if adicionar_produto(novo_nome, novo_preco, novo_desc_curta, novo_desc_longa, novo_link_imagem, novo_disponivel, novo_cashback):
                        st.success(f"Produto '{novo_nome}' adicionado com sucesso!"); st.session_state['data_version'] += 1; st.rerun()
                    else: st.error("Falha ao adicionar produto.")
                else: st.warning("Preencha o nome e o preço corretamente.")
    st.markdown("---")
    st.subheader("📝 Editar/Excluir Produtos Existentes")
    if df_produtos_catalogo.empty:
        st.info("Nenhum produto cadastrado.")
    else:
        df_produtos_catalogo['ID_STR'] = df_produtos_catalogo['ID'].astype(str)
        opcoes_produtos = df_produtos_catalogo.apply(lambda row: f"{row['ID_STR']} - {row['NOME']}", axis=1).tolist()
        produto_selecionado_str = st.selectbox("Selecione o Produto para Editar", opcoes_produtos)
        if produto_selecionado_str:
            id_selecionado = int(produto_selecionado_str.split(' - ')[0])
            produto_atual = df_produtos_catalogo[df_produtos_catalogo['ID'] == id_selecionado].iloc[0]
            try:
                preco_float = float(str(produto_atual.get('PRECO', '0.01')).replace(',', '.'))
            except (ValueError, TypeError): preco_float = 0.01
            try:
                cashback_float = float(str(produto_atual.get('CASHBACKPERCENT', '0.0')).replace(',', '.'))
            except (ValueError, TypeError): cashback_float = 0.0
            with st.form("form_editar_produto"):
                st.info(f"Editando produto ID: {id_selecionado}")
                edit_nome = st.text_input("Nome do Produto", value=produto_atual.get('NOME', ''))
                edit_preco = st.number_input("Preço (R$)", min_value=0.01, format="%.2f", value=preco_float)
                edit_desc_curta = st.text_input("Descrição Curta", value=produto_atual.get('DESCRICAOCURTA', ''))
                edit_desc_longa = st.text_area("Descrição Longa", value=produto_atual.get('DESCRICAOLONGA', ''))
                edit_link_imagem = st.text_input("Link da Imagem", value=produto_atual.get('LINKIMAGEM', ''))
                edit_cashback = st.number_input("Cashback (%)", min_value=0.0, max_value=100.0, format="%.2f", value=cashback_float)
                disponivel_default = produto_atual.get('DISPONIVEL', False)
                if isinstance(disponivel_default, str): disponivel_default = disponivel_default.upper() == 'TRUE'
                edit_disponivel = st.checkbox("Disponível para Venda", value=disponivel_default)
                col_update, col_delete = st.columns(2)
                if col_update.form_submit_button("💾 Salvar Alterações", type="primary"):
                    if edit_nome and edit_preco > 0:
                        if atualizar_produto(id_selecionado, edit_nome, edit_preco, edit_desc_curta, edit_desc_longa, edit_link_imagem, edit_disponivel, edit_cashback):
                            st.success(f"Produto '{edit_nome}' atualizado com sucesso!"); st.session_state['data_version'] += 1; st.rerun()
                        else: st.error("Falha ao atualizar produto.")
                    else: st.warning("Preencha o nome e o preço corretamente.")
                if col_delete.form_submit_button("🗑️ Excluir Produto"):
                    if excluir_produto(id_selecionado):
                        st.success(f"Produto ID {id_selecionado} excluído!"); st.session_state['data_version'] += 1; st.rerun()
                    else: st.error("Falha ao excluir produto.")

with tab_promocoes:
    # (O código da aba de promoções continua aqui, sem alterações)
    st.header("🔥 Gerenciador de Promoções")
    df_promocoes = carregar_dados(SHEET_NAME_PROMOCOES)
    df_produtos_catalogo = carregar_dados(SHEET_NAME_CATALOGO)
    with st.expander("➕ Criar Nova Promoção"):
        with st.form("form_nova_promocao", clear_on_submit=True):
            if df_produtos_catalogo.empty:
                st.warning("Nenhum produto cadastrado para criar promoção.")
            else:
                df_produtos_catalogo['ID_STR'] = df_produtos_catalogo['ID'].astype(str)
                opcoes_produtos_promo = df_produtos_catalogo.apply(lambda row: f"{row['ID_STR']} - {row['NOME']}", axis=1).tolist()
                produto_selecionado_promo_str = st.selectbox("Selecione o Produto", opcoes_produtos_promo)
                if produto_selecionado_promo_str:
                    id_produto_promo = int(produto_selecionado_promo_str.split(' - ')[0])
                    produto_atual_promo = df_produtos_catalogo[df_produtos_catalogo['ID'] == id_produto_promo].iloc[0]
                    nome_produto_promo = produto_atual_promo.get('NOME', 'Produto sem nome')
                    try:
                        preco_original_float = float(str(produto_atual_promo.get('PRECO', '0.01')).replace(',', '.'))
                        if preco_original_float < 0.01: preco_original_float = 0.01
                    except (ValueError, TypeError): preco_original_float = 0.01
                    st.caption(f"Preço Original: R$ {preco_original_float:.2f}")
                    preco_promocional = st.number_input("Preço Promocional (R$)", min_value=0.01, max_value=preco_original_float, format="%.2f")
                    data_inicio = st.date_input("Data de Início", value=date.today())
                    data_fim = st.date_input("Data de Fim", value=date.today())
                    if st.form_submit_button("Criar Promoção"):
                        if preco_promocional > 0 and data_fim >= data_inicio:
                            if criar_promocao(id_produto_promo, nome_produto_promo, preco_original_float, preco_promocional, data_inicio, data_fim):
                                st.success(f"Promoção para '{nome_produto_promo}' criada!"); st.session_state['data_version'] += 1; st.rerun()
                            else: st.error("Falha ao criar promoção.")
                        else: st.warning("Preço promocional inválido ou datas incorretas.")
    st.markdown("---")
    st.subheader("📝 Gerenciar Promoções Ativas")
    if df_promocoes.empty:
        st.info("Nenhuma promoção cadastrada.")
    else:
        df_promocoes['ID_PROMOCAO_STR'] = df_promocoes['ID_PROMOCAO'].astype(str)
        opcoes_promocoes = df_promocoes.apply(lambda row: f"{row['ID_PROMOCAO_STR']} - {row['NOME_PRODUTO']} ({row['STATUS']})", axis=1).tolist()
        promocao_selecionada_str = st.selectbox("Selecione a Promoção para Editar", opcoes_promocoes)
        if promocao_selecionada_str:
            id_promocao_selecionada = int(promocao_selecionada_str.split(' - ')[0])
            promocao_atual = df_promocoes[df_promocoes['ID_PROMOCAO'] == id_promocao_selecionada].iloc[0]
            try: preco_promo_float = float(str(promocao_atual['PRECO_PROMOCIONAL']).replace(',', '.'))
            except: preco_promo_float = 0.0
            id_produto_relacionado = pd.to_numeric(promocao_atual['ID_PRODUTO'], errors='coerce')
            preco_max_promo = preco_promo_float
            if not df_produtos_catalogo.empty and not pd.isna(id_produto_relacionado) and not df_produtos_catalogo[df_produtos_catalogo['ID'] == int(id_produto_relacionado)].empty:
                produto_catalogo = df_produtos_catalogo[df_produtos_catalogo['ID'] == int(id_produto_relacionado)].iloc[0]
                try: preco_max_promo = float(str(produto_catalogo['PRECO']).replace(',', '.'))
                except: pass
            with st.form("form_editar_promocao"):
                st.info(f"Editando promoção ID: {id_promocao_selecionada} para '{promocao_atual['NOME_PRODUTO']}'")
                edit_preco_promocional = st.number_input("Novo Preço Promocional (R$)", min_value=0.01, max_value=preco_max_promo, format="%.2f", value=preco_promo_float)
                try: data_inicio_default = datetime.strptime(str(promocao_atual['DATA_INICIO']), '%Y-%m-%d').date()
                except: data_inicio_default = date.today()
                try: data_fim_default = datetime.strptime(str(promocao_atual['DATA_FIM']), '%Y-%m-%d').date()
                except: data_fim_default = date.today()
                edit_data_inicio = st.date_input("Data de Início", value=data_inicio_default)
                edit_data_fim = st.date_input("Data de Fim", value=data_fim_default)
                edit_status = st.selectbox("Status", ['Ativa', 'Inativa', 'Expirada'], index=['Ativa', 'Inativa', 'Expirada'].index(promocao_atual['STATUS']))
                col_update, col_delete = st.columns(2)
                if col_update.form_submit_button("💾 Salvar Alterações", type="primary"):
                    if edit_preco_promocional > 0 and edit_data_fim >= edit_data_inicio:
                        if atualizar_promocao(id_promocao_selecionada, edit_preco_promocional, edit_data_inicio, edit_data_fim, edit_status):
                            st.success(f"Promoção ID {id_promocao_selecionada} atualizada!"); st.session_state['data_version'] += 1; st.rerun()
                        else: st.error("Falha ao atualizar promoção.")
                    else: st.warning("Verifique o preço promocional ou as datas.")
                if col_delete.form_submit_button("🗑️ Excluir Promoção"):
                    if excluir_promocao(id_promocao_selecionada):
                        st.success(f"Promoção ID {id_promocao_selecionada} excluída!"); st.session_state['data_version'] += 1; st.rerun()
                    else: st.error("Falha ao excluir promoção.")

# --- NOVO: CONTEÚDO DA ABA DE CUPONS ---
with tab_cupons:
    st.header("🎟️ Gerenciador de Cupons de Desconto")

    with st.expander("➕ Criar Novo Cupom", expanded=True):
        with st.form("form_novo_cupom", clear_on_submit=True):
            st.subheader("Configurações do Cupom")

            col1, col2 = st.columns(2)
            with col1:
                novo_codigo = st.text_input("Código do Cupom (ex: BEMVINDO10)").upper()
                novo_tipo = st.selectbox("Tipo de Desconto", ["PERCENTUAL", "FIXO"])
            
            with col2:
                label_valor = "Valor do Desconto (%)" if novo_tipo == "PERCENTUAL" else "Valor do Desconto (R$)"
                novo_valor = st.number_input(label_valor, min_value=0.01, format="%.2f")

            st.markdown("---")
            st.subheader("Regras e Limites")

            col3, col4 = st.columns(2)
            with col3:
                sem_validade = st.checkbox("Sem data de validade")
                nova_validade = st.date_input(
                    "Data de Expiração", 
                    disabled=sem_validade,
                    min_value=date.today(),
                    value=None if sem_validade else date.today()
                )
            with col4:
                novo_valor_minimo = st.number_input("Valor mínimo da compra para uso (R$)", min_value=0.0, format="%.2f")

            uso_ilimitado = st.checkbox("Uso ilimitado")
            novo_limite_usos = st.number_input(
                "Quantidade de vezes que pode ser usado", 
                min_value=1, 
                step=1, 
                disabled=uso_ilimitado,
                help="Se for ilimitado, este campo será ignorado."
            )
            limite_final = 0 if uso_ilimitado else novo_limite_usos

            submitted = st.form_submit_button("Salvar Novo Cupom", type="primary", use_container_width=True)
            
            if submitted:
                if novo_codigo and novo_valor > 0:
                    if criar_cupom(novo_codigo, novo_tipo, novo_valor, None if sem_validade else nova_validade, novo_valor_minimo, limite_final):
                        st.success(f"Cupom '{novo_codigo}' criado com sucesso!")
                        st.session_state['data_version'] += 1
                        st.rerun()
                else:
                    st.warning("Preencha o Código e o Valor do cupom corretamente.")

    st.markdown("---")
    st.subheader("📝 Cupons Cadastrados")
    
    if st.button("Recarregar Lista de Cupons"):
        st.session_state['data_version'] += 1
        st.rerun()

    df_cupons = carregar_dados(SHEET_NAME_CUPONS)
    if df_cupons.empty:
        st.info("Nenhum cupom cadastrado ainda.")
    else:
        st.dataframe(df_cupons, use_container_width=True)
