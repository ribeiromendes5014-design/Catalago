import streamlit as st
import pandas as pd
import gspread
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# =====================================================================================
# 1. CONFIGURAÇÃO E CSS MÍNIMO E ESTÁVEL
# =====================================================================================

st.set_page_config(layout="wide", page_title="Doce&Bella | Catálogo", page_icon="🌸")

# CSS focado APENAS no carrinho flutuante, que sabemos que funciona.
st.markdown("""
    <style>
        #MainMenu, footer, [data-testid="stHeader"] { display: none !important; }
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
    </style>
""", unsafe_allow_html=True)

# =====================================================================================
# 2. LÓGICA DO APLICATIVO (FUNÇÕES DE DADOS E CARRINHO)
# =====================================================================================

if 'carrinho' not in st.session_state: st.session_state.carrinho = []
if 'finalizando' not in st.session_state: st.session_state.finalizando = False
if 'pedido_enviado' not in st.session_state: st.session_state.pedido_enviado = False

def adicionar_ao_carrinho(prod_id, nome, preco, qtd):
    for item in st.session_state.carrinho:
        if item['id'] == prod_id: item['quantidade'] += qtd; break
    else: st.session_state.carrinho.append({'id': prod_id, 'nome': nome, 'preco': preco, 'quantidade': qtd})

def remover_do_carrinho(prod_id):
    st.session_state.carrinho = [item for item in st.session_state.carrinho if item['id'] != prod_id]

def limpar_carrinho():
    st.session_state.carrinho, st.session_state.finalizando, st.session_state.pedido_enviado = [], False, False
    st.rerun()

@st.cache_data(ttl=300)
def load_data():
    try:
        creds_json = st.secrets["gsheets"]["creds"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        worksheet = client.open_by_url(st.secrets["gsheets"]["sheets_url"]).worksheet("produtos")
        df = pd.DataFrame(worksheet.get_all_records())
        if df.empty: return pd.DataFrame(), None
        
        def _normalize(s): return unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('ASCII').upper().strip()
        df.columns = [_normalize(col) for col in df.columns]
        
        rename_map = {'PRODUTO': 'NOME', 'PRECO': 'PRECO', 'IMAGEM': 'LINKIMAGEM', 'DESCRICAO CURTA': 'DESCRICAOCURTA', 'DESCRICAO LONGA': 'DESCRICAOLONGA'}
        df.rename(columns=lambda c: rename_map.get(c, c), inplace=True)
        
        df = df[df['DISPONIVEL'].astype(str).str.lower().isin(['sim', 's', 'true', '1'])].copy()
        df['PRECO'] = pd.to_numeric(df['PRECO'], errors='coerce').fillna(0)
        df['ID'] = df['ID'].astype(str)
        return df, client
    except Exception as e:
        st.error(f"Erro ao carregar produtos: {e}"); return pd.DataFrame(), None

df_produtos, gsheets_client = load_data()

def salvar_pedido(nome, contato, pedido_df, total):
    if gsheets_client is None: return False
    try:
        relatorio = "; ".join([f"{row['Qtd']}x {row['Produto']}" for _, row in pedido_df.iterrows()])
        worksheet = gsheets_client.open_by_url(st.secrets["gsheets"]["pedidos_url"]).worksheet("Pedidos")
        worksheet.append_row([datetime.now().strftime("%d/%m/%Y %H:%M:%S"), nome, contato, f"{total:.2f}", relatorio])
        st.session_state.pedido_enviado = True; return True
    except Exception: return False

# =====================================================================================
# 3. RENDERIZAÇÃO DA PÁGINA
# =====================================================================================

# --- Header Centralizado (Sua excelente sugestão) ---
st.markdown("""
    <style>
        .centered-header {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .centered-header img {
            max-width: 220px;
            height: auto;
            margin-bottom: -10px;
        }
        .centered-header h1 {
            font-size: 2.5rem;
            color: #E91E63;
            text-align: center;
            font-weight: 700;
        }
    </style>
    <div class="centered-header">
        <img src="https://i.ibb.co/cdqJ92W/logo-docebella.png" alt="Logo Doce&Bella">
        <h1>💖 Nossos Produtos</h1>
    </div>
""", unsafe_allow_html=True)
st.divider()

# --- Lógica de Exibição de Conteúdo ---
if st.session_state.pedido_enviado:
    st.balloons()
    st.success("🎉 Pedido Enviado com Sucesso!", icon="✅")
    if st.button("🛍️ Fazer Novo Pedido"): limpar_carrinho()

elif st.session_state.finalizando:
    st.title("Finalizar Pedido")
    total = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho)
    pedido_df = pd.DataFrame(st.session_state.carrinho).rename(columns={'nome': 'Produto', 'quantidade': 'Qtd'})
    with st.form("Formulario_Finalizacao"):
        st.text_input("Seu Nome Completo:", key="nome_cliente")
        st.text_input("Seu WhatsApp ou E-mail:", key="contato_cliente")
        st.dataframe(pedido_df[['Produto', 'Qtd']], use_container_width=True, hide_index=True)
        st.markdown(f"### Valor Final: R$ {total:.2f}")
        if st.form_submit_button("ENVIAR PEDIDO", type="primary"):
            if st.session_state.nome_cliente and st.session_state.contato_cliente:
                if salvar_pedido(st.session_state.nome_cliente, st.session_state.contato_cliente, pedido_df, total): st.rerun()
                else: st.error("Falha ao salvar o pedido.")
            else: st.warning("Por favor, preencha nome e contato.")
    if st.button("⬅️ Voltar ao Catálogo"): st.session_state.finalizando = False; st.rerun()

elif not df_produtos.empty:
    num_colunas = 4
    cols = st.columns(num_colunas)
    for index, row in df_produtos.iterrows():
        with cols[index % num_colunas]:
            with st.container(border=True):
                st.image(row.get('LINKIMAGEM') or "https://placehold.co/400x300/F0F0F0/AAAAAA?text=Sem+imagem", use_container_width=True)
                st.markdown(f"**{row.get('NOME', '')}**")
                st.markdown(f"R$ {row.get('PRECO', 0.0):.2f}")
                with st.popover("Comprar", use_container_width=True):
                    st.subheader(row.get('NOME'))
                    st.markdown(f"**Descrição:** {row.get('DESCRICAOLONGA', 'Sem descrição adicional.')}")
                    qtd = st.number_input("Quantidade:", 1, key=f"qty_{row.get('ID')}")
                    if st.button("Adicionar", key=f"add_{row.get('ID')}", type="primary"):
                        adicionar_ao_carrinho(row.get('ID'), row.get('NOME'), row.get('PRECO'), qtd); st.rerun()
else:
    st.info("Nenhum produto disponível no momento.")

# --- Carrinho Flutuante (Renderizado por último) ---
total_itens = sum(item['quantidade'] for item in st.session_state.carrinho)
if not st.session_state.finalizando and not st.session_state.pedido_enviado:
    st.markdown(f'<div data-badge="{total_itens if total_itens > 0 else ""}"></div>', unsafe_allow_html=True)
    with st.popover("🛒", use_container_width=False):
        st.header("Meu Carrinho")
        if not st.session_state.carrinho: st.write("Seu carrinho está vazio.")
        else:
            total_valor = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho)
            for item in st.session_state.carrinho:
                c1, c2 = st.columns([0.8, 0.2])
                c1.text(f"{item['quantidade']}x {item['nome']}")
                if c2.button("🗑️", key=f"del_{item['id']}"): remover_do_carrinho(item['id']); st.rerun()
            st.markdown(f"**Total:** R$ {total_valor:.2f}")
            if st.button("Finalizar Pedido", type="primary"): st.session_state.finalizando = True; st.rerun()
