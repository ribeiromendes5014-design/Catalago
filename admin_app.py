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

# O bloco de código de teste que lia 'pedidos.csv' localmente FOI REMOVIDO.
# A lógica principal agora irá carregar os dados CORRETAMENTE do GitHub,
# através da função carregar_dados() na aba Pedidos.

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos_estoque"
SHEET_NAME_PEDIDOS = "pedidos"
SHEET_NAME_PROMOCOES = "promocoes"
# === NOVO: ARQUIVO DE CASHBACK E CONSTANTES ===
SHEET_NAME_CLIENTES_CASH = "clientes_cash"
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

             if 'CONTATO' in df.columns:
                 df['CONTATO'] = df['CONTATO'].astype(str).str.replace(r'\D', '', regex=True).str.strip()  
                 df['CASHBACK_DISPONIVEL'] = pd.to_numeric(df.get('CASHBACK_DISPONIVEL', 0.0), errors='coerce').fillna(0.0)
                 df['GASTO_ACUMULADO'] = pd.to_numeric(df.get('GASTO_ACUMULADO', 0.0), errors='coerce').fillna(0.0)
                 df['NIVEL_ATUAL'] = df['NIVEL_ATUAL'].fillna('Prata')
             
             for col in ['NOME', 'CONTATO', 'CASHBACK_DISPONIVEL', 'NIVEL_ATUAL', 'GASTO_ACUMULADO']:
                 if col not in df.columns: df[col] = '' if col != 'CASHBACK_DISPONIVEL' and col != 'GASTO_ACUMULADO' else 0.0
             df.dropna(subset=['CONTATO'], inplace=True)
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
        fetch_github_data_v2.clear() 
        return True
    else:
        error_message = put_response.json().get('message', 'Erro desconhecido')
        st.error(f"Falha no Commit: {put_response.status_code} - {error_message}")
        return False

# --------------------------------------------------------------------------------
# --- FUNÇÕES DE LÓGICA DE CASHBACK (INTEGRADO AO ADMIN) ---
# --------------------------------------------------------------------------------

def calcular_nivel_e_beneficios(gasto_acumulado: float):
    """Calcula o nível de fidelidade e taxa normal de cashback baseada no gasto acumulado."""
    # Lógica baseada em 3%, 7%, 15% para Prata, Ouro, Diamante, respectivamente.
    if gasto_acumulado >= 1000.01: nivel, cb_normal = 'Diamante', 0.15
    elif gasto_acumulado >= 200.01: nivel, cb_normal = 'Ouro', 0.07
    else: nivel, cb_normal = 'Prata', 0.03
    return nivel, cb_normal

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
        'CONTATO_LIMPO': contato # Usado para manter a consistência da busca
    }
    return pd.concat([df_clientes, pd.DataFrame([novo_cliente])], ignore_index=True)

def lancar_venda_cashback(nome: str, contato: str, valor_venda_bruto):
    """Lança a venda, cadastra o cliente se novo, credita o cashback e persiste o DF."""
    
    # 0. Limpeza do Valor Bruto da Venda
    try:
        valor_venda = float(str(valor_venda_bruto).replace(',', '.').strip())
    except:
        st.error(f"Erro: Valor da venda '{valor_venda_bruto}' inválido. Não foi possível converter para número.")
        return False
        
    df_clientes = carregar_clientes_cashback()
    contato_limpo = str(contato).replace('(', '').replace(')', '').replace('-', '').replace(' ', '').strip()
    
    # 1. Busca Cliente (Pelo Contato Limpo)
    cliente_idx = df_clientes[df_clientes['CONTATO_LIMPO'] == contato_limpo].index
    
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
    
    nivel_atual, cb_normal_rate = calcular_nivel_e_beneficios(gasto_antigo)
    taxa_final = cb_normal_rate
    
    # Se for a primeira compra ou cliente novo, usa taxa de primeira compra (5%)
    if cliente['PRIMEIRA_COMPRA_FEITA'].upper() == 'FALSE' or is_new_customer:
        taxa_final = CASHBACK_INDICADO_PRIMEIRA_COMPRA # 0.05
        
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
# --- FUNÇÕES DE LÓGICA DE CASHBACK (PARA VISUALIZAÇÃO) ---
# --------------------------------------------------------------------------------

def calcular_cashback_a_creditar(pedido_json, df_catalogo):
    """
    Calcula o valor total de cashback a ser creditado a partir do pedido JSON.
    Usa a porcentagem de cashback registrada no Catálogo (df_catalogo).
    """
    valor_cashback_total = 0.0
    
    pedido_str = str(pedido_json).strip()
    if not pedido_str or pedido_str.lower() in ('nan', '{}', ''):
        return 0.0

    try:
        # Tenta carregar o JSON (com tratamento para strings complexas)
        try:
            detalhes_pedido = json.loads(pedido_str)
        except json.JSONDecodeError:
            detalhes_pedido = ast.literal_eval(pedido_str)
            
        itens = detalhes_pedido.get('itens', [])
        
        for item in itens:
    # --- 1. Extração e Conversão Inicial de Dados do Item ---
    
    # Converte o ID para inteiro de forma segura (necessário para buscar no catálogo)
    try:
        item_id = int(item.get('id'))
    except (TypeError, ValueError):
        continue  # Pula o item se o ID for inválido

    # 1️⃣ Tenta pegar do JSON do pedido primeiro
    cashback_percent_str = str(item.get('cashbackpercent', 0)).replace(',', '.')
    
    # Converte a string (tratada) para float, usando 0.0 se falhar
    try:
        cashback_percent = float(cashback_percent_str)
    except ValueError:
        cashback_percent = 0.0

    # --- 2. Busca no Catálogo se o Valor For Inválido ou Zero ---

    # Checa se o catálogo não está vazio E se o cashback_percent é 0 ou inválido (NaN)
    if (cashback_percent == 0.0 or cashback_percent_str in ('nan', 'None')) and not df_catalogo.empty:
        
        # Filtra o catálogo usando .loc para maior clareza e eficiência
        produto_catalogo = df_catalogo.loc[df_catalogo['ID'] == item_id]
        
        if not produto_catalogo.empty:
            # Pega o valor do catálogo (primeira linha .iloc[0])
            catalogo_cashback_str = str(produto_catalogo.iloc[0].get('CASHBACKPERCENT', 0)).replace(',', '.')
            
            # Atualiza o cashback_percent, se a conversão for bem sucedida
            try:
                cashback_percent = float(catalogo_cashback_str)
            except ValueError:
                pass  # Mantém o valor 0.0 se o do catálogo também for inválido

    # --- 3. Cálculo Normal do Cashback ---
    
    if cashback_percent > 0:
        # Extração de Preço e Quantidade com valores padrão
        preco_unitario = float(item.get('preco', 0.0))
        
        # Tenta converter a quantidade para int, senão usa 0
        try:
            quantidade = int(item.get('quantidade'))
        except (TypeError, ValueError):
            quantidade = 0
            
        valor_item = preco_unitario * quantidade
        valor_cashback_total += valor_item * (cashback_percent / 100)
                    
    except Exception:
        # Erro de leitura/cálculo
        return 0.0
        
    return valor_cashback_total

# --------------------------------------------------------------------------------
# --- FUNÇÕES DE PEDIDOS (ESCRITA HABILITADA) ---
# --------------------------------------------------------------------------------

# A função agora requer df_catalogo para o cálculo de cashback
def atualizar_status_pedido(id_pedido, novo_status, df_catalogo):
    df = carregar_dados(SHEET_NAME_PEDIDOS).copy()
    
    if df.empty: 
        st.error("Não há dados de pedidos para atualizar.")
        return False

    index_to_update = df[df['ID_PEDIDO'] == str(id_pedido)].index
    if not index_to_update.empty:
        
        # === LÓGICA DE CRÉDITO DE CASHBACK (APENAS AO FINALIZAR) ===
        if novo_status == 'Finalizado' and df.loc[index_to_update[0], 'STATUS'] != 'Finalizado':
            pedido = df.loc[index_to_update[0]]
            
            pedido_json = pedido.get('ITENS_JSON') 
            contato_cliente = pedido.get('CONTATO_CLIENTE')
            nome_cliente_pedido = pedido.get('NOME_CLIENTE')
            valor_venda_bruto = pedido.get('VALOR_TOTAL')
            
            if pedido_json and contato_cliente:
                # 1. Lança a Venda/Cashback
                if not lancar_venda_cashback(nome_cliente_pedido, contato_cliente, valor_venda_bruto):
                    # Se falhar no cashback, não finaliza o pedido!
                    return False 
        # ==============================================================
        
        df.loc[index_to_update, 'STATUS'] = novo_status
        commit_msg = f"Atualizar status do pedido {id_pedido} para {novo_status}"
        return write_csv_to_github(df, SHEET_NAME_PEDIDOS, commit_msg)
    return False

def excluir_pedido(id_pedido):
    df = carregar_dados(SHEET_NAME_PEDIDOS).copy()
    if df.empty: return False

    df = df[df['ID_PEDIDO'] != str(id_pedido)]
    commit_msg = f"Excluir pedido {id_pedido}"
    return write_csv_to_github(df, SHEET_NAME_PEDIDOS, commit_msg)


def exibir_itens_pedido(id_pedido, pedido_json, df_catalogo):
    """
    Exibe os itens do pedido com um checkbox de separação e retorna a
    porcentagem de itens separados.
    """
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
            
            checked = col_check.checkbox(
                label="Separado",
                value=st.session_state[key_progress][i],
                key=f"check_{id_pedido}_{i}",
            )
            
            if checked != st.session_state[key_progress][i]:
                st.session_state[key_progress][i] = checked
                st.rerun() 
            
            col_img.image(link_imagem, width=100)
            quantidade = item.get('qtd', item.get('quantidade', 0))
            preco_unitario = float(item.get('preco', 0.0))
            subtotal = item.get('subtotal')
            if subtotal is None: subtotal = preco_unitario * quantidade
            
            col_detalhes.markdown(
                f"**Produto:** {item.get('nome', 'N/A')}\n\n"
                f"**Quantidade:** {quantidade}\n\n"
                f"**Subtotal:** R$ {subtotal:.2f}"
            ); 
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

# --- FUNÇÕES CRUD PARA PRODUTOS (ESCRITA HABILITADA) ---
# ... (Restante das funções CRUD de Produtos e Promoções) ...
def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel, cashback_percent_prod=0.0):
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
        'CASHBACKPERCENT': str(cashback_percent_prod).replace('.', ',') 
    }
    
    if not df.empty:
        df.loc[len(df)] = nova_linha
    else:
        df = pd.DataFrame([nova_linha])
        
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
def extract_customer_cashback(itens_json_string):
    """Extrai o saldo do cashback diretamente da string JSON (via Regex) para máxima robustez."""
    import pandas as pd
    import json
    import ast
    import re # Necessário aqui para garantir que o Streamlit o encontre

    if pd.isna(itens_json_string) or not itens_json_string:
        return 0.0

    s = str(itens_json_string).strip()
    
    # === 1. TENTATIVA COM REGEX (Mais robusto para strings corrompidas) ===
    # Busca por "cliente_saldo_cashback": seguido de zero ou mais espaços, e captura o número (com ponto)
    # r'\"cliente_saldo_cashback\"\s*:\s*([\d\.]+)'
    match = re.search(r'\"cliente_saldo_cashback\"\s*:\s*([\d\.]+)', s)
    
    if match:
        try:
            # Converte o valor capturado (ex: "0.9") para float
            return float(match.group(1))
        except ValueError:
            # Se a conversão falhar, segue para o parsing JSON
            pass

    # === 2. FALLBACK COM LIMPEZA E JSON.LOADS (Se o RegEx falhar) ===
    
    # Limpeza agressiva (necessária para JSON.loads)
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    s = s.replace('""', '"')
    s = s.replace('\\"', '"') 

    try:
        data = json.loads(s)
        return data.get("cliente_saldo_cashback", 0.0)
    except Exception:
        # 3. Fallback final com ast.literal_eval
        try:
            # Reverte para a string original, caso a limpeza tenha sido agressiva demais
            data = ast.literal_eval(itens_json_string) 
            return data.get("cliente_saldo_cashback", 0.0)
        except Exception:
            # Retorna 0.0 se falhar em todas as tentativas
            return 0.0

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
    
    # ======================================================================
    # 💥 CORREÇÃO CASHBACK: Extrai o saldo do cliente do JSON
    if not df_pedidos_raw.empty and 'ITENS_JSON' in df_pedidos_raw.columns:
        df_pedidos_raw['SALDO_CASHBACK_CLIENTE_PEDIDO'] = df_pedidos_raw['ITENS_JSON'].apply(
            extract_customer_cashback
        )
    else:
        # Garante que a coluna exista mesmo se estiver vazia
        df_pedidos_raw['SALDO_CASHBACK_CLIENTE_PEDIDO'] = 0.0
    # ======================================================================
    
    # 💥 CORREÇÃO DE INDENTAÇÃO: O 'else' deve estar alinhado com o 'if'
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
                
                # --- BLOCO DE VISUALIZAÇÃO DE CASHBACK ---
                pedido_json_data = pedido.get('ITENS_JSON', pedido.get('ITENS_PEDIDO', '{}'))
                cashback_a_creditar = calcular_cashback_a_creditar(pedido_json_data, df_catalogo_pedidos)
                
                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{id_pedido}`")
                    
                    # 💥 EXIBIÇÃO DO SALDO ACUMULADO (R$ 0,90)
                    saldo_anterior = pedido['SALDO_CASHBACK_CLIENTE_PEDIDO']
                    st.markdown(f"**Saldo Cashback do Cliente:** **R$ {saldo_anterior:.2f}**")
                    st.markdown("---")
                    
                    if cashback_a_creditar > 0.00:
                        st.markdown(f"**💰 Cashback a ser Creditado:** **R$ {cashback_a_creditar:.2f}**")
                        st.info("Este valor será creditado ao cliente (no clientes_cash.csv) **após** a finalização deste pedido.")
                    else:
                        st.markdown("💰 **Cashback a ser Creditado:** R$ 0.00")
                        st.caption("Nenhum produto neste pedido está configurado com porcentagem de Cashback (CASHBACKPERCENT).")
                        
                    # --- FIM BLOCO DE VISUALIZAÇÃO DE CASHBACK ---
                    
                    progresso_separacao = exibir_itens_pedido(id_pedido, pedido_json_data, df_catalogo_pedidos)
                    
                    st.markdown(f"**Progresso de Separação:** {progresso_separacao}%")
                    st.progress(progresso_separacao / 100) # Barra de progresso

                    pode_finalizar = progresso_separacao == 100
                    
                    if st.button("✅ Finalizar Pedido", key=f"finalizar_{id_pedido}", disabled=not pode_finalizar):
                        # CHAMA A FUNÇÃO QUE CRÉDITA O CASHBACK E ATUALIZA STATUS
                        if atualizar_status_pedido(id_pedido, novo_status="Finalizado", df_catalogo=df_catalogo_pedidos):
                            st.success(f"Pedido {id_pedido} finalizado!")
                            # Limpa o estado de separação após finalizar
                            key_progress = f'pedido_{id_pedido}_itens_separados'
                            if key_progress in st.session_state:
                                del st.session_state[key_progress]
                                
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
                        
                        # 💥 EXIBIÇÃO DO SALDO ACUMULADO (também nos finalizados)
                        saldo_anterior = pedido['SALDO_CASHBACK_CLIENTE_PEDIDO']
                        st.markdown(f"**Saldo Cashback do Cliente:** **R$ {saldo_anterior:.2f}**")
                        st.markdown("---")
                        
                        col_reverter, col_excluir = st.columns(2)
                        with col_reverter:
                            if st.button("↩️ Reverter para Pendente", key=f"reverter_{pedido['ID_PEDIDO']}", use_container_width=True):
                                if atualizar_status_pedido(pedido['ID_PEDIDO'], novo_status="PENDENTE", df_catalogo=pd.DataFrame()):  
                                    st.success(f"Pedido {pedido['ID_PEDIDO']} revertido para PENDENTE.")
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
                        st.markdown("---")
                        exibir_itens_pedido(pedido['ID_PEDIDO'], pedido.get('ITENS_JSON', pedido.get('ITENS_PEDIDO', '{}')), df_catalogo_pedidos)


with tab_produtos:
    st.header("🛍️ Gerenciamento de Produtos")
    # ... (Restante do código da aba Produtos) ...

with tab_promocoes:
    st.header("🔥 Gerenciador de Promoções")
    # ... (Restante do código da aba Promoções) ...












