# catalogo_app.py
import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
from streamlit_autorefresh import st_autorefresh
from collections import defaultdict

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos"
SHEET_NAME_PEDIDOS = "pedidos"
SHEET_NAME_PROMOCOES = "promocoes"
BACKGROUND_IMAGE_URL = 'https://i.ibb.co/x8HNtgxP/Без-названия-3.jpg'

# --- URLs DAS IMAGENS DE TÍTULO ---
URL_MAIS_VENDIDOS = "https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-queridinhos1.png"
URL_OFERTAS = "https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-oferta.png"
# REMOVIDO: URL_ICONE_OFERTAS que estava causando a imagem quebrada.


# Inicialização do Carrinho de Compras
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {}

# --- Funções de Conexão e Carregamento de Dados (sem alterações) ---

def get_gspread_client():
    """Cria um cliente GSpread autenticado."""
    try:
        gcp_sa_credentials = {
            "type": st.secrets["gsheets"]["type"], "project_id": st.secrets["gsheets"]["project_id"],
            "private_key_id": st.secrets["gsheets"]["private_key_id"], "private_key": st.secrets["gsheets"]["private_key"],
            "client_email": st.secrets["gsheets"]["client_email"], "client_id": st.secrets["gsheets"]["client_id"],
            "auth_uri": st.secrets["gsheets"]["auth_uri"], "token_uri": st.secrets["gsheets"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gsheets"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gsheets"]["client_x509_cert_url"]
        }
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(gcp_sa_credentials, scope)
        client = gspread.authorize(creds)
        sh = client.open_by_url(st.secrets["gsheets"]["sheet_url"])
        return sh
    except Exception as e:
        st.error(f"Erro na autenticação do Google Sheets: {e}")
        st.stop()

@st.cache_data(ttl=5)
def carregar_catalogo():
    """Carrega o catálogo, aplica as promoções e prepara o DataFrame."""
    try:
        sh = get_gspread_client()
        worksheet_produtos = sh.worksheet(SHEET_NAME_CATALOGO)
        data_produtos = worksheet_produtos.get_all_values()
        df_produtos = pd.DataFrame(data_produtos[1:], columns=data_produtos[0])
        df_produtos['PRECO'] = pd.to_numeric(df_produtos['PRECO'].str.replace(',', '.'), errors='coerce').fillna(0.0)
        df_produtos['ID'] = pd.to_numeric(df_produtos['ID'], errors='coerce').astype('Int64')
        df_produtos = df_produtos[df_produtos['DISPONIVEL'].astype(str).str.strip().str.lower() == 'sim'].copy()
        df_produtos.set_index('ID', inplace=True)

        try:
            worksheet_promocoes = sh.worksheet(SHEET_NAME_PROMOCOES)
            data_promocoes = worksheet_promocoes.get_all_values()
            df_promocoes = pd.DataFrame(data_promocoes[1:], columns=data_promocoes[0])
            df_promocoes = df_promocoes[['ID_PRODUTO', 'PRECO_PROMOCIONAL']].copy()
            df_promocoes['PRECO_PROMOCIONAL'] = pd.to_numeric(df_promocoes['PRECO_PROMOCIONAL'].str.replace(',', '.'), errors='coerce')
            df_promocoes['ID_PRODUTO'] = pd.to_numeric(df_promocoes['ID_PRODUTO'], errors='coerce').astype('Int64')
            df_promocoes.dropna(subset=['ID_PRODUTO', 'PRECO_PROMOCIONAL'], inplace=True)
        except gspread.exceptions.WorksheetNotFound:
            df_promocoes = pd.DataFrame(columns=['ID_PRODUTO', 'PRECO_PROMOCIONAL'])

        if not df_promocoes.empty:
            df_final = pd.merge(df_produtos, df_promocoes, left_index=True, right_on='ID_PRODUTO', how='left')
            df_final['PRECO_FINAL'] = df_final['PRECO_PROMOCIONAL'].fillna(df_final['PRECO'])
        else:
            df_final = df_produtos
            df_final['PRECO_FINAL'] = df_final['PRECO']
            df_final['PRECO_PROMOCIONAL'] = None
        return df_final
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar o catálogo: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def carregar_mais_vendidos(df_catalogo, top_n=4):
    """Lê a planilha de pedidos, calcula os produtos mais vendidos e retorna um DataFrame com os detalhes."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_PEDIDOS)
        pedidos = worksheet.get_all_values()
        
        if len(pedidos) < 2:
            return pd.DataFrame()

        vendas = defaultdict(int)
        for linha in pedidos[1:]:
            try:
                itens_json = linha[4]
                dados_pedido = json.loads(itens_json)
                for item in dados_pedido.get('itens', []):
                    vendas[item['id']] += item.get('quantidade', 1)
            except (IndexError, json.JSONDecodeError):
                continue
        
        if not vendas:
            return pd.DataFrame()

        df_vendas = pd.DataFrame(list(vendas.items()), columns=['ID', 'QTD_VENDIDA']).astype({'ID': 'int64'})
        df_vendas = df_vendas.sort_values(by='QTD_VENDIDA', ascending=False)
        
        df_mais_vendidos = pd.merge(df_vendas, df_catalogo, left_on='ID', right_index=True)
        
        return df_mais_vendidos.head(top_n)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame() # Retorna vazio se a aba não existe, para não mostrar erro
    except Exception as e:
        st.error(f"Erro ao calcular os mais vendidos: {e}")
        return pd.DataFrame()


# --- Funções do Aplicativo (sem grandes alterações) ---
def salvar_pedido(nome_cliente, contato_cliente, valor_total, itens_json):
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_PEDIDOS)
        novo_registro = [ int(datetime.now().timestamp()), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), nome_cliente, contato_cliente, itens_json, f"{valor_total:.2f}".replace('.', ',')]
        worksheet.append_row(novo_registro)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar o pedido: {e}")
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
    placeholder_html = """<div class="product-image-container"><span class="placeholder-text">Sem Imagem</span></div>"""
    if link_imagem and str(link_imagem).strip().startswith('http'):
        st.markdown(f'<div class="product-image-container"><img src="{link_imagem}"></div>', unsafe_allow_html=True)
    else:
        st.markdown(placeholder_html, unsafe_allow_html=True)

def render_product_card(prod_id, row, key_prefix):
    with st.container(border=True):
        render_product_image(row.get('LINKIMAGEM'))
        preco_final = row['PRECO_FINAL']
        preco_original = row['PRECO']
        is_promotion = pd.notna(row.get('PRECO_PROMOCIONAL')) and preco_final < preco_original

        if is_promotion:
            st.markdown(f"""<span class="promo-badge">🔥 PROMOÇÃO</span>""", unsafe_allow_html=True)
        
        st.markdown(f"**{row['NOME']}**")
        st.caption(row.get('DESCRICAOCURTA', ''))
        
        with st.expander("Ver detalhes"): 
            st.markdown(row.get('DESCRICAOLONGA', 'Sem descrição detalhada.'))
            
        col_preco, col_botao = st.columns([2, 2])
        with col_preco:
            if is_promotion:
                st.markdown(f"""<div class="price-container"><span class='price-original'>R$ {preco_original:.2f}</span><h4 class='price-promo'>R$ {preco_final:.2f}</h4></div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"<h4 class='price-normal'>R$ {preco_final:.2f}</h4>", unsafe_allow_html=True)
        with col_botao:
            if st.button("➕ Adicionar", key=f'{key_prefix}_{prod_id}', use_container_width=True):
                adicionar_ao_carrinho(prod_id, row['NOME'], preco_final); st.rerun()

# --- Layout do Aplicativo ---
st.set_page_config(page_title="Catálogo Doce&Bella", layout="wide", initial_sidebar_state="collapsed")

# --- CSS ---
st.markdown(f"""
<style>
    .stApp {{ background-image: url({BACKGROUND_IMAGE_URL}); background-size: cover; background-attachment: fixed; }}
    div.block-container {{ background-color: rgba(255, 255, 255, 0.95); border-radius: 10px; padding: 2rem; margin-top: 1rem; }}
    .pink-bar-container {{ background-color: #E91E63; padding: 20px 0; width: 100vw; position: relative; left: 50%; right: 50%; margin-left: -50vw; margin-right: -50vw; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
    .pink-bar-content {{ width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 2rem; display: flex; align-items: center; }}
    div[data-testid="stPopover"] > div:first-child > button {{ display: none; }}
    .cart-badge-button {{ background-color: #C2185B; color: white; border-radius: 12px; padding: 8px 15px; font-size: 16px; font-weight: bold; cursor: pointer; border: none; transition: background-color 0.3s; display: inline-flex; align-items: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); min-width: 150px; justify-content: center; }}
    .cart-badge-button:hover {{ background-color: #E91E63; }}
    .cart-count {{ background-color: white; color: #E91E63; border-radius: 50%; padding: 2px 7px; margin-left: 8px; font-size: 14px; line-height: 1; }}
    .product-image-container {{ height: 220px; display: flex; align-items: center; justify-content: center; margin-bottom: 1rem; overflow: hidden; }}
    .product-image-container img {{ max-height: 100%; max-width: 100%; object-fit: contain; border-radius: 8px; }}
    .placeholder-text {{ color: #a0a0a0; font-size: 1.1rem; font-weight: bold; }}
    .promo-badge {{ background-color: #D32F2F; color: white; font-weight: bold; padding: 3px 8px; border-radius: 5px; font-size: 0.9rem; margin-bottom: 0.5rem; display: inline-block;}}
    .price-container {{ line-height: 1.2; }}
    .price-original {{ text-decoration: line-through; color: #757575; font-size: 0.9rem; }}
    .price-promo {{ color: #D32F2F; margin:0; }}
    .price-normal {{ color: #880E4F; margin:0; line-height:2.5; }}
    .section-title-container {{ text-align: center; margin-top: 2rem; margin-bottom: 1.5rem; }}
    .section-title-image {{ max-width: 300px; }}
</style>
""", unsafe_allow_html=True)

# --- ATUALIZAÇÃO AUTOMÁTICA ---
st_autorefresh(interval=60000, key="auto_refresh_catalogo")

# --- CABEÇALHO ---
col_logo, col_titulo = st.columns([0.1, 5]); col_logo.markdown("<h3>💖</h3>", unsafe_allow_html=True); col_titulo.title("Catálogo de Pedidos Doce&Bella")

# --- BARRA ROSA (PESQUISA E CARRINHO) (Inalterado) ---
total_acumulado = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho.values())
num_itens = sum(item['quantidade'] for item in st.session_state.carrinho.values())
carrinho_vazio = not st.session_state.carrinho
st.markdown("<div class='pink-bar-container'><div class='pink-bar-content'>", unsafe_allow_html=True)
col_pesquisa, col_carrinho = st.columns([5, 1])
with col_pesquisa:
    st.text_input("Buscar...", key='termo_pesquisa_barra', label_visibility="collapsed", placeholder="Buscar produtos...")
with col_carrinho:
    st.markdown(f"""<div class='cart-badge-button' onclick='document.querySelector("[data-testid=\"stPopover\"] > div:first-child > button").click();'>🛒 SEU PEDIDO<span class='cart-count'>{num_itens}</span></div>""", unsafe_allow_html=True)
    with st.popover(" ", use_container_width=False):
        st.header("🛒 Detalhes do Pedido")
        if carrinho_vazio: st.info("Seu carrinho está vazio.")
        else:
            st.markdown(f"<h3 style='color: #E91E63;'>Total: R$ {total_acumulado:.2f}</h3>", unsafe_allow_html=True)
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
                            st.balloons();st.success("🎉 Pedido enviado!");st.session_state.carrinho={};st.rerun()
                        else:st.error("Falha ao salvar o pedido.")
                    else:st.warning("Preencha seu nome e contato.")
st.markdown("</div></div>", unsafe_allow_html=True)


# --- Carregamento principal dos dados ---
df_catalogo = carregar_catalogo()

# --------------------------------------------------------------------------
# --- NOVO LAYOUT PRINCIPAL (COM AS CORREÇÕES) ---
# --------------------------------------------------------------------------

if df_catalogo.empty:
    st.warning("O catálogo de produtos não pôde ser carregado. Verifique a planilha.")
else:
    # --- SEÇÃO: OS MAIS QUERIDINHOS (AGORA SÓ APARECE SE HOUVER DADOS) ---
    df_mais_vendidos = carregar_mais_vendidos(df_catalogo, top_n=4)

    # A verificação é feita ANTES de desenhar qualquer coisa na tela
    if not df_mais_vendidos.empty:
        st.markdown(f"<div class='section-title-container'><img src='{URL_MAIS_VENDIDOS}' class='section-title-image'></div>", unsafe_allow_html=True)
        cols = st.columns(4)
        for i, (prod_id, row) in enumerate(df_mais_vendidos.iterrows()):
            with cols[i % 4]:
                # Usamos o 'ID' real do produto que veio da junção dos dataframes
                render_product_card(row['ID'], row, key_prefix='vendido')
        st.markdown("<hr>", unsafe_allow_html=True)

    # --- SEÇÃO: NOSSAS OFERTAS (AGORA SÓ APARECE SE HOUVER PROMOÇÕES) ---
    df_ofertas = df_catalogo[pd.notna(df_catalogo['PRECO_PROMOCIONAL']) & (df_catalogo['PRECO_FINAL'] < df_catalogo['PRECO'])]
    
    if not df_ofertas.empty: # <--- MUDANÇA AQUI: Só renderiza se houver ofertas
        st.markdown(f"<div class='section-title-container'><img src='{URL_OFERTAS}' class='section-title-image'></div>", unsafe_allow_html=True)
        
        cols = st.columns(4)
        for i, (prod_id, row) in enumerate(df_ofertas.iterrows()):
            with cols[i % 4]:
                render_product_card(prod_id, row, key_prefix='oferta')
        
        st.markdown("<hr>", unsafe_allow_html=True) # <--- MUDANÇA AQUI: A linha também é condicional

    # --- SEÇÃO: CATÁLOGO COMPLETO ---
    st.subheader("🛍️ Catálogo Completo")
    termo = st.session_state.get('termo_pesquisa_barra', '').lower()
    if termo:
        df_filtrado = df_catalogo[df_catalogo.apply(lambda row: termo in str(row['NOME']).lower() or termo in str(row['DESCRICAOLONGA']).lower(), axis=1)]
    else:
        df_filtrado = df_catalogo
    
    if df_filtrado.empty:
        st.info(f"Nenhum produto encontrado com o termo '{termo}'.")
    else:
        cols = st.columns(4)
        for i, (prod_id, row) in enumerate(df_filtrado.iterrows()):
            with cols[i % 4]:
                render_product_card(prod_id, row, key_prefix='catalogo')
