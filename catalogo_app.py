# catalogo_app.py

import streamlit as st
import pandas as pd
from datetime import datetime
import json
import time
from streamlit_autorefresh import st_autorefresh
import requests
import base64
from io import StringIO
import os
import ast
import pytz


# --- Variáveis de Configuração ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
DATA_REPO_NAME = os.environ.get("DATA_REPO_NAME", os.environ.get("REPO_NAME"))
BRANCH = os.environ.get("BRANCH")
ESTOQUE_BAIXO_LIMITE = 5 # Define o limite para exibir o alerta de "Últimas Unidades"

# URLs da API
GITHUB_BASE_API = f"https://api.github.com/repos/{DATA_REPO_NAME}/contents/"

# Fontes de Dados (CSV no GitHub)
SHEET_NAME_CATALOGO_CSV = "produtos_estoque.csv"
SHEET_NAME_PROMOCOES_CSV = "promocoes.csv"
SHEET_NAME_PEDIDOS_CSV = "pedidos.csv"
SHEET_NAME_VIDEOS_CSV = "video.csv"
SHEET_NAME_CLIENTES_CASHBACK_CSV = "clientes_cash.csv"
SHEET_NAME_CUPONS_CSV = "cupons.csv"
BACKGROUND_IMAGE_URL = 'https://i.ibb.co/x8HNtgxP/Без-na-zvania-3.jpg'
LOGO_DOCEBELLA_URL = "https://i.ibb.co/S9kT5nS/logo_docebella.png"

# NÚMERO DE TELEFONE PARA O BOTÃO FLUTUANTE DO WHATSAPP
NUMERO_WHATSAPP = "5541987876191" # SEU DDD + Número


# Inicialização do Carrinho de Compras e Estado
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {}
if 'pedido_confirmado' not in st.session_state:
    st.session_state.pedido_confirmado = None
if 'cupom_aplicado' not in st.session_state:
    st.session_state.cupom_aplicado = None
if 'desconto_cupom' not in st.session_state:
    st.session_state.desconto_cupom = 0.0
if 'cupom_mensagem' not in st.session_state:
    st.session_state.cupom_mensagem = ""
    
# OTIMIZAÇÃO: Cache do catálogo principal no estado da sessão para evitar re-leitura constante
if 'df_catalogo_indexado' not in st.session_state:
    st.session_state.df_catalogo_indexado = None


# --- Funções de Conexão GITHUB ---
def get_data_from_github(file_name):
    """
    Lê o conteúdo de um CSV do GitHub diretamente via API (sem cache da CDN).
    Garante que sempre trará a versão mais recente do arquivo.
    """
    api_url = f"{GITHUB_BASE_API}{file_name}?ref={BRANCH}"

    try:
        headers_content = {
            "Authorization": f"token {GITHUB_TOKEN}",
        }
        response = requests.get(api_url, headers=headers_content)

        if response.status_code == 404:
            if file_name != SHEET_NAME_CUPONS_CSV:
                st.error(f"Erro 404: Arquivo '{file_name}' não encontrado no repositório '{DATA_REPO_NAME}' na branch '{BRANCH}'. Verifique o nome do arquivo/branch/repo.")
            return None

        response.raise_for_status()

        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            st.error(f"Erro de JSON ao decodificar a resposta da API do GitHub para '{file_name}'.")
            st.code(response.text[:500])
            return None

        if "content" not in data:
            st.error(f"O campo 'content' não foi encontrado na resposta da API. Verifique se o arquivo {file_name} existe na branch '{BRANCH}'.")
            st.json(data)
            return None

        content = base64.b64decode(data["content"]).decode("utf-8")
        csv_data = StringIO(content)
        df = pd.read_csv(csv_data, sep=",", encoding="utf-8", engine="python", on_bad_lines="warn")
        df.columns = [col.strip().upper().replace(' ', '_') for col in df.columns]
        return df

    except requests.exceptions.HTTPError as e:
        if e.response.status_code != 404:
            st.error(f"Erro HTTP ao acessar '{file_name}' via API ({e.response.status_code}). URL: {api_url}")
        return None
    except Exception as e:
        st.error(f"Erro ao carregar '{file_name}' via API do GitHub: {e}")
        return None

# catalogo_app.py

import pytz

# === FUNÇÃO DE CUPONS ATUALIZADA COM CORREÇÃO DE FUSO HORÁRIO ===
@st.cache_data(ttl=30)
def carregar_cupons():
    """Carrega os cupons do 'cupons.csv' do GitHub, validando com fuso horário do Brasil."""
    df = get_data_from_github(SHEET_NAME_CUPONS_CSV)
    
    colunas_essenciais = ['CODIGO', 'TIPO_DESCONTO', 'VALOR', 'DATA_VALIDADE', 
                           'VALOR_MINIMO_PEDIDO', 'LIMITE_USOS', 'USOS_ATUAIS', 'STATUS']
                           
    if df is None or df.empty:
        return pd.DataFrame(columns=colunas_essenciais)

    df.rename(columns={'CODIGO': 'NOME_CUPOM', 'VALOR': 'VALOR_DESCONTO'}, inplace=True)
    colunas_essenciais_renomeadas = ['NOME_CUPOM', 'TIPO_DESCONTO', 'VALOR_DESCONTO', 'DATA_VALIDADE', 
                                    'VALOR_MINIMO_PEDIDO', 'LIMITE_USOS', 'USOS_ATUAIS', 'STATUS']

    for col in colunas_essenciais_renomeadas:
        if col not in df.columns:
            st.warning(f"A planilha de cupons existe, mas a coluna essencial '{col}' não foi encontrada.")
            return pd.DataFrame(columns=colunas_essenciais_renomeadas)

    df_ativo = df[df['STATUS'].astype(str).str.strip().str.upper() == 'ATIVO'].copy()
    if df_ativo.empty:
        return pd.DataFrame(columns=colunas_essenciais_renomeadas)

    df_ativo['NOME_CUPOM'] = df_ativo['NOME_CUPOM'].astype(str).str.strip().str.upper()
    df_ativo['TIPO_DESCONTO'] = df_ativo['TIPO_DESCONTO'].astype(str).str.strip().str.upper()
    df_ativo['VALOR_DESCONTO'] = pd.to_numeric(df_ativo['VALOR_DESCONTO'].astype(str).str.replace(',', '.'), errors='coerce')
    df_ativo['VALOR_MINIMO_PEDIDO'] = pd.to_numeric(df_ativo['VALOR_MINIMO_PEDIDO'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
    df_ativo['LIMITE_USOS'] = pd.to_numeric(df_ativo['LIMITE_USOS'], errors='coerce').fillna(999999)
    df_ativo['USOS_ATUAIS'] = pd.to_numeric(df_ativo['USOS_ATUAIS'], errors='coerce').fillna(0)
    
    # --- Validação da DATA_VALIDADE com FUSO HORÁRIO ---
    # Converte a coluna para datetime (sem fuso horário inicialmente)
    df_ativo['DATA_VALIDADE'] = pd.to_datetime(df_ativo['DATA_VALIDADE'], errors='coerce')
    df_ativo = df_ativo.dropna(subset=['DATA_VALIDADE'])
    
    # Define o fuso horário de São Paulo
    tz_brasil = pytz.timezone('America/Sao_Paulo')
    
    # "Avisa" para a coluna de datas que ela deve considerar o fuso horário do Brasil
    df_ativo['DATA_VALIDADE'] = df_ativo['DATA_VALIDADE'].dt.tz_localize(tz_brasil)
    
    # Pega a data e hora de agora no Brasil usando PANDAS e normaliza (zera a hora)
    hoje_brasil = pd.Timestamp.now(tz=tz_brasil).normalize()
    
    # Agora a comparação funciona, pois ambas as datas têm fuso horário
    df_ativo = df_ativo[df_ativo['DATA_VALIDADE'].dt.normalize() >= hoje_brasil]
    # --- Fim da Validação de Data ---

    df_ativo = df_ativo[df_ativo['USOS_ATUAIS'] < df_ativo['LIMITE_USOS']]

    return df_ativo.dropna(subset=['NOME_CUPOM', 'VALOR_DESCONTO']).reset_index(drop=True)
# =======================================

@st.cache_data(ttl=5)
def carregar_promocoes():
    """Carrega as promoções do 'promocoes.csv' do GitHub."""
    df = get_data_from_github(SHEET_NAME_PROMOCOES_CSV)

    colunas_essenciais = ['ID_PRODUTO', 'PRECO_PROMOCIONAL', 'STATUS']
    if df is None or df.empty:
        return pd.DataFrame(columns=colunas_essenciais)

    for col in colunas_essenciais:
        if col not in df.columns:
            st.error(f"Coluna essencial '{col}' não encontrada no 'promocoes.csv'. Verifique o cabeçalho.")
            return pd.DataFrame(columns=colunas_essenciais)

    df = df[df['STATUS'].astype(str).str.strip().str.upper() == 'ATIVO'].copy()
    df_essencial = df[colunas_essenciais].copy()

    df_essencial['PRECO_PROMOCIONAL'] = pd.to_numeric(df_essencial['PRECO_PROMOCIONAL'].astype(str).str.replace(',', '.'), errors='coerce')
    df_essencial['ID_PRODUTO'] = pd.to_numeric(df_essencial['ID_PRODUTO'], errors='coerce').astype('Int64')

    return df_essencial.dropna(subset=['ID_PRODUTO', 'PRECO_PROMOCIONAL']).reset_index(drop=True)


@st.cache_data(ttl=2)
def carregar_catalogo():
    """
    Carrega o catálogo, aplica promoções e vídeos, e prepara o DataFrame.
    IMPORTANTE: Retorna o DataFrame com 'ID' como índice para buscas rápidas (indexação).
    """
    df_produtos = get_data_from_github(SHEET_NAME_CATALOGO_CSV)

    if df_produtos is None or df_produtos.empty:
        st.warning(f"Catálogo indisponível. Verifique o arquivo '{SHEET_NAME_CATALOGO_CSV}' no GitHub.")
        return pd.DataFrame()

    if 'ID' in df_produtos.columns:
        df_produtos['RECENCIA'] = pd.to_numeric(df_produtos['ID'], errors='coerce')
        df_produtos['ID'] = pd.to_numeric(df_produtos['ID'], errors='coerce').astype('Int64')
        df_produtos.dropna(subset=['ID'], inplace=True)
    else:
        df_produtos['RECENCIA'] = range(len(df_produtos), 0, -1)
        
    # --- NOVO: Lidar com PRECOVISTA e PRECOCARTAO ---
    colunas_minimas = ['PRECOVISTA', 'ID', 'NOME']
    for col in colunas_minimas:
        if col not in df_produtos.columns:
            st.error(f"Coluna essencial '{col}' não encontrada no '{SHEET_NAME_CATALOGO_CSV}'. O aplicativo não pode continuar.")
            return pd.DataFrame()
    
    # Renomeia PRECOVISTA para PRECO
    mapa_renomeacao = {'PRECOVISTA': 'PRECO', 'MARCA': 'DESCRICAOCURTA'}
    df_produtos.rename(columns=mapa_renomeacao, inplace=True)
    
    # Garante que PRECOCARTAO existe, senão, copia PRECO
    if 'PRECOCARTAO' not in df_produtos.columns:
        df_produtos['PRECOCARTAO'] = df_produtos['PRECO']
    
    # Converte colunas de preço para numérico
    df_produtos['PRECO'] = pd.to_numeric(df_produtos['PRECO'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
    df_produtos['PRECOCARTAO'] = pd.to_numeric(df_produtos['PRECOCARTAO'].astype(str).str.replace(',', '.'), errors='coerce').fillna(df_produtos['PRECO'])
    
    # Adiciona CONDICAOPAGAMENTO (se não existir, calcula a simulação de 3x no cartão)
    if 'CONDICAOPAGAMENTO' not in df_produtos.columns:
        def gerar_condicao_pagamento(row):
            preco_cartao = row['PRECOCARTAO']
            if preco_cartao > 0:
                parcela = preco_cartao / 3
                return f"3x de R$ {parcela:.2f} no cartão"
            return 'Preço à vista'
            
        df_produtos['CONDICAOPAGAMENTO'] = df_produtos.apply(gerar_condicao_pagamento, axis=1)
    
    # --- FIM: Lidar com PRECOVISTA e PRECOCARTAO ---

    coluna_foto_encontrada = None
    nomes_possiveis_foto = ['FOTOURL', 'LINKIMAGEM', 'FOTO_URL', 'IMAGEM', 'URL_FOTO', 'LINK']
    for nome in nomes_possiveis_foto:
        if nome in df_produtos.columns:
            coluna_foto_encontrada = nome
            break
            
    if coluna_foto_encontrada:
        df_produtos.rename(columns={coluna_foto_encontrada: 'LINKIMAGEM'}, inplace=True, errors='ignore')
    else:
        st.warning("Nenhuma coluna de imagem encontrada (Ex: FOTOURL, IMAGEM). Os produtos serão exibidos sem fotos.")
        df_produtos['LINKIMAGEM'] = ""

    df_produtos.rename(columns={'MARCA': 'DESCRICAOCURTA'}, inplace=True, errors='ignore')

    if 'DISPONIVEL' not in df_produtos.columns:
        df_produtos['DISPONIVEL'] = 'SIM'
    if 'DESCRICAOLONGA' not in df_produtos.columns:
        df_produtos['DESCRICAOLONGA'] = df_produtos.get('CATEGORIA', '')

    df_produtos = df_produtos[df_produtos['DISPONIVEL'].astype(str).str.strip().str.lower() == 'sim'].copy()
    
    # Garante que a coluna de percentual de cashback existe e é numérica
    if 'CASHBACKPERCENT' not in df_produtos.columns:
        df_produtos['CASHBACKPERCENT'] = 0.0
    df_produtos['CASHBACKPERCENT'] = pd.to_numeric(df_produtos['CASHBACKPERCENT'], errors='coerce').fillna(0.0)
    
    if 'QUANTIDADE' in df_produtos.columns:
        df_produtos['QUANTIDADE'] = pd.to_numeric(df_produtos['QUANTIDADE'], errors='coerce').fillna(0)
    else:
        df_produtos['QUANTIDADE'] = 999999
    
    # Define o índice antes do merge, o que é mais limpo, mas precisamos do ID como coluna
    # para o merge com promoções/vídeos, então vamos resetar e definir novamente.

    df_promocoes = carregar_promocoes()

    if not df_promocoes.empty:
        # Usa PRECOCARTAO se estiver na promoção e for o menor preço
        # Por simplicidade e consistência, a promoção aplica-se ao PRECO_FINAL (preço à vista ou promocional)
        # O PRECOCARTAO é mantido apenas para a exibição da condição de pagamento
        df_final = pd.merge(df_produtos.reset_index(), df_promocoes[['ID_PRODUTO', 'PRECO_PROMOCIONAL']], left_on='ID', right_on='ID_PRODUTO', how='left')
        df_final['PRECO_FINAL'] = df_final['PRECO_PROMOCIONAL'].fillna(df_final['PRECO']) # PRECO_FINAL é o preço à vista ou promocional
        df_final.drop(columns=['ID_PRODUTO'], inplace=True, errors='ignore')
    else:
        df_final = df_produtos.reset_index()
        df_final['PRECO_FINAL'] = df_final['PRECO']
        df_final['PRECO_PROMOCIONAL'] = None

    df_videos = get_data_from_github(SHEET_NAME_VIDEOS_CSV)

    if df_videos is not None and not df_videos.empty:
        if 'ID_PRODUTO' in df_videos.columns and 'YOUTUBE_URL' in df_videos.columns:
            df_videos['ID_PRODUTO'] = pd.to_numeric(df_videos['ID_PRODUTO'], errors='coerce').astype('Int64')
            df_final = pd.merge(df_final, df_videos[['ID_PRODUTO', 'YOUTUBE_URL']], left_on='ID', right_on='ID_PRODUTO', how='left')
            df_final.drop(columns=['ID_PRODUTO_y'], inplace=True, errors='ignore')
            df_final.rename(columns={'ID_PRODUTO_x': 'ID_PRODUTO'}, inplace=True, errors='ignore')
        else:
            st.warning("Arquivo 'video.csv' encontrado, mas as colunas 'ID_PRODUTO' ou 'YOUTUBE_URL' estão faltando.")

    if 'CATEGORIA' not in df_final.columns:
         df_final['CATEGORIA'] = 'Geral'
         
    # Garante que o ID é o índice para buscas rápidas.
    return df_final.set_index('ID')


@st.cache_data(ttl=1) 
def carregar_clientes_cashback():
    """Carrega os clientes do cashback, limpa o contato e renomeia as colunas para facilitar."""
    df = get_data_from_github(SHEET_NAME_CLIENTES_CASHBACK_CSV)
    
    if df is None or df.empty:
        return pd.DataFrame(columns=['NOME', 'CONTATO', 'CASHBACK_DISPONIVEL', 'NIVEL_ATUAL'])
        
    df.rename(columns={
        'CASHBACK_DISPONIVEL': 'CASHBACK_DISPONIVEL',
        'NIVEL_ATUAL': 'NIVEL_ATUAL', 
        'TELEFONE': 'CONTATO',
        'NOME': 'NOME'
    }, inplace=True)
    
    if 'CASHBACK_DISPONÍVEL' in df.columns:
        df.rename(columns={'CASHBACK_DISPONÍVEL': 'CASHBACK_DISPONIVEL'}, inplace=True)

    if 'TELEFONE' in df.columns:
        df.rename(columns={'TELEFONE': 'CONTATO'}, inplace=True)
    elif 'CONTATO' not in df.columns:
        if 'TELEFONE' in df.columns: df.rename(columns={'TELEFONE': 'CONTATO'}, inplace=True)
        
    if 'CONTATO' in df.columns:
        df['CONTATO'] = df['CONTATO'].astype(str).str.replace(r'\D', '', regex=True).str.strip() 
        df['CASHBACK_DISPONIVEL'] = pd.to_numeric(df['CASHBACK_DISPONIVEL'], errors='coerce').fillna(0.0)
        df['NIVEL_ATUAL'] = df['NIVEL_ATUAL'].fillna('Prata')
    
        return df[['NOME', 'CONTATO', 'CASHBACK_DISPONIVEL', 'NIVEL_ATUAL']].dropna(subset=['CONTATO'])
    else:
        st.error("Erro: A coluna 'Telefone' (ou equivalente) do clientes_cash.csv não foi encontrada para a busca.")
        return pd.DataFrame(columns=['NOME', 'CONTATO', 'CASHBACK_DISPONIVEL', 'NIVEL_ATUAL'])


DF_CLIENTES_CASH = carregar_clientes_cashback()


def buscar_cliente_cashback(numero_contato, df_clientes_cash):
    """Busca um cliente pelo número de contato (limpo) e retorna saldo e nível."""
    contato_limpo = str(numero_contato).replace('(', '').replace(')', '').replace('-', '').replace(' ', '').strip()
    
    if df_clientes_cash.empty:
        return False, None, 0.00, 'NENHUM'
        
    cliente = df_clientes_cash[df_clientes_cash['CONTATO'] == contato_limpo]
    
    if not cliente.empty:
        saldo = cliente['CASHBACK_DISPONIVEL'].iloc[0]
        nome = cliente['NOME'].iloc[0]
        nivel = cliente['NIVEL_ATUAL'].iloc[0] 
        return True, nome, saldo, nivel
    else:
        return False, None, 0.00, 'NENHUM'
        

# --- Funções do Aplicativo ---

def salvar_pedido(nome_cliente, contato_cliente, valor_total, itens_json, pedido_data):
    """Salva o novo pedido no 'pedidos.csv' do GitHub usando a Content API."""
    file_path = SHEET_NAME_PEDIDOS_CSV
    api_url = f"{GITHUB_BASE_API}{file_path}"

    novo_cabecalho = 'ID_PEDIDO,DATA_HORA,NOME_CLIENTE,CONTATO_CLIENTE,ITENS_PEDIDO,VALOR_TOTAL,LINKIMAGEM,STATUS,itens_json'

    headers_get = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.com.v3+json"
    }

    try:
        response_get = requests.get(f"{api_url}?ref={BRANCH}", headers=headers_get)
        response_get.raise_for_status()

        file_data = response_get.json()
        current_sha = file_data['sha']
        content_base64 = file_data.get('content', '')

        if not content_base64:
            current_content = novo_cabecalho
        else:
            current_content = base64.b64decode(content_base64).decode('utf-8')

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            st.info(f"Arquivo '{file_path}' não encontrado. Criando um novo.")
            current_sha = None
            current_content = novo_cabecalho
        else:
            st.error(f"Erro HTTP ao obter o SHA do arquivo no GitHub: {e}")
            return False
    except Exception as e:
        st.error(f"Erro na decodificação ou leitura do arquivo 'pedidos.csv'. Detalhe: {e}")
        return False

    timestamp = int(datetime.now().timestamp())
    data_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    id_pedido = timestamp
    status = "PENDENTE"
    link_imagem = ""

    try:
        itens_data = json.loads(itens_json)
        resumo_itens = "; ".join([f"{i['quantidade']}x {i['nome']}" for i in itens_data.get('itens', [])])
    except Exception:
        resumo_itens = "Erro ao gerar resumo"

    escaped_itens_json = itens_json.replace('"', '""')

    novo_registro = (
        f'\n"{id_pedido}","{data_hora}","{nome_cliente}","{contato_cliente}",'
        f'"{resumo_itens}","{valor_total:.2f}","{link_imagem}","{status}","{escaped_itens_json}"'
    )

    if current_content.strip() and current_content.strip() != novo_cabecalho:
        new_content = current_content.strip() + novo_registro
    else:
        new_content = novo_cabecalho + novo_registro

    encoded_content = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')

    commit_data = {
        "message": f"PEDIDO: Novo pedido de {nome_cliente} - PENDENTE",
        "content": encoded_content,
        "branch": BRANCH
    }
    if current_sha:
        commit_data["sha"] = current_sha

    headers_put = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.com.v3+json"
    }

    try:
        response_put = requests.put(api_url, headers=headers_put, data=json.dumps(commit_data))
        response_put.raise_for_status()
        st.session_state.pedido_confirmado = pedido_data
        return True
    except requests.exceptions.HTTPError as e:
        st.error(f"Erro ao salvar o pedido (Commit no GitHub). Status {e.response.status_code}. "
                 f"Verifique as permissões 'repo' do seu PAT. Detalhe: {e.response.text}")
        return False
    except Exception as e:
        st.error(f"Erro desconhecido ao enviar o pedido: {e}")
        return False

# Função para calcular o cashback total do carrinho
def calcular_cashback_total(carrinho, df_catalogo_indexado):
    """Calcula o total de cashback a ser ganho pelos itens no carrinho."""
    cashback_total = 0.0
    for prod_id, item in carrinho.items():
        if prod_id in df_catalogo_indexado.index:
            row = df_catalogo_indexado.loc[prod_id]
            cashback_percent = pd.to_numeric(row.get('CASHBACKPERCENT'), errors='coerce')
            preco_final = item['preco'] # Já é o preço final com promoção
            
            if pd.notna(cashback_percent) and cashback_percent > 0:
                cashback_valor_unitario = (cashback_percent / 100) * preco_final
                cashback_total += cashback_valor_unitario * item['quantidade']
    return cashback_total


def adicionar_qtd_ao_carrinho(produto_id, produto_row, quantidade):
    produto_nome = produto_row['NOME']
    produto_preco = produto_row['PRECO_FINAL']
    produto_imagem = produto_row.get('LINKIMAGEM', '')
    
    # Busca a quantidade máxima do catálogo indexado no session_state
    df_catalogo = st.session_state.df_catalogo_indexado
    
    quantidade_max = int(df_catalogo.loc[produto_id, 'QUANTIDADE'] if produto_id in df_catalogo.index else 999999)
    
    if quantidade_max <= 0:
         st.warning(f"⚠️ Produto '{produto_nome}' está esgotado.")
         return

    if produto_id in st.session_state.carrinho:
        nova_quantidade = st.session_state.carrinho[produto_id]['quantidade'] + quantidade
        
        if nova_quantidade > quantidade_max:
            disponivel = quantidade_max - st.session_state.carrinho[produto_id]['quantidade']
            st.warning(f"⚠️ Você só pode adicionar mais {disponivel} unidades. Total disponível: {quantidade_max}.")
            return
            
        st.session_state.carrinho[produto_id]['quantidade'] = nova_quantidade
    else:
        if quantidade > quantidade_max:
             st.warning(f"⚠️ Quantidade solicitada ({quantidade}) excede o estoque ({quantidade_max}) para '{produto_nome}'.")
             return
        st.session_state.carrinho[produto_id] = {
            'nome': produto_nome,
            'preco': produto_preco,
            'quantidade': quantidade,
            'imagem': produto_imagem
        }
    st.toast(f"✅ {quantidade}x {produto_nome} adicionado(s)!", icon="🛍️"); time.sleep(0.1)


def adicionar_ao_carrinho(produto_id, produto_row):
    pass 

def remover_do_carrinho(produto_id):
    # ✅ CORREÇÃO DE ERRO: Usando 'produto_id' no lugar de 'prod_id'
    if produto_id in st.session_state.carrinho:
        nome = st.session_state.carrinho[produto_id]['nome']
        del st.session_state.carrinho[produto_id]
        st.toast(f"❌ {nome} removido.", icon="🗑️")

def render_product_image(link_imagem):
    placeholder_html = """<div class="product-image-container" style="background-color: #f0f0f0; border-radius: 8px;"><span style="color: #a0a0a0; font-size: 1.1rem; font-weight: bold;">Sem Imagem</span></div>"""
    if link_imagem and str(link_imagem).strip().startswith('http'):
        st.markdown(f'<div class="product-image-container"><img src="{link_imagem}"></div>', unsafe_allow_html=True)
    else:
        st.markdown(placeholder_html, unsafe_allow_html=True)

def limpar_carrinho():
    st.session_state.carrinho = {}
    st.session_state.cupom_aplicado = None
    st.session_state.desconto_cupom = 0.0
    st.session_state.cupom_mensagem = ""
    st.toast("🗑️ Pedido limpo!", icon="🧹")
    st.rerun()

# ✅ OTIMIZAÇÃO: Recebe o DF de catálogo para evitar re-execução (mesmo que cacheada)
def render_product_card(prod_id, row, key_prefix, df_catalogo_indexado):
    """Renderiza um card de produto com suporte para abas de foto e vídeo, seletor de quantidade e feedback de estoque."""
    with st.container(border=True):
        
        produto_nome = str(row['NOME'])
        descricao_curta = str(row.get('DESCRICAOCURTA', '')).strip()
        
        # Usa a linha de dados que já veio, evitando re-busca
        estoque_atual = int(row.get('QUANTIDADE', 999999)) 
        esgotado = estoque_atual <= 0
        estoque_baixo = estoque_atual > 0 and estoque_atual <= ESTOQUE_BAIXO_LIMITE
        
        if esgotado:
            st.markdown('<span class="esgotado-badge">🚫 ESGOTADO</span>', unsafe_allow_html=True)
        elif estoque_baixo:
            st.markdown(f'<span class="estoque-baixo-badge">⚠️ Últimas {estoque_atual} Unidades!</span>', unsafe_allow_html=True)

        youtube_url = row.get('YOUTUBE_URL')

        if youtube_url and isinstance(youtube_url, str) and youtube_url.strip().startswith('http'):
            tab_foto, tab_video = st.tabs(["📷 Foto", "▶️ Vídeo"])
            with tab_foto:
                render_product_image(row.get('LINKIMAGEM'))
            with tab_video:
                st.video(youtube_url)
        else:
            render_product_image(row.get('LINKIMAGEM'))

        preco_final = row['PRECO_FINAL']
        preco_original = row['PRECO']
        is_promotion = pd.notna(row.get('PRECO_PROMOCIONAL'))

        if is_promotion:
            st.markdown(f"""
            <div style="margin-bottom: 0.5rem;">
                <span style="background-color: #D32F2F; color: white; font-weight: bold; padding: 3px 8px; border-radius: 5px; font-size: 0.9rem;">
                    🔥 PROMOÇÃO
                </span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown(f"**{produto_nome}**")
        st.caption(descricao_curta)

        with st.expander("Ver detalhes"):
            descricao_principal = row.get('DESCRICAOLONGA')
            detalhes_str = row.get('DETALHESGRADE')
            
            tem_descricao = descricao_principal and isinstance(descricao_principal, str) and descricao_principal.strip()
            tem_detalhes = detalhes_str and isinstance(detalhes_str, str) and detalhes_str.strip()
            
            if not tem_descricao and not tem_detalhes:
                st.info('Sem informações detalhadas disponíveis para este produto.')
            else:
                if tem_descricao:
                    if descricao_principal.strip() != descricao_curta:
                        st.subheader('Descrição')
                        st.markdown(descricao_principal)
                        if tem_detalhes:
                            st.markdown('---') 
                    
                if tem_detalhes:
                    st.subheader('Especificações')
                    if detalhes_str.strip().startswith('{'):
                        try:
                            detalhes_dict = ast.literal_eval(detalhes_str)
                            texto_formatado = ""
                            for chave, valor in detalhes_dict.items():
                                texto_formatado += f"* **{chave.strip()}**: {str(valor).strip()}\n"
                            st.markdown(texto_formatado)
                        except (ValueError, SyntaxError):
                            st.markdown(detalhes_str)
                    else:
                        st.markdown(detalhes_str)


        col_preco, col_botao = st.columns([2, 2])

        # Obtém a condição de pagamento
        condicao_pagamento = row.get('CONDICAOPAGAMENTO', 'Preço à vista')
        
        with col_preco:
            cashback_percent = pd.to_numeric(row.get('CASHBACKPERCENT'), errors='coerce')
            cashback_html = ""

            if pd.notna(cashback_percent) and cashback_percent > 0:
                # O cashback é baseado no PRECO_FINAL (preço à vista/promocional)
                cashback_valor_calculado = (cashback_percent / 100) * preco_final
                # Agora, garantimos que a string HTML não tenha quebras de linha indesejadas
                # e colocamos o texto do cashback dentro da tag span corretamente.
                cashback_html = f"""
                <span style='color: #2E7D32; font-size: 0.8rem; font-weight: bold; display: block; margin-top: 5px;'>
                    Cashback: R$ {cashback_valor_calculado:.2f}
                </span>
                """
                
            # HTML para exibir a condição de pagamento
            condicao_html = f"""
            <span style='color: #757575; font-size: 0.85rem; font-weight: normal; margin-top: 5px; display: block;'>
                ({condicao_pagamento})
            </span>
            """

            if is_promotion:
                st.markdown(f"""
                <div style="line-height: 1.2;">
                    <span style='text-decoration: line-through; color: #757575; font-size: 0.9rem;'>R$ {preco_original:.2f}</span>
                    <h4 style='color: #D32F2F; margin:0;'>R$ {preco_final:.2f}</h4>
                    {condicao_html}
                    {cashback_html}
                </div>
                """, unsafe_allow_html=True)
            else:
                # Corrigido para garantir que todo o HTML do preço, condição e cashback seja injetado de uma vez
                st.markdown(f"""
                <div style='display: flex; align-items: flex-end; flex-wrap: wrap; gap: 8px;'>
                    <h4 style='color: #880E4F; margin:0; line-height:1;'>R$ {preco_final:.2f}</h4>
                </div>
                {condicao_html}
                {cashback_html}
                """, unsafe_allow_html=True)


        with col_botao:
            item_ja_no_carrinho = prod_id in st.session_state.carrinho

            if esgotado:
                st.empty() 
                
            elif item_ja_no_carrinho:
                qtd_atual = st.session_state.carrinho[prod_id]['quantidade']
                st.button(
                    f"✅ {qtd_atual}x NO PEDIDO", 
                    key=f'btn_add_qtd_{key_prefix}', 
                    use_container_width=True, 
                    disabled=True 
                )
            else:
                qtd_a_adicionar = st.number_input(
                    label=f'Qtd_Input_{key_prefix}',
                    min_value=1,
                    max_value=estoque_atual, 
                    value=1,
                    step=1,
                    key=f'qtd_input_{key_prefix}',
                    label_visibility="collapsed"
                )
                
                # Botão de adicionar chama a função otimizada
                if st.button(f"🛒 Adicionar {qtd_a_adicionar} un.", key=f'btn_add_qtd_{key_prefix}', use_container_width=True):
                    if qtd_a_adicionar >= 1:
                        adicionar_qtd_ao_carrinho(prod_id, row, qtd_a_adicionar)
                        st.rerun()


# --- Layout do Aplicativo (INÍCIO DO SCRIPT PRINCIPAL) ---
st.set_page_config(page_title="Catálogo Doce&Bella", layout="wide", initial_sidebar_state="collapsed")

# 1. OTIMIZAÇÃO: Carrega o catálogo indexado na session_state APENAS se não estiver lá
if st.session_state.df_catalogo_indexado is None:
    st.session_state.df_catalogo_indexado = carregar_catalogo()


# --- CSS ---
st.markdown(f"""
<style>
#MainMenu, footer, [data-testid="stSidebar"] {{visibility: hidden;}}
[data-testid="stSidebarHeader"], [data-testid="stToolbar"], a[data-testid="stAppDeployButton"], [data-testid="stStatusWidget"], [data-testid="stDecoration"] {{ display: none !important; }}
div[data-testid="stPopover"] > div:first-child > button {{ display: none; }}
.stApp {{ background-image: url({BACKGROUND_IMAGE_URL}) !important; background-size: cover; background-attachment: fixed; }}

/* CORREÇÃO PARA MODO ESCURO: Força a cor do texto para ser escura dentro do container principal */
div.block-container {{ 
    background-color: rgba(255, 255, 255, 0.95); 
    border-radius: 10px; 
    padding: 2rem; 
    margin-top: 1rem; 
    color: #262626; /* Cor de texto padrão forçada para preto escuro */
}}
/* Garante que o texto em parágrafos e títulos também seja escuro, superando o modo escuro do celular */
div.block-container p, div.block-container h1, div.block-container h2, div.block-container h3, div.block-container h4, div.block-container h5, div.block-container h6, div.block-container span {{
    color: #262626 !important;
}}

.pink-bar-container {{ background-color: #E91E63; padding: 20px 0; width: 100vw; position: relative; left: 50%; right: 50%; margin-left: -50vw; margin-right: -50vw; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
.pink-bar-content {{ width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 2rem; display: flex; align-items: center; }}
.cart-badge-button {{ background-color: #C2185B; color: white; border-radius: 12px; padding: 8px 15px; font-size: 16px; font-weight: bold; cursor: pointer; border: none; transition: background-color 0.3s; display: inline-flex; align-items: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); min-width: 150px; justify-content: center; }}
.cart-badge-button:hover {{ background-color: #C2185B; }}
.cart-count {{ background-color: white; color: #E91E63; border-radius: 50%; padding: 2px 7px; margin-left: 8px; font-size: 14px; line-height: 1; }}
div[data-testid="stButton"] > button {{ background-color: #E91E63; color: white; border-radius: 10px; border: 1px solid #C2185B; font-weight: bold; }}
div[data-testid="stButton"] > button:hover {{ background-color: #C2185B; color: white; border: 1px solid #E91E63; }}
.product-image-container {{ height: 220px; display: flex; align-items: center; justify-content: center; margin-bottom: 1rem; overflow: hidden; }}
.product-image-container img {{ max-height: 100%; max-width: 100%; object-fit: contain; border-radius: 8px; }}
.esgotado-badge {{ background-color: #757575; color: white; font-weight: bold; padding: 3px 8px; border-radius: 5px; font-size: 0.9rem; margin-bottom: 0.5rem; display: block; }}
.estoque-baixo-badge {{ background-color: #FFC107; color: black; font-weight: bold; padding: 3px 8px; border-radius: 5px; font-size: 0.9rem; margin-bottom: 0.5rem; display: block; }}

/* --- CSS para o Botão Flutuante (Injetado na chamada única de st.markdown) --- */
.whatsapp-float {{
    position: fixed;
    bottom: 40px;
    right: 40px;
    background-color: #25D366;
    color: white;
    border-radius: 50px;
    width: 60px;
    height: 60px;
    text-align: center;
    font-size: 30px;
    box-shadow: 2px 2px 3px #999;
}}
</style>
""", unsafe_allow_html=True)


def copy_to_clipboard_js(text_to_copy):
    js_code = f"""
    <script>
    function copyTextToClipboard(text) {{
      if (navigator.clipboard) {{
        navigator.clipboard.writeText(text).then(function() {{
          alert('Resumo do pedido copiado!');
        }}, function(err) {{
          console.error('Não foi possível copiar o texto: ', err);
          alert('Erro ao copiar o texto. Tente novamente.');
        }});
      }} else {{
        const textArea = document.createElement("textarea");
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        try {{
          document.execCommand('copy');
          alert('Resumo do pedido copiado!');
        }} catch (err) {{
          console.error('Fallback: Não foi possível copiar o texto: ', err);
          alert('Erro ao copiar o texto. Tente novamente.');
        }}
        document.body.removeChild(textArea);
      }}
    }}
    </script>
    """
    st.markdown(js_code, unsafe_allow_html=True)


st_autorefresh(interval=6000000000, key="auto_refresh_catalogo")


if st.session_state.pedido_confirmado:
    st.balloons()
    st.success("🎉 Pedido enviado com sucesso! Utilize o resumo abaixo para confirmar o pedido pelo WhatsApp.")
    
    pedido = st.session_state.pedido_confirmado
    itens_formatados = '\n'.join([
        f"- {item['quantidade']}x {item['nome']} (R$ {item['preco']:.2f} un.)" 
        for item in pedido['itens']
    ])

    resumo_texto = (
        f"***📝 RESUMO DO PEDIDO - DOCE&BELLA ***\n\n"
        f"🛒 Cliente: {pedido['nome']}\n"
        f"📞 Contato: {pedido['contato']}\n"
        f"💎 Nível Atual: {pedido.get('cliente_nivel_atual', 'N/A')}\n"
        f"💰 Saldo Cashback: R$ {pedido.get('cliente_saldo_cashback', 0.00):.2f}\n\n"
        f"📦 Itens Pedidos:\n"
        f"{itens_formatados}\n\n"
        f"🎟️ Cupom Aplicado: {pedido.get('cupom_aplicado', 'Nenhum')}\n"
        f"📉 Desconto Total: R$ {pedido.get('desconto_cupom', 0.0):.2f}\n\n"
        f"✅ CASHBACK A SER GANHO: R$ {pedido.get('cashback_a_ganhar', 0.0):.2f}\n" # NOVO: Cashback total
        f"💰 VALOR TOTAL A PAGAR: R$ {pedido['total']:.2f}\n\n"
        f"Obrigado por seu pedido!"
    )

    st.text_area("Resumo do Pedido (Clique para copiar)", resumo_texto, height=300)
    
    copy_to_clipboard_js(resumo_texto)
    st.markdown(
        f'<button class="cart-badge-button" style="background-color: #25D366; width: 100%; margin-bottom: 15px;" onclick="copyTextToClipboard(\'{resumo_texto.replace("'", "\\'")}\')">✅ Copiar Resumo</button>',
        unsafe_allow_html=True
    )
    
    if st.button("Voltar ao Catálogo"):
        st.session_state.pedido_confirmado = None
        limpar_carrinho()
        st.rerun()
    st.stop()


st.markdown(f"""
<style>
/* Estilo do container do banner colorido */
.banner-colored {{
    background-color: #e91e63;
    padding: 10px 25px; /* <-- PADDING VERTICAL REDUZIDO */
    border-radius: 10px;
    display: flex;
    align-items: center;
    gap: 25px;
    margin-bottom: 20px;
}}

.banner-colored img {{
    max-height: 60px; /* <-- ALTURA MÁXIMA DO LOGO REDUZIDA */
    width: auto;
}}

.banner-colored h1 {{
    color: white;
    font-size: 2rem; /* <-- FONTE UM POUCO MENOR */
    margin: 0;
}}
</style>

<div class="banner-colored">
    <img src="{LOGO_DOCEBELLA_URL}" alt="Doce&Bella Logo">
    <h1>Catálogo de Pedidos Doce&Bella</h1>
</div>
""", unsafe_allow_html=True)

total_acumulado = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho.values())
num_itens = sum(item['quantidade'] for item in st.session_state.carrinho.values())
carrinho_vazio = not st.session_state.carrinho

# NOVO: Cálculo do cashback total no carrinho
df_catalogo_completo = st.session_state.df_catalogo_indexado 
cashback_a_ganhar = calcular_cashback_total(st.session_state.carrinho, df_catalogo_completo)

st.markdown("<div class='pink-bar-container'><div class='pink-bar-content'>", unsafe_allow_html=True)

col_pesquisa, col_carrinho = st.columns([5, 1])
with col_pesquisa:
    st.text_input("Buscar...", key='termo_pesquisa_barra', label_visibility="collapsed", placeholder="Buscar produtos...")

with col_carrinho:
    custom_cart_button = f"""
        <div class='cart-badge-button' onclick='document.querySelector("[data-testid=\\"stPopover\\"] > div:first-child > button").click();'>
            🛒 SEU PEDIDO
            <span class='cart-count'>{num_itens}</span>
        </div>
    """
    st.markdown(custom_cart_button, unsafe_allow_html=True)
    with st.popover(" ", use_container_width=False, help="Clique para ver os itens e finalizar o pedido"):
        st.header("🛒 Detalhes do Pedido")
        if carrinho_vazio:
            st.info("Seu carrinho está vazio.")
        else:
            desconto_cupom = st.session_state.get('desconto_cupom', 0.0)
            total_com_desconto = total_acumulado - desconto_cupom

            if total_com_desconto < 0:
                total_com_desconto = 0

            st.markdown(f"Subtotal: `R$ {total_acumulado:.2f}`")
            if desconto_cupom > 0:
                st.markdown(f"Desconto (`{st.session_state.cupom_aplicado}`): <span style='color: #D32F2F;'>- R$ {desconto_cupom:.2f}</span>", unsafe_allow_html=True)
            
            # NOVO: Exibição do cashback
            st.markdown(f"<span style='color: #2E7D32; font-weight: bold;'>Cashback a Ganhar: R$ {cashback_a_ganhar:.2f}</span>", unsafe_allow_html=True)
            
            st.markdown(f"<h3 style='color: #E91E63; margin-top: 0;'>Total: R$ {total_com_desconto:.2f}</h3>", unsafe_allow_html=True)
            st.markdown("---")
            
            col_h1, col_h2, col_h3, col_h4 = st.columns([3, 1.5, 2.5, 1])
            col_h2.markdown("**Qtd**")
            col_h3.markdown("**Subtotal**")
            col_h4.markdown("")
            st.markdown('<div style="margin-top: -10px; border-top: 1px solid #ccc;"></div>', unsafe_allow_html=True)
            
            # Reutiliza o catálogo indexado do session_state
            df_catalogo_completo = st.session_state.df_catalogo_indexado 
            
            # === EXIBIÇÃO DO SUBTOTAL DO ITEM ===
            for prod_id, item in list(st.session_state.carrinho.items()):
                c1, c2, c3, c4 = st.columns([3, 1.5, 2.5, 1])
                c1.write(f"*{item['nome']}*")
                
                # Busca rápida de estoque
                if prod_id in df_catalogo_completo.index:
                    max_qtd = df_catalogo_completo.loc[prod_id, 'QUANTIDADE']
                    if isinstance(max_qtd, pd.Series):
                         max_qtd = max_qtd.iloc[0]
                else:
                    max_qtd = 999999
                max_qtd = int(max_qtd)
                
                if item['quantidade'] > max_qtd:
                    st.session_state.carrinho[prod_id]['quantidade'] = max_qtd
                    item['quantidade'] = max_qtd
                    st.toast(f"Ajustado: {item['nome']} ao estoque máximo de {max_qtd}.", icon="⚠️")
                    st.rerun()
                    
                nova_quantidade = c2.number_input(
                    label=f'Qtd_{prod_id}', min_value=1, max_value=max_qtd,
                    value=item['quantidade'], step=1, key=f'qtd_{prod_id}_popover',
                    label_visibility="collapsed"
                )
                
                if nova_quantidade != item['quantidade']:
                    st.session_state.carrinho[prod_id]['quantidade'] = nova_quantidade
                    st.rerun()

                subtotal_item = item['preco'] * item['quantidade']
                preco_unitario = item['preco']
                html_preco = f"""
                <div style="text-align: left; white-space: nowrap;">
                    <strong>R$ {subtotal_item:.2f}</strong>
                    <br>
                    <span style='font-size: 0.8rem; color: #757575;'>(R$ {preco_unitario:.2f} un.)</span>
                </div>
                """
                c3.markdown(html_preco, unsafe_allow_html=True)
                
                if c4.button("X", key=f'rem_{prod_id}_popover'):
                    remover_do_carrinho(prod_id)
                    st.rerun()
            st.markdown("---")
            
            # === LÓGICA DO CUPOM DE DESCONTO ===
            st.subheader("🎟️ Cupom de Desconto")
            
            cupom_col1, cupom_col2 = st.columns([3, 1])
            
            with cupom_col1:
                codigo_cupom_input = st.text_input("Código do Cupom", key="cupom_input", label_visibility="collapsed").upper()
            
            with cupom_col2:
                if st.button("Aplicar", key="aplicar_cupom_btn", use_container_width=True):
                    # OTIMIZAÇÃO: A função carregar_cupons() é cacheada (ttl=30), o que ajuda na performance aqui.
                    if codigo_cupom_input:
                        df_cupons_validos = carregar_cupons()
                        cupom_encontrado = df_cupons_validos[df_cupons_validos['NOME_CUPOM'] == codigo_cupom_input]
                        
                        if not cupom_encontrado.empty:
                            cupom_info = cupom_encontrado.iloc[0]
                            valor_minimo = cupom_info['VALOR_MINIMO_PEDIDO']

                            if float(total_acumulado) >= float(valor_minimo):
                                tipo = cupom_info['TIPO_DESCONTO']
                                valor = cupom_info['VALOR_DESCONTO']
                                
                                desconto = 0.0
                                if tipo == 'PERCENTUAL':
                                    desconto = (valor / 100) * total_acumulado
                                elif tipo == 'FIXO':
                                    desconto = valor
                                
                                st.session_state.cupom_aplicado = codigo_cupom_input
                                st.session_state.desconto_cupom = desconto
                                st.session_state.cupom_mensagem = f"✅ Cupom '{codigo_cupom_input}' aplicado!"
                            else:
                                st.session_state.cupom_aplicado = None
                                st.session_state.desconto_cupom = 0.0
                                st.session_state.cupom_mensagem = f"❌ O valor mínimo para este cupom é de R$ {valor_minimo:.2f}."
                        else:
                            st.session_state.cupom_aplicado = None
                            st.session_state.desconto_cupom = 0.0
                            st.session_state.cupom_mensagem = "❌ Cupom inválido, expirado ou esgotado."
                    else:
                        st.session_state.cupom_mensagem = "⚠️ Digite um código de cupom."
                    st.rerun()

            if st.session_state.cupom_mensagem:
                if "✅" in st.session_state.cupom_mensagem:
                    st.success(st.session_state.cupom_mensagem)
                else:
                    st.error(st.session_state.cupom_mensagem)

            st.markdown("---")
            
            st.button("🗑️ Limpar Pedido", on_click=limpar_carrinho, use_container_width=True)
            st.markdown("---")
            
            # ... O resto do código (Finalizar Pedido) continua o mesmo ...
            st.subheader("Finalizar Pedido")

            nome_input = st.text_input("Seu Nome Completo:", key='checkout_nome_dynamic')
            contato_input = st.text_input("Seu Contato (WhatsApp - apenas números, com DDD):", key='checkout_contato_dynamic')
            
            nivel_cliente = 'N/A'
            saldo_cashback = 0.00
            
            if nome_input and contato_input and DF_CLIENTES_CASH is not None and not DF_CLIENTES_CASH.empty:
                existe, nome_encontrado, saldo_cashback, nivel_cliente = buscar_cliente_cashback(contato_input, DF_CLIENTES_CASH)

                if existe:
                    st.success(
                        f"🎉 **Bem-vindo(a) de volta, {nome_encontrado}!** Seu Nível é: **{nivel_cliente.upper()}**."
                        f"\n\nSeu saldo atual de Cashback é de **R$ {saldo_cashback:.2f}**."
                    )
                elif contato_input.strip():
                    st.info("👋 **Novo Cliente!** Você começará a acumular cashback após a finalização do seu primeiro pedido no painel de administração.")

            with st.form("form_finalizar_pedido", clear_on_submit=True):
                st.text_input("Nome (Preenchido)", value=nome_input, disabled=True, label_visibility="collapsed")
                st.text_input("Contato (Preenchido)", value=contato_input, disabled=True, label_visibility="collapsed")

                if st.form_submit_button("✅ Enviar Pedido", type="primary", use_container_width=True):
                    if nome_input and contato_input:
                        
                        contato_limpo = contato_input.replace('(', '').replace(')', '').replace('-', '').replace(' ', '').strip()
                        
                        detalhes = {
                            "subtotal": total_acumulado,
                            "desconto_cupom": st.session_state.desconto_cupom,
                            "cupom_aplicado": st.session_state.cupom_aplicado,
                            "total": total_com_desconto,
                            "itens": [
                                {
                                    "id": int(k),
                                    "nome": v['nome'],
                                    "preco": v['preco'],
                                    "quantidade": v['quantidade'],
                                    "imagem": v.get('imagem', '')
                                } for k, v in st.session_state.carrinho.items()
                            ],
                            "nome": nome_input,
                            "contato": contato_limpo,
                            "cliente_nivel_atual": nivel_cliente, 
                            "cliente_saldo_cashback": saldo_cashback,
                            "cashback_a_ganhar": cashback_a_ganhar, # Adiciona o cashback total aos detalhes
                        }
                        
                        if salvar_pedido(nome_input, contato_limpo, total_com_desconto, json.dumps(detalhes, ensure_ascii=False), detalhes):
                            st.session_state.carrinho = {}
                            st.session_state.cupom_aplicado = None
                            st.session_state.desconto_cupom = 0.0
                            st.session_state.cupom_mensagem = ""
                            st.rerun()
                    else:
                        st.warning("Preencha seu nome e contato.")

st.markdown("</div></div>", unsafe_allow_html=True)

# 2. OTIMIZAÇÃO: Usa o catálogo em cache no session_state e reseta o índice (cria uma cópia) para filtros/ordenação
df_catalogo = st.session_state.df_catalogo_indexado.reset_index()

if 'CATEGORIA' in df_catalogo.columns:
    categorias = df_catalogo['CATEGORIA'].dropna().astype(str).unique().tolist()
    categorias.sort()
    categorias.insert(0, "TODAS AS CATEGORIAS")
else:
    categorias = ["TODAS AS CATEGORIAS"]
    if "Geral" not in df_catalogo.columns:
         st.warning("A coluna 'CATEGORIA' não foi encontrada no seu arquivo de catálogo. O filtro não será exibido.")

col_filtro_cat, col_select_ordem, _ = st.columns([1, 1, 3])

termo = st.session_state.get('termo_pesquisa_barra', '').lower()

with col_filtro_cat:
    categoria_selecionada = st.selectbox(
        "Filtrar por:",
        categorias,
        key='filtro_categoria_barra'
    )
    if termo:
        st.markdown(f'<div style="font-size: 0.8rem; color: #E91E63;">Busca ativa desabilita filtro.</div>', unsafe_allow_html=True)

df_filtrado = df_catalogo.copy()

if not termo and categoria_selecionada != "TODAS AS CATEGORIAS":
    df_filtrado = df_filtrado[df_filtrado['CATEGORIA'].astype(str) == categoria_selecionada]
elif termo:
    df_filtrado = df_filtrado[df_filtrado.apply(
        lambda row: termo in str(row['NOME']).lower() or termo in str(row['DESCRICAOLONGA']).lower(), 
        axis=1
    )]

if df_filtrado.empty:
    if termo:
        st.info(f"Nenhum produto encontrado com o termo '{termo}' na categoria '{categoria_selecionada}'.")
    else:
        st.info(f"Nenhum produto encontrado na categoria '{categoria_selecionada}'.")
else:
    st.subheader("✨ Nossos Produtos")

    with col_select_ordem:
        opcoes_ordem = ['Lançamento', 'Promoção', 'Menor Preço', 'Maior Preço', 'Nome do Produto (A-Z)']
        ordem_selecionada = st.selectbox(
            "Ordenar por:",
            opcoes_ordem,
            key='ordem_produtos'
        )

    df_filtrado['EM_PROMOCAO'] = df_filtrado['PRECO_PROMOCIONAL'].notna()

    if ordem_selecionada == 'Lançamento':
        df_ordenado = df_filtrado.sort_values(by=['RECENCIA', 'EM_PROMOCAO'], ascending=[False, False])
    elif ordem_selecionada == 'Promoção':
        df_ordenado = df_filtrado.sort_values(by=['EM_PROMOCAO', 'RECENCIA'], ascending=[False, False])
    elif ordem_selecionada == 'Menor Preço':
        df_ordenado = df_filtrado.sort_values(by=['EM_PROMOCAO', 'PRECO_FINAL'], ascending=[False, True])
    elif ordem_selecionada == 'Maior Preço':
        df_ordenado = df_filtrado.sort_values(by=['EM_PROMOCAO', 'PRECO_FINAL'], ascending=[False, False])
    elif ordem_selecionada == 'Nome do Produto (A-Z)':
        df_ordenado = df_filtrado.sort_values(by=['EM_PROMOCAO', 'NOME'], ascending=[False, True])
    else:
        df_ordenado = df_filtrado

    df_filtrado = df_ordenado

    cols = st.columns(4)
    for i, row in df_filtrado.reset_index(drop=True).iterrows():
        product_id = row['ID']
        unique_key = f'prod_{product_id}_{i}'
        with cols[i % 4]:
            # 3. OTIMIZAÇÃO: Passa o DF indexado para a função de renderização
            render_product_card(product_id, row, key_prefix=unique_key, df_catalogo_indexado=st.session_state.df_catalogo_indexado)


# --- ADICIONA O BOTÃO FLUTUANTE NO FINAL DO SCRIPT ---
MENSAGEM_PADRAO = "Olá, vi o catálogo de pedidos da Doce&Bella e gostaria de ajuda!"
LINK_WHATSAPP = f"https://wa.me/{NUMERO_WHATSAPP}?text={requests.utils.quote(MENSAGEM_PADRAO)}"

# HTML do botão flutuante (usa o CSS que você definiu)
whatsapp_button_html = f"""
<a href="{LINK_WHATSAPP}" class="whatsapp-float" target="_blank" title="Fale Conosco pelo WhatsApp">
    <span style="margin-top: -5px;">📞</span>
</a>
"""

# Injeta o botão flutuante
st.markdown(whatsapp_button_html, unsafe_allow_html=True)
# --- FIM DO BLOCO ADICIONADO ---
