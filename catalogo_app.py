# catalogo_app.py
import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos"
SHEET_NAME_PEDIDOS = "PEDIDOS"
BACKGROUND_IMAGE_URL = 'https://images.unsplash.com/photo-1549480103-51152a12908f?fm=jpg&w=1000&auto=format&fit=crop&q=60&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8MTJ8fHBpbmt8ZW58MHx8MHx8fDA%3D'

# --- Inicialização do Estado ---
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {} # {id_produto: {'nome': str, 'preco': float, 'quantidade': int}}

# --- Funções de Conexão e Dados ---

@st.cache_resource(ttl=3600)
def get_gspread_client():
    """Cria um cliente GSpread autenticado usando o service account do st.secrets."""
    try:
        creds_dict = {
            "type": st.secrets["gsheets"]["type"],
            "project_id": st.secrets["gsheets"]["project_id"],
            "private_key_id": st.secrets["gsheets"]["private_key_id"],
            "private_key": st.secrets["gsheets"]["private_key"],
            "client_email": st.secrets["gsheets"]["client_email"],
            "client_id": st.secrets["gsheets"]["client_id"],
            "auth_uri": st.secrets["gsheets"]["auth_uri"],
            "token_uri": st.secrets["gsheets"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gsheets"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gsheets"]["client_x509_cert_url"],
        }
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open_by_url(st.secrets["gsheets"]["sheet_url"])
    except Exception as e:
        st.error(f"Erro na autenticação com Google Sheets. Verifique o secrets.toml. Detalhe: {e}")
        st.stop()

@st.cache_data(ttl=60)
def carregar_catalogo():
    """Carrega e prepara o catálogo de produtos da planilha."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_CATALOGO)
        data = worksheet.get_all_records()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df['PRECO'] = pd.to_numeric(df['PRECO'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
        df['ID'] = pd.to_numeric(df['ID'], errors='coerce').astype('Int64')
        df_disponivel = df[df['DISPONIVEL'].astype(str).str.strip().str.lower() == 'sim'].copy()
        return df_disponivel.set_index('ID')
    except Exception as e:
        st.error(f"Erro ao carregar o catálogo: {e}")
        st.info(f"Dica: Verifique se o nome da aba da planilha é '{SHEET_NAME_CATALOGO}'.")
        return pd.DataFrame()

# --- Funções de Lógica do App ---
def salvar_pedido(nome: str, contato: str, total: float, itens_json: str):
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_PEDIDOS)
        novo_pedido = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), nome, contato, itens_json, f"{total:.2f}"]
        worksheet.append_row(novo_pedido)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar pedido: {e}")
        return False

def adicionar_ao_carrinho(prod_id, qtd, nome, preco):
    if qtd > 0:
        st.session_state.carrinho[prod_id] = {'nome': nome, 'preco': preco, 'quantidade': qtd}
        st.toast(f"✅ {qtd}x {nome} adicionado!", icon="🛍️")
        time.sleep(0.1)

def remover_do_carrinho(prod_id):
    if prod_id in st.session_state.carrinho:
        nome = st.session_state.carrinho.pop(prod_id)['nome']
        st.toast(f"❌ {nome} removido.", icon="🗑️")

def render_product_image(link):
    placeholder_html = """<div style='background-color:#f0f2f6;height:200px;display:flex;align-items:center;justify-content:center;border-radius:8px;'><span style='color:#adb5bd;font-weight:bold;'>Sem Imagem</span></div>"""
    if link and isinstance(link, str) and link.strip():
        st.image(link, use_column_width="always")
    else:
        st.markdown(placeholder_html, unsafe_allow_html=True)


# --- LAYOUT PRINCIPAL E CSS ---
st.set_page_config(page_title="Catálogo Doce&Bella", layout="wide", initial_sidebar_state="collapsed")

st.markdown(f"""
<style>
.stApp {{ background-image: url({BACKGROUND_IMAGE_URL}); background-size: cover; background-attachment: fixed; }}
div.block-container {{ background-color: rgba(255, 255, 255, 0.95); border-radius: 10px; padding: 2rem; margin-top: 1rem; }}
.pink-bar-container {{ background-color: #E91E63; padding: 10px 0; width: 100vw; position: relative; left: 50%; right: 50%; margin-left: -50vw; margin-right: -50vw; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
.pink-bar-content {{ width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 2rem; display: flex; align-items: center; }}
/* ESCONDE O BOTÃO PADRÃO DO POPOVER DO CARRINHO */
div[data-testid="stPopover"] > div:first-child > button {{ display: none; }}
/* BOTÃO DO CARRINHO PERSONALIZADO */
.cart-badge-button {{ background-color:#C2185B; color:white; border-radius:12px; padding:8px 15px; font-size:16px; font-weight:bold; cursor:pointer; border:none; transition:background-color 0.3s; display:inline-flex; align-items:center; box-shadow:0 4px 6px rgba(0,0,0,0.1); min-width:150px; justify-content:center; }}
.cart-badge-button:hover {{ background-color: #E91E63; }}
.cart-count {{ background-color:white; color:#E91E63; border-radius:50%; padding:2px 7px; margin-left:8px; font-size:14px; line-height:1; }}
.stButton>button {{ border-radius: 8px; width: 100%; }}
</style>
""", unsafe_allow_html=True)


# --- CABEÇALHO ---
st.title("💖 Catálogo de Pedidos Doce&Bella")

# --- LÓGICA DO CARRINHO (CÁLCULOS) ---
total_acumulado = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho.values())
num_itens = sum(item['quantidade'] for item in st.session_state.carrinho.values())

# --- BARRA SUPERIOR COM PESQUISA E CARRINHO ---
st.markdown("<div class='pink-bar-container'><div class='pink-bar-content'>", unsafe_allow_html=True)
col_pesquisa, col_carrinho_wrapper = st.columns([4, 1])

with col_pesquisa:
    termo_pesquisa = st.text_input("Buscar...", key='termo_pesquisa', label_visibility="collapsed", placeholder="Buscar por nome ou descrição...")

with col_carrinho_wrapper:
    # Botão personalizado que aciona o popover oculto
    custom_cart_button = f"""<div class='cart-badge-button' onclick='document.querySelector("[data-testid=\"stPopover\"] > div:first-child > button").click();'>🛒 SEU PEDIDO <span class='cart-count'>{num_itens}</span></div>"""
    st.markdown(custom_cart_button, unsafe_allow_html=True)

    # Popover do carrinho (o conteúdo real)
    with st.popover(" ", use_container_width=False):
        st.header("🛒 Detalhes do Seu Pedido")
        if not st.session_state.carrinho:
            st.info("Seu carrinho está vazio.")
        else:
            st.markdown(f"### Total: R$ {total_acumulado:.2f}")
            st.markdown("---")
            for prod_id, item in list(st.session_state.carrinho.items()):
                c1, c2, c3, c4 = st.columns([3, 1.5, 2, 1])
                c1.write(f"*{item['nome']}*")
                c2.markdown(f"**{item['quantidade']}x**")
                c3.markdown(f"R$ {item['preco'] * item['quantidade']:.2f}")
                if c4.button("✖", key=f'rem_{prod_id}', help=f"Remover {item['nome']}"):
                    remover_do_carrinho(prod_id)
                    st.rerun()
            st.markdown("---")
            with st.form("form_finalizar_pedido", clear_on_submit=True):
                nome = st.text_input("Seu Nome Completo:")
                contato = st.text_input("Seu Contato (WhatsApp/E-mail):")
                if st.form_submit_button("✅ Enviar Pedido", type="primary", use_container_width=True):
                    if nome and contato:
                        itens_dict = {k: v for k, v in st.session_state.carrinho.items()}
                        if salvar_pedido(nome, contato, total_acumulado, json.dumps(itens_dict, ensure_ascii=False)):
                            st.balloons()
                            st.success("🎉 Pedido enviado! Entraremos em contato.")
                            st.session_state.carrinho.clear()
                            time.sleep(2)
                            st.rerun()
                    else:
                        st.warning("Preencha Nome e Contato para finalizar.")
st.markdown("</div></div><br>", unsafe_allow_html=True)


# --- EXIBIÇÃO DO CATÁLOGO DE PRODUTOS ---
df_catalogo = carregar_catalogo()
if df_catalogo.empty:
    st.error("O catálogo de produtos não pôde ser carregado.")
    st.stop()

df_filtrado = df_catalogo
if termo_pesquisa:
    termo = termo_pesquisa.lower()
    df_filtrado = df_catalogo[df_catalogo.apply(lambda row: termo in str(row['NOME']).lower() or termo in str(row['DESCRICAOLONGA']).lower(), axis=1)]

st.subheader("🛍️ Nossos Produtos")
st.markdown("---")

if df_filtrado.empty:
    st.info(f"Nenhum produto encontrado com o termo '{termo_pesquisa}'.")
else:
    cols = st.columns(3)
    for i, (prod_id, row) in enumerate(df_filtrado.iterrows()):
        with cols[i % 3]:
            with st.container(border=True):
                render_product_image(row.get('LINKIMAGEM'))
                st.markdown(f"**{row['NOME']}**")
                st.markdown(f"<h4 style='color:#E91E63;'>R$ {row['PRECO']:.2f}</h4>", unsafe_allow_html=True)
                st.caption(row['DESCRICAOCURTA'])

                # --- BOTÕES DE AÇÃO NO PRODUTO ---
                col_det, col_add = st.columns(2)
                with col_det:
                    with st.popover("🔍 Detalhes", use_container_width=True):
                        st.markdown(f"#### {row['NOME']}")
                        st.markdown(row['DESCRICAOLONGA'])
                        st.markdown("---")
                        qtd = st.number_input("Quantidade:", min_value=1, value=1, step=1, key=f'qtd_{prod_id}')
                        if st.button("Adicionar", key=f'add_pop_{prod_id}', type="primary"):
                            adicionar_ao_carrinho(prod_id, qtd, row['NOME'], row['PRECO'])
                            st.rerun()
                with col_add:
                    if st.button("➕ Add Pedido", key=f'add_card_{prod_id}', help="Adiciona 1 unidade ao pedido"):
                        adicionar_ao_carrinho(prod_id, 1, row['NOME'], row['PRECO'])
                        st.rerun()
            st.markdown("<br>", unsafe_allow_html=True)
