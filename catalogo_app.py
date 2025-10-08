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


# --- Variáveis de Configuração ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
DATA_REPO_NAME = os.environ.get("DATA_REPO_NAME", os.environ.get("REPO_NAME"))
BRANCH = os.environ.get("BRANCH")
# === MUDANÇAS NOVAS ===
ESTOQUE_BAIXO_LIMITE = 5 # Define o limite para exibir o alerta de "Últimas Unidades"
# === FIM DAS MUDANÇAS NOVAS ===

# URLs da API
GITHUB_BASE_API = f"https://api.github.com/repos/{DATA_REPO_NAME}/contents/"

# Fontes de Dados (CSV no GitHub)
SHEET_NAME_CATALOGO_CSV = "produtos_estoque.csv"
SHEET_NAME_PROMOCOES_CSV = "promocoes.csv"
SHEET_NAME_PEDIDOS_CSV = "pedidos.csv"
SHEET_NAME_VIDEOS_CSV = "video.csv"
BACKGROUND_IMAGE_URL = 'https://i.ibb.co/x8HNtgxP/Без-na-zvania-3.jpg'
LOGO_DOCEBELLA_URL = "https://i.ibb.co/cdqJ92W/logo_docebella.png"


# Inicialização do Carrinho de Compras e Estado
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {}
# === MUDANÇAS NOVAS ===
if 'pedido_confirmado' not in st.session_state:
    st.session_state.pedido_confirmado = None
# === FIM DAS MUDANÇAS NOVAS ---


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
        st.error(f"Erro HTTP ao acessar '{file_name}' via API ({e.response.status_code}). URL: {api_url}")
        return None
    except Exception as e:
        st.error(f"Erro ao carregar '{file_name}' via API do GitHub: {e}")
        return None


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
    """Carrega o catálogo, aplica promoções e vídeos, e prepara o DataFrame."""
    df_produtos = get_data_from_github(SHEET_NAME_CATALOGO_CSV)

    if df_produtos is None or df_produtos.empty:
        st.warning(f"Catálogo indisponível. Verifique o arquivo '{SHEET_NAME_CATALOGO_CSV}' no GitHub.")
        return pd.DataFrame()

    # --- CORREÇÃO DE RECÊNCIA: usa o ID como base da recência para maior precisão ---
    if 'ID' in df_produtos.columns:
        df_produtos['RECENCIA'] = pd.to_numeric(df_produtos['ID'], errors='coerce')
        
        # === CORREÇÃO DE DUPLICATAS (Sem remoção e sem aviso, conforme solicitado) ===
        df_produtos['ID'] = pd.to_numeric(df_produtos['ID'], errors='coerce').astype('Int64')
        df_produtos.dropna(subset=['ID'], inplace=True)
        # === FIM DA CORREÇÃO DE DUPLICATAS ===

    else:
        df_produtos['RECENCIA'] = range(len(df_produtos), 0, -1)
    # --- FIM DA CORREÇÃO DE RECÊNCIA ---

    # --- LÓGICA ROBUSTA PARA ENCONTRAR E RENOMEAR COLUNAS ---
    colunas_minimas = ['PRECOVISTA', 'ID', 'NOME']
    for col in colunas_minimas:
        if col not in df_produtos.columns:
            st.error(f"Coluna essencial '{col}' não encontrada no '{SHEET_NAME_CATALOGO_CSV}'. O aplicativo não pode continuar.")
            return pd.DataFrame()

    coluna_foto_encontrada = None
    nomes_possiveis_foto = ['FOTOURL', 'LINKIMAGEM', 'FOTO_URL', 'IMAGEM', 'URL_FOTO', 'LINK']
    for nome in nomes_possiveis_foto:
        if nome in df_produtos.columns:
            coluna_foto_encontrada = nome
            break

    mapa_renomeacao = {'PRECOVISTA': 'PRECO', 'MARCA': 'DESCRICAOCURTA'}
    if coluna_foto_encontrada:
        mapa_renomeacao[coluna_foto_encontrada] = 'LINKIMAGEM'
    else:
        st.warning("Nenhuma coluna de imagem encontrada (Ex: FOTOURL, IMAGEM). Os produtos serão exibidos sem fotos.")
        df_produtos['LINKIMAGEM'] = ""

    df_produtos.rename(columns=mapa_renomeacao, inplace=True)
    # --- FIM DA LÓGICA ROBUSTA ---

    if 'DISPONIVEL' not in df_produtos.columns:
        df_produtos['DISPONIVEL'] = 'SIM'
    if 'DESCRICAOLONGA' not in df_produtos.columns:
        df_produtos['DESCRICAOLONGA'] = df_produtos.get('CATEGORIA', '')

    df_produtos['PRECO'] = pd.to_numeric(df_produtos['PRECO'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
    df_produtos = df_produtos[df_produtos['DISPONIVEL'].astype(str).str.strip().str.lower() == 'sim'].copy()
    
    if 'QUANTIDADE' in df_produtos.columns:
        df_produtos['QUANTIDADE'] = pd.to_numeric(df_produtos['QUANTIDADE'], errors='coerce').fillna(0)
    else:
        df_produtos['QUANTIDADE'] = 999999
    
    df_produtos.set_index('ID', inplace=True)

    df_promocoes = carregar_promocoes()

    if not df_promocoes.empty:
        df_final = pd.merge(df_produtos.reset_index(), df_promocoes[['ID_PRODUTO', 'PRECO_PROMOCIONAL']], left_on='ID', right_on='ID_PRODUTO', how='left')
        df_final['PRECO_FINAL'] = df_final['PRECO_PROMOCIONAL'].fillna(df_final['PRECO'])
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
         
    return df_final.set_index('ID').reset_index()


# --- Funções do Aplicativo ---

def salvar_pedido(nome_cliente, contato_cliente, valor_total, itens_json, pedido_data):
    """Salva o novo pedido no 'pedidos.csv' do GitHub usando a Content API."""
    file_path = SHEET_NAME_PEDIDOS_CSV
    api_url = f"{GITHUB_BASE_API}{file_path}"

    novo_cabecalho = 'ID_PEDIDO,DATA_HORA,NOME_CLIENTE,CONTATO_CLIENTE,ITENS_PEDIDO,VALOR_TOTAL,LINKIMAGEM,STATUS,itens_json'

    headers_get = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
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
    status = "NOVO"
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
        "message": f"PEDIDO: Novo pedido de {nome_cliente} em {datetime.now().strftime('%Y-%m-%d %H:%M')}",
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
        # === MUDANÇAS NOVAS ===
        st.session_state.pedido_confirmado = pedido_data
        # === FIM DAS MUDANÇAS NOVAS ===
        return True
    except requests.exceptions.HTTPError as e:
        st.error(f"Erro ao salvar o pedido (Commit no GitHub). Status {e.response.status_code}. "
                 f"Verifique as permissões 'repo' do seu PAT. Detalhe: {e.response.text}")
        return False
    except Exception as e:
        st.error(f"Erro desconhecido ao enviar o pedido: {e}")
        return False

# === FUNÇÃO DE ADIÇÃO DE QUANTIDADE (Usada no card e no carrinho) ===
def adicionar_qtd_ao_carrinho(produto_id, produto_row, quantidade):
    produto_nome = produto_row['NOME']
    produto_preco = produto_row['PRECO_FINAL']
    produto_imagem = produto_row.get('LINKIMAGEM', '')
    
    # Obtém o estoque máximo garantindo que seja um número inteiro positivo
    quantidade_max = int(produto_row.get('QUANTIDADE', 999999))
    
    if quantidade_max <= 0:
         st.warning(f"⚠️ Produto '{produto_nome}' está esgotado.")
         return

    if produto_id in st.session_state.carrinho:
        # Soma a quantidade já existente + a quantidade a adicionar
        nova_quantidade = st.session_state.carrinho[produto_id]['quantidade'] + quantidade
        
        if nova_quantidade > quantidade_max:
            disponivel = quantidade_max - st.session_state.carrinho[produto_id]['quantidade']
            st.warning(f"⚠️ Você só pode adicionar mais {disponivel} unidades. Total disponível: {quantidade_max}.")
            return
            
        st.session_state.carrinho[produto_id]['quantidade'] = nova_quantidade
    else:
        # Primeira adição
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

# Esta função agora é um placeholder e não é usada diretamente no card, mas é mantida por compatibilidade.
def adicionar_ao_carrinho(produto_id, produto_row):
    pass 

def remover_do_carrinho(produto_id):
    if produto_id in st.session_state.carrinho:
        nome = st.session_state.carrinho[produto_id]['nome']
        del st.session_state.carrinho[prod_id]
        st.toast(f"❌ {nome} removido.", icon="🗑️")

def render_product_image(link_imagem):
    placeholder_html = """<div class="product-image-container" style="background-color: #f0f0f0; border-radius: 8px;"><span style="color: #a0a0a0; font-size: 1.1rem; font-weight: bold;">Sem Imagem</span></div>"""
    if link_imagem and str(link_imagem).strip().startswith('http'):
        st.markdown(f'<div class="product-image-container"><img src="{link_imagem}"></div>', unsafe_allow_html=True)
    else:
        st.markdown(placeholder_html, unsafe_allow_html=True)

# === MUDANÇAS NOVAS (Função para limpar o carrinho) ===
def limpar_carrinho():
    st.session_state.carrinho = {}
    st.toast("🗑️ Pedido limpo!", icon="🧹")
    st.rerun()
# === FIM DAS MUDANÇAS NOVAS ===

# === INÍCIO DA FUNÇÃO RENDER_PRODUCT_CARD (MOVIMENTO PARA CIMA) ===
def render_product_card(prod_id, row, key_prefix):
    """Renderiza um card de produto com suporte para abas de foto e vídeo, seletor de quantidade e feedback de estoque."""
    with st.container(border=True):
        
        # --- PREPARAÇÃO DE DADOS (Correção de tipo para segurança) ---
        # Garante que NOME e DESCRICAOCURTA sejam sempre strings (Correção do float.strip)
        produto_nome = str(row['NOME'])
        descricao_curta = str(row.get('DESCRICAOCURTA', '')).strip()
        
        # === LÓGICA DE ESTOQUE ===
        estoque_atual = int(row.get('QUANTIDADE', 999999)) 
        esgotado = estoque_atual <= 0
        estoque_baixo = estoque_atual > 0 and estoque_atual <= ESTOQUE_BAIXO_LIMITE
        
        if esgotado:
            st.markdown('<span class="esgotado-badge">🚫 ESGOTADO</span>', unsafe_allow_html=True)
        elif estoque_baixo:
            st.markdown(f'<span class="estoque-baixo-badge">⚠️ Últimas {estoque_atual} Unidades!</span>', unsafe_allow_html=True)
        # === FIM DA LÓGICA DE ESTOQUE ===

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
        st.caption(descricao_curta) # Usa a variável corrigida

        with st.expander("Ver detalhes"):
            # Lógica de Detalhes 
            descricao_principal = row.get('DESCRICAOLONGA')
            detalhes_str = row.get('DETALHESGRADE')
            
            tem_descricao = descricao_principal and isinstance(descricao_principal, str) and descricao_principal.strip()
            tem_detalhes = detalhes_str and isinstance(detalhes_str, str) and detalhes_str.strip()
            
            if not tem_descricao and not tem_detalhes:
                st.info('Sem informações detalhadas disponíveis para este produto.')
            else:
                if tem_descricao:
                    # Usa 'descricao_curta' que já é string
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

        with col_preco:
            # Lógica de Preço e Cashback 
            cashback_percent = pd.to_numeric(row.get('CASHBACKPERCENT'), errors='coerce')
            cashback_html = ""

            if pd.notna(cashback_percent) and cashback_percent > 0:
                cashback_valor_calculado = (cashback_percent / 100) * preco_final
                cashback_html = f"""
                <span style='color: #D32F2F; font-size: 0.8rem; font-weight: bold;'>
                    🔥 R$ {cashback_valor_calculado:.2f}
                </span>
                """

            if is_promotion:
                st.markdown(f"""
                <div style="line-height: 1.2;">
                    <span style='text-decoration: line-through; color: #757575; font-size: 0.9rem;'>R$ {preco_original:.2f}</span>
                    <h4 style='color: #D32F2F; margin:0;'>R$ {preco_final:.2f}</h4>
                    {cashback_html}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style='display: flex; align-items: flex-end; flex-wrap: wrap; gap: 8px;'>
                    <h4 style='color: #880E4F; margin:0; line-height:1;'>R$ {preco_final:.2f}</h4>
                    {cashback_html}
                </div>
                """, unsafe_allow_html=True)


        # === SELETOR DE QUANTIDADE NO CARD ===
        with col_botao:
            item_ja_no_carrinho = prod_id in st.session_state.carrinho

            if esgotado:
                st.empty() 
                
            elif item_ja_no_carrinho:
                qtd_atual = st.session_state.carrinho[prod_id]['quantidade']
                # Exibe o botão de indicador
                st.button(
                    f"✅ {qtd_atual}x NO PEDIDO", 
                    key=f'btn_add_qtd_{key_prefix}', 
                    use_container_width=True, 
                    disabled=True 
                )
            else:
                # Se não esgotado E não está no carrinho, mostra o seletor normal
                qtd_a_adicionar = st.number_input(
                    label=f'Qtd_Input_{key_prefix}',
                    min_value=1,
                    max_value=estoque_atual, 
                    value=1,
                    step=1,
                    key=f'qtd_input_{key_prefix}',
                    label_visibility="collapsed"
                )
                
                if st.button(f"🛒 Adicionar {qtd_a_adicionar} un.", key=f'btn_add_qtd_{key_prefix}', use_container_width=True):
                    if qtd_a_adicionar >= 1:
                        adicionar_qtd_ao_carrinho(prod_id, row, qtd_a_adicionar)
                        st.rerun()
        # === FIM SELETOR DE QUANTIDADE ===
# === FIM DA FUNÇÃO RENDER_PRODUCT_CARD ===


# --- Layout do Aplicativo (CONTINUAÇÃO) ---
st.set_page_config(page_title="Catálogo Doce&Bella", layout="wide", initial_sidebar_state="collapsed")

# --- CSS ---
st.markdown(f"""
<style>
#MainMenu, footer, [data-testid="stSidebar"] {{visibility: hidden;}}
[data-testid="stSidebarHeader"], [data-testid="stToolbar"], a[data-testid="stAppDeployButton"], [data-testid="stStatusWidget"], [data-testid="stDecoration"] {{ display: none !important; }}
div[data-testid="stPopover"] > div:first-child > button {{ display: none; }}
.stApp {{ background-image: url({BACKGROUND_IMAGE_URL}) !important; background-size: cover; background-attachment: fixed; }}
div.block-container {{ background-color: rgba(255, 255, 255, 0.95); border-radius: 10px; padding: 2rem; margin-top: 1rem; }}
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
</style>
""", unsafe_allow_html=True)

# === MUDANÇAS NOVAS (JS para copiar o resumo do pedido) ===
# Função JS para copiar texto (usada após o envio do pedido)
def copy_to_clipboard_js(text_to_copy):
    js_code = f"""
    <script>
    function copyTextToClipboard(text) {{
      if (navigator.clipboard) {{
        navigator.clipboard.writeText(text).then(function() {{
          // St.toast não está disponível em JS, mas podemos usar um alerta simples
          alert('Resumo do pedido copiado!');
        }}, function(err) {{
          console.error('Não foi possível copiar o texto: ', err);
          alert('Erro ao copiar o texto. Tente novamente.');
        }});
      }} else {{
        // Fallback para navegadores mais antigos (usando um textarea temporário)
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
    // Chama a função ao renderizar o botão, mas de forma segura com onclick
    // O botão deve ser gerado separadamente com um ID
    </script>
    """
    st.markdown(js_code, unsafe_allow_html=True)
# === FIM DAS MUDANÇAS NOVAS ===


st_autorefresh(interval=5000, key="auto_refresh_catalogo")

# --- LÓGICA DE CONFIRMAÇÃO DE PEDIDO (Nova Seção) ---
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
        f"📞 Contato: {pedido['contato']}\n\n"
        f"📦 Itens Pedidos:\n"
        f"{itens_formatados}\n\n"
        f"💰 VALOR TOTAL: R$ {pedido['total']:.2f}\n\n"
        f"Obrigado por seu pedido!"
    )

    st.text_area("Resumo do Pedido (Clique para copiar)", resumo_texto, height=300)
    
    # Botão de Copiar (usando JS)
    copy_to_clipboard_js(resumo_texto)
    st.markdown(
        f'<button class="cart-badge-button" style="background-color: #25D366; width: 100%; margin-bottom: 15px;" onclick="copyTextToClipboard(\'{resumo_texto.replace("'", "\\'")}\')">✅ Copiar Resumo</button>',
        unsafe_allow_html=True
    )
    
    # Após exibir, limpa a variável de confirmação
    if st.button("Voltar ao Catálogo"):
        st.session_state.pedido_confirmado = None
        st.rerun()
    st.stop()
# --- FIM DA LÓGICA DE CONFIRMAÇÃO ---

# --- LOGO E TÍTULO (Alterado) ---
col_logo, col_titulo = st.columns([1.5, 4.5])
col_logo.image(LOGO_DOCEBELLA_URL, width=200)
col_titulo.title("Catálogo de Pedidos Doce&Bella")
# --- FIM DA ALTERAÇÃO ---

total_acumulado = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho.values())
num_itens = sum(item['quantidade'] for item in st.session_state.carrinho.values())
carrinho_vazio = not st.session_state.carrinho

st.markdown("<div class='pink-bar-container'><div class='pink-bar-content'>", unsafe_allow_html=True)

# A busca principal está na barra rosa, mas usaremos o novo filtro na seção de produtos.
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
            st.markdown(f"<h3 style='color: #E91E63; margin-top: 0;'>Total: R$ {total_acumulado:.2f}</h3>", unsafe_allow_html=True)
            st.markdown("---")
            
            df_catalogo_completo = carregar_catalogo().set_index('ID')
            
            for prod_id, item in list(st.session_state.carrinho.items()):
                # === CORREÇÃO DO NAMEERROR: DEFINIÇÃO DE COLUNAS ===
                # === IMPLEMENTAÇÃO: Mais espaço para o subtotal/preço unitário ===
                c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                # === FIM DA CORREÇÃO ===
                
                c1.write(f"*{item['nome']}*")
                
                # === Lógica de Max Qtd no Carrinho ===
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
                    label=f'Qtd_{prod_id}',
                    min_value=1,
                    max_value=max_qtd,
                    value=item['quantidade'],
                    step=1,
                    key=f'qtd_{prod_id}_popover',
                    label_visibility="collapsed"
                )
                
                if nova_quantidade != item['quantidade']:
                    st.session_state.carrinho[prod_id]['quantidade'] = nova_quantidade
                    st.rerun()
                # === Fim Lógica de Max Qtd no Carrinho ===

                # === IMPLEMENTAÇÃO: Subtotal e Preço Unitário ===
                c3.markdown(f"**R$ {item['preco']*item['quantidade']:.2f}**<br><span style='font-size: 0.8rem; color: #757575;'>(R$ {item['preco']:.2f} un.)</span>", unsafe_allow_html=True)
                # === FIM DA IMPLEMENTAÇÃO ===
                
                if c4.button("X", key=f'rem_{prod_id}_popover'):
                    remover_do_carrinho(prod_id)
                    st.rerun()
            st.markdown("---")
            
            # === MUDANÇAS NOVAS (Botão Limpar Carrinho) ===
            st.button("🗑️ Limpar Pedido", on_click=limpar_carrinho, use_container_width=True)
            st.markdown("---")
            # === FIM DAS MUDANÇAS NOVAS ===
            
            with st.form("form_finalizar_pedido", clear_on_submit=True):
                st.subheader("Finalizar Pedido")
                nome = st.text_input("Seu Nome Completo:")
                contato = st.text_input("Seu Contato (WhatsApp/E-mail):")
                if st.form_submit_button("✅ Enviar Pedido", type="primary", use_container_width=True):
                    if nome and contato:
                        detalhes = {
                            "total": total_acumulado,
                            "itens": [
                                {
                                    "id": int(k),
                                    "nome": v['nome'],
                                    "preco": v['preco'],
                                    "quantidade": v['quantidade'],
                                    "imagem": v.get('imagem', '')
                                } for k, v in st.session_state.carrinho.items()
                            ],
                            "nome": nome,
                            "contato": contato
                        }
                        if salvar_pedido(nome, contato, total_acumulado, json.dumps(detalhes, ensure_ascii=False), detalhes):
                            st.session_state.carrinho = {}
                            st.rerun()
                    else:
                        st.warning("Preencha seu nome e contato.")
st.markdown("</div></div>", unsafe_allow_html=True)

df_catalogo = carregar_catalogo()

# --- NOVO BLOCO: FILTRO POR CATEGORIA E BUSCA AVANÇADA ---

if 'CATEGORIA' in df_catalogo.columns:
    categorias = df_catalogo['CATEGORIA'].dropna().astype(str).unique().tolist()
    categorias.sort()
    categorias.insert(0, "TODAS AS CATEGORIAS")
else:
    categorias = ["TODAS AS CATEGORIAS"]
    if "Geral" not in df_catalogo.columns:
         st.warning("A coluna 'CATEGORIA' não foi encontrada no seu arquivo de catálogo. O filtro não será exibido.")


# 2. Widgets de Filtro e Ordenação
col_filtro_cat, col_select_ordem, _ = st.columns([1, 1, 3])

# Variável de termo da busca principal (capturada na barra rosa)
termo = st.session_state.get('termo_pesquisa_barra', '').lower()

with col_filtro_cat:
    categoria_selecionada = st.selectbox(
        "Filtrar por:",
        categorias,
        key='filtro_categoria_barra'
    )
    if termo:
        st.markdown(f'<div style="font-size: 0.8rem; color: #E91E63;">Busca ativa desabilita filtro.</div>', unsafe_allow_html=True)


# 3. Lógica de Filtragem

df_filtrado = df_catalogo.copy()

if not termo and categoria_selecionada != "TODAS AS CATEGORIAS":
    df_filtrado = df_filtrado[df_filtrado['CATEGORIA'].astype(str) == categoria_selecionada]

elif termo:
    df_filtrado = df_filtrado[df_filtrado.apply(
        lambda row: termo in str(row['NOME']).lower() or termo in str(row['DESCRICAOLONGA']).lower(), 
        axis=1
    )]
# --- FIM DO NOVO BLOCO DE FILTRO ---


if df_filtrado.empty:
    if termo:
        st.info(f"Nenhum produto encontrado com o termo '{termo}' na categoria '{categoria_selecionada}'.")
    else:
        st.info(f"Nenhum produto encontrado na categoria '{categoria_selecionada}'.")
else:
    st.subheader("✨ Nossos Produtos")

    # --- WIDGET DE ORDENAÇÃO (movido para a coluna ao lado do filtro) ---
    with col_select_ordem:
        opcoes_ordem = ['Lançamento', 'Promoção', 'Menor Preço', 'Maior Preço', 'Nome do Produto (A-Z)']
        ordem_selecionada = st.selectbox(
            "Ordenar por:",
            opcoes_ordem,
            key='ordem_produtos'
        )
    # --- FIM DA ALTERAÇÃO ---

    # --- LÓGICA DE ORDENAÇÃO CORRIGIDA E OTIMIZADA ---
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
    # --- FIM DA LÓGICA DE ORDENAÇÃO ---

    cols = st.columns(4)
    for i, row in df_filtrado.reset_index(drop=True).iterrows():
        product_id = row['ID']
        unique_key = f'prod_{product_id}_{i}'
        with cols[i % 4]:
            render_product_card(product_id, row, key_prefix=unique_key)
