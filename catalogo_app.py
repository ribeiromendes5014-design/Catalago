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
# **IMPORTANTE: SUBSTITUA ESTA URL PELO SEU LINK DIRETO DA IMAGEM DE FUNDO**
BACKGROUND_IMAGE_URL = 'https://images.unsplash.com/photo-1549480103-51152a12908f?fm=jpg&w=1000&auto=format&fit=crop&q=60&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8MTJ8fHBpbmt8ZW58MHx8MHx8fDA%3D'


# Inicialização do Carrinho de Compras e Estado
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {} # {id_produto: {'nome': str, 'preco': float, 'quantidade': int}}

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
            "client_x509_cert_url": st.secrets["gsheets"]["client_x509_cert_url"],
            "universe_domain": st.secrets["gsheets"].get("universe_domain", "googleapis.com")
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
    """Carrega o catálogo de produtos (aba 'produtos') e prepara o DataFrame."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_CATALOGO)
        data = worksheet.get_all_values()
        if data and len(data) > 1:
            df = pd.DataFrame(data[1:], columns=data[0])
        else:
            return pd.DataFrame()
        df['PRECO'] = pd.to_numeric(df['PRECO'].str.replace(',', '.'), errors='coerce').fillna(0.0)
        df['ID'] = pd.to_numeric(df['ID'], errors='coerce').astype('Int64')
        df_filtrado = df[df['DISPONIVEL'].astype(str).str.strip().str.lower() == 'sim'].copy()
        return df_filtrado.set_index('ID')
    except Exception as e:
        st.error(f"Erro ao carregar o catálogo: {e}")
        st.error(f"Dica: Verifique se o nome da aba da planilha está correto: '{SHEET_NAME_CATALOGO}'")
        return pd.DataFrame()

# --- Funções de Lógica do Carrinho e Pedidos ---

def salvar_pedido(nome_cliente: str, contato_cliente: str, valor_total: float, itens_json: str):
    """Salva um novo pedido na planilha de PEDIDOS."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_PEDIDOS)
        novo_registro = [
            int(datetime.now().timestamp()),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            nome_cliente,
            contato_cliente,
            itens_json,
            f"{valor_total:.2f}"
        ]
        worksheet.append_row(novo_registro)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar o pedido: {e}")
        return False

def adicionar_ao_carrinho(produto_id, quantidade, produto_nome, produto_preco):
    if quantidade > 0:
        st.session_state.carrinho[produto_id] = {
            'nome': produto_nome,
            'preco': produto_preco,
            'quantidade': quantidade
        }
        st.toast(f"✅ {quantidade}x {produto_nome} adicionado(s)!", icon="🛍️")
        time.sleep(0.1)

def remover_do_carrinho(produto_id):
    if produto_id in st.session_state.carrinho:
        nome = st.session_state.carrinho[produto_id]['nome']
        del st.session_state.carrinho[produto_id]
        st.toast(f"❌ {nome} removido do pedido.", icon="🗑️")

def render_product_image(link_imagem):
    """Renderiza a imagem do produto ou um placeholder elegante."""
    placeholder_html = """
        <div style="background-color: #f0f0f0; border-radius: 4px; height: 200px; display: flex; align-items: center; justify-content: center;">
            <p style="color: #a0a0a0; font-size: 1.1rem; font-weight: bold;">Sem Imagem</p>
        </div>
    """
    if link_imagem and str(link_imagem).strip():
        try:
            st.image(link_imagem, use_column_width="always")
        except Exception:
            st.markdown(placeholder_html, unsafe_allow_html=True)
    else:
        st.markdown(placeholder_html, unsafe_allow_html=True)

# --- Layout do Aplicativo ---

st.set_page_config(
    page_title="Catálogo Doce&Bella",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS Customizado ---
st.markdown(f"""
<style>
/* 1. BACKGROUND */
.stApp {{
    background-image: url({BACKGROUND_IMAGE_URL});
    background-size: cover;
    background-attachment: fixed;
    background-position: center;
}}
/* 2. CONTAINER PRINCIPAL */
div.block-container {{
    background-color: rgba(255, 255, 255, 0.95);
    border-radius: 10px;
    padding: 2rem;
    margin-top: 1rem;
}}
/* 3. BARRA ROSA SUPERIOR */
.pink-bar-container {{
    background-color: #E91E63;
    padding: 10px 0;
    width: 100vw;
    position: relative;
    left: 50%; right: 50%;
    margin-left: -50vw; margin-right: -50vw;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}}
.pink-bar-content {{
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 2rem;
    display: flex;
    align-items: center;
}}
/* 4. BOTÃO DO CARRINHO */
div[data-testid="stPopover"] > div:first-child > button {{ display: none; }}
.cart-badge-button {{
    background-color: #C2185B; color: white; border-radius: 12px;
    padding: 8px 15px; font-size: 16px; font-weight: bold; cursor: pointer;
    border: none; transition: background-color 0.3s; display: inline-flex;
    align-items: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    min-width: 150px; justify-content: center;
}}
.cart-badge-button:hover {{ background-color: #E91E63; }}
.cart-count {{
    background-color: white; color: #E91E63; border-radius: 50%;
    padding: 2px 7px; margin-left: 8px; font-size: 14px; line-height: 1;
}}
/* 5. ESTILO BOTÕES DOS PRODUTOS */
.stButton>button {{
    border-radius: 8px;
    width: 100%;
}}
</style>
""", unsafe_allow_html=True)

# --- 1. CABEÇALHO ---
col_logo, col_titulo = st.columns([0.1, 5])
with col_logo:
    st.markdown("<h3>💖</h3>", unsafe_allow_html=True)
with col_titulo:
    st.title("Catálogo de Pedidos Doce&Bella")

# --- 2. LÓGICA DO CARRINHO ---
total_acumulado = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho.values())
num_itens = sum(item['quantidade'] for item in st.session_state.carrinho.values())
carrinho_vazio = not st.session_state.carrinho

# --- 3. BARRA ROSA (PESQUISA E CARRINHO) ---
st.markdown("<div class='pink-bar-container'><div class='pink-bar-content'>", unsafe_allow_html=True)
col_pesquisa, col_carrinho = st.columns([4, 1])

with col_pesquisa:
    termo_pesquisa = st.text_input("Buscar...", key='termo_pesquisa_barra', label_visibility="collapsed", placeholder="Buscar produtos...")

with col_carrinho:
    custom_cart_button = f"""
        <div class='cart-badge-button' onclick='document.querySelector("[data-testid=\"stPopover\"] > div:first-child > button").click();'>
            🛒 SEU PEDIDO <span class='cart-count'>{num_itens}</span>
        </div>
    """
    st.markdown(custom_cart_button, unsafe_allow_html=True)

    with st.popover(" ", use_container_width=False):
        st.header("🛒 Detalhes do Seu Pedido")
        if carrinho_vazio:
            st.info("Seu carrinho está vazio.")
        else:
            st.markdown(f"<h3 style='color: #E91E63; margin-top: 0;'>Total: R$ {total_acumulado:.2f}</h3>", unsafe_allow_html=True)
            st.markdown("---")
            for prod_id, item in st.session_state.carrinho.items():
                c1, c2, c3, c4 = st.columns([3, 1.5, 2, 1])
                c1.write(f"*{item['nome']}*")
                c2.markdown(f"**{item['quantidade']}x**")
                c3.markdown(f"R$ {item['preco'] * item['quantidade']:.2f}")
                if c4.button("X", key=f'rem_{prod_id}_popover', help=f"Remover {item['nome']}"):
                    remover_do_carrinho(prod_id)
                    st.rerun()

            st.markdown("---")
            with st.form("form_finalizar_pedido_popover", clear_on_submit=True):
                nome = st.text_input("Seu Nome Completo:", key='nome_cliente')
                contato = st.text_input("Seu Contato (WhatsApp/E-mail):", key='contato_cliente')
                if st.form_submit_button("✅ Enviar Pedido", type="primary", use_container_width=True):
                    if not nome or not contato:
                        st.error("Por favor, preencha seu nome e contato.")
                    else:
                        detalhes_pedido = {"total": total_acumulado, "itens": [{"id": int(k), **v} for k, v in st.session_state.carrinho.items()]}
                        if salvar_pedido(nome, contato, total_acumulado, json.dumps(detalhes_pedido, ensure_ascii=False)):
                            st.balloons()
                            st.success("🎉 Pedido enviado com sucesso!")
                            st.session_state.carrinho = {}
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Falha ao salvar o pedido. Tente novamente.")
st.markdown("</div></div>", unsafe_allow_html=True)


# --- 4. EXIBIÇÃO DOS PRODUTOS ---
df_catalogo = carregar_catalogo()
if df_catalogo.empty:
    st.warning("O catálogo está vazio ou indisponível no momento. Tente novamente mais tarde.")
    st.stop()

# Lógica de Filtragem pela barra de pesquisa
df_filtrado = df_catalogo.copy()
if termo_pesquisa:
    termo = termo_pesquisa.lower()
    df_filtrado = df_catalogo[
        df_catalogo['NOME'].str.lower().str.contains(termo) |
        df_catalogo['DESCRICAOCURTA'].str.lower().str.contains(termo) |
        df_catalogo['DESCRICAOLONGA'].str.lower().str.contains(termo)
    ]

st.markdown("<br>", unsafe_allow_html=True)
st.subheader("🛍️ Nossos Produtos")
st.markdown("---")

if df_filtrado.empty:
    st.info(f"Nenhum produto encontrado com o termo '{termo_pesquisa}'.")
else:
    cols_per_row = 3
    cols = st.columns(cols_per_row)
    for i, (prod_id, row) in enumerate(df_filtrado.iterrows()):
        col = cols[i % cols_per_row]
        with col:
            with st.container(border=True):
                render_product_image(row.get('LINKIMAGEM'))
                st.markdown(f"**{row['NOME']}**")
                st.markdown(f"<h4 style='color: #E91E63; margin-top: 0;'>R$ {row['PRECO']:.2f}</h4>", unsafe_allow_html=True)
                st.caption(row['DESCRICAOCURTA'])

                # --- BOTÕES DE AÇÃO CORRIGIDOS ---
                col_det, col_add = st.columns(2)

                # Botão para Ver Detalhes (abre o popover)
                with col_det:
                    with st.popover("🔍 Detalhes", use_container_width=True):
                        st.markdown(f"### {row['NOME']}")
                        st.markdown(row['DESCRICAOLONGA'])
                        st.markdown("---")
                        q_inicial = st.session_state.carrinho.get(prod_id, {}).get('quantidade', 1)
                        q = st.number_input("Quantidade:", min_value=1, step=1, key=f'qtd_{prod_id}', value=q_inicial)
                        if st.button("Adicionar", key=f'add_pop_{prod_id}', type="primary", use_container_width=True):
                            adicionar_ao_carrinho(prod_id, q, row['NOME'], row['PRECO'])
                            st.rerun()

                # Botão para Adicionar Rápido
                with col_add:
                    if st.button("➕ Add Pedido", key=f'add_card_{prod_id}', help="Adiciona 1 unidade ao pedido"):
                        adicionar_ao_carrinho(prod_id, 1, row['NOME'], row['PRECO'])
                        st.rerun()

            # Adiciona espaço vertical entre os cards
            st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)
