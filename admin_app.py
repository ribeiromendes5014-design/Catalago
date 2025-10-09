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
import ast

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos"
SHEET_NAME_PEDIDOS = "pedidos"
SHEET_NAME_PROMOCOES = "promocoes"
# === NOVO: Constante para Clientes Cashback ===
SHEET_NAME_CLIENTES_CASH = "clientes_cash"
# ==============================================

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
            if sheet_name == SHEET_NAME_CLIENTES_CASH and response.status_code == 404:
                return pd.DataFrame(columns=['NOME', 'CONTATO', 'CASHBACK_DISPONIVEL', 'NIVEL_ATUAL', 'TOTAL_ACUMULADO'])
            # st.warning(f"Erro ao buscar '{csv_filename}': {response.status_code}")
            return pd.DataFrame()

        # Decodifica o conteúdo base64 retornado pela API
        content = base64.b64decode(response.json()["content"]).decode("utf-8")

        # Converte o conteúdo em DataFrame
        from io import StringIO
        df = pd.read_csv(StringIO(content), sep=",")

        # Padroniza as colunas (Incluindo a substituição de espaços por _ para consistência)
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
        
        # === Padronização para Clientes Cashback (limpeza e types) ===
        if sheet_name == SHEET_NAME_CLIENTES_CASH:
            if 'CASHBACK_DISPONÍVEL' in df.columns:
                 df.rename(columns={'CASHBACK_DISPONÍVEL': 'CASHBACK_DISPONIVEL'}, inplace=True)
            if 'TELEFONE' in df.columns:
                 df.rename(columns={'TELEFONE': 'CONTATO'}, inplace=True)

            if 'CONTATO' in df.columns:
                df['CONTATO'] = df['CONTATO'].astype(str).str.replace(r'\D', '', regex=True).str.strip() 
                df['CASHBACK_DISPONIVEL'] = pd.to_numeric(df.get('CASHBACK_DISPONIVEL', 0.0), errors='coerce').fillna(0.0)
                df['TOTAL_ACUMULADO'] = pd.to_numeric(df.get('TOTAL_ACUMULADO', 0.0), errors='coerce').fillna(0.0)
                
                for col in ['NOME', 'CONTATO', 'CASHBACK_DISPONIVEL', 'NIVEL_ATUAL', 'TOTAL_ACUMULADO']:
                    if col not in df.columns: df[col] = '' if col != 'CASHBACK_DISPONIVEL' and col != 'TOTAL_ACUMULADO' else 0.0
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

# =========================================================================
# === NOVAS FUNÇÕES DE CASHBACK ===
# =========================================================================

def calcular_cashback_a_creditar(pedido_json, df_catalogo):
    """Calcula o valor total de cashback a ser creditado a partir do pedido JSON."""
    valor_cashback_total = 0.0
    
    # Adiciona a verificação de tipo para evitar erros de JSONDecodeError com float ou nan
    if not isinstance(pedido_json, str) or pedido_json.strip().lower() in ('nan', '{}', ''):
        return 0.0

    try:
        # Tenta carregar o JSON
        detalhes_pedido = json.loads(pedido_json)
        itens = detalhes_pedido.get('itens', [])
        
        for item in itens:
            item_id = pd.to_numeric(item.get('id'), errors='coerce')
            if pd.isna(item_id) or df_catalogo.empty:
                 continue
            
            # Garante que o ID é inteiro para a busca
            produto_catalogo = df_catalogo[df_catalogo['ID'] == int(item_id)]
            
            if not produto_catalogo.empty:
                # Usa a coluna 'CASHBACKPERCENT' do catálogo
                cashback_percent = pd.to_numeric(produto_catalogo.iloc[0].get('CASHBACKPERCENT', 0), errors='coerce').fillna(0)
                
                if cashback_percent > 0:
                    # Usa o preço registrado na linha do pedido, que é o preço final.
                    preco_unitario = float(item.get('preco', 0.0))
                    quantidade = int(item.get('quantidade', 0))
                    
                    valor_item = preco_unitario * quantidade
                    cashback_item = valor_item * (cashback_percent / 100)
                    valor_cashback_total += cashback_item
                    
    except Exception as e:
        # st.error(f"Erro ao calcular cashback: {e}. JSON: {pedido_json[:100]}")
        return 0.0
        
    return valor_cashback_total

def creditar_cashback_e_atualizar_cliente(contato_cliente, valor_a_creditar, nome_cliente_pedido):
    """
    Credita o valor ao saldo do cliente no clientes_cash.csv.
    Cria o cliente se ele não existir.
    """
    # Força a atualização dos dados do cliente_cash para garantir que estamos lendo a versão mais recente
    st.session_state['data_version'] += 1 
    df_cash = carregar_dados(SHEET_NAME_CLIENTES_CASH).copy()
    contato_limpo = str(contato_cliente).replace('(', '').replace(')', '').replace('-', '').replace(' ', '').strip()

    if df_cash.empty:
        df_cash = pd.DataFrame(columns=['NOME', 'CONTATO', 'CASHBACK_DISPONIVEL', 'NIVEL_ATUAL', 'TOTAL_ACUMULADO'])
    
    # Busca pelo cliente
    cliente_idx = df_cash[df_cash['CONTATO'] == contato_limpo].index
    
    # 1. Cria ou atualiza o registro
    if cliente_idx.empty:
        nome_cliente = nome_cliente_pedido if nome_cliente_pedido and nome_cliente_pedido.strip() else 'Cliente Novo'
        novo_registro = {
            'NOME': nome_cliente,
            'CONTATO': contato_limpo,
            'CASHBACK_DISPONIVEL': valor_a_creditar,
            'NIVEL_ATUAL': 'Bronze',
            'TOTAL_ACUMULADO': valor_a_creditar 
        }
        # Adiciona nova linha com o cabeçalho correto
        df_cash = pd.concat([df_cash, pd.DataFrame([novo_registro])], ignore_index=True)
        cliente_idx = df_cash[df_cash['CONTATO'] == contato_limpo].index # Busca o novo índice
    
    # 2. Atualiza os saldos e nível
    if not cliente_idx.empty:
        idx = cliente_idx[0]
        
        # Garante que o nome seja atualizado se for "Cliente Novo" ou vazio
        if (df_cash.loc[idx, 'NOME'] == 'Cliente Novo' or not df_cash.loc[idx, 'NOME'].strip()) and nome_cliente_pedido.strip():
             df_cash.loc[idx, 'NOME'] = nome_cliente_pedido
        
        df_cash.loc[idx, 'CASHBACK_DISPONIVEL'] = df_cash.loc[idx, 'CASHBACK_DISPONIVEL'] + valor_a_creditar
        df_cash.loc[idx, 'TOTAL_ACUMULADO'] = df_cash.loc[idx, 'TOTAL_ACUMULADO'] + valor_a_creditar
        
        # Lógica simplificada de Nível
        total_acumulado = df_cash.loc[idx, 'TOTAL_ACUMULADO']
        if total_acumulado >= 1500:
            df_cash.loc[idx, 'NIVEL_ATUAL'] = 'Ouro'
        elif total_acumulado >= 500:
            df_cash.loc[idx, 'NIVEL_ATUAL'] = 'Prata'
        else:
            df_cash.loc[idx, 'NIVEL_ATUAL'] = 'Bronze'
        
        commit_msg = f"Cashback creditado: R$ {valor_a_creditar:.2f} para {contato_limpo}"
        # Salva o arquivo de clientes_cash.csv
        if write_csv_to_github(df_cash, SHEET_NAME_CLIENTES_CASH, commit_msg):
             return True
    
    return False

# =========================================================================
# === FIM NOVAS FUNÇÕES DE CASHBACK ===
# =========================================================================

# --- Funções de Pedidos (ESCRITA HABILITADA) ---

# A função agora requer df_catalogo como argumento
def atualizar_status_pedido(id_pedido, novo_status, df_catalogo):
    # Carrega os pedidos para manipulação
    df = carregar_dados(SHEET_NAME_PEDIDOS).copy()
    
    if df.empty: 
        st.error("Não há dados de pedidos para atualizar.")
        return False

    index_to_update = df[df['ID_PEDIDO'] == id_pedido].index
    if not index_to_update.empty:
        
        # === LÓGICA DE CRÉDITO DE CASHBACK (APENAS AO FINALIZAR) ===
        # Verifica se o novo status é 'Finalizado' E se o status anterior NÃO era 'Finalizado'
        if novo_status == 'Finalizado' and df.loc[index_to_update[0], 'STATUS'] != 'Finalizado':
            pedido = df.loc[index_to_update[0]]
            
            # Use ITENS_JSON para garantir que a coluna correta seja usada
            pedido_json = pedido.get('ITENS_JSON') 
            contato_cliente = pedido.get('CONTATO_CLIENTE')
            nome_cliente_pedido = pedido.get('NOME_CLIENTE')
            
            if pedido_json and contato_cliente:
                valor_cashback = calcular_cashback_a_creditar(pedido_json, df_catalogo)
                
                if valor_cashback > 0.00:
                    st.toast(f"Cashback calculado e creditado: R$ {valor_cashback:.2f}", icon="💰")
                    if not creditar_cashback_e_atualizar_cliente(contato_cliente, valor_cashback, nome_cliente_pedido):
                        st.warning("⚠️ Falha ao creditar cashback. Status do pedido será atualizado, mas saldo não.")
                # else:
                    # st.info("Nenhum cashback a creditar neste pedido.")
        # ==============================================================
        
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
    Exibe os itens do pedido com um checkbox de separação e retorna a
    porcentagem de itens separados.
    """
    try:
        # --- CORREÇÃO CRÍTICA PARA LER JSON (ITENS_JSON/ITENS_PEDIDO) ---
        pedido_str = str(pedido_json).strip()
        
        if not pedido_str or pedido_str.lower() in ('nan', '{}', ''):
            st.warning("⚠️ Detalhes do pedido (JSON) não encontrados ou vazios.")
            return 0
            
        try:
             # Tenta carregar como JSON normal
             detalhes_pedido = json.loads(pedido_str)
        except json.JSONDecodeError:
             # Tenta carregar usando ast.literal_eval como fallback para string mal formatada
             detalhes_pedido = ast.literal_eval(pedido_str)
        # --- FIM CORREÇÃO ---
        
        itens = detalhes_pedido.get('itens', [])
        total_itens = len(itens)
        itens_separados = 0
        
        # Cria um estado de sessão para o progresso do pedido, se ainda não existir
        key_progress = f'pedido_{id_pedido}_itens_separados'
        if key_progress not in st.session_state:
            st.session_state[key_progress] = [False] * total_itens
            
        for i, item in enumerate(itens):
            link_imagem = "https://via.placeholder.com/150?text=Sem+Imagem"
            item_id = pd.to_numeric(item.get('id'), errors='coerce')
            
            # Busca link da imagem no catálogo
            if not df_catalogo.empty and not pd.isna(item_id) and not df_catalogo[df_catalogo['ID'] == int(item_id)].empty: 
                link_na_tabela = str(df_catalogo[df_catalogo['ID'] == int(item_id)].iloc[0].get('LINKIMAGEM', link_imagem)).strip()
                
                if link_na_tabela.lower() != 'nan' and link_na_tabela:
                    link_imagem = link_na_tabela

            col_check, col_img, col_detalhes = st.columns([0.5, 1, 3.5])
            
            # --- Lógica do Checkbox de Separação ---
            checked = col_check.checkbox(
                label="Separado",
                value=st.session_state[key_progress][i],
                key=f"check_{id_pedido}_{i}",
            )
            
            # Armazena o estado do checkbox
            if checked != st.session_state[key_progress][i]:
                st.session_state[key_progress][i] = checked
                st.rerun() 
            # --- Fim Lógica do Checkbox ---

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
                
        # Calcula e retorna a porcentagem de progresso
        if total_itens > 0:
            progresso = int((itens_separados / total_itens) * 100)
            return progresso
        return 0
        
    except Exception as e: 
        st.error(f"Erro fatal ao processar itens do pedido. Verifique o JSON. Detalhe: {e}")
        return 0 # Retorna 0% em caso de erro

# --- FUNÇÕES CRUD PARA PRODUTOS (ESCRITA HABILITADA) ---
# Adiciona cashback_percent_prod como um argumento opcional
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
        'CASHBACKPERCENT': str(cashback_percent_prod).replace('.', ',') # Salva a porcentagem
    }
    
    if not df.empty:
        df.loc[len(df)] = nova_linha
    else:
        df = pd.DataFrame([nova_linha])
        
    commit_msg = f"Adicionar produto: {nome} (ID: {novo_id})"
    return write_csv_to_github(df, SHEET_NAME_CATALOGO, commit_msg)

# Adiciona cashback_percent_prod para atualização
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
        df.loc[idx, 'CASHBACKPERCENT'] = str(cashback_percent_prod).replace('.', ',') # Atualiza a porcentagem
        
        commit_msg = f"Atualizar produto ID: {id_produto}"
        return write_csv_to_github(df, SHEET_NAME_CATALOGO, commit_msg)
    return False

def excluir_produto(id_produto):
    df = carregar_dados(SHEET_NAME_CATALOGO).copy()
    if df.empty: return False

    df = df[df['ID'] != int(id_produto)]
    commit_msg = f"Excluir produto ID: {id_produto}"
    return write_csv_to_github(df, SHEET_NAME_CATALOGO, commit_msg)


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
    return write_csv_to_github(df, SHEET_NAME_PROMOCOES, commit_message)


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
        return write_csv_to_github(df, SHEET_NAME_PROMOCOES, commit_message)
    return False


# --- LAYOUT DO APP ---
st.set_page_config(page_title="Admin Doce&Bella", layout="wide")
st.title("⭐ Painel de Administração | Doce&Bella")



# --- TABS DO SISTEMA ---
tab_pedidos, tab_produtos, tab_promocoes = st.tabs(["Pedidos", "Produtos", "🔥 Promoções"])

# --- VARIÁVEL DE CONTROLE DE VERSÃO JÁ ESTÁ NO TOPO ---

with tab_pedidos:
    st.header("📋 Pedidos Recebidos"); 
    if st.button("Recarregar Pedidos"): 
        # Limpa o estado de separação dos itens ao recarregar
        keys_to_delete = [k for k in st.session_state if k.startswith('pedido_') and k.endswith('_itens_separados')]
        for k in keys_to_delete:
            del st.session_state[k]
        st.session_state['data_version'] += 1 
        st.rerun() 
    
    df_pedidos_raw = carregar_dados(SHEET_NAME_PEDIDOS); 
    df_catalogo_pedidos = carregar_dados(SHEET_NAME_CATALOGO)
    
    if df_pedidos_raw.empty: st.info("Nenhum pedido foi encontrado na planilha.")
    else:
        df_pedidos_raw['DATA_HORA'] = pd.to_datetime(df_pedidos_raw['DATA_HORA'], errors='coerce'); st.subheader("🔍 Filtrar Pedidos")
        col_filtro1, col_filtro2 = st.columns(2); data_filtro = col_filtro1.date_input("Filtrar por data:"); texto_filtro = col_filtro2.text_input("Buscar por cliente ou produto:")
        df_filtrado = df_pedidos_raw.copy()
        if data_filtro: df_filtrado = df_filtrado[df_filtrado['DATA_HORA'].dt.date == data_filtro]
        if texto_filtro.strip():
            texto_filtro = texto_filtro.lower(); df_filtrado = df_filtrado[df_filtrado['NOME_CLIENTE'].astype(str).str.lower().str.contains(texto_filtro) | df_filtrado['ITENS_PEDIDO'].astype(str).str.lower().str.contains(texto_filtro) | df_filtrado['ITENS_JSON'].astype(str).str.lower().str.contains(texto_filtro)] 
        st.markdown("---"); pedidos_pendentes = df_filtrado[df_filtrado['STATUS'] != 'Finalizado']; pedidos_finalizados = df_filtrado[df_filtrado['STATUS'] == 'Finalizado']
        st.header("⏳ Pedidos Pendentes")
        if pedidos_pendentes.empty: st.info("Nenhum pedido pendente encontrado.")
        else:
            for index, pedido in pedidos_pendentes.iloc[::-1].iterrows():
                id_pedido = pedido['ID_PEDIDO']
                data_hora_str = pedido['DATA_HORA'].strftime('%d/%m/%Y %H:%M') if pd.notna(pedido['DATA_HORA']) else "Data Indisponível"
                titulo = f"Pedido de **{pedido['NOME_CLIENTE']}** - {data_hora_str} - Total: R$ {pedido['VALOR_TOTAL']}"
                with st.expander(titulo):
                    st.markdown(f"**Contato:** `{pedido['CONTATO_CLIENTE']}` | **ID:** `{id_pedido}`")
                    
                    # --- NOVO: Exibe itens e retorna o progresso (usando ITENS_JSON) ---
                    progresso_separacao = exibir_itens_pedido(id_pedido, pedido.get('ITENS_JSON', pedido.get('ITENS_PEDIDO', '{}')), df_catalogo_pedidos)
                    
                    st.markdown(f"**Progresso de Separação:** {progresso_separacao}%")
                    st.progress(progresso_separacao / 100) # Barra de progresso

                    # O botão Finalizar Pedido só é habilitado se o progresso for 100%
                    pode_finalizar = progresso_separacao == 100
                    
                    if st.button("✅ Finalizar Pedido", key=f"finalizar_{id_pedido}", disabled=not pode_finalizar):
                        # PASSANDO df_catalogo_pedidos PARA ATUALIZAR_STATUS_PEDIDO
                        if atualizar_status_pedido(id_pedido, novo_status="Finalizado", df_catalogo=df_catalogo_pedidos): 
                            st.success(f"Pedido {id_pedido} finalizado!")
                            # Limpa o estado de separação após finalizar
                            key_progress = f'pedido_{id_pedido}_itens_separados'
                            if key_progress in st.session_state:
                                del st.session_state[key_progress]
                                
                            st.session_state['data_version'] += 1 
                            st.rerun() 
                        else: st.error("Falha ao finalizar pedido.")
        # O resto do código permanece igual para Pedidos Finalizados
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
                        # CORREÇÃO: Passa o df_catalogo, mesmo que vazio, para satisfazer a assinatura da função
                        if st.button("↩️ Reverter para Pendente", key=f"reverter_{pedido['ID_PEDIDO']}", use_container_width=True):
                            if atualizar_status_pedido(pedido['ID_PEDIDO'], novo_status="", df_catalogo=pd.DataFrame()): 
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
                    st.markdown("---"); exibir_itens_pedido(pedido['ID_PEDIDO'], pedido.get('ITENS_JSON', pedido.get('ITENS_PEDIDO', '{}')), df_catalogo_pedidos)


with tab_produtos:
    st.header("🛍️ Gerenciamento de Produtos")
    import time
    if int(time.time()) % 5 == 0:
        pass
        
    with st.expander("➕ Cadastrar Novo Produto", expanded=False):
        with st.form("form_novo_produto", clear_on_submit=True):
            col1, col2 = st.columns(2); 
            nome_prod = col1.text_input("Nome do Produto*"); 
            preco_prod = col1.number_input("Preço (R$)*", min_value=0.0, format="%.2f", step=0.50); 
            link_imagem_prod = col1.text_input("URL da Imagem"); 
            # NOVO CAMPO: Cashback
            cashback_percent_prod = col1.number_input("Cashback (%)", min_value=0.0, max_value=100.0, format="%.2f", value=0.0) 
            
            desc_curta_prod = col2.text_input("Descrição Curta"); 
            desc_longa_prod = col2.text_area("Descrição Longa"); 
            disponivel_prod = col2.selectbox("Disponível?", ("Sim", "Não"))
            
            
            if st.form_submit_button("Cadastrar Produto"):
                if not nome_prod or preco_prod <= 0: 
                    st.warning("Preencha Nome e Preço.")
                # CORREÇÃO: Passa o novo argumento
                elif adicionar_produto(nome_prod, preco_prod, desc_curta_prod, desc_longa_prod, link_imagem_prod, disponivel_prod, cashback_percent_prod=cashback_percent_prod):
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
                    cashback_info = f" | Cashback: {produto.get('CASHBACKPERCENT', '0')}%" if 'CASHBACKPERCENT' in produto else ""
                    st.markdown(f"**{produto.get('NOME', 'N/A')}** (ID: {produto.get('ID', 'N/A')}){cashback_info}")
                    st.markdown(f"**Preço:** R$ {produto.get('PRECO', 'N/A')}")
                    with st.popover("📝 Editar"):
                        with st.form(f"edit_form_{produto.get('ID', index)}", clear_on_submit=True):
                            st.markdown(f"Editando: **{produto.get('NOME', 'N/A')}**")
                            preco_val_str = str(produto.get('PRECO', '0')).replace(',','.')
                            try:
                                preco_val = float(preco_val_str)
                            except ValueError:
                                preco_val = 0.0
                            
                            cashback_val = pd.to_numeric(produto.get('CASHBACKPERCENT', 0), errors='coerce').fillna(0)
                            
                            nome_edit = st.text_input("Nome", value=produto.get('NOME', ''))
                            preco_edit = st.number_input("Preço", value=preco_val, format="%.2f")
                            # NOVO CAMPO: Cashback na edição
                            cashback_edit = st.number_input("Cashback (%)", value=cashback_val, min_value=0.0, max_value=100.0, format="%.2f") 
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
                                # CORREÇÃO: Passa o novo argumento
                                if atualizar_produto(produto['ID'], nome_edit, preco_edit, curta_edit, longa_edit, link_edit, disponivel_edit, cashback_percent_prod=cashback_edit):
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
                        
                        preco_promo_val_str = str(promo.get('PRECO_PROMOCIONAL', '0')).replace(',','.')
                        try:
                             preco_promo_val = float(preco_promo_val_str)
                        except ValueError:
                             preco_promo_val = 0.0

                        preco_promo_edit = st.number_input("Preço Promocional", value=preco_promo_val, format="%.2f")
                        
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
