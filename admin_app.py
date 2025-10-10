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
SHEET_NAME_CUPONS = "cupons" 
CASHBACK_LANCAMENTOS_CSV = "lancamentos.csv"
BONUS_INDICACAO_PERCENTUAL = 0.03
CASHBACK_INDICADO_PRIMEIRA_COMPRA = 0.05

# --- Configurações do Repositório ---
PEDIDOS_REPO_FULL = "ribeiromendes5014-design/fluxo"
PEDIDOS_BRANCH = "main"

if 'data_version' not in st.session_state:
    st.session_state['data_version'] = 0

try:
    GITHUB_TOKEN = st.secrets["github"]["token"]
    REPO_NAME_FULL = st.secrets["github"]["repo_name"]
    BRANCH = st.secrets["github"]["branch"]
    HEADERS = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
except KeyError:
    st.error("Erro de configuração: As chaves do GitHub precisam estar no secrets.toml."); st.stop()

# --- Funções Base do GitHub ---
@st.cache_data(ttl=5)
def fetch_github_data_v2(sheet_name, version_control):
    csv_filename = f"{sheet_name}.csv"
    repo_to_use, branch_to_use = (PEDIDOS_REPO_FULL, PEDIDOS_BRANCH) if sheet_name in [SHEET_NAME_PEDIDOS, SHEET_NAME_CLIENTES_CASH, SHEET_NAME_CUPONS] else (REPO_NAME_FULL, BRANCH)
    api_url = f"https://api.github.com/repos/{repo_to_use}/contents/{csv_filename}?ref={branch_to_use}"
    try:
        response = requests.get(api_url, headers=HEADERS)
        if response.status_code != 200:
            return pd.DataFrame()
        content = base64.b64decode(response.json()["content"]).decode("utf-8")
        if not content.strip(): return pd.DataFrame()
        df = pd.read_csv(StringIO(content), sep=",", engine='python', on_bad_lines='warn')
        df.columns = df.columns.str.strip().str.upper().str.replace(' ', '_')

        if sheet_name == SHEET_NAME_PEDIDOS:
            for col in ['VALOR_TOTAL', 'VALOR_DESCONTO']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                else:
                    df[col] = 0.0
        
        if sheet_name == SHEET_NAME_CATALOGO and "ID" in df.columns:
            df["ID"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0).astype(int)

        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados de '{csv_filename}': {e}")
        return pd.DataFrame()

def carregar_dados(sheet_name):
    return fetch_github_data_v2(sheet_name, st.session_state['data_version'])

def write_csv_to_github(df, sheet_name, commit_message):
    csv_filename = f"{sheet_name}.csv"
    repo_to_write, branch_to_write = (PEDIDOS_REPO_FULL, PEDIDOS_BRANCH) if sheet_name in [SHEET_NAME_PEDIDOS, SHEET_NAME_CLIENTES_CASH, SHEET_NAME_CUPONS] else (REPO_NAME_FULL, BRANCH)
    api_url = f"https://api.github.com/repos/{repo_to_write}/contents/{csv_filename}"
    response = requests.get(api_url, headers=HEADERS)
    sha = response.json().get('sha') if response.status_code == 200 else None
    
    df_to_save = df.copy()
    if 'CONTATO_LIMPO' in df_to_save.columns:
        df_to_save = df_to_save.drop(columns=['CONTATO_LIMPO'], errors='ignore')

    csv_content = df_to_save.fillna('').to_csv(index=False, sep=',')
    content_base64 = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
    payload = {"message": commit_message, "content": content_base64, "branch": branch_to_write}
    if sha: payload["sha"] = sha 
    put_response = requests.put(api_url, headers=HEADERS, json=payload)
    if put_response.status_code in [200, 201]:
        fetch_github_data_v2.clear(); return True
    else:
        st.error(f"Falha no Commit: {put_response.json().get('message', 'Erro')}"); return False

# --- FUNÇÃO DE PARSING DE JSON ROBUSTA (NOVA) ---
def parse_json_from_string(json_string):
    if pd.isna(json_string) or not isinstance(json_string, str) or not json_string.strip():
        return {}
    
    s = json_string.strip()
    
    # Tentativa 1: JSON Válido
    try: return json.loads(s)
    except json.JSONDecodeError: pass

    # Tentativa 2: Limpeza de aspas duplas de CSV
    try:
        s_cleaned = s.replace('""', '"')
        if s_cleaned.startswith('"') and s_cleaned.endswith('"'):
            s_cleaned = s_cleaned[1:-1]
        return json.loads(s_cleaned)
    except (json.JSONDecodeError, TypeError): pass

    # Tentativa 3: Fallback com ast.literal_eval
    try: return ast.literal_eval(s)
    except: return {}


# --- FUNÇÕES CRUD COMPLETAS ---
def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel, cashback_percent_prod):
    df = carregar_dados(SHEET_NAME_CATALOGO).copy()
    novo_id = (df['ID'].max() + 1) if not df.empty and df['ID'].notna().any() else 1
    nova_linha = {'ID': novo_id, 'NOME': nome, 'PRECO': str(preco).replace('.', ','), 'DESCRICAOCURTA': desc_curta, 'DESCRICAOLONGA': desc_longa, 'LINKIMAGEM': link_imagem, 'DISPONIVEL': disponivel, 'CASHBACKPERCENT': str(cashback_percent_prod).replace('.', ',')}
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    return write_csv_to_github(df, SHEET_NAME_CATALOGO, f"Adicionar produto: {nome}")

def atualizar_produto(id_produto, nome, preco, desc_curta, desc_longa, link_imagem, disponivel, cashback_percent_prod):
    df = carregar_dados(SHEET_NAME_CATALOGO)
    idx = df[df['ID'] == int(id_produto)].index
    if not idx.empty:
        df.loc[idx[0], ['NOME', 'PRECO', 'DESCRICAOCURTA', 'DESCRICAOLONGA', 'LINKIMAGEM', 'DISPONIVEL', 'CASHBACKPERCENT']] = [nome, str(preco).replace('.', ','), desc_curta, desc_longa, link_imagem, disponivel, str(cashback_percent_prod).replace('.', ',')]
        return write_csv_to_github(df, SHEET_NAME_CATALOGO, f"Atualizar produto ID: {id_produto}")
    return False

def excluir_produto(id_produto):
    df = carregar_dados(SHEET_NAME_CATALOGO)
    df = df[df['ID'] != int(id_produto)]
    return write_csv_to_github(df, SHEET_NAME_CATALOGO, f"Excluir produto ID: {id_produto}")

def criar_cupom(codigo, tipo_desconto, valor, data_validade, valor_minimo, limite_usos):
    df = carregar_dados(SHEET_NAME_CUPONS)
    if not df.empty and codigo.upper() in df['CODIGO'].str.upper().tolist():
        st.error(f"O código de cupom '{codigo}' já existe!")
        return False
    nova_linha = {'CODIGO': codigo.upper(), 'TIPO_DESCONTO': tipo_desconto, 'VALOR': valor, 'DATA_VALIDADE': str(data_validade) if data_validade else '', 'VALOR_MINIMO_PEDIDO': valor_minimo, 'LIMITE_USOS': limite_usos, 'USOS_ATUAIS': 0, 'STATUS': 'ATIVO'}
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    return write_csv_to_github(df, SHEET_NAME_CUPONS, f"Criar novo cupom: {codigo.upper()}")

# --- FUNÇÕES DE CASHBACK E PEDIDOS ---
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
        df_clientes.loc[idx, 'GASTO_ACUMULADO'] = df_clientes.loc[idx].get('GASTO_ACUMULADO', 0.0) + valor_final_compra
        df_clientes.loc[idx, 'PRIMEIRA_COMPRA_FEITA'] = 'TRUE'
    if write_csv_to_github(df_clientes, SHEET_NAME_CLIENTES_CASH, f"CRÉDITO CASHBACK: {nome} (R$ {valor_cashback_credito:.2f})"):
        st.toast(f"Cashback creditado: +R$ {valor_cashback_credito:.2f}", icon='💵')
        return True
    return False

def extract_customer_cashback(json_data):
    data = parse_json_from_string(json_data)
    return data.get("cliente_saldo_cashback", 0.0)

def calcular_cashback_a_creditar(pedido_json, df_catalogo, valor_desconto_total=0.0):
    valor_cashback_total, subtotal_bruto = 0.0, 0.0
    data = parse_json_from_string(pedido_json)
    itens = data.get('itens', [])
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
    return round(valor_cashback_total, 2)

def atualizar_status_pedido(id_pedido, novo_status, df_catalogo):
    df = carregar_dados(SHEET_NAME_PEDIDOS)
    idx = df[df['ID_PEDIDO'] == str(id_pedido)].index
    if not idx.empty:
        idx = idx[0]
        if novo_status == 'Finalizado' and df.loc[idx, 'STATUS'] != 'Finalizado':
            pedido = df.loc[idx]
            valor_desconto = pedido.get('VALOR_DESCONTO', 0.0)
            valor_final_pago = pedido.get('VALOR_TOTAL', 0.0)
            cashback = calcular_cashback_a_creditar(pedido.get('ITENS_JSON'), df_catalogo, valor_desconto)
            if cashback > 0:
                if not lancar_venda_cashback(pedido.get('NOME_CLIENTE'), pedido.get('CONTATO_CLIENTE'), cashback, valor_final_pago):
                    st.error("Falha ao creditar cashback. Status não alterado."); return False
            df.loc[idx, 'VALOR_CASHBACK_CREDITADO'] = cashback
        df.loc[idx, 'STATUS'] = novo_status
        return write_csv_to_github(df, SHEET_NAME_PEDIDOS, f"Status pedido {id_pedido} para {novo_status}")
    return False

def exibir_itens_pedido(id_pedido, pedido_json, df_catalogo):
    data = parse_json_from_string(pedido_json)
    itens = data.get('itens', [])
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
        df_pedidos['DATA_HORA'] = pd.to_datetime(df_pedidos['DATA_HORA'], errors='coerce')
        df_pedidos.sort_values(by="DATA_HORA", ascending=False, inplace=True)
        
        st.header("⏳ Pedidos Pendentes")
        pedidos_pendentes = df_pedidos[~df_pedidos.get('STATUS', pd.Series(dtype=str)).fillna('').isin(['Finalizado', 'Cancelado'])]
        
        if pedidos_pendentes.empty:
            st.info("Nenhum pedido pendente.")
        else:
            for _, pedido in pedidos_pendentes.iterrows():
                data_hora = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indefinida"
                
                with st.expander(f"Pedido de **{pedido.get('NOME_CLIENTE','N/A')}** - {data_hora} - Total: R$ {pedido.get('VALOR_TOTAL', 0.0):.2f}"):
                    # --- Exibição de detalhes do pedido ---
                    json_data = parse_json_from_string(pedido.get('ITENS_JSON'))
                    subtotal_bruto = json_data.get('subtotal', 0.0)
                    desconto = json_data.get('desconto_cupom', pedido.get('VALOR_DESCONTO', 0.0))
                    cupom = json_data.get('cupom_aplicado', pedido.get('CUPOM_APLICADO'))

                    st.metric(label="Subtotal (sem desconto)", value=f"R$ {subtotal_bruto:.2f}")
                    if pd.notna(cupom) and str(cupom).strip():
                        st.metric(label=f"Desconto Cupom ({cupom})", value=f"- R$ {desconto:.2f}")
                    
                    saldo_cashback_cliente = extract_customer_cashback(pedido.get('ITENS_JSON'))
                    st.metric(label="Saldo Cashback do Cliente", value=f"R$ {saldo_cashback_cliente:.2f}")

                    cashback_a_creditar = calcular_cashback_a_creditar(pedido.get('ITENS_JSON'), df_catalogo, desconto)
                    if cashback_a_creditar > 0:
                        st.success(f"**💰 Cashback a ser Creditado:** R$ {cashback_a_creditar:.2f}")
                    st.markdown("---")
                    
                    progresso = exibir_itens_pedido(pedido.get('ID_PEDIDO'), pedido.get('ITENS_JSON'), df_catalogo)
                    st.progress(progresso / 100, f"Progresso de Separação: {progresso}%")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ Finalizar", key=f"finalizar_{pedido.get('ID_PEDIDO')}", disabled=progresso!=100, use_container_width=True):
                            if atualizar_status_pedido(pedido.get('ID_PEDIDO'), "Finalizado", df_catalogo): st.success("Pedido finalizado!"); st.rerun()
                    with col2:
                        if st.button("✖️ Cancelar", key=f"cancelar_{pedido.get('ID_PEDIDO')}", type="secondary", use_container_width=True):
                            if atualizar_status_pedido(pedido.get('ID_PEDIDO'), "Cancelado", df_catalogo): st.warning("Pedido cancelado!"); st.rerun()
        
        st.header("✅ Pedidos Finalizados e Cancelados")
        # Restante do código para exibir pedidos concluídos...

with tab_produtos:
    # Código da aba de produtos...
    st.header("🛍️ Gerenciamento de Produtos")
    st.info("Seção em desenvolvimento")

with tab_promocoes:
    # Código da aba de promoções...
    st.header("🔥 Gerenciador de Promoções")
    st.info("Seção em desenvolvimento")

with tab_cupons:
    # Código da aba de cupons...
    st.header("🎟️ Gerenciador de Cupons")
    st.info("Seção em desenvolvimento")

