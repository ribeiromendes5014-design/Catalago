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
                df[col] = pd.to_numeric(df.get(col), errors='coerce').fillna(0.0)
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
    csv_content = df.fillna('').to_csv(index=False, sep=',')
    content_base64 = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
    payload = {"message": commit_message, "content": content_base64, "branch": branch_to_write}
    if sha: payload["sha"] = sha 
    put_response = requests.put(api_url, headers=HEADERS, json=payload)
    if put_response.status_code in [200, 201]:
        fetch_github_data_v2.clear(); return True
    else:
        st.error(f"Falha no Commit: {put_response.json().get('message', 'Erro')}"); return False

# --- FUNÇÕES DE PEDIDOS E CASHBACK ---
def calcular_cashback_a_creditar(pedido_json, df_catalogo, valor_desconto_total=0.0):
    valor_cashback_total = 0.0
    subtotal_bruto = 0.0
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
                    proporcao = subtotal_item / subtotal_bruto
                    valor_final_item = subtotal_item - (valor_desconto_total * proporcao)
                    valor_cashback_total += valor_final_item * (cashback_percent / 100)
    except: return 0.0
    return round(valor_cashback_total, 2)

def atualizar_status_pedido(id_pedido, novo_status, df_catalogo):
    df = carregar_dados(SHEET_NAME_PEDIDOS)
    idx = df[df['ID_PEDIDO'] == str(id_pedido)].index
    if not idx.empty:
        if novo_status == 'Finalizado':
            pedido = df.loc[idx[0]]
            valor_desconto = pedido.get('VALOR_DESCONTO', 0.0)
            cashback = calcular_cashback_a_creditar(pedido.get('ITENS_JSON'), df_catalogo, valor_desconto)
            df.loc[idx[0], 'VALOR_CASHBACK_CREDITADO'] = cashback
        df.loc[idx[0], 'STATUS'] = novo_status
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
            
            # --- CORREÇÃO DO ERRO 'LINKIMAGEM' ---
            if not produto.empty and 'LINKIMAGEM' in produto.columns:
                link_na_tabela = produto.iloc[0]['LINKIMAGEM']
                if pd.notna(link_na_tabela) and str(link_na_tabela).strip():
                    link_imagem = str(link_na_tabela)

            col1, col2, col3 = st.columns([0.5, 1, 3.5])
            st.session_state[key_progress][i] = col1.checkbox(" ", st.session_state[key_progress][i], key=f"c_{id_pedido}_{i}", label_visibility="collapsed")
            col2.image(link_imagem, width=100)
            subtotal = float(item.get('preco', 0)) * int(item.get('quantidade', 0))
            col3.markdown(f"**{item.get('nome', 'N/A')}**\n\n**Qtd:** {item.get('quantidade', 0)} | **Subtotal:** R$ {subtotal:.2f}")
            st.markdown("---")
            if st.session_state[key_progress][i]: itens_separados += 1
        return 100 if total_itens == 0 else int((itens_separados / total_itens) * 100)
    except Exception as e:
        st.error(f"Erro ao processar itens do pedido. Verifique o JSON. Detalhe: {e}")
        return 0

# --- Demais funções (CRUDs) ---
def criar_cupom(codigo, tipo_desconto, valor, data_validade, valor_minimo, limite_usos):
    df = carregar_dados(SHEET_NAME_CUPONS)
    if not df.empty and codigo.upper() in df['CODIGO'].str.upper().tolist():
        st.error(f"O código de cupom '{codigo}' já existe!")
        return False
    nova_linha = {'CODIGO': codigo.upper(), 'TIPO_DESCONTO': tipo_desconto, 'VALOR': valor, 'DATA_VALIDADE': str(data_validade) if data_validade else '', 'VALOR_MINIMO_PEDIDO': valor_minimo, 'LIMITE_USOS': limite_usos, 'USOS_ATUAIS': 0, 'STATUS': 'ATIVO'}
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    return write_csv_to_github(df, SHEET_NAME_CUPONS, f"Criar novo cupom: {codigo.upper()}")

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
        for _, pedido in df_pedidos.sort_values(by="DATA_HORA", ascending=False).iterrows():
            if pedido['STATUS'] != 'Finalizado':
                # --- CORREÇÃO DO VALOR TOTAL ---
                valor_total = pedido.get('VALOR_TOTAL', 0.0)
                if valor_total == 0.0:
                    try:
                        itens = ast.literal_eval(str(pedido.get('ITENS_JSON'))).get('itens', [])
                        valor_total = sum(float(i.get('preco', 0)) * int(i.get('quantidade', 0)) for i in itens)
                    except: pass
                
                data_hora = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indefinida"
                with st.expander(f"Pedido de **{pedido['NOME_CLIENTE']}** - {data_hora} - Total: R$ {valor_total:.2f}"):
                    progresso = exibir_itens_pedido(pedido['ID_PEDIDO'], pedido.get('ITENS_JSON'), df_catalogo)
                    st.progress(progresso / 100, f"Progresso: {progresso}%")
                    if st.button("✅ Finalizar Pedido", key=f"finalizar_{pedido['ID_PEDIDO']}", disabled=progresso != 100):
                        if atualizar_status_pedido(pedido['ID_PEDIDO'], "Finalizado", df_catalogo):
                            st.success(f"Pedido {pedido['ID_PEDIDO']} finalizado!"); st.rerun()
                        else: st.error("Falha ao finalizar.")

with tab_cupons:
    st.header("🎟️ Gerenciador de Cupons de Desconto")
    with st.expander("➕ Criar Novo Cupom", expanded=True):
        with st.form("form_novo_cupom", clear_on_submit=True):
            col1, col2 = st.columns(2)
            novo_codigo = col1.text_input("Código do Cupom").upper()
            novo_tipo = col1.selectbox("Tipo de Desconto", ["PERCENTUAL", "FIXO"])
            label_valor = f"Valor ({'%' if novo_tipo == 'PERCENTUAL' else 'R$'})"
            novo_valor = col2.number_input(label_valor, min_value=0.01, format="%.2f")
            sem_validade = st.checkbox("Sem data de validade")
            nova_validade = st.date_input("Data de Expiração", disabled=sem_validade, min_value=date.today())
            novo_valor_minimo = st.number_input("Valor mínimo da compra (R$)", min_value=0.0, format="%.2f")
            uso_ilimitado = st.checkbox("Uso ilimitado")
            novo_limite_usos = st.number_input("Limite de usos", min_value=1, step=1, disabled=uso_ilimitado)
            if st.form_submit_button("Salvar Novo Cupom", type="primary", use_container_width=True):
                if novo_codigo and novo_valor > 0:
                    limite = 0 if uso_ilimitado else novo_limite_usos
                    validade = None if sem_validade else nova_validade
                    if criar_cupom(novo_codigo, novo_tipo, novo_valor, validade, novo_valor_minimo, limite):
                        st.success(f"Cupom '{novo_codigo}' criado!"); st.rerun()
                else: st.warning("Preencha Código e Valor.")
    st.subheader("📝 Cupons Cadastrados")
    df_cupons = carregar_dados(SHEET_NAME_CUPONS)
    if df_cupons.empty: st.info("Nenhum cupom cadastrado.")
    else: st.dataframe(df_cupons, use_container_width=True)

# As abas de Produtos e Promoções podem ser adicionadas aqui como estavam antes.
# O código foi omitido para focar nas correções.

