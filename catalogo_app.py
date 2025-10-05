import streamlit as st
import pandas as pd
import gspread
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# =====================================================================================
# 1. CSS E CONFIGURAÇÃO VISUAL COMPLETA (INSPIRADO NOS SEUS ARQUIVOS)
# =====================================================================================
def inject_custom_css():
    st.markdown("""
        <style>
        /* ===== CONFIGURAÇÕES GLOBAIS ===== */
        /* Oculta menu padrão, footer e a decoração do topo */
        #MainMenu, footer, [data-testid="stDecoration"] {
            display: none !important;
            visibility: hidden !important;
        }
        .stApp {
            background-color: #FFFFFF; /* Fundo branco */
        }

        /* ===== HEADER CUSTOMIZADO ===== */
        .header-container {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 40px;
            background-color: #FFFFFF;
            border-bottom: 1px solid #e0e0e0;
            width: 100%;
        }
        .header-title {
            font-size: 1.5rem;
            font-weight: bold;
            color: #333;
        }

        /* ===== ESTILO DO CATÁLOGO DE PRODUTOS ===== */
        /* Card de Produto Individual */
        div[data-testid="stVerticalBlock"] [data-testid="stContainer"] {
            border: 1px solid #f0f0f0 !important;
            border-radius: 8px !important;
            padding: 1rem !important;
            transition: box-shadow 0.2s ease-in-out, transform 0.2s ease-in-out;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        div[data-testid="stVerticalBlock"] [data-testid="stContainer"]:hover {
            box-shadow: 0 8px 20px rgba(0,0,0,0.08);
            transform: translateY(-5px);
        }

        /* Imagem dentro do card */
        div[data-testid="stVerticalBlock"] [data-testid="stContainer"] img {
            border-radius: 4px;
            object-fit: contain;
            height: 180px;
            margin-bottom: 1rem;
        }

        /* Título do produto (negrito) */
        div[data-testid="stVerticalBlock"] [data-testid="stContainer"] p strong {
            font-size: 1rem; color: #333;
        }
        /* Preço do produto */
        div[data-testid="stVerticalBlock"] [data-testid="stContainer"] p:not(:has(strong)) {
            font-size: 1.1rem; font-weight: bold; color: #E91E63; margin-top: -10px;
        }
        
        /* Botão 'Comprar' (Popover) */
        div[data-testid="stVerticalBlock"] [data-testid="stContainer"] [data-testid="stPopover"] > button {
            background-color: #E91E63 !important; color: white !important;
            border: none !important; border-radius: 5px !important; width: 100% !important; font-weight: bold;
        }

        /* ===== ESTILO DO CARRINHO FLUTUANTE ===== */
        div[data-testid="stVerticalBlock"]:has(div[data-testid="stPopover"]):last-of-type {
            position: fixed; bottom: 30px; right: 30px; z-index: 1000;
        }
        div[data-testid="stPopover"] > button {
            background-color: #F06292 !important; color: white !important; border-radius: 50% !important;
            width: 60px !important; height: 60px !important; font-size: 28px !important;
            border: none !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }
        div[data-testid="stPopover"] > button::after {
            content: attr(data-badge); position: absolute; top: 0px; right: 0px;
            width: 25px; height: 25px; background-color: #E53935; color: white;
            border-radius: 50%; display: flex; justify-content: center; align-items: center;
            font-size: 14px; font-weight: bold; border: 2px solid white;
        }
        div[data-testid="stPopover"] div[data-testid="stPopup"] {
            width: 380px !important; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        </style>
    """, unsafe_allow_html=True)

# Configuração da página
st.set_page_config(layout="wide", page_title="Doce&Bella | Catálogo", page_icon="🌸")
inject_custom_css()

# =====================================================================================
# 2. LÓGICA DO APLICATIVO (FUNÇÕES DE DADOS E CARRINHO)
# =====================================================================================

# --- Inicialização do Estado ---
if 'carrinho' not in st.session_state: st.session_state.carrinho = []
if 'finalizando' not in st.session_state: st.session_state.finalizando = False
if 'pedido_enviado' not in st.session_state: st.session_state.pedido_enviado = False

# --- Funções de Carrinho ---
def adicionar_ao_carrinho(produto_id, nome, preco, quantidade):
    for item in st.session_state.carrinho:
        if item['id'] == produto_id:
            item['quantidade'] += quantidade; break
    else:
        st.session_state.carrinho.append({'id': produto_id, 'nome': nome, 'preco': preco, 'quantidade': quantidade})
def remover_do_carrinho(produto_id):
    st.session_state.carrinho = [item for item in st.session_state.carrinho if item['id'] != produto_id]
def limpar_carrinho():
    st.session_state.carrinho, st.session_state.finalizando, st.session_state.pedido_enviado = [], False, False
    st.rerun()

# --- Funções de Conexão e Carga de Dados (Google Sheets) ---
@st.cache_data(ttl=600)
def load_data():
    try:
        creds_json = {"type": st.secrets["gsheets"]["creds"]["type"], "project_id": st.secrets["gsheets"]["creds"]["project_id"], "private_key_id": st.secrets["gsheets"]["creds"]["private_key_id"], "private_key": st.secrets["gsheets"]["creds"]["private_key"], "client_email": st.secrets["gsheets"]["creds"]["client_email"], "client_id": st.secrets["gsheets"]["creds"]["client_id"], "auth_uri": st.secrets["gsheets"]["creds"]["auth_uri"], "token_uri": st.secrets["gsheets"]["creds"]["token_uri"], "auth_provider_x509_cert_url": st.secrets["gsheets"]["creds"]["auth_provider_x509_cert_url"], "client_x509_cert_url": st.secrets["gsheets"]["creds"]["client_x509_cert_url"]}
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_url(st.secrets["gsheets"]["sheets_url"])
        worksheet = spreadsheet.worksheet("produtos")
        data = worksheet.get_all_values()
        if not data: return pd.DataFrame(), client
        df = pd.DataFrame(data[1:], columns=data[0])
        if df.empty: return pd.DataFrame(), client

        def _normalize_header(s):
            s = str(s)
            s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
            return s.upper().strip()

        expected_map = {'ID': ['ID', 'CODIGO', 'SKU'], 'NOME': ['NOME', 'PRODUTO'], 'PRECO': ['PRECO', 'PREÇO', 'VALOR'], 'DISPONIVEL': ['DISPONIVEL', 'ATIVO'], 'LINKIMAGEM': ['LINKIMAGEM', 'IMAGEM', 'FOTO'], 'DESCRICAOCURTA': ['DESCRICAOCURTA'], 'DESCRICAOLONGA': ['DESCRICAOLONGA']}
        rename_cols = {}
        df_cols_normalized = {_normalize_header(c): c for c in df.columns}
        for std_name, variations in expected_map.items():
            for var in variations:
                if var in df_cols_normalized:
                    rename_cols[df_cols_normalized[var]] = std_name; break
        df.rename(columns=rename_cols, inplace=True)

        for required in ['ID', 'NOME', 'PRECO', 'DISPONIVEL']:
            if required not in df.columns: return pd.DataFrame(), client

        df['DISPONIVEL'] = df['DISPONIVEL'].apply(lambda v: str(v).strip().lower() in ('sim', 's', 'yes', 'y', 'true', '1', 'x'))
        df = df[df['DISPONIVEL'] == True].copy()
        df['PRECO'] = pd.to_numeric(df['PRECO'], errors='coerce').fillna(0)
        df['ID'] = df['ID'].astype(str)
        return df, client
    except Exception as e:
        st.error(f"Erro Crítico de Conexão: {e}")
        return pd.DataFrame(), None

df_produtos, gsheets_client = load_data()

# --- Função para Salvar Pedido ---
def salvar_pedido(nome, contato, pedido_df, total):
    if gsheets_client is None: return False
    try:
        relatorio = "; ".join([f"{row['Qtd']}x {row['Produto']}" for _, row in pedido_df.iterrows()])
        worksheet = gsheets_client.open_by_url(st.secrets["gsheets"]["pedidos_url"]).worksheet("Pedidos")
        worksheet.append_row([datetime.now().strftime("%d/%m/%Y %H:%M:%S"), nome, contato, f"{total:.2f}", relatorio])
        st.session_state.pedido_enviado = True
        return True
    except Exception as e:
        st.error(f"Erro ao salvar o pedido: {e}"); return False

# =====================================================================================
# 3. RENDERIZAÇÃO DAS PÁGINAS E ELEMENTOS
# =====================================================================================

# --- Header Customizado ---
st.markdown('<div class="header-container"><img src="https://i.ibb.co/cdqJ92W/logo_docebella.png" width=180><div class="header-title"></div></div>', unsafe_allow_html=True)

# --- Lógica de Exibição das Páginas ---
if st.session_state.pedido_enviado:
    st.balloons()
    st.success("🎉 Pedido Enviado com Sucesso!")
    if st.button("Fazer Novo Pedido"): limpar_carrinho()

elif st.session_state.finalizando:
    st.title("Finalizar Pedido")
    total_valor = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho)
    pedido_df = pd.DataFrame(st.session_state.carrinho).rename(columns={'nome': 'Produto', 'quantidade': 'Qtd'})
    with st.form("Formulario_Finalizacao"):
        nome = st.text_input("Seu Nome Completo:")
        contato = st.text_input("Seu WhatsApp ou E-mail:")
        st.dataframe(pedido_df[['Produto', 'Qtd']], use_container_width=True, hide_index=True)
        st.markdown(f"### Valor Final: R$ {total_valor:.2f}")
        if st.form_submit_button("✅ ENVIAR PEDIDO", type="primary"):
            if nome and contato:
                if salvar_pedido(nome, contato, pedido_df, total_valor): st.rerun()
            else:
                st.error("Por favor, preencha seu nome e contato.")
    if st.button("⬅️ Voltar ao Catálogo"): st.session_state.finalizando = False; st.rerun()

elif not df_produtos.empty:
    st.image("https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-queridinhos1.png", use_column_width=True)
    
    num_colunas = 4
    cols = st.columns(num_colunas)
    for index, row in df_produtos.iterrows():
        with cols[index % num_colunas]:
            with st.container(border=False):
                st.image(row.get('LINKIMAGEM') or "https://placehold.co/400x300/F0F0F0/AAAAAA?text=Sem+imagem", use_column_width=True)
                st.markdown(f"**{row.get('NOME', '')}**")
                st.markdown(f"R$ {row.get('PRECO', 0.0):.2f}")
                with st.popover("Comprar", use_container_width=True):
                    st.subheader(row.get('NOME'))
                    st.markdown(f"**Preço:** R$ {row.get('PRECO', 0.0):.2f}")
                    st.markdown(f"**Descrição:** {row.get('DESCRICAOLONGA', '')}")
                    qtd = st.number_input("Qtd:", 1, key=f"qty_{row.get('ID')}")
                    if st.button("➕ Adicionar", key=f"add_{row.get('ID')}"):
                        adicionar_ao_carrinho(row.get('ID'), row.get('NOME'), row.get('PRECO'), qtd); st.rerun()
else:
    st.info("Nenhum produto disponível no momento.")

# --- Renderiza o Carrinho Flutuante por último ---
total_itens = sum(item['quantidade'] for item in st.session_state.carrinho)
if not st.session_state.finalizando and not st.session_state.pedido_enviado:
    st.markdown(f'<div data-badge="{total_itens if total_itens > 0 else ""}"></div>', unsafe_allow_html=True)
    with st.popover("🛒", use_container_width=False):
        st.header("Meu Carrinho")
        if not st.session_state.carrinho:
            st.write("Seu carrinho está vazio.")
        else:
            total_valor = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho)
            for item in st.session_state.carrinho:
                c1, c2 = st.columns([0.8, 0.2])
                c1.text(f"{item['quantidade']}x {item['nome']}")
                if c2.button("🗑️", key=f"del_{item['id']}"):
                    remover_do_carrinho(item['id']); st.rerun()
            st.markdown(f"**Total:** R$ {total_valor:.2f}")
            if st.button("✅ Finalizar Pedido", type="primary"):
                st.session_state.finalizando = True; st.rerun()
