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
        
        if sheet_name == SHEET_NAME_CLIENTES_CASH:
             if 'CONTATO' in df.columns:
                 df['CONTATO_LIMPO'] = df['CONTATO'].astype(str).str.replace(r'\D', '', regex=True).str.strip() 

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
    
    # Prepara o DF para salvar, removendo colunas temporárias se existirem
    df_to_save = df.copy()
    if 'CONTATO_LIMPO' in df_to_save.columns:
        df_to_save = df_to_save.drop(columns=['CONTATO_LIMPO'])

    csv_content = df_to_save.fillna('').to_csv(index=False, sep=',')
    content_base64 = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
    payload = {"message": commit_message, "content": content_base64, "branch": branch_to_write}
    if sha: payload["sha"] = sha 
    put_response = requests.put(api_url, headers=HEADERS, json=payload)
    if put_response.status_code in [200, 201]:
        fetch_github_data_v2.clear(); return True
    else:
        st.error(f"Falha no Commit: {put_response.json().get('message', 'Erro')}"); return False

# --- FUNÇÕES DE CASHBACK ---
def calcular_nivel_e_beneficios(gasto_acumulado: float):
    if gasto_acumulado >= 1000.01: nivel, cb_normal = 'Diamante', 0.15
    elif gasto_acumulado >= 200.01: nivel, cb_normal = 'Ouro', 0.07
    else: nivel, cb_normal = 'Prata', 0.03
    return nivel, cb_normal

def cadastrar_cliente_cashback(df_clientes, nome, contato_limpo):
    novo_cliente = {'NOME': nome, 'CONTATO': contato_limpo, 'CASHBACK_DISPONIVEL': 0.0, 'GASTO_ACUMULADO': 0.0, 'NIVEL_ATUAL': 'Prata', 'PRIMEIRA_COMPRA_FEITA': 'FALSE'}
    return pd.concat([df_clientes, pd.DataFrame([novo_cliente])], ignore_index=True)

def lancar_venda_cashback(nome: str, contato: str, valor_cashback_credito: float):
    contato_limpo = re.sub(r'\D', '', str(contato))
    df_clientes = carregar_dados(SHEET_NAME_CLIENTES_CASH)
    
    # Lida com o caso de df vazio ou sem a coluna
    if df_clientes.empty or 'CONTATO' not in df_clientes.columns:
        df_clientes = cadastrar_cliente_cashback(pd.DataFrame(columns=['NOME', 'CONTATO', 'CASHBACK_DISPONIVEL', 'GASTO_ACUMULADO', 'NIVEL_ATUAL', 'PRIMEIRA_COMPRA_FEITA']), nome, contato_limpo)
    
    df_clientes['CONTATO_LIMPO'] = df_clientes['CONTATO'].astype(str).str.replace(r'\D', '', regex=True)
    cliente_idx = df_clientes[df_clientes['CONTATO_LIMPO'] == contato_limpo].index
    
    if cliente_idx.empty:
        df_clientes = cadastrar_cliente_cashback(df_clientes, nome, contato_limpo)
        cliente_idx = df_clientes[df_clientes['CONTATO_LIMPO'] == contato_limpo].index # Busca de novo
    
    idx = cliente_idx[0]
    df_clientes.loc[idx, 'CASHBACK_DISPONIVEL'] = df_clientes.loc[idx].get('CASHBACK_DISPONIVEL', 0.0) + valor_cashback_credito
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
                    proporcao = subtotal_item / subtotal_bruto
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
            cashback = calcular_cashback_a_creditar(pedido.get('ITENS_JSON'), df_catalogo, valor_desconto)
            if cashback > 0:
                if not lancar_venda_cashback(pedido.get('NOME_CLIENTE'), pedido.get('CONTATO_CLIENTE'), cashback):
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
        if 'ITENS_JSON' in df_pedidos.columns:
            df_pedidos['SALDO_CASHBACK_CLIENTE_PEDIDO'] = df_pedidos['ITENS_JSON'].apply(extract_customer_cashback)
        else:
            df_pedidos['SALDO_CASHBACK_CLIENTE_PEDIDO'] = 0.0
            
        df_pedidos['DATA_HORA'] = pd.to_datetime(df_pedidos['DATA_HORA'], errors='coerce')
        
        for _, pedido in df_pedidos.sort_values(by="DATA_HORA", ascending=False).iterrows():
            if pedido.get('STATUS') != 'Finalizado':
                valor_total = pedido.get('VALOR_TOTAL', 0.0)
                if valor_total == 0.0:
                    try:
                        itens = ast.literal_eval(str(pedido.get('ITENS_JSON'))).get('itens', [])
                        valor_total = sum(float(i.get('preco', 0)) * int(i.get('quantidade', 0)) for i in itens)
                    except: pass
                
                data_hora = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indefinida"
                
                with st.expander(f"Pedido de **{pedido.get('NOME_CLIENTE','N/A')}** - {data_hora} - Total: R$ {valor_total:.2f}"):
                    # --- LÓGICA DE CASHBACK RESTAURADA ---
                    saldo_anterior = pedido.get('SALDO_CASHBACK_CLIENTE_PEDIDO', 0.0)
                    st.markdown(f"**Saldo Cashback do Cliente:** **R$ {saldo_anterior:.2f}**")
                    valor_desconto = pedido.get('VALOR_DESCONTO', 0.0)
                    cashback_a_creditar = calcular_cashback_a_creditar(pedido.get('ITENS_JSON'), df_catalogo, valor_desconto)
                    if cashback_a_creditar > 0.00:
                        st.markdown(f"**💰 Cashback a ser Creditado:** **R$ {cashback_a_creditar:.2f}**")
                        st.info("Este valor será creditado ao cliente **após** a finalização deste pedido.")
                    st.markdown("---")
                    # --- FIM DO BLOCO RESTAURADO ---

                    progresso = exibir_itens_pedido(pedido.get('ID_PEDIDO'), pedido.get('ITENS_JSON'), df_catalogo)
                    st.progress(progresso / 100, f"Progresso: {progresso}%")
                    if st.button("✅ Finalizar Pedido", key=f"finalizar_{pedido.get('ID_PEDIDO')}", disabled=progresso != 100):
                        if atualizar_status_pedido(pedido.get('ID_PEDIDO'), "Finalizado", df_catalogo):
                            st.success(f"Pedido {pedido.get('ID_PEDIDO')} finalizado!"); st.rerun()
                        else: st.error("Falha ao finalizar.")
                        
# --- Outras Abas ---
with tab_produtos:
    st.header("🛍️ Gerenciamento de Produtos") # Adicione aqui a lógica da sua aba de produtos
    st.info("Seção de gerenciamento de produtos.")

with tab_promocoes:
    st.header("🔥 Gerenciador de Promoções") # Adicione aqui a lógica da sua aba de promoções
    st.info("Seção de gerenciamento de promoções.")
    
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

