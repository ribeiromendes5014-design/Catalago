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

# --- FUNÇÕES DE CASHBACK ---
def lancar_venda_cashback(nome: str, contato: str, valor_cashback_credito: float, valor_final_compra: float):
    contato_limpo = re.sub(r'\D', '', str(contato))
    df_clientes = carregar_dados(SHEET_NAME_CLIENTES_CASH)
    
    if df_clientes.empty or 'CONTATO' not in df_clientes.columns:
        df_clientes = pd.DataFrame(columns=['NOME', 'CONTATO', 'CASHBACK_DISPONIVEL', 'GASTO_ACUMULADO', 'NIVEL_ATUAL', 'PRIMEIRA_COMPRA_FEITA'])

    df_clientes['CONTATO_LIMPO'] = df_clientes['CONTATO'].astype(str).str.replace(r'\D', '', regex=True)
    cliente_idx = df_clientes[df_clientes['CONTATO_LIMPO'] == contato_limpo].index
    
    if cliente_idx.empty:
        novo_cliente = {'NOME': nome, 'CONTATO': contato_limpo, 'CASHBACK_DISPONIVEL': valor_cashback_credito, 'GASTO_ACUMULADO': valor_final_compra, 'NIVEL_ATUAL': 'Prata', 'PRIMEIRA_COMPRA_FEITA': 'TRUE'}
        df_clientes = pd.concat([df_clientes, pd.DataFrame([novo_cliente])], ignore_index=True)
    else:
        idx = cliente_idx[0]
        df_clientes.loc[idx, 'CASHBACK_DISPONIVEL'] = df_clientes.loc[idx].get('CASHBACK_DISPONIVEL', 0.0) + valor_cashback_credito
        # --- CORREÇÃO DO GASTO ACUMULADO ---
        df_clientes.loc[idx, 'GASTO_ACUMULADO'] = df_clientes.loc[idx].get('GASTO_ACUMULADO', 0.0) + valor_final_compra
        df_clientes.loc[idx, 'PRIMEIRA_COMPRA_FEITA'] = 'TRUE'
    
    if write_csv_to_github(df_clientes, SHEET_NAME_CLIENTES_CASH, f"CRÉDITO CASHBACK: {nome} (R$ {valor_cashback_credito:.2f})"):
        st.toast(f"Cashback creditado: +R$ {valor_cashback_credito:.2f}", icon='💵')
        return True
    return False

def extract_customer_cashback(itens_json_string):
    if pd.isna(itens_json_string) or not itens_json_string: return 0.0
    s = str(itens_json_string).strip()
    match = re.search(r'\"cliente_saldo_cashback\"\s*:\s*([\d\.]+)', s)
    if match:
        try: return float(match.group(1))
        except: pass
    try: return ast.literal_eval(s).get("cliente_saldo_cashback", 0.0)
    except: return 0.0

def calcular_cashback_a_creditar(pedido_json, df_catalogo, valor_desconto_total=0.0):
    valor_cashback_total, subtotal_bruto = 0.0, 0.0
    try:
        itens = ast.literal_eval(str(pedido_json)).get('itens', [])
        for item in itens: subtotal_bruto += float(item.get('preco', 0)) * int(item.get('quantidade', 0))
        if subtotal_bruto == 0: return 0.0
        for item in itens:
            produto = df_catalogo[df_catalogo['ID'] == int(item.get('id', -1))]
            if not produto.empty:
                cashback_percent = float(str(produto.iloc[0].get('CASHBACKPERCENT', '0')).replace(',', '.'))
                if cashback_percent > 0:
                    subtotal_item = float(item.get('preco', 0)) * int(item.get('quantidade', 0))
                    proporcao = subtotal_item / subtotal_bruto if subtotal_bruto > 0 else 0
                    valor_final_item = subtotal_item - (valor_desconto_total * proporcao)
                    valor_cashback_total += valor_final_item * (cashback_percent / 100)
    except: return 0.0
    return round(valor_cashback_total, 2)

def atualizar_status_pedido(id_pedido, novo_status, df_catalogo):
    df = carregar_dados(SHEET_NAME_PEDIDOS)
    idx = df[df['ID_PEDIDO'] == str(id_pedido)].index
    if not idx.empty:
        idx = idx[0]
        if novo_status == 'Finalizado' and df.loc[idx, 'STATUS'] != 'Finalizado':
            pedido = df.loc[idx]
            valor_desconto = pedido.get('VALOR_DESCONTO', 0.0)
            valor_final_pago = pedido.get('VALOR_TOTAL', 0.0) # Valor final para o gasto acumulado
            cashback = calcular_cashback_a_creditar(pedido.get('ITENS_JSON'), df_catalogo, valor_desconto)
            
            if cashback > 0:
                if not lancar_venda_cashback(pedido.get('NOME_CLIENTE'), pedido.get('CONTATO_CLIENTE'), cashback, valor_final_pago):
                    st.error("Falha ao creditar cashback. Status não alterado."); return False
            
            df.loc[idx, 'VALOR_CASHBACK_CREDITADO'] = cashback
        
        df.loc[idx, 'STATUS'] = novo_status
        return write_csv_to_github(df, SHEET_NAME_PEDIDOS, f"Status pedido {id_pedido} para {novo_status}")
    return False

def exibir_itens_pedido(id_pedido, pedido_json, df_catalogo):
    try:
        itens = ast.literal_eval(str(pedido_json)).get('itens', [])
        total_itens, itens_separados = len(itens), 0
        key_progress = f'pedido_{id_pedido}_itens_separados'
        if key_progress not in st.session_state: st.session_state[key_progress] = [False] * total_itens
        for i, item in enumerate(itens):
            link_imagem = "https://placehold.co/150x150/e2e8f0/e2e8f0?text=Sem+Imagem"
            produto = df_catalogo[df_catalogo['ID'] == int(item.get('id', -1))]
            if not produto.empty and 'LINKIMAGEM' in produto.columns and pd.notna(produto.iloc[0]['LINKIMAGEM']):
                link_imagem = str(produto.iloc[0]['LINKIMAGEM'])
            col1, col2, col3 = st.columns([0.5, 1, 3.5])
            st.session_state[key_progress][i] = col1.checkbox(" ", st.session_state[key_progress][i], key=f"c_{id_pedido}_{i}", label_visibility="collapsed")
            col2.image(link_imagem, width=100)
            subtotal = float(item.get('preco', 0)) * int(item.get('quantidade', 0))
            col3.markdown(f"**{item.get('nome', 'N/A')}**\n\n**Qtd:** {item.get('quantidade', 0)} | **Subtotal:** R$ {subtotal:.2f}")
            st.markdown("---")
            if st.session_state[key_progress][i]: itens_separados += 1
        return 100 if total_itens == 0 else int((itens_separados / total_itens) * 100)
    except Exception as e:
        st.error(f"Erro ao processar itens: {e}"); return 0

# --- LAYOUT DO APP ---
st.set_page_config(page_title="Admin Doce&Bella", layout="wide")
st.title("⭐ Painel de Administração | Doce&Bella")
tab_pedidos, tab_produtos, tab_promocoes, tab_cupons = st.tabs(["Pedidos", "Produtos", "🔥 Promoções", "🎟️ Cupons"])

with tab_pedidos:
    st.header("📋 Pedidos Recebidos")
    if st.button("Recarregar Pedidos"): st.session_state['data_version'] += 1; st.rerun() 
    
    df_pedidos = carregar_dados(SHEET_NAME_PEDIDOS)
    df_catalogo = carregar_dados(SHEET_NAME_CATALOGO)
    
    if df_pedidos.empty:
        st.info("Nenhum pedido foi encontrado.")
    else:
        # Garante colunas essenciais
        if 'ITENS_JSON' in df_pedidos.columns:
            df_pedidos['SALDO_CASHBACK_CLIENTE_PEDIDO'] = df_pedidos['ITENS_JSON'].apply(extract_customer_cashback)
        else:
            df_pedidos['SALDO_CASHBACK_CLIENTE_PEDIDO'] = 0.0
        if 'STATUS' not in df_pedidos.columns:
            df_pedidos['STATUS'] = 'PENDENTE' # Default
            
        df_pedidos['DATA_HORA'] = pd.to_datetime(df_pedidos['DATA_HORA'], errors='coerce')
        df_pedidos.sort_values(by="DATA_HORA", ascending=False, inplace=True)
        
        # --- SEÇÃO DE PEDIDOS PENDENTES ---
        st.header("⏳ Pedidos Pendentes")
        pedidos_pendentes = df_pedidos[df_pedidos['STATUS'] == 'PENDENTE']
        if pedidos_pendentes.empty:
            st.info("Nenhum pedido pendente.")
        else:
            for _, pedido in pedidos_pendentes.iterrows():
                valor_final_a_exibir = pedido.get('VALOR_TOTAL', 0.0)
                data_hora = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indefinida"
                
                with st.expander(f"Pedido de **{pedido.get('NOME_CLIENTE','N/A')}** - {data_hora} - Total: R$ {valor_final_a_exibir:.2f}"):
                    col_botoes1, col_botoes2 = st.columns(2)
                    
                    cupom_aplicado = pedido.get('CUPOM_APLICADO')
                    valor_desconto = pedido.get('VALOR_DESCONTO', 0.0)
                    if pd.notna(cupom_aplicado) and str(cupom_aplicado).strip():
                        st.success(f"🎟️ Cupom: **{cupom_aplicado}** (-R$ {valor_desconto:.2f})")

                    saldo_anterior = pedido.get('SALDO_CASHBACK_CLIENTE_PEDIDO', 0.0)
                    st.markdown(f"**Saldo Cashback do Cliente:** **R$ {saldo_anterior:.2f}**")
                    cashback_a_creditar = calcular_cashback_a_creditar(pedido.get('ITENS_JSON'), df_catalogo, valor_desconto)
                    if cashback_a_creditar > 0.00:
                        st.markdown(f"**💰 Cashback a ser Creditado:** **R$ {cashback_a_creditar:.2f}**")
                    st.markdown("---")

                    progresso = exibir_itens_pedido(pedido.get('ID_PEDIDO'), pedido.get('ITENS_JSON'), df_catalogo)
                    st.progress(progresso / 100, f"Progresso: {progresso}%")
                    
                    with col_botoes1:
                        if st.button("✅ Finalizar Pedido", key=f"finalizar_{pedido.get('ID_PEDIDO')}", disabled=progresso != 100, use_container_width=True):
                            if atualizar_status_pedido(pedido.get('ID_PEDIDO'), "Finalizado", df_catalogo):
                                st.success(f"Pedido {pedido.get('ID_PEDIDO')} finalizado!"); st.rerun()
                    
                    with col_botoes2:
                        if st.button("✖️ Cancelar Pedido", key=f"cancelar_{pedido.get('ID_PEDIDO')}", type="secondary", use_container_width=True):
                            if atualizar_status_pedido(pedido.get('ID_PEDIDO'), "Cancelado", df_catalogo):
                                st.warning(f"Pedido {pedido.get('ID_PEDIDO')} cancelado!"); st.rerun()
        
        # --- SEÇÃO DE PEDIDOS FINALIZADOS (RESTAURADA) ---
        st.header("✅ Pedidos Finalizados")
        pedidos_finalizados = df_pedidos[df_pedidos['STATUS'] == 'Finalizado']
        if pedidos_finalizados.empty:
            st.info("Nenhum pedido finalizado.")
        else:
            for _, pedido in pedidos_finalizados.iterrows():
                data_hora = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indefinida"
                with st.expander(f"Pedido finalizado de **{pedido.get('NOME_CLIENTE','N/A')}** - {data_hora} - Total: R$ {pedido.get('VALOR_TOTAL', 0.0):.2f}"):
                     st.write(f"ID do Pedido: {pedido.get('ID_PEDIDO')}")
                     st.info(f"Cashback creditado neste pedido: R$ {pedido.get('VALOR_CASHBACK_CREDITADO', 0.0):.2f}")

# --- Outras Abas ---
with tab_produtos:
    st.header("🛍️ Gerenciamento de Produtos")
    st.info("Seção de gerenciamento de produtos.")

with tab_promocoes:
    st.header("🔥 Gerenciador de Promoções")
    st.info("Seção de gerenciamento de promoções.")
    
with tab_cupons:
    st.header("🎟️ Gerenciador de Cupons de Desconto")
    st.info("Seção de gerenciamento de cupons.")



