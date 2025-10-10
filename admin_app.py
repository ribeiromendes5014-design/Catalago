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
            if sheet_name not in [SHEET_NAME_CLIENTES_CASH, SHEET_NAME_CUPONS]:
                st.warning(f"Erro ao buscar '{csv_filename}': Status {response.status_code}. Repositório: {repo_to_use}")
            return pd.DataFrame()

        content = base64.b64decode(response.json()["content"]).decode("utf-8")
        
        if not content.strip(): 
            return pd.DataFrame()

        try:
            df = pd.read_csv(StringIO(content), sep=",", engine='python', on_bad_lines='warn')
        except Exception as read_error:
            st.error(f"Erro de leitura do CSV de {csv_filename}. Causa: {read_error}. O arquivo pode estar vazio ou mal formatado.")
            return pd.DataFrame()

        df.columns = df.columns.str.strip().str.upper().str.replace(' ', '_')

        if "PRECO" in df.columns:
            df["PRECO"] = df["PRECO"].astype(str).str.replace(".", ",", regex=False)

        # --- Tratamentos específicos para PEDIDOS ---
        if sheet_name == SHEET_NAME_PEDIDOS:
            if "STATUS" not in df.columns: df["STATUS"] = ""
            if "ID_PEDIDO" in df.columns: df['ID_PEDIDO'] = df['ID_PEDIDO'].astype(str)
            
            # Garante que colunas de valor sejam numéricas, tratando erros e valores vazios
            for col in ['VALOR_TOTAL', 'VALOR_DESCONTO']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                else:
                    df[col] = 0.0

        if sheet_name == SHEET_NAME_CATALOGO and "ID" in df.columns:
            df["ID"] = pd.to_numeric(df["ID"], errors="coerce")
            df.dropna(subset=["ID"], inplace=True)
            df["ID"] = df["ID"].astype(int)

        if sheet_name == SHEET_NAME_CLIENTES_CASH:
             if 'CASHBACK_DISPONÍVEL' in df.columns: df.rename(columns={'CASHBACK_DISPONÍVEL': 'CASHBACK_DISPONIVEL'}, inplace=True)
             if 'TELEFONE' in df.columns: df.rename(columns={'TELEFONE': 'CONTATO'}, inplace=True)
             if 'CONTATO' in df.columns:
                 df['CONTATO_LIMPO'] = df['CONTATO'].astype(str).str.replace(r'\D', '', regex=True).str.strip() 
                 df['CASHBACK_DISPONIVEL'] = pd.to_numeric(df.get('CASHBACK_DISPONIVEL', 0.0), errors='coerce').fillna(0.0)
                 df['GASTO_ACUMULADO'] = pd.to_numeric(df.get('GASTO_ACUMULADO', 0.0), errors='coerce').fillna(0.0)
                 df['NIVEL_ATUAL'] = df['NIVEL_ATUAL'].fillna('Prata')
             for col in ['NOME', 'CONTATO', 'CASHBACK_DISPONIVEL', 'NIVEL_ATUAL', 'GASTO_ACUMULADO', 'CONTATO_LIMPO', 'PRIMEIRA_COMPRA_FEITA']:
                 if col not in df.columns: df[col] = '' if col not in ['CASHBACK_DISPONIVEL', 'GASTO_ACUMULADO'] else 0.0
             df.dropna(subset=['CONTATO_LIMPO'], inplace=True)

        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados de '{csv_filename}': {e}")
        return pd.DataFrame()


def carregar_dados(sheet_name):
    return fetch_github_data_v2(sheet_name, st.session_state['data_version'])

def write_csv_to_github(df, sheet_name, commit_message):
    csv_filename = f"{sheet_name}.csv"
    if sheet_name in [SHEET_NAME_PEDIDOS, SHEET_NAME_CLIENTES_CASH, SHEET_NAME_CUPONS]:
        repo_to_write = PEDIDOS_REPO_FULL
        branch_to_write = PEDIDOS_BRANCH
    else:
        repo_to_write = REPO_NAME_FULL
        branch_to_write = BRANCH
    api_url = f"https://api.github.com/repos/{repo_to_write}/contents/{csv_filename}"
    
    response = requests.get(api_url, headers=HEADERS)
    sha = response.json().get('sha') if response.status_code == 200 else None
    
    df_to_save = df.copy()
    df_to_save.columns = df_to_save.columns.str.strip().str.upper().str.replace(' ', '_')
    csv_content = df_to_save.fillna('').to_csv(index=False, sep=',').replace('\n\n', '\n')
    content_base64 = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
    
    payload = {"message": commit_message, "content": content_base64, "branch": branch_to_write}
    if sha: payload["sha"] = sha 
    
    put_response = requests.put(api_url, headers=HEADERS, json=payload)
    if put_response.status_code in [200, 201]:
        fetch_github_data_v2.clear() 
        return True
    else:
        st.error(f"Falha no Commit: {put_response.status_code} - {put_response.json().get('message', 'Erro')}")
        return False

# --- FUNÇÕES DE CASHBACK ---
def calcular_cashback_a_creditar(pedido_json, df_catalogo, valor_desconto_total=0.0):
    """
    Calcula o cashback com base no valor final pago pelo cliente (após descontos).
    """
    valor_cashback_total = 0.0
    subtotal_bruto = 0.0
    
    try:
        try: detalhes_pedido = json.loads(str(pedido_json))
        except: detalhes_pedido = ast.literal_eval(str(pedido_json))
        
        itens = detalhes_pedido.get('itens', [])
        if not itens: return 0.0

        # 1. Calcula o subtotal bruto (sem descontos)
        for item in itens:
            preco_unitario = float(item.get('preco', 0.0))
            quantidade = int(item.get('quantidade', 0))
            subtotal_bruto += preco_unitario * quantidade

        if subtotal_bruto == 0: return 0.0

        # 2. Calcula o cashback para cada item, proporcional ao desconto
        for item in itens:
            item_id = pd.to_numeric(item.get('id'), errors='coerce')
            if pd.isna(item_id): continue

            produto_catalogo = df_catalogo[df_catalogo['ID'] == int(item_id)]
            if produto_catalogo.empty: continue
            
            cashback_percent_str = str(produto_catalogo.iloc[0].get('CASHBACKPERCENT', '0')).replace(',', '.')
            try: cashback_percent = float(cashback_percent_str)
            except: cashback_percent = 0.0

            if cashback_percent > 0:
                preco_unitario = float(item.get('preco', 0.0))
                quantidade = int(item.get('quantidade', 0))
                subtotal_item = preco_unitario * quantidade
                
                # Distribui o desconto total proporcionalmente ao valor do item
                proporcao_item = subtotal_item / subtotal_bruto
                desconto_no_item = valor_desconto_total * proporcao_item
                
                valor_final_item = subtotal_item - desconto_no_item
                
                # Calcula o cashback sobre o valor efetivamente pago pelo item
                valor_cashback_total += valor_final_item * (cashback_percent / 100)
                
    except Exception:
        return 0.0
        
    return round(valor_cashback_total, 2)

def lancar_venda_cashback(nome: str, contato: str, valor_cashback_credito: float):
    contato_limpo = re.sub(r'\D', '', str(contato))
    df_clientes = carregar_dados(SHEET_NAME_CLIENTES_CASH)
    
    if 'CONTATO_LIMPO' not in df_clientes.columns and 'CONTATO' in df_clientes.columns:
        df_clientes['CONTATO_LIMPO'] = df_clientes['CONTATO'].astype(str).str.replace(r'\D', '', regex=True)

    cliente_idx = df_clientes[df_clientes['CONTATO_LIMPO'] == contato_limpo].index
    
    if cliente_idx.empty:
        # Cadastra novo cliente
        novo_cliente = {'NOME': nome, 'CONTATO': contato_limpo, 'CASHBACK_DISPONIVEL': valor_cashback_credito, 'GASTO_ACUMULADO': 0.0, 'NIVEL_ATUAL': 'Prata', 'PRIMEIRA_COMPRA_FEITA': 'TRUE', 'CONTATO_LIMPO': contato_limpo}
        df_clientes = pd.concat([df_clientes, pd.DataFrame([novo_cliente])], ignore_index=True)
        st.toast(f"Cliente '{nome}' cadastrado.", icon='👤')
    else:
        idx = cliente_idx[0]
        df_clientes.loc[idx, 'CASHBACK_DISPONIVEL'] += valor_cashback_credito
        df_clientes.loc[idx, 'PRIMEIRA_COMPRA_FEITA'] = 'TRUE'
    
    if write_csv_to_github(df_clientes, SHEET_NAME_CLIENTES_CASH, f"CRÉDITO CASHBACK: {nome} (R$ {valor_cashback_credito:.2f})"):
        st.toast(f"Cashback creditado: +R$ {valor_cashback_credito:.2f}", icon='💵')
        return True
    return False

# --- FUNÇÕES DE PEDIDOS ---
def atualizar_status_pedido(id_pedido, novo_status, df_catalogo):
    df = carregar_dados(SHEET_NAME_PEDIDOS).copy()
    if df.empty: return False
    
    index_to_update = df[df['ID_PEDIDO'] == str(id_pedido)].index
    if not index_to_update.empty:
        idx = index_to_update[0]
        
        if novo_status == 'Finalizado' and df.loc[idx, 'STATUS'] != 'Finalizado':
            pedido = df.loc[idx]
            valor_desconto = pedido.get('VALOR_DESCONTO', 0.0)
            valor_cashback = calcular_cashback_a_creditar(pedido.get('ITENS_JSON'), df_catalogo, valor_desconto)
            
            if valor_cashback > 0:
                if not lancar_venda_cashback(pedido.get('NOME_CLIENTE'), pedido.get('CONTATO_CLIENTE'), valor_cashback):
                    st.warning("Falha ao lançar cashback. Pedido não finalizado.")
                    return False
            df.loc[idx, 'VALOR_CASHBACK_CREDITADO'] = valor_cashback
            
        df.loc[idx, 'STATUS'] = novo_status
        if novo_status != 'Finalizado':
            df.loc[idx, 'VALOR_CASHBACK_CREDITADO'] = 0.0
        
        return write_csv_to_github(df, SHEET_NAME_PEDIDOS, f"Status pedido {id_pedido} para {novo_status}")
    return False

def exibir_itens_pedido(id_pedido, pedido_json, df_catalogo):
    try:
        try: detalhes_pedido = json.loads(str(pedido_json))
        except: detalhes_pedido = ast.literal_eval(str(pedido_json))
            
        itens = detalhes_pedido.get('itens', [])
        total_itens, itens_separados = len(itens), 0
        
        key_progress = f'pedido_{id_pedido}_itens_separados'
        if key_progress not in st.session_state: st.session_state[key_progress] = [False] * total_itens
            
        for i, item in enumerate(itens):
            link_imagem = "https://placehold.co/150x150/e2e8f0/e2e8f0?text=Sem+Imagem" # Placeholder
            item_id = pd.to_numeric(item.get('id'), errors='coerce')
            
            # Lógica de busca da imagem mais robusta
            if not pd.isna(item_id) and not df_catalogo.empty and int(item_id) in df_catalogo['ID'].values: 
                link_na_tabela = df_catalogo.loc[df_catalogo['ID'] == int(item_id), 'LINKIMAGEM'].iloc[0]
                if pd.notna(link_na_tabela) and str(link_na_tabela).strip():
                    link_imagem = str(link_na_tabela)

            col_check, col_img, col_detalhes = st.columns([0.5, 1, 3.5])
            st.session_state[key_progress][i] = col_check.checkbox(" ", value=st.session_state[key_progress][i], key=f"check_{id_pedido}_{i}", label_visibility="collapsed")
            
            col_img.image(link_imagem, width=100)
            subtotal = float(item.get('preco', 0)) * int(item.get('quantidade', 0))
            col_detalhes.markdown(f"**{item.get('nome', 'N/A')}**\n\n**Qtd:** {item.get('quantidade', 0)} | **Subtotal:** R$ {subtotal:.2f}")
            st.markdown("---")
            if st.session_state[key_progress][i]: itens_separados += 1
                
        return int((itens_separados / total_itens) * 100) if total_itens > 0 else 100
        
    except Exception as e: 
        st.error(f"Erro ao processar itens do pedido. Verifique o JSON. Detalhe: {e}")
        return 0 

# Demais funções (CRUD de produtos, promoções, cupons) permanecem as mesmas
def excluir_pedido(id_pedido):
    df = carregar_dados(SHEET_NAME_PEDIDOS)
    df = df[df['ID_PEDIDO'] != str(id_pedido)]
    return write_csv_to_github(df, SHEET_NAME_PEDIDOS, f"Excluir pedido {id_pedido}")

def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel, cashback_percent_prod=0.0):
    df = carregar_dados(SHEET_NAME_CATALOGO).copy()
    novo_id = (df['ID'].max() + 1) if not df.empty and df['ID'].notna().any() else 1
    nova_linha = {'ID': novo_id, 'NOME': nome, 'PRECO': str(preco).replace('.', ','), 'DESCRICAOCURTA': desc_curta, 'DESCRICAOLONGA': desc_longa, 'LINKIMAGEM': link_imagem, 'DISPONIVEL': disponivel, 'CASHBACKPERCENT': str(cashback_percent_prod).replace('.', ',')}
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    return write_csv_to_github(df, SHEET_NAME_CATALOGO, f"Adicionar produto: {nome}")

def atualizar_produto(id_produto, nome, preco, desc_curta, desc_longa, link_imagem, disponivel, cashback_percent_prod=0.0):
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

def criar_promocao(id_produto, nome_produto, preco_original, preco_promocional, data_inicio, data_fim):
    df = carregar_dados(SHEET_NAME_PROMOCOES)
    nova_linha = {'ID_PROMOCAO': int(time.time()), 'ID_PRODUTO': str(id_produto), 'NOME_PRODUTO': nome_produto, 'PRECO_ORIGINAL': str(preco_original), 'PRECO_PROMOCIONAL': str(preco_promocional).replace('.', ','), 'STATUS': "Ativa", 'DATA_INICIO': str(data_inicio), 'DATA_FIM': str(data_fim)}
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    return write_csv_to_github(df, SHEET_NAME_PROMOCOES, f"Criar promoção para {nome_produto}")

def excluir_promocao(id_promocao):
    df = carregar_dados(SHEET_NAME_PROMOCOES)
    df = df[df['ID_PROMOCAO'] != int(id_promocao)]
    return write_csv_to_github(df, SHEET_NAME_PROMOCOES, f"Excluir promoção ID: {id_promocao}")

def atualizar_promocao(id_promocao, preco_promocional, data_inicio, data_fim, status):
    df = carregar_dados(SHEET_NAME_PROMOCOES)
    idx = df[df['ID_PROMOCAO'] == int(id_promocao)].index
    if not idx.empty:
        df.loc[idx[0], ['PRECO_PROMOCIONAL', 'DATA_INICIO', 'DATA_FIM', 'STATUS']] = [str(preco_promocional).replace('.', ','), str(data_inicio), str(data_fim), status]
        return write_csv_to_github(df, SHEET_NAME_PROMOCOES, f"Atualizar promoção ID: {id_promocao}")
    return False

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
    if st.button("Recarregar Pedidos"): 
        st.session_state['data_version'] += 1; st.rerun() 
    
    df_pedidos_raw = carregar_dados(SHEET_NAME_PEDIDOS)
    df_catalogo_pedidos = carregar_dados(SHEET_NAME_CATALOGO)
    
    if df_pedidos_raw.empty:
        st.info("Nenhum pedido foi encontrado.")
    else:
        df_pedidos_raw['DATA_HORA'] = pd.to_datetime(df_pedidos_raw['DATA_HORA'], errors='coerce')
        # Filtros aqui se necessário...
        
        st.markdown("---")
        pedidos_pendentes = df_pedidos_raw[df_pedidos_raw['STATUS'] != 'Finalizado']
        
        st.header(f"⏳ Pedidos Pendentes ({len(pedidos_pendentes)})")
        if pedidos_pendentes.empty: st.info("Nenhum pedido pendente.")
        else:
            for _, pedido in pedidos_pendentes.sort_values(by="DATA_HORA", ascending=False).iterrows():
                valor_total_pedido = pedido.get('VALOR_TOTAL', 0.0)
                data_hora_str = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indefinida"
                
                with st.expander(f"Pedido de **{pedido['NOME_CLIENTE']}** - {data_hora_str} - Total: R$ {valor_total_pedido:.2f}"):
                    # Exibição do Cupom e Desconto
                    cupom_aplicado = pedido.get('CUPOM_APLICADO')
                    valor_desconto = pedido.get('VALOR_DESCONTO', 0.0)
                    
                    if pd.notna(cupom_aplicado) and cupom_aplicado.strip():
                        st.success(f"🎟️ Cupom Aplicado: **{cupom_aplicado}** (-R$ {valor_desconto:.2f})")

                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{pedido['ID_PEDIDO']}`")
                    st.markdown("---")
                    
                    cashback_a_creditar = calcular_cashback_a_creditar(pedido.get('ITENS_JSON'), df_catalogo_pedidos, valor_desconto)
                    if cashback_a_creditar > 0:
                        st.markdown(f"**💰 Cashback a ser Creditado:** **R$ {cashback_a_creditar:.2f}**")
                        st.info("Valor calculado sobre o total pago após desconto.")
                    
                    progresso = exibir_itens_pedido(pedido['ID_PEDIDO'], pedido.get('ITENS_JSON'), df_catalogo_pedidos)
                    st.progress(progresso / 100, f"Progresso de Separação: {progresso}%")
                    
                    if st.button("✅ Finalizar Pedido", key=f"finalizar_{pedido['ID_PEDIDO']}", disabled=progresso != 100):
                        if atualizar_status_pedido(pedido['ID_PEDIDO'], "Finalizado", df_catalogo_pedidos):
                            st.success(f"Pedido {pedido['ID_PEDIDO']} finalizado!")
                            if f'pedido_{pedido["ID_PEDIDO"]}_itens_separados' in st.session_state: del st.session_state[f'pedido_{pedido["ID_PEDIDO"]}_itens_separados']
                            st.session_state['data_version'] += 1; st.rerun()
                        else: st.error("Falha ao finalizar pedido.")
                        
        pedidos_finalizados = df_pedidos_raw[df_pedidos_raw['STATUS'] == 'Finalizado']
        st.header(f"✅ Pedidos Finalizados ({len(pedidos_finalizados)})")
        # Lógica para exibir finalizados...

# ... (Restante do código para as outras abas) ...
with tab_produtos:
    st.header("🛍️ Gerenciamento de Produtos")
    df_produtos_catalogo = carregar_dados(SHEET_NAME_CATALOGO)
    with st.expander("➕ Adicionar Novo Produto"):
        with st.form("form_novo_produto", clear_on_submit=True):
            novo_nome, novo_preco = st.text_input("Nome do Produto"), st.number_input("Preço (R$)", 0.01, format="%.2f")
            novo_desc_curta, novo_desc_longa = st.text_input("Descrição Curta"), st.text_area("Descrição Longa")
            novo_link_imagem, novo_cashback = st.text_input("Link da Imagem"), st.number_input("Cashback (%)", 0.0, 100.0, format="%.2f")
            novo_disponivel = st.checkbox("Disponível para Venda", True)
            if st.form_submit_button("Salvar Novo Produto"):
                if novo_nome and novo_preco > 0:
                    if adicionar_produto(novo_nome, novo_preco, novo_desc_curta, novo_desc_longa, novo_link_imagem, novo_disponivel, novo_cashback): st.success(f"Produto '{novo_nome}' adicionado!"); st.session_state['data_version'] += 1; st.rerun()
                    else: st.error("Falha ao adicionar produto.")
                else: st.warning("Preencha o nome e o preço.")
    st.markdown("---")
    st.subheader("📝 Editar/Excluir Produtos Existentes")
    if df_produtos_catalogo.empty: st.info("Nenhum produto cadastrado.")
    else:
        opcoes_produtos = df_produtos_catalogo.apply(lambda r: f"{r['ID']} - {r['NOME']}", axis=1).tolist()
        produto_selecionado_str = st.selectbox("Selecione o Produto para Editar", opcoes_produtos)
        if produto_selecionado_str:
            id_selecionado = int(produto_selecionado_str.split(' - ')[0])
            produto_atual = df_produtos_catalogo[df_produtos_catalogo['ID'] == id_selecionado].iloc[0]
            with st.form("form_editar_produto"):
                st.info(f"Editando produto ID: {id_selecionado}")
                try: preco_float = float(str(produto_atual.get('PRECO', '0.01')).replace(',', '.'))
                except: preco_float = 0.01
                try: cashback_float = float(str(produto_atual.get('CASHBACKPERCENT', '0.0')).replace(',', '.'))
                except: cashback_float = 0.0
                disponivel_default = produto_atual.get('DISPONIVEL', False)
                if isinstance(disponivel_default, str): disponivel_default = disponivel_default.upper() == 'TRUE'
                
                edit_nome = st.text_input("Nome", value=produto_atual.get('NOME', ''))
                edit_preco = st.number_input("Preço (R$)", 0.01, format="%.2f", value=preco_float)
                edit_desc_curta = st.text_input("Descrição Curta", value=produto_atual.get('DESCRICAOCURTA', ''))
                edit_desc_longa = st.text_area("Descrição Longa", value=produto_atual.get('DESCRICAOLONGA', ''))
                edit_link_imagem = st.text_input("Link da Imagem", value=produto_atual.get('LINKIMAGEM', ''))
                edit_cashback = st.number_input("Cashback (%)", 0.0, 100.0, format="%.2f", value=cashback_float)
                edit_disponivel = st.checkbox("Disponível", value=disponivel_default)
                
                col_update, col_delete = st.columns(2)
                if col_update.form_submit_button("💾 Salvar Alterações", type="primary"):
                    if edit_nome and edit_preco > 0:
                        if atualizar_produto(id_selecionado, edit_nome, edit_preco, edit_desc_curta, edit_desc_longa, edit_link_imagem, edit_disponivel, edit_cashback): st.success(f"Produto '{edit_nome}' atualizado!"); st.session_state['data_version'] += 1; st.rerun()
                        else: st.error("Falha ao atualizar produto.")
                    else: st.warning("Preencha nome e preço.")
                if col_delete.form_submit_button("🗑️ Excluir Produto"):
                    if excluir_produto(id_selecionado): st.success(f"Produto ID {id_selecionado} excluído!"); st.session_state['data_version'] += 1; st.rerun()
                    else: st.error("Falha ao excluir produto.")

with tab_promocoes:
    st.header("🔥 Gerenciador de Promoções")
    # Código da aba de promoções...

with tab_cupons:
    st.header("🎟️ Gerenciador de Cupons de Desconto")
    # Código da aba de cupons...

