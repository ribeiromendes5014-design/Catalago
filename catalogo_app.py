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
# --- ALTERAÇÃO APLICADA AQUI ---
SHEET_NAME_PEDIDOS = "pedidos" # Trocado para minúsculo
BACKGROUND_IMAGE_URL = 'https://i.ibb.co/x8HNtgxP/Без-названия-3.jpg'


# Inicialização do Carrinho de Compras e Estado
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {}

# --- Funções de Conexão GSpread ---
@st.cache_resource(ttl=None)
def get_gspread_client():
    """Cria um cliente GSpread autenticado usando o service account do st.secrets."""
    try:
        gcp_sa_credentials = {
            "type": st.secrets["gsheets"]["type"],
            "project_id": st.secrets["gsheets"]["project_id"],
            "private_key_id": st.secrets["gsheets"]["private_key_id"],
            "private_key": st.secrets["gsheets"]["private_key"],
            "client_email": st.secrets["gsheets"]["client_email"],
            "client_id": st.secrets["gsheets"]["client_id"],
            "auth_uri": st.secrets["gsheets"]["auth_uri"],
            "token_uri": st.secrets["gsheets"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gsheets"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gsheets"]["client_x509_cert_url"]
        }
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(gcp_sa_credentials, scope)
        client = gspread.authorize(creds)
        sh = client.open_by_url(st.secrets["gsheets"]["sheet_url"])
        return sh
    except Exception as e:
        st.error(f"Erro na autenticação do Google Sheets. Verifique o secrets.toml. Detalhe: {e}")
        st.stop()

@st.cache_data(ttl=600)
def carregar_catalogo():
    """Carrega o catálogo de produtos e prepara o DataFrame."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_CATALOGO)
        data = worksheet.get_all_values()
        if not data or len(data) < 2:
            return pd.DataFrame()

        df = pd.DataFrame(data[1:], columns=data[0])
        df['PRECO'] = pd.to_numeric(df['PRECO'].str.replace(',', '.'), errors='coerce').fillna(0.0)
        df['ID'] = pd.to_numeric(df['ID'], errors='coerce').astype('Int64')
        df_filtrado = df[df['DISPONIVEL'].astype(str).str.strip().str.lower() == 'sim'].copy()
        return df_filtrado.set_index('ID')
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Erro: A aba '{SHEET_NAME_CATALOGO}' não foi encontrada na planilha.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar o catálogo: {e}")
        return pd.DataFrame()


# --- Funções do Aplicativo ---

def salvar_pedido(nome_cliente, contato_cliente, valor_total, itens_json):
    """Salva um novo pedido na planilha."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_PEDIDOS)
        novo_registro = [
            int(datetime.now().timestamp()),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            nome_cliente,
            contato_cliente,
            itens_json,
            f"{valor_total:.2f}".replace('.', ',')
        ]
        worksheet.append_row(novo_registro)
        return True
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Erro ao salvar: A aba '{SHEET_NAME_PEDIDOS}' não foi encontrada. Verifique o nome da aba na planilha.")
        return False
    except Exception as e:
        st.error(f"Erro ao salvar o pedido: {e}")
        return False

def adicionar_ao_carrinho(produto_id, produto_nome, produto_preco):
    """Adiciona 1 unidade de um produto ao carrinho."""
    if produto_id in st.session_state.carrinho:
        st.session_state.carrinho[produto_id]['quantidade'] += 1
    else:
        st.session_state.carrinho[produto_id] = {'nome': produto_nome, 'preco': produto_preco, 'quantidade': 1}
    st.toast(f"✅ {produto_nome} adicionado!", icon="🛍️")
    time.sleep(0.1)

def remover_do_carrinho(produto_id):
    """Remove um produto do carrinho."""
    if produto_id in st.session_state.carrinho:
        nome = st.session_state.carrinho[produto_id]['nome']
        del st.session_state.carrinho[produto_id]
        st.toast(f"❌ {nome} removido.", icon="🗑️")

def render_product_image(link_imagem):
    """Renderiza a imagem do produto com HTML para controle de tamanho via CSS."""
    placeholder_html = """
        <div class="product-image-container" style="background-color: #f0f0f0; border-radius: 8px;">
            <span style="color: #a0a0a0; font-size: 1.1rem; font-weight: bold;">Sem Imagem</span>
        </div>
    """
    if link_imagem and str(link_imagem).strip().startswith('http'):
        st.markdown(f'<div class="product-image-container"><img src="{link_imagem}"></div>', unsafe_allow_html=True)
    else:
        st.markdown(placeholder_html, unsafe_allow_html=True)


# --- Layout do Aplicativo ---
st.set_page_config(page_title="Catálogo Doce&Bella", layout="wide", initial_sidebar_state="collapsed")

# --- CSS ---
st.markdown(f"""
<style>
.stApp {{ background-image: url({BACKGROUND_IMAGE_URL}) !important; background-size: cover; background-attachment: fixed; }}
div.block-container {{ background-color: rgba(255, 255, 255, 0.95); border-radius: 10px; padding: 2rem; margin-top: 1rem; }}
.pink-bar-container {{ background-color: #E91E63; padding: 20px 0; width: 100vw; position: relative; left: 50%; right: 50%; margin-left: -50vw; margin-right: -50vw; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
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


# --- CABEÇALHO ---
col_logo, col_titulo = st.columns([0.1, 5])
with col_logo: st.markdown("<h3>💖</h3>", unsafe_allow_html=True)
with col_titulo: st.title("Catálogo de Pedidos Doce&Bella")

# --- BARRA ROSA (PESQUISA E CARRINHO) ---
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
                c1, c2, c3, c4 = st.columns([3, 1.5, 2, 1])
                c1.write(f"*{item['nome']}*"); c2.markdown(f"**{item['quantidade']}x**"); c3.markdown(f"R$ {item['preco']*item['quantidade']:.2f}")
                if c4.button("X", key=f'rem_{prod_id}_popover'): remover_do_carrinho(prod_id); st.rerun()
            st.markdown("---")
            with st.form("form_finalizar_pedido", clear_on_submit=True):
                st.subheader("Finalizar Pedido"); nome = st.text_input("Seu Nome Completo:"); contato = st.text_input("Seu Contato (WhatsApp/E-mail):")
                if st.form_submit_button("✅ Enviar Pedido", type="primary", use_container_width=True):
                    if nome and contato:
                        detalhes = {"total": total_acumulado, "itens": [{"id": int(k), "nome": v['nome'], "preco": v['preco'], "quantidade": v['quantidade']} for k, v in st.session_state.carrinho.items()]}
                        if salvar_pedido(nome, contato, total_acumulado, json.dumps(detalhes, ensure_ascii=False)):
                            st.balloons(); st.success("🎉 Pedido enviado com sucesso!"); st.session_state.carrinho = {}; st.rerun()
                        else: st.error("Falha ao salvar o pedido.")
                    else: st.warning("Preencha seu nome e contato.")
st.markdown("</div></div>", unsafe_allow_html=True)

# --- SEÇÃO DE PRODUTOS ---
st.markdown("---")
df_catalogo = carregar_catalogo()

def render_product_card(prod_id, row, key_prefix):
    with st.container(border=True):
        render_product_image(row.get('LINKIMAGEM'))
        st.markdown(f"**{row['NOME']}**"); st.caption(row.get('DESCRICAOCURTA', ''))
        with st.expander("Ver detalhes"): st.markdown(row.get('DESCRICAOLONGA', 'Sem descrição detalhada.'))
        col_preco, col_botao = st.columns([2, 2])
        col_preco.markdown(f"<h4 style='color: #880E4F; margin:0; line-height:2.5;'>R$ {row['PRECO']:.2f}</h4>", unsafe_allow_html=True)
        if col_botao.button("➕ Adicionar", key=f'{key_prefix}_{prod_id}', use_container_width=True):
            adicionar_ao_carrinho(prod_id, row['NOME'], row['PRECO']); st.rerun()

# Filtragem e Renderização
termo = st.session_state.get('termo_pesquisa_barra', '').lower()
if termo:
    df_filtrado = df_catalogo[df_catalogo.apply(lambda row: termo in str(row['NOME']).lower() or termo in str(row['DESCRICAOLONGA']).lower(), axis=1)]
else:
    df_filtrado = df_catalogo

if df_filtrado.empty:
    if termo: st.info(f"Nenhum produto encontrado com o termo '{termo}'.")
    else: st.warning("O catálogo está vazio ou indisponível no momento.")
else:
    st.subheader("✨ Nossos Produtos")
    cols = st.columns(4)
    for i, (prod_id, row) in enumerate(df_filtrado.iterrows()):
        with cols[i % 4]: render_product_card(prod_id, row, key_prefix='prod')

