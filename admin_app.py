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
        
        if sheet_name == SHEET_NAME_PEDIDOS:
            content = content.replace(',"","PENDENTE",', ',"PENDENTE",')

        df = pd.read_csv(
            StringIO(content),
            sep=",",
            engine="python",
            on_bad_lines="warn",
            quotechar='"',
            escapechar="\\",
            doublequote=True
         )
        
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
    
    csv_content = df.fillna('').to_csv(index=False, sep=',')
    content_base64 = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
    payload = {"message": commit_message, "content": content_base64, "branch": branch_to_write}
    if sha: payload["sha"] = sha 
    put_response = requests.put(api_url, headers=HEADERS, json=payload)
    if put_response.status_code in [200, 201]:
        fetch_github_data_v2.clear(); return True
    else:
        st.error(f"Falha no Commit: {put_response.json().get('message', 'Erro')}"); return False

def parse_json_from_string(json_string):
    import json, ast
    if pd.isna(json_string) or not isinstance(json_string, str) or not json_string.strip():
        return {}
    s = str(json_string).strip().replace('\\"', '"').replace('""', '"')
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1].strip()
    for _ in range(3):
        try:
            data = json.loads(s)
            return data if not isinstance(data, str) else ast.literal_eval(data)
        except: pass
    return {}

def adicionar_produto(nome, preco, desc_curta, desc_longa, link_imagem, disponivel, cashback):
    df = carregar_dados(SHEET_NAME_CATALOGO).copy()
    novo_id = (df['ID'].max() + 1) if not df.empty and df['ID'].notna().any() else 1
    nova_linha = {'ID': novo_id, 'NOME': nome, 'PRECO': str(preco), 'DESCRICAOCURTA': desc_curta, 'DESCRICAOLONGA': desc_longa, 'LINKIMAGEM': link_imagem, 'DISPONIVEL': disponivel, 'CASHBACKPERCENT': str(cashback)}
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    return write_csv_to_github(df, SHEET_NAME_CATALOGO, f"Adicionar produto: {nome}")

def atualizar_produto(id_prod, nome, preco, desc_curta, desc_longa, link_img, disp, cash):
    df = carregar_dados(SHEET_NAME_CATALOGO)
    idx = df[df['ID'] == int(id_prod)].index
    if not idx.empty:
        df.loc[idx[0], ['NOME', 'PRECO', 'DESCRICAOCURTA', 'DESCRICAOLONGA', 'LINKIMAGEM', 'DISPONIVEL', 'CASHBACKPERCENT']] = [nome, str(preco), desc_curta, desc_longa, link_img, disp, str(cash)]
        return write_csv_to_github(df, SHEET_NAME_CATALOGO, f"Atualizar produto ID: {id_prod}")
    return False

def excluir_produto(id_prod):
    df = carregar_dados(SHEET_NAME_CATALOGO)
    df = df[df['ID'] != int(id_prod)]
    return write_csv_to_github(df, SHEET_NAME_CATALOGO, f"Excluir produto ID: {id_prod}")

def criar_cupom(codigo, tipo, valor, validade, val_min, limite):
    df = carregar_dados(SHEET_NAME_CUPONS)
    if not df.empty and codigo.upper() in df['CODIGO'].str.upper().tolist():
        st.error(f"O cupom '{codigo}' já existe!")
        return False
    nova_linha = {'CODIGO': codigo.upper(), 'TIPO_DESCONTO': tipo, 'VALOR': valor, 'DATA_VALIDADE': str(validade) if validade else '', 'VALOR_MINIMO_PEDIDO': val_min, 'LIMITE_USOS': limite, 'USOS_ATUAIS': 0, 'STATUS': 'ATIVO'}
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    return write_csv_to_github(df, SHEET_NAME_CUPONS, f"Criar cupom: {codigo.upper()}")

def lancar_venda_cashback(nome, contato, cashback, valor_pago):
    df = carregar_dados(SHEET_NAME_CLIENTES_CASH)
    contato_limpo = re.sub(r'\D', '', str(contato))
    df['CONTATO_LIMPO'] = df['CONTATO'].astype(str).str.replace(r'\D', '', regex=True)
    idx = df[df['CONTATO_LIMPO'] == contato_limpo].index
    if idx.empty:
        novo = {'NOME': nome, 'CONTATO': contato, 'CASHBACK_DISPONIVEL': cashback, 'GASTO_ACUMULADO': valor_pago, 'NIVEL_ATUAL': 'Prata', 'PRIMEIRA_COMPRA_FEITA': 'TRUE'}
        df = pd.concat([df.drop(columns=['CONTATO_LIMPO']), pd.DataFrame([novo])], ignore_index=True)
    else:
        df.loc[idx[0], 'CASHBACK_DISPONIVEL'] += cashback
        df.loc[idx[0], 'GASTO_ACUMULADO'] += valor_pago
        df.loc[idx[0], 'PRIMEIRA_COMPRA_FEITA'] = 'TRUE'
        df = df.drop(columns=['CONTATO_LIMPO'])
    return write_csv_to_github(df, SHEET_NAME_CLIENTES_CASH, f"Cashback: {nome}")

def extract_customer_cashback(json_data):
    data = parse_json_from_string(json_data)
    return data.get("cliente_saldo_cashback", 0.0)

def calcular_cashback_a_creditar(pedido_json, df_catalogo, desconto):
    data = parse_json_from_string(pedido_json)
    itens = data.get('itens', [])
    subtotal = sum(float(i.get('preco', 0)) * int(i.get('quantidade', 0)) for i in itens)
    if subtotal == 0: return 0.0
    cashback = 0.0
    for item in itens:
        prod = df_catalogo[df_catalogo['ID'] == int(item.get('id', -1))]
        if not prod.empty:
            cash_pct = float(str(prod.iloc[0].get('CASHBACKPERCENT', '0')).replace(',', '.'))
            if cash_pct > 0:
                sub_item = float(item.get('preco', 0)) * int(item.get('quantidade', 0))
                prop = sub_item / subtotal if subtotal > 0 else 0
                val_final = sub_item - (desconto * prop)
                cashback += val_final * (cash_pct / 100)
    return round(cashback, 2)

# --- INÍCIO DA CORREÇÃO ---
def atualizar_status_pedido(id_pedido, novo_status, df_catalogo):
    df = carregar_dados(SHEET_NAME_PEDIDOS)
    # Garante que a coluna 'ID_PEDIDO' seja do tipo string para a comparação.
    df['ID_PEDIDO'] = df['ID_PEDIDO'].astype(str)
    
    # A comparação agora é mais confiável, comparando string com string.
    idx = df[df['ID_PEDIDO'] == str(id_pedido)].index
    
    if not idx.empty:
        idx = idx[0]
        if novo_status == 'Finalizado' and df.loc[idx, 'STATUS'] != 'Finalizado':
            pedido = df.loc[idx]
            desconto = pd.to_numeric(pedido.get('VALOR_DESCONTO', 0.0), errors='coerce')
            valor_pago = pd.to_numeric(pedido.get('VALOR_TOTAL', 0.0), errors='coerce')
            cashback = calcular_cashback_a_creditar(pedido.get('ITENS_JSON'), df_catalogo, desconto)
            if cashback > 0:
                lancar_venda_cashback(pedido.get('NOME_CLIENTE'), pedido.get('CONTATO_CLIENTE'), cashback, valor_pago)
            df.loc[idx, 'VALOR_CASHBACK_CREDITADO'] = cashback
        df.loc[idx, 'STATUS'] = novo_status
        return write_csv_to_github(df, SHEET_NAME_PEDIDOS, f"Status pedido {id_pedido} para {novo_status}")
    else:
        st.error(f"Erro: Pedido com ID {id_pedido} não encontrado para atualização.")
        return False
# --- FIM DA CORREÇÃO ---

def exibir_itens_pedido(id_pedido, pedido_json, df_catalogo):
    data = parse_json_from_string(pedido_json)
    itens = data.get('itens', [])
    if not itens:
        st.warning("Nenhum item encontrado no pedido.")
        return 0
    
    total_itens, itens_sep = len(itens), 0
    key = f'pedido_{id_pedido}_itens'
    if key not in st.session_state: st.session_state[key] = [False] * total_itens

    for i, item in enumerate(itens):
        link_img = "https://placehold.co/150x150/e2e8f0/e2e8f0?text=Sem+Imagem"
        prod_id = int(item.get('id', -1))
        prod = df_catalogo[df_catalogo['ID'] == prod_id]
        
        cashback_percent = 0.0
        if not prod.empty:
            if 'LINKIMAGEM' in prod.columns and pd.notna(prod.iloc[0]['LINKIMAGEM']):
                link_img = str(prod.iloc[0]['LINKIMAGEM'])
            cashback_str = str(prod.iloc[0].get('CASHBACKPERCENT', '0')).replace(',', '.')
            cashback_percent = float(cashback_str)

        c1, c2, c3 = st.columns([0.5, 1, 3.5])
        st.session_state[key][i] = c1.checkbox(" ", st.session_state[key][i], key=f"c_{id_pedido}_{i}", label_visibility="collapsed")
        c2.image(link_img, width=100)
        sub = float(item.get('preco', 0)) * int(item.get('quantidade', 0))
        
        info_text = (
            f"**Produto:** {item.get('nome', 'N/A')}\n\n"
            f"**Quantidade:** {item.get('quantidade', 0)} | **Subtotal:** R$ {sub:.2f}\n\n"
            f"**Cashback do produto:** {cashback_percent:.2f}%"
        )
        c3.markdown(info_text)
        
        st.markdown("---")
        if st.session_state[key][i]: itens_sep += 1
    return 100 if total_itens == 0 else int((itens_sep / total_itens) * 100)

st.set_page_config(page_title="Admin Doce&Bella", layout="wide")
st.title("⭐ Painel de Administração | Doce&Bella")
tab_pedidos, tab_produtos, tab_promocoes, tab_cupons = st.tabs(["Pedidos", "Produtos", "🔥 Promoções", "🎟️ Cupons"])

with tab_pedidos:
    st.header("📋 Pedidos Recebidos")
    if st.button("Recarregar Pedidos"): st.session_state['data_version'] += 1; st.rerun()
    df_pedidos = carregar_dados(SHEET_NAME_PEDIDOS)
    df_catalogo = carregar_dados(SHEET_NAME_CATALOGO)
    df_pedidos = df_pedidos.fillna("")
    if df_pedidos.empty: st.info("Nenhum pedido encontrado.")
    else:
        df_pedidos['DATA_HORA'] = pd.to_datetime(df_pedidos['DATA_HORA'], errors='coerce')
        df_pedidos.sort_values(by="DATA_HORA", ascending=False, inplace=True)
        st.header("⏳ Pedidos Pendentes")
        pendentes = df_pedidos[~df_pedidos.get('STATUS', pd.Series(dtype=str)).fillna('').isin(['Finalizado', 'Cancelado'])]
        if pendentes.empty: st.info("Nenhum pedido pendente.")
        else:
            for _, pedido in pendentes.iterrows():
                id_pedido = pedido.get('ID_PEDIDO')
                data_hora = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indefinida"
                with st.expander(f"Pedido de **{pedido.get('NOME_CLIENTE','N/A')}** - {data_hora} - Total: R$ {pd.to_numeric(pedido.get('VALOR_TOTAL', 0.0), errors='coerce'):.2f}"):
                    st.markdown(f"**Contato:** {pedido.get('CONTATO_CLIENTE', 'N/A')} | **ID do Pedido:** {id_pedido}")
                    json_data = parse_json_from_string(pedido.get('ITENS_JSON'))
                    desconto = pd.to_numeric(json_data.get('desconto_cupom', pedido.get('VALOR_DESCONTO', 0.0)), errors='coerce')
                    saldo_cashback = extract_customer_cashback(pedido.get('ITENS_JSON'))
                    st.metric(label="Saldo Cashback do Cliente", value=f"R$ {saldo_cashback:.2f}")
                    cashback = calcular_cashback_a_creditar(pedido.get('ITENS_JSON'), df_catalogo, desconto)
                    if cashback > 0: 
                        st.success(f"**💰 Cashback a ser Creditado:** R$ {cashback:.2f}")
                        st.info("Este valor será creditado ao cliente após a finalização deste pedido.")
                    st.markdown("---")
                    progresso = exibir_itens_pedido(id_pedido, pedido.get('ITENS_JSON'), df_catalogo)
                    st.progress(progresso / 100, f"Progresso de Separação: {progresso}%")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Finalizar", key=f"fin_{id_pedido}", disabled=progresso!=100, use_container_width=True):
                        if atualizar_status_pedido(id_pedido, "Finalizado", df_catalogo): st.success("Pedido finalizado!"); st.rerun()
                    if c2.button("✖️ Cancelar", key=f"can_{id_pedido}", type="secondary", use_container_width=True):
                        if atualizar_status_pedido(id_pedido, "Cancelado", df_catalogo): st.warning("Pedido cancelado!"); st.rerun()
                        
        st.header("✅ Pedidos Finalizados e Cancelados")
        concluidos = df_pedidos[df_pedidos.get('STATUS', pd.Series(dtype=str)).isin(['Finalizado', 'Cancelado'])]
        if concluidos.empty: st.info("Nenhum pedido finalizado ou cancelado.")
        else:
             for _, pedido in concluidos.iterrows():
                data_hora = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indefinida"
                cor = "green" if pedido.get('STATUS') == 'Finalizado' else "red"
                with st.expander(f":{cor}[{pedido.get('STATUS')}] Pedido de **{pedido.get('NOME_CLIENTE','N/A')}** - {data_hora} - Total: R$ {pd.to_numeric(pedido.get('VALOR_TOTAL', 0.0), errors='coerce'):.2f}"):
                     st.write(f"ID do Pedido: {pedido.get('ID_PEDIDO')}")
                     if pedido.get('STATUS') == 'Finalizado': st.info(f"Cashback creditado: R$ {pd.to_numeric(pedido.get('VALOR_CASHBACK_CREDITADO', 0.0), errors='coerce'):.2f}")

with tab_produtos:
    st.header("🛍️ Gerenciamento de Produtos")
    df_prods = carregar_dados(SHEET_NAME_CATALOGO)
    with st.expander("➕ Adicionar Novo Produto"):
        with st.form("form_novo_produto", clear_on_submit=True):
            nome, preco = st.text_input("Nome"), st.number_input("Preço", 0.01, format="%.2f")
            desc_c, desc_l = st.text_input("Descrição Curta"), st.text_area("Descrição Longa")
            link, cash = st.text_input("Link Imagem"), st.number_input("Cashback (%)", 0.0, 100.0, format="%.2f")
            disp = st.checkbox("Disponível", True)
            if st.form_submit_button("Salvar"):
                if nome and preco > 0 and adicionar_produto(nome, preco, desc_c, desc_l, link, disp, cash):
                    st.success("Produto adicionado!"); st.rerun()
    st.subheader("📝 Editar/Excluir")
    if df_prods.empty: st.info("Nenhum produto.")
    else:
        opts = [f"{r.get('ID','N/A')} - {r.get('NOME','N/A')}" for _, r in df_prods.iterrows()]
        sel = st.selectbox("Selecione um produto para editar", opts, key="sel_prod_edit")
        if sel:
            id_prod = int(sel.split(' - ')[0])
            prod = df_prods[df_prods['ID'] == id_prod].iloc[0]
            with st.form(f"form_edit_{id_prod}"):
                p_f = float(str(prod.get('PRECO','0.01')).replace(',','.'))
                c_f = float(str(prod.get('CASHBACKPERCENT','0.0')).replace(',','.'))
                d = prod.get('DISPONIVEL', False)
                if isinstance(d, str): d = d.upper() == 'TRUE'
                nome_e, preco_e = st.text_input("Nome", prod.get('NOME', '')), st.number_input("Preço (R$)", 0.01, p_f, "%.2f")
                desc_c_e, desc_l_e = st.text_input("Descrição Curta", prod.get('DESCRICAOCURTA', '')), st.text_area("Descrição Longa", prod.get('DESCRICAOLONGA', ''))
                link_e, cash_e = st.text_input("Link Imagem", prod.get('LINKIMAGEM', '')), st.number_input("Cashback (%)", 0.0, 100.0, c_f, "%.2f")
                disp_e = st.checkbox("Disponível", d)
                c1, c2 = st.columns(2)
                if c1.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True) and atualizar_produto(id_prod, nome_e, preco_e, desc_c_e, desc_l_e, link_e, disp_e, cash_e):
                    st.success("Produto atualizado!"); st.rerun()
                if c2.form_submit_button("🗑️ Excluir Produto", use_container_width=True) and excluir_produto(id_prod):
                    st.success("Produto excluído!"); st.rerun()

with tab_promocoes:
    st.header("🔥 Gerenciador de Promoções")
    st.info("Em desenvolvimento.")
    
with tab_cupons:
    st.header("🎟️ Gerenciador de Cupons")
    with st.expander("➕ Criar Novo Cupom"):
        with st.form("form_novo_cupom", clear_on_submit=True):
            c1, c2 = st.columns(2)
            codigo, tipo = c1.text_input("Código").upper(), c1.selectbox("Tipo", ["PERCENTUAL", "FIXO"])
            valor = c2.number_input(f"Valor ({'%' if tipo == 'PERCENTUAL' else 'R$'})", 0.01, format="%.2f")
            sem_val = st.checkbox("Sem data de validade")
            validade = st.date_input("Validade", disabled=sem_val, min_value=date.today())
            val_min, uso_ilim = st.number_input("Compra mínima (R$)", 0.0, format="%.2f"), st.checkbox("Uso ilimitado")
            limite = st.number_input("Limite de usos", 1, step=1, disabled=uso_ilim)
            if st.form_submit_button("Salvar Cupom"):
                if codigo and valor > 0 and criar_cupom(codigo, tipo, valor, None if sem_val else validade, val_min, 0 if uso_ilim else limite):
                    st.success("Cupom criado!"); st.rerun()
    st.subheader("📝 Cupons Cadastrados")
    df_cupons = carregar_dados(SHEET_NAME_CUPONS)
    if not df_cupons.empty: st.dataframe(df_cupons, use_container_width=True)

