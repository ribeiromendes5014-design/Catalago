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

# --- Variáveis de Configuração (MANTIDO) ---
# Carregadas do .streamlit/secrets.toml
GITHUB_TOKEN = st.secrets["github"]["token"]
REPO_NAME = st.secrets["github"]["repo_name"]
BRANCH = st.secrets["github"]["branch"]

# URLs da API (MANTIDO)
GITHUB_BASE_API = f"https://api.github.com/repos/{REPO_NAME}/contents/"

# Fontes de Dados (CSV no GitHub) (MANTIDO)
SHEET_NAME_CATALOGO_CSV = "produtos.csv" 
SHEET_NAME_PROMOCOES_CSV = "promocoes.csv"
SHEET_NAME_PEDIDOS_CSV = "pedidos.csv" 
BACKGROUND_IMAGE_URL = 'https://i.ibb.co/x8HNtgxP/Без-названия-3.jpg'


# Inicialização do Carrinho de Compras e Estado (MANTIDO)
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {} 

# --- Headers para Autenticação do GitHub (MANTIDO) ---
def get_github_headers(content_type='json'):
    """Retorna os cabeçalhos de autorização e aceitação para escrita."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
    }
    # Para interações com a API de Conteúdo (leitura de SHA, escrita)
    if content_type == 'json':
        headers["Accept"] = "application/vnd.github.v3+json"
    
    return headers

# --- Funções de Conexão GITHUB (LEITURA PÚBLICA) ---
# Adicionada tolerância a erros no CSV usando 'engine="python"' e 'on_bad_lines="warn"'
def get_data_from_github(file_name):
    """
    Lê o conteúdo de um CSV do GitHub diretamente via API (sem cache da CDN).
    Garante que sempre trará a versão mais recente do arquivo.
    """
    api_url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_name}?ref={BRANCH}"
    
    try:
        # Autenticação com token do secrets
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        response = requests.get(api_url, headers=headers)
        response.raise_for_status()

        data = response.json()
        if "content" not in data:
            st.error(f"O campo 'content' não foi encontrado na resposta da API. Verifique se o arquivo {file_name} existe na branch '{BRANCH}'.")
            st.json(data)
            return None

        # Decodifica o conteúdo base64 retornado pela API
        content = base64.b64decode(data["content"]).decode("utf-8")
        csv_data = StringIO(content)

        # Lê o CSV e trata erros de formatação
        df = pd.read_csv(csv_data, sep=",", encoding="utf-8", engine="python", on_bad_lines="warn")

        # Normaliza nomes de colunas (boa prática)
        df.columns = [col.strip().upper() for col in df.columns]
        return df

    except requests.exceptions.HTTPError as e:
        st.error(f"Erro HTTP ao acessar '{file_name}' via API ({response.status_code}). URL: {api_url}")
        return None
    except Exception as e:
        st.error(f"Erro ao carregar '{file_name}' via API do GitHub: {e}")
        return None


@st.cache_data(ttl=5)
def carregar_promocoes():
    """Carrega as promoções do 'promocoes.csv' do GitHub. (MANTIDO)"""
    df = get_data_from_github(SHEET_NAME_PROMOCOES_CSV)
    if df is None or df.empty:
        return pd.DataFrame(columns=['ID_PRODUTO', 'PRECO_PROMOCIONAL'])

    df.columns = [col.upper().replace(' ', '_') for col in df.columns]
    
    df_essencial = df[['ID_PRODUTO', 'PRECO_PROMOCIONAL']].copy()
    df_essencial['PRECO_PROMOCIONAL'] = pd.to_numeric(df_essencial['PRECO_PROMOCIONAL'].astype(str).str.replace(',', '.'), errors='coerce')
    df_essencial['ID_PRODUTO'] = pd.to_numeric(df_essencial['ID_PRODUTO'], errors='coerce').astype('Int64')
    return df_essencial.dropna(subset=['ID_PRODUTO', 'PRECO_PROMOCIONAL'])


@st.cache_data(ttl=2)
def carregar_catalogo():
    """Carrega o catálogo do 'produtos.csv' do GitHub, aplica as promoções e prepara o DataFrame."""
    df_produtos = get_data_from_github(SHEET_NAME_CATALOGO_CSV)
    
    if df_produtos is None or df_produtos.empty:
        st.warning("Catálogo indisponível. Verifique o arquivo 'produtos.csv' no GitHub.")
        return pd.DataFrame()
    
    df_produtos.columns = [col.upper().replace(' ', '_') for col in df_produtos.columns]

    # <<< MUDANÇA AQUI: Removendo a referência à coluna CATEGORIA se ela não existe mais. >>>
    # O código abaixo verifica se o DF tem as colunas essenciais antes de prosseguir
    colunas_essenciais = ['PRECO', 'ID', 'DISPONIVEL', 'NOME']
    for col in colunas_essenciais:
        if col not in df_produtos.columns:
            st.error(f"Coluna essencial '{col}' não encontrada no 'produtos.csv'. Verifique o cabeçalho.")
            return pd.DataFrame()

    df_produtos['PRECO'] = pd.to_numeric(df_produtos['PRECO'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
    df_produtos['ID'] = pd.to_numeric(df_produtos['ID'], errors='coerce').astype('Int64')
    
    df_produtos = df_produtos[df_produtos['DISPONIVEL'].astype(str).str.strip().str.lower() == 'sim'].copy()
    df_produtos.set_index('ID', inplace=True)
    
    df_promocoes = carregar_promocoes()
    
    if not df_promocoes.empty:
        df_final = pd.merge(df_produtos.reset_index(), df_promocoes, left_on='ID', right_on='ID_PRODUTO', how='left').set_index('ID')
        df_final['PRECO_FINAL'] = df_final['PRECO_PROMOCIONAL'].fillna(df_final['PRECO'])
    else:
        df_final = df_produtos
        df_final['PRECO_FINAL'] = df_final['PRECO']
        df_final['PRECO_PROMOCIONAL'] = None 

    return df_final.reset_index()


# --- Funções do Aplicativo (SALVAR PEDIDO NO GITHUB) (MANTIDO) ---

def salvar_pedido(nome_cliente, contato_cliente, valor_total, itens_json):
    """Salva o novo pedido no 'pedidos.csv' do GitHub usando a Content API."""
    file_path = SHEET_NAME_PEDIDOS_CSV
    api_url = f"{GITHUB_BASE_API}{file_path}?ref={BRANCH}"
    
    # 1. Obter o conteúdo atual do arquivo (e o SHA)
    headers_get = get_github_headers(content_type='json')
    
    try:
        # A requisição GET AQUI DEVE USAR AUTENTICAÇÃO, pois a Content API exige.
        response_get = requests.get(api_url, headers=headers_get)
        response_get.raise_for_status()
        
        file_data = response_get.json()
        current_sha = file_data['sha']
        content_base64 = file_data['content']
        current_content = base64.b64decode(content_base64).decode('utf-8')

    except requests.exceptions.HTTPError as e:
        if response_get.status_code == 404:
            st.error(f"Erro 404: O arquivo '{file_path}' não existe. Crie um CSV vazio com os cabeçalhos para pedidos: 'timestamp,data_hora,nome_cliente,contato,itens_json,valor_total'")
            return False
        st.error(f"Erro ao obter o SHA do arquivo no GitHub (Leitura para Escrita): {e}")
        return False
    except Exception as e:
        st.error(f"Erro na decodificação do CSV: {e}")
        return False

    # 2. Adicionar o novo pedido ao conteúdo (garantindo que o JSON esteja entre aspas)
    novo_registro = f"\n{int(datetime.now().timestamp())},\"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\",\"{nome_cliente}\",\"{contato_cliente}\",\"{itens_json.replace('"', '""')}\",\"{valor_total:.2f}\""
    
    new_content = current_content.strip() + novo_registro + "\n"
    
    # 3. Codificar o novo conteúdo em Base64
    encoded_content = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')
    
    # 4. Enviar o novo conteúdo (PUT)
    commit_data = {
        "message": f"PEDIDO: Novo pedido de {nome_cliente} em {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": encoded_content,
        "sha": current_sha,
        "branch": BRANCH
    }
    
    headers_put = get_github_headers(content_type='json')

    try:
        response_put = requests.put(api_url, headers=headers_put, data=json.dumps(commit_data))
        response_put.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        st.error(f"Erro ao salvar o pedido (Commit no GitHub). Status {response_put.status_code}. Verifique as permissões 'repo' do seu PAT. Detalhe: {e}")
        return False
    except Exception as e:
        st.error(f"Erro desconhecido ao enviar o pedido: {e}")
        return False

def adicionar_ao_carrinho(produto_id, produto_nome, produto_preco):
    if produto_id in st.session_state.carrinho:
        st.session_state.carrinho[produto_id]['quantidade'] += 1
    else:
        st.session_state.carrinho[produto_id] = {'nome': produto_nome, 'preco': produto_preco, 'quantidade': 1}
    st.toast(f"✅ {produto_nome} adicionado!", icon="🛍️"); time.sleep(0.1)

def remover_do_carrinho(produto_id):
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


# --- Layout do Aplicativo (MANTIDO) ---
st.set_page_config(page_title="Catálogo Doce&Bella", layout="wide", initial_sidebar_state="collapsed")

# --- CSS (CORRIGIDO NOVAMENTE PARA FIXAÇÃO FORÇADA) ---
st.markdown(f"""
<style>
/* ---------------------------------------------------- */
/* SOLUÇÃO PARA CORRIGIR 'position: fixed' NO STREAMLIT */
/* ---------------------------------------------------- */
html, body, .main, .stApp {{
    /* Força o contêiner Streamlit a não restringir a rolagem */
    overflow-x: hidden !important;
}}
.stApp {{ 
    background-image: url({BACKGROUND_IMAGE_URL}) !important; 
    background-size: cover; 
    background-attachment: fixed; 
}}

/* CORREÇÃO 1: FATOR CHAVE para fixar a barra e garantir que ela ocupe toda a largura */
.pink-bar-container {{ 
    background-color: #E91E63; 
    padding: 20px 0; 
    width: 100vw; 
    position: fixed !important;  /* FORÇANDO FIXAÇÃO */
    top: 0 !important;           /* COLADO NO TOPO */
    left: 0 !important;          /* COLADO À ESQUERDA */
    right: 0 !important;         /* COLADO À DIREITA */
    z-index: 2000 !important;    /* PRIORIDADE MÁXIMA */
    box-shadow: 0 4px 8px rgba(0,0,0,0.3); /* Sombra mais forte para destaque */
}}

/* CORREÇÃO 2: Adiciona padding-top ao contêiner principal para o conteúdo não ficar embaixo da barra fixa */
div.block-container {{ 
    background-color: rgba(255, 255, 255, 0.95); 
    border-radius: 10px; 
    padding: 2rem; 
    padding-top: 160px !important; /* VALOR AUMENTADO E FORÇADO */
    margin-top: 0; /* Remove a margem superior desnecessária */
}}
/* ---------------------------------------------------- */
/* OUTROS ESTILOS (MANTIDOS) */
/* ---------------------------------------------------- */
.pink-bar-content {{ width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 2rem; display: flex; align-items: center; }}
div[data-testid="stPopover"] > div:first-child > button {{ display: none; }}
.cart-badge-button {{ background-color: #C2185B; color: white; border-radius: 12px; padding: 8px 15px; font-size: 16px; font-weight: bold; cursor: pointer; border: none; transition: background-color 0.3s; display: inline-flex; align-items: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); min-width: 150px; justify-content: center; }}
.cart-badge-button:hover {{ background-color: #E91E63; }}
.cart-count {{ background-color: white; color: #E91E63; border-radius: 50%; padding: 2px 7px; margin-left: 8px; font-size: 14px; line-height: 1; }}
div[data-testid="stButton"] > button {{ background-color: #E91E63; color: white; border-radius: 10px; border: 1px solid #C2185B; font-weight: bold; }}
div[data-testid="stButton"] > button:hover {{ background-color: #C2185B; color: white; border: 1px solid #E91E63; }}
.product-image-container {{ height: 220px; display: flex; align-items: center; justify-content: center; margin-bottom: 1rem; overflow: hidden; }}
.product-image-container img {{ max-height: 100%; max-width: 100%; object-fit: contain; border-radius: 8px; }}
</style>
""", unsafe_allow_html=True)


# --- ATUALIZAÇÃO AUTOMÁTICA (MANTIDO) ---
st_autorefresh(interval=10000, key="auto_refresh_catalogo")


# --- CABEÇALHO (MANTIDO) ---
col_logo, col_titulo = st.columns([0.1, 5]); col_logo.markdown("<h3>💖</h3>", unsafe_allow_html=True); col_titulo.title("Catálogo de Pedidos Doce&Bella")

# --- BARRA ROSA (PESQUISA E CARRINHO) (MANTIDO) ---
total_acumulado = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho.values())
num_itens = sum(item['quantidade'] for item in st.session_state.carrinho.values())
carrinho_vazio = not st.session_state.carrinho

st.markdown("<div class='pink-bar-container'><div class='pink-bar-content'>", unsafe_allow_html=True)
col_pesquisa, col_carrinho = st.columns([5, 1])
with col_pesquisa:
    st.text_input("Buscar...", key='termo_pesquisa_barra', label_visibility="collapsed", placeholder="Buscar produtos...")

with col_carrinho:
    custom_cart_button = f"""
        <div class='cart-badge-button' onclick='document.querySelector("[data-testid=\"stPopover\"] > div:first-child > button").click();'>
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
            st.markdown(f"<h3 style='color: #E91E63; margin-top: 0;'>Total: R$ {total_acumulado:.2f}</h3>", unsafe_allow_html=True)
            st.markdown("---")
            for prod_id, item in list(st.session_state.carrinho.items()):
                c1,c2,c3,c4=st.columns([3,1.5,2,1]);c1.write(f"*{item['nome']}*");c2.markdown(f"**{item['quantidade']}x**");c3.markdown(f"R$ {item['preco']*item['quantidade']:.2f}")
                if c4.button("X", key=f'rem_{prod_id}_popover'): remover_do_carrinho(prod_id); st.rerun()
            st.markdown("---")
            with st.form("form_finalizar_pedido", clear_on_submit=True):
                st.subheader("Finalizar Pedido")
                nome=st.text_input("Seu Nome Completo:");contato=st.text_input("Seu Contato (WhatsApp/E-mail):")
                if st.form_submit_button("✅ Enviar Pedido", type="primary", use_container_width=True):
                    if nome and contato:
                        detalhes={"total":total_acumulado,"itens":[{"id":int(k),"nome":v['nome'],"preco":v['preco'],"quantidade":v['quantidade']} for k,v in st.session_state.carrinho.items()]}
                        if salvar_pedido(nome,contato,total_acumulado,json.dumps(detalhes,ensure_ascii=False)):
                            st.balloons();st.success("🎉 Pedido enviado com sucesso!");st.session_state.carrinho={};st.rerun()
                        # else: o erro é exibido dentro de salvar_pedido()
                    else:st.warning("Preencha seu nome e contato.")
st.markdown("</div></div>", unsafe_allow_html=True)

# --- SEÇÃO DE PRODUTOS (MANTIDO) ---
st.markdown("---")
df_catalogo = carregar_catalogo()

# --------------------------------------------------------------------------
# FUNÇÃO render_product_card (MANTIDO)
# --------------------------------------------------------------------------
def render_product_card(prod_id, row, key_prefix):
    """Renderiza um card de produto, incluindo um selo de promoção se aplicável."""
    with st.container(border=True):
        render_product_image(row.get('LINKIMAGEM'))
        
        # Define as variáveis de preço e verifica se é uma promoção
        preco_final = row['PRECO_FINAL']
        preco_original = row['PRECO']
        is_promotion = pd.notna(row.get('PRECO_PROMOCIONAL')) and preco_final < preco_original

        # --- NOVO: Lógica para exibir o selo de promoção ---
        if is_promotion:
            st.markdown(f"""
            <div style="margin-bottom: 0.5rem;">
                <span style="background-color: #D32F2F; color: white; font-weight: bold; padding: 3px 8px; border-radius: 5px; font-size: 0.9rem;">
                    🔥 PROMOÇÃO
                </span>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown(f"**{row['NOME']}**")
        st.caption(row.get('DESCRICAOCURTA', ''))
        
        with st.expander("Ver detalhes"): 
            st.markdown(row.get('DESCRICAOLONGA', 'Sem descrição detalhada.'))
            
        col_preco, col_botao = st.columns([2, 2])
        
        with col_preco:
            # Reutiliza a variável 'is_promotion' para mostrar o preço
            if is_promotion:
                st.markdown(f"""
                <div style="line-height: 1.2;">
                    <span style='text-decoration: line-through; color: #757575; font-size: 0.9rem;'>R$ {preco_original:.2f}</span>
                    <h4 style='color: #D32F2F; margin:0;'>R$ {preco_final:.2f}</h4>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"<h4 style='color: #880E4F; margin:0; line-height:2.5;'>R$ {preco_final:.2f}</h4>", unsafe_allow_html=True)
                
        with col_botao:
            if st.button("➕ Adicionar", key=f'{key_prefix}_{prod_id}', use_container_width=True):
                adicionar_ao_carrinho(prod_id, row['NOME'], preco_final)
                st.rerun()

# --- Filtragem e Renderização (MANTIDO) ---
termo = st.session_state.get('termo_pesquisa_barra', '').lower()
if termo:
    # A filtragem ainda funciona com DESCRICAOLONGA, NOME
    df_filtrado = df_catalogo[df_catalogo.apply(lambda row: termo in str(row['NOME']).lower() or termo in str(row['DESCRICAOLONGA']).lower(), axis=1)]
else:
    df_filtrado = df_catalogo
    
if df_filtrado.empty:
    if termo: 
        st.info(f"Nenhum produto encontrado com o termo '{termo}'.")
    else: 
        st.warning("O catálogo está vazio ou indisponível no momento.")
else:
    st.subheader("✨ Nossos Produtos")
    cols = st.columns(4)
    for i, (prod_id, row) in enumerate(df_filtrado.iterrows()):
        product_id = row['ID'] 
        with cols[i % 4]: 
            render_product_card(product_id, row, key_prefix='prod')
