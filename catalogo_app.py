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
# **IMPORTANTE: SUBSTITUA ESTA URL PELO SEU LINK DIRETO DO ImgBB**
BACKGROUND_IMAGE_URL = 'https://images.unsplash.com/photo-1549480103-51152a12908f?fm=jpg&w=1000&auto=format&fit=crop&q=60&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8MTJ8fHBpbmt8ZW58MHx8MHx8fDA%3D'


# Inicialização do Carrinho de Compras e Estado
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {}  # {id_produto: {'nome': str, 'preco': float, 'quantidade': int}}

# --- Funções de Conexão GSpread (Mantidas e Corrigidas) ---

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
        st.error(f"Erro na autenticação do Google Sheets. Verifique o secrets.toml ou se o service account tem acesso à planilha. Detalhe: {e}")
        st.stop()

@st.cache_data(ttl=600)
def carregar_catalogo():
    """Carrega o catálogo de produtos (aba 'produtos') e prepara o DataFrame."""
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
        st.error(f"Erro ao carregar o catálogo: A aba com o nome '{SHEET_NAME_CATALOGO}' não foi encontrada na sua planilha.")
        st.info("Dica: Verifique se o nome da aba está escrito exatamente igual (minúsculas/maiúsculas).")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado ao carregar o catálogo: {e}")
        return pd.DataFrame()


# --- Funções salvar_pedido, adicionar/remover do carrinho (Mantidas) ---

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
            f"{valor_total:.2f}".replace('.', ',') # Salva com vírgula
        ]
        worksheet.append_row(novo_registro)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar o pedido: {e}")
        return False

def adicionar_ao_carrinho(produto_id, produto_nome, produto_preco):
    """Adiciona 1 unidade de um produto ao carrinho ou incrementa a quantidade se já existir."""
    if produto_id in st.session_state.carrinho:
        st.session_state.carrinho[produto_id]['quantidade'] += 1
    else:
        st.session_state.carrinho[produto_id] = {
            'nome': produto_nome,
            'preco': produto_preco,
            'quantidade': 1
        }
    st.toast(f"✅ {produto_nome} adicionado ao pedido!", icon="🛍️")
    time.sleep(0.1)

def remover_do_carrinho(produto_id):
    if produto_id in st.session_state.carrinho:
        nome = st.session_state.carrinho[produto_id]['nome']
        del st.session_state.carrinho[produto_id]
        st.toast(f"❌ {nome} removido do pedido.", icon="🗑️")

def render_product_image(link_imagem):
    """Renderiza a imagem do produto ou um placeholder."""
    placeholder_html = """
        <div style="background-color: #f0f0f0; border-radius: 4px; height: 200px; display: flex; align-items: center; justify-content: center; text-align: center; color: #a0a0a0; font-size: 1.2rem; font-weight: bold;">
            Sem Imagem
        </div>
    """
    if link_imagem and str(link_imagem).strip().startswith('http'):
        st.image(link_imagem, use_column_width="always")
    else:
        st.markdown(placeholder_html, unsafe_allow_html=True)


# --- Layout do Aplicativo ---

st.set_page_config(
    page_title="Catálogo Doce&Bella",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# -----------------------------------
# CSS (Fundo, Carrinho e Botão Adicionar)
# -----------------------------------
st.markdown(f"""
<style>
/* 1. BACKGROUND PERSONALIZADO */
.stApp {{
    background-image: url({BACKGROUND_IMAGE_URL}) !important;
    background-size: cover !important;
    background-attachment: fixed !important;
    background-position: center !important;
}}

/* 2. CONTEÚDO PRINCIPAL COM FUNDO BRANCO */
div.block-container {{
    background-color: rgba(255, 255, 255, 0.95);
    border-radius: 10px;
    padding: 2rem;
    margin-top: 1rem;
}}

/* 3. BARRA ROSA SUPERIOR */
.pink-bar-container {{
    background-color: #E91E63;
    padding: 20px 0;
    width: 100vw;
    position: relative;
    left: 50%;
    right: 50%;
    margin-left: -50vw;
    margin-right: -50vw;
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

/* 4. BOTÃO FLUTUANTE DO CARRINHO */
div[data-testid="stPopover"] > div:first-child > button {{
    display: none;
}}

.cart-badge-button {{
    background-color: #C2185B;
    color: white;
    border-radius: 12px;
    padding: 8px 15px;
    font-size: 16px;
    font-weight: bold;
    cursor: pointer;
    border: none;
    transition: background-color 0.3s;
    display: inline-flex;
    align-items: center;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    min-width: 150px;
    justify-content: center;
}}

.cart-badge-button:hover {{ background-color: #E91E63; }}

.cart-count {{
    background-color: white;
    color: #E91E63;
    border-radius: 50%;
    padding: 2px 7px;
    margin-left: 8px;
    font-size: 14px;
    line-height: 1;
}}

/* 5. NOVO ESTILO PARA O BOTÃO "ADICIONAR" */
div[data-testid="stButton"] > button {{
    background-color: #E91E63;
    color: white;
    border-radius: 10px;
    border: 1px solid #C2185B;
    font-weight: bold;
}}
div[data-testid="stButton"] > button:hover {{
    background-color: #C2185B;
    color: white;
    border: 1px solid #E91E63;
}}

</style>
""", unsafe_allow_html=True)


# --- 1. CABEÇALHO PRINCIPAL ---

col_logo, col_titulo = st.columns([0.1, 5])
with col_logo:
    st.markdown("<h3>💖</h3>", unsafe_allow_html=True)
with col_titulo:
    st.title("Catálogo de Pedidos Doce&Bella")

# 2. Lógica do Carrinho
total_acumulado = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho.values())
num_itens = sum(item['quantidade'] for item in st.session_state.carrinho.values())
carrinho_vazio = not st.session_state.carrinho

# 3. BARRA ROSA (PESQUISA E CARRINHO)
st.markdown("<div class='pink-bar-container'>", unsafe_allow_html=True)
st.markdown("<div class='pink-bar-content'>", unsafe_allow_html=True)

col_pesquisa, col_carrinho = st.columns([5, 1])

with col_pesquisa:
    termo_pesquisa = st.text_input("Buscar produtos...",
                                   key='termo_pesquisa_barra',
                                   label_visibility="collapsed",
                                   placeholder="Buscar produtos...")

with col_carrinho:
    custom_cart_button = f"""
        <div class='cart-badge-button' onclick='document.querySelector("[data-testid=\"stPopover\"] > div:first-child > button").click();'>
            🛒 SEU PEDIDO
            <span class='cart-count'>{num_itens}</span>
        </div>
    """
    st.markdown(custom_cart_button, unsafe_allow_html=True)

    with st.popover(" ", use_container_width=False, help="Clique para ver os itens e finalizar o pedido"):
        st.header("🛒 Detalhes do Seu Pedido")

        if carrinho_vazio:
            st.info("Seu carrinho está vazio. Adicione itens do catálogo!")
        else:
            st.markdown(f"<h3 style='color: #E91E63; margin-top: 0;'>Total: R$ {total_acumulado:.2f}</h3>", unsafe_allow_html=True)
            st.markdown("---")

            for prod_id, item in list(st.session_state.carrinho.items()):
                col_nome, col_qtd, col_preco, col_remover = st.columns([3, 1.5, 2, 1])
                col_nome.write(f"*{item['nome']}*")
                col_qtd.markdown(f"**{item['quantidade']}x**")
                col_preco.markdown(f"R$ {item['preco'] * item['quantidade']:.2f}")

                if col_remover.button("X", key=f'rem_{prod_id}_popover', help=f"Remover {item['nome']}"):
                    remover_do_carrinho(prod_id)
                    st.rerun()

            st.markdown("---")

            with st.form("form_finalizar_pedido_popover", clear_on_submit=True):
                st.subheader("Finalizar Pedido")
                nome = st.text_input("Seu Nome Completo:", key='nome_cliente_popover')
                contato = st.text_input("Seu Contato (WhatsApp/E-mail):", key='contato_cliente_popover')
                submitted = st.form_submit_button("✅ Enviar Pedido", type="primary", use_container_width=True)

                if submitted:
                    if not nome or not contato:
                        st.warning("Por favor, preencha seu nome e contato para finalizar.")
                    else:
                        detalhes_pedido = {
                            "total": total_acumulado,
                            "itens": [
                                {"id": int(prod_id), "nome": item['nome'], "preco": item['preco'], "qtd": item['quantidade'], "subtotal": item['preco'] * item['quantidade']}
                                for prod_id, item in st.session_state.carrinho.items()
                            ]
                        }
                        if salvar_pedido(nome, contato, total_acumulado, json.dumps(detalhes_pedido, ensure_ascii=False)):
                            st.balloons()
                            st.success("🎉 Pedido enviado com sucesso! Entraremos em contato em breve.")
                            st.session_state.carrinho = {}
                            st.rerun()
                        else:
                            st.error("Falha ao salvar o pedido. Tente novamente.")

st.markdown("</div></div>", unsafe_allow_html=True)


# --- 4. SEÇÃO DE PRODUTOS ---
st.markdown("---")

df_catalogo = carregar_catalogo()

# Função para renderizar um único produto (evita repetição de código)
def render_product_card(prod_id, row, key_prefix):
    with st.container(border=True):
        render_product_image(row.get('LINKIMAGEM'))
        st.markdown(f"**{row['NOME']}**")
        st.caption(row.get('DESCRICAOCURTA', ''))

        # Expander para detalhes longos
        with st.expander("Ver detalhes"):
            st.markdown(row.get('DESCRICAOLONGA', 'Sem descrição detalhada.'))

        # Colunas para Preço e Botão Adicionar
        col_preco, col_botao = st.columns([2, 2])

        with col_preco:
            st.markdown(f"<h4 style='color: #880E4F; margin:0; line-height:2.5;'>R$ {row['PRECO']:.2f}</h4>", unsafe_allow_html=True)

        with col_botao:
            if st.button("➕ Adicionar", key=f'{key_prefix}_{prod_id}', use_container_width=True):
                adicionar_ao_carrinho(prod_id, row['NOME'], row['PRECO'])
                st.rerun()

# Filtragem por pesquisa
df_filtrado = df_catalogo.copy()
if 'termo_pesquisa_barra' in st.session_state and st.session_state.termo_pesquisa_barra:
    termo = st.session_state.termo_pesquisa_barra.lower()
    df_filtrado = df_filtrado[
        df_filtrado['NOME'].astype(str).str.lower().str.contains(termo) |
        df_filtrado['DESCRICAOLONGA'].astype(str).str.lower().str.contains(termo)
    ]

# Renderização dos produtos
if df_filtrado.empty:
    if 'termo_pesquisa_barra' in st.session_state and st.session_state.termo_pesquisa_barra:
        st.info(f"Nenhum produto encontrado com o termo '{st.session_state.termo_pesquisa_barra}'.")
    else:
        st.warning("O catálogo está vazio ou indisponível no momento. Tente novamente mais tarde.")
else:
    st.subheader("✨ Nossos Produtos")
    cols_per_row = 3
    cols = st.columns(cols_per_row)

    for i, (prod_id, row) in enumerate(df_filtrado.iterrows()):
        col = cols[i % cols_per_row]
        with col:
            render_product_card(prod_id, row, key_prefix='prod')
