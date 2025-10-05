# catalogo_app.py
import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials 
from io import StringIO 
import time

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "produtos" 
SHEET_NAME_PEDIDOS = "PEDIDOS"
# **IMPORTANTE: SUBSTITUA ESTA URL PELO SEU LINK DIRETO DO ImgBB**
BACKGROUND_IMAGE_URL = 'https://images.unsplash.com/photo-1549480103-51152a12908f?fm=jpg&w=1000&auto=format&fit=crop&q=60&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8MTJ8fHBpbmt8ZW58MHx8MHx8fDA%3D' 


# Inicialização do Carrinho de Compras e Estado
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {} 

# --- Funções de Conexão GSpread (Mantidas) ---

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
            "client_x509_cert_url": st.secrets["googleapis.com"]
        }
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(gcp_sa_credentials, scope)
        client = gspread.authorize(creds)
        sh = client.open_by_url(st.secrets["gsheets"]["sheet_url"])
        return sh
    except Exception as e:
        st.error("Erro na autenticação do Google Sheets. Verifique o secrets.toml ou se o service account tem acesso à planilha.")
        st.stop()
        
@st.cache_data(ttl=600)
def carregar_catalogo():
    """Carrega o catálogo de produtos (aba 'produtos') e prepara o DataFrame."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_CATALOGO)
        data = worksheet.get_all_values()
        if data:
            df = pd.DataFrame(data[1:], columns=data[0]) 
        else:
            return pd.DataFrame()
        df['PRECO'] = pd.to_numeric(df['PRECO'], errors='coerce').fillna(0.0)
        df['ID'] = pd.to_numeric(df['ID'], errors='coerce').astype('Int64')
        df_filtrado = df[df['DISPONIVEL'].astype(str).str.lower() == 'sim'].copy()
        return df_filtrado.set_index('ID')
    except Exception as e:
        st.error(f"Erro ao carregar o catálogo: {e}")
        st.error(f"Dica: Verifique se o nome da aba da planilha está correto: '{SHEET_NAME_CATALOGO}'")
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
        st.toast(f"✅ {quantidade}x {produto_nome} adicionado(s) ao pedido!", icon="🛍️")
        time.sleep(0.1) 

def remover_do_carrinho(produto_id):
    if produto_id in st.session_state.carrinho:
        nome = st.session_state.carrinho[produto_id]['nome']
        del st.session_state.carrinho[produto_id]
        st.toast(f"❌ {nome} removido do pedido.", icon="🗑️")


# --- Layout do Aplicativo ---

st.set_page_config(
    page_title="Catálogo Doce&Bella", 
    layout="wide", 
    initial_sidebar_state="collapsed" 
)

# -----------------------------------
# NOVO: CSS de Fundo e Carrinho
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

/* Cor de Fundo para o conteúdo principal ficar legível */
div.block-container {{
    background-color: rgba(255, 255, 255, 0.95);
    border-radius: 10px;
    padding: 2rem;
    margin-top: 1rem;
}}

/* Força a barra rosa a ocupar a largura total (CORREÇÃO DE LAYOUT) */
.pink-bar-container {{
    background-color: #E91E63; 
    padding: 20px 0; /* Aumenta a altura */
    width: 100vw; /* Garante 100% da viewport width */
    position: relative;
    left: 50%;
    right: 50%;
    margin-left: -50vw; /* Truque para centralizar e expandir a div */
    margin-right: -50vw;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}}

/* Alinha o conteúdo interno da barra rosa */
.pink-bar-content {{
    width: 100%;
    max-width: 1200px; /* Limita a largura do conteúdo interno */
    margin: 0 auto; /* Centraliza o conteúdo */
    padding: 0 2rem; /* Adiciona padding lateral */
    display: flex;
    align-items: center;
}}

/* 2. ESTILO DO CARRINHO (Mantido) */
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

.cart-badge-button:hover {{
    background-color: #E91E63; 
}}

.cart-count {{
    background-color: white;
    color: #E91E63;
    border-radius: 50%;
    padding: 2px 7px;
    margin-left: 8px;
    font-size: 14px;
    line-height: 1;
}}
/* Estilo para botão de detalhes */
.btn-detalhes {{
    background-color: #fce4ec; /* Rosa claro para o botão de detalhes */
    color: #E91E63;
    border-radius: 8px;
    font-weight: bold;
}}
</style>
""", unsafe_allow_html=True)


# --- 1. CABEÇALHO PRINCIPAL (Título e Logotipo) ---

col_logo, col_titulo = st.columns([0.1, 5])
with col_logo:
    st.markdown("<h3>💖</h3>", unsafe_allow_html=True)
with col_titulo:
    st.title("Catálogo de Pedidos Doce&Bella")

# 2. Lógica do Carrinho
total_acumulado = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho.values())
num_itens = sum(item['quantidade'] for item in st.session_state.carrinho.values())
carrinho_vazio = not st.session_state.carrinho

# 3. BARRA ROSA (PESQUISA E CARRINHO) - ENVELOPADA PARA COBRIR A TELA

st.markdown("<div class='pink-bar-container'>", unsafe_allow_html=True)
st.markdown("<div class='pink-bar-content'>", unsafe_allow_html=True) # Alinha o conteúdo

# Colunas dentro da barra rosa: Pesquisa e Carrinho
col_pesquisa, col_carrinho = st.columns([5, 1])

# LÓGICA DE PESQUISA
with col_pesquisa:
    termo_pesquisa = st.text_input("Buscar produtos...", 
                                   key='termo_pesquisa_barra', 
                                   label_visibility="collapsed",
                                   placeholder="Buscar produtos...")

# LÓGICA DO BOTÃO DO CARRINHO
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
            
            for prod_id, item in st.session_state.carrinho.items():
                col_nome, col_qtd, col_preco, col_remover = st.columns([3, 1.5, 2, 1])
                col_nome.write(f"*{item['nome']}*")
                col_qtd.markdown(f"**{item['quantidade']}x**")
                col_preco.markdown(f"R$ {item['preco'] * item['quantidade']:.2f}")

                if col_remover.button("X", key=f'rem_{prod_id}_popover', help=f"Remover {item['nome']}"):
                    remover_do_carrinho(prod_id)
                    st.rerun()
                    
            st.markdown("---")
            
            st.subheader("Finalizar Pedido")
            with st.form("form_finalizar_pedido_popover", clear_on_submit=True):
                nome = st.text_input("Seu Nome Completo:", key='nome_cliente_popover')
                contato = st.text_input("Seu Contato (WhatsApp/E-mail):", key='contato_cliente_popover')
                
                submitted = st.form_submit_button("✅ Enviar Pedido", type="primary", use_container_width=True)
                
                if submitted:
                    if not nome or not contato:
                        st.error("Por favor, preencha seu nome e contato para finalizar.")
                    else:
                        detalhes_pedido = {
                            "total": total_acumulado,
                            "itens": [
                                {"id": int(prod_id), "nome": item['nome'], "preco": item['preco'], "qtd": item['quantidade'], "subtotal": item['preco'] * item['quantidade']} 
                                for prod_id, item in st.session_state.carrinho.items()
                            ]
                        }
                        if salvar_pedido(nome, contato, total_acumulado, json.dumps(detalhes_pedido)):
                            st.balloons() 
                            st.success("🎉 Pedido enviado com sucesso! Entraremos em contato em breve para combinar o pagamento e a entrega.")
                            st.session_state.carrinho = {} 
                            st.rerun()
                        else:
                            st.error("Falha ao salvar o pedido. Tente novamente.")

st.markdown("</div>", unsafe_allow_html=True) # Fecha a div pink-bar-content
st.markdown("</div>", unsafe_allow_html=True) # Fecha a div pink-bar-container


# --- 3. SEÇÃO DE PRODUTOS EM DESTAQUE ---
st.markdown("---")

df_catalogo = carregar_catalogo()
if df_catalogo.empty:
    st.warning("O catálogo está vazio.")
    st.stop()

# Filtra Destaque (os 3 primeiros)
df_destaque = df_catalogo.head(3) 

if not df_destaque.empty:
    st.subheader("✨ Produtos em Destaque")
    cols_destaque = st.columns(3)

    for i, (prod_id, row) in enumerate(df_destaque.iterrows()):
        if i < 3:
            with cols_destaque[i]:
                with st.container(border=True):
                    st.markdown(f"**{row['NOME']}**", unsafe_allow_html=True)
                    st.markdown(f"<h4 style='color: #880E4F;'>R$ {row['PRECO']:.2f}</h4>", unsafe_allow_html=True)
                    if row['LINKIMAGEM']: 
                        try:
                            st.image(row['LINKIMAGEM'], use_column_width="always")
                        except:
                            st.markdown("*(Erro ao carregar imagem)*")
                    st.caption(row['DESCRICAOCURTA'])
                    
                    # NOVO: Botão de Detalhes
                    with st.popover("✨ Detalhes", use_container_width=True):
                        st.markdown(f"### {row['NOME']}")
                        st.markdown(row['DESCRICAOLONGA'])
                        st.markdown("---")
                        
                        quantidade_inicial = st.session_state.carrinho.get(prod_id, {}).get('quantidade', 1)
                        quantidade = st.number_input("Quantidade:", min_value=1, step=1, key=f'qtd_destaque_{prod_id}', value=quantidade_inicial)
                        
                        if st.button("➕ Adicionar ao Pedido", key=f'add_detalhes_destaque_{prod_id}', type="primary", use_container_width=True):
                            adicionar_ao_carrinho(prod_id, quantidade, row['NOME'], row['PRECO'])
                            st.rerun() 

    st.markdown("---")


# --- 4. EXIBIÇÃO DO CATÁLOGO GERAL (Filtrado pela Pesquisa) ---

st.subheader("🛍️ Todos os Produtos")

df_geral = df_catalogo.copy()

# Lógica de Filtragem (agora baseada no termo_pesquisa global)
if 'termo_pesquisa_barra' in st.session_state and st.session_state.termo_pesquisa_barra:
    termo = st.session_state.termo_pesquisa_barra.lower()
    df_geral = df_geral[
        df_geral['NOME'].astype(str).str.lower().str.contains(termo) |
        df_geral['DESCRICAOCURTA'].astype(str).str.lower().str.contains(termo) |
        df_geral['DESCRICAOLONGA'].astype(str).str.lower().str.contains(termo)
    ]
    
if df_geral.empty:
    st.info(f"Nenhum produto encontrado com o termo '{st.session_state.termo_pesquisa_barra}'." if 'termo_pesquisa_barra' in st.session_state else "Nenhum produto.")
else:
    cols_per_row = 3
    cols_geral = st.columns(cols_per_row) 

    for i, (prod_id, row) in enumerate(df_geral.iterrows()):
        col = cols_geral[i % cols_per_row]
        
        with col:
            with st.container(border=True):
                
                st.markdown(f"**{row['NOME']}**", unsafe_allow_html=True)
                st.markdown(f"<h3 style='color: #E91E63; margin-top: 0;'>R$ {row['PRECO']:.2f}</h3>", unsafe_allow_html=True)

                if row['LINKIMAGEM']:
                    try:
                        st.image(row['LINKIMAGEM'], use_column_width="always")
                    except:
                        st.markdown("*(Erro ao carregar imagem)*")
                else:
                    st.markdown("*(Sem Imagem)*")
                
                st.caption(row['DESCRICAOCURTA'])
                
                # NOVO: Botão de Detalhes
                with st.popover("✨ Detalhes", use_container_width=True):
                    st.markdown(f"### {row['NOME']}")
                    st.markdown(row['DESCRICAOLONGA'])
                    st.markdown("---")
                    
                    quantidade_inicial = st.session_state.carrinho.get(prod_id, {}).get('quantidade', 1)
                    quantidade = st.number_input("Quantidade:", min_value=1, step=1, key=f'qtd_geral_{prod_id}', value=quantidade_inicial)
                    
                    if st.button("➕ Adicionar ao Pedido", key=f'add_detalhes_geral_{prod_id}', type="primary", use_container_width=True):
                        adicionar_ao_carrinho(prod_id, quantidade, row['NOME'], row['PRECO'])
                        st.rerun()
