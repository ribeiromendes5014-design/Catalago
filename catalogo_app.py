import streamlit as st
import pandas as pd
import gspread
import math
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- FUNÇÃO PARA INJETAR CSS ---
def local_css(css_code):
    st.markdown(f'<style>{css_code}</style>', unsafe_allow_html=True)

# CSS para o novo ícone de carrinho flutuante e painel
local_css("""
    /* Oculta a barra lateral padrão */
    section[data-testid="stSidebar"] {
        display: none;
    }

    /* Contêiner que segura o botão do popover para posicioná-lo */
    div[data-testid="stVerticalBlock"]:has(div[data-testid="stPopover"]):last-of-type {
        position: fixed;
        bottom: 30px;
        right: 30px;
        z-index: 1000;
    }
    
    /* Estilo do novo botão de ícone flutuante */
    div[data-testid="stPopover"] > button {
        background-color: #F06292 !important; /* Cor Rosa */
        color: white !important;
        border-radius: 50% !important; /* Círculo */
        width: 60px !important;
        height: 60px !important;
        font-size: 28px !important; /* Tamanho do ícone de carrinho */
        border: none !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }

    /* Badge (notificação) com o número de itens */
    div[data-testid="stPopover"] > button::after {
        content: attr(data-badge); /* Pega o número do atributo 'data-badge' */
        position: absolute;
        top: 0px;
        right: 0px;
        width: 25px;
        height: 25px;
        background-color: #E53935; /* Vermelho */
        color: white;
        border-radius: 50%;
        display: flex;
        justify-content: center;
        align-items: center;
        font-size: 14px;
        font-weight: bold;
        border: 2px solid white;
    }

    /* Estilo do painel do carrinho que abre */
    div[data-testid="stPopover"] div[data-testid="stPopup"] {
        width: 380px !important;
        border-radius: 10px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    }
""")

# --- 1. Configuração da Página e Inicialização do Carrinho ---
st.set_page_config(
    page_title="Catálogo de Produtos | Doce&Bella",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Inicializa o carrinho na memória (session_state) se ele ainda não existir
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = []
if 'finalizando' not in st.session_state:
    st.session_state.finalizando = False
if 'pedido_enviado' not in st.session_state:
    st.session_state.pedido_enviado = False

# --- Helpers ---
def _normalize_header(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize('NFKD', s)
    s = s.encode('ASCII', 'ignore').decode('ASCII')
    return s.upper().strip()

def _guess_yes(value):
    if pd.isna(value):
        return False
    v = str(value).strip().lower()
    return v in ('sim', 's', 'yes', 'y', 'true', '1', 'x')

# --- 2. Funções de Carrinho ---
def adicionar_ao_carrinho(produto_id, nome, preco, quantidade):
    for item in st.session_state.carrinho:
        if item['id'] == produto_id:
            item['quantidade'] += quantidade
            break
    else:
        st.session_state.carrinho.append({
            'id': produto_id,
            'nome': nome,
            'preco': preco,
            'quantidade': quantidade
        })

def remover_do_carrinho(produto_id):
    st.session_state.carrinho = [item for item in st.session_state.carrinho if item['id'] != produto_id]

def limpar_carrinho():
    st.session_state.carrinho = []
    st.session_state.finalizando = False
    st.session_state.pedido_enviado = False
    st.rerun()

# --- 3. Função de Cache para Carregar os Dados (CONEXÃO COM GOOGLE SHEETS) ---
@st.cache_data(ttl=600)
def load_data():
    try:
        creds_json = {
            "type": st.secrets["gsheets"]["creds"]["type"],
            "project_id": st.secrets["gsheets"]["creds"]["project_id"],
            "private_key_id": st.secrets["gsheets"]["creds"]["private_key_id"],
            "private_key": st.secrets["gsheets"]["creds"]["private_key"],
            "client_email": st.secrets["gsheets"]["creds"]["client_email"],
            "client_id": st.secrets["gsheets"]["creds"]["client_id"],
            "auth_uri": st.secrets["gsheets"]["creds"]["auth_uri"],
            "token_uri": st.secrets["gsheets"]["creds"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gsheets"]["creds"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gsheets"]["creds"]["client_x509_cert_url"],
        }
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_url(st.secrets["gsheets"]["sheets_url"])
        worksheet = spreadsheet.worksheet("produtos")
        data = worksheet.get_all_values()
        
        if not data:
            st.error("A planilha de produtos foi acessada, mas está completamente vazia.")
            return pd.DataFrame(), client
            
        header = data[0]
        records = data[1:]
        df = pd.DataFrame(records, columns=header)
        
        if df.empty:
            st.error("Não há registros de produtos na planilha.")
            return pd.DataFrame(), client

        expected_map = {
            'ID': ['ID', 'CODIGO', 'SKU'],
            'NOME': ['NOME', 'PRODUTO', 'NAME'],
            'PRECO': ['PRECO', 'PREÇO', 'PRICE', 'VALOR'],
            'DISPONIVEL': ['DISPONIVEL', 'DISPONÍVEL', 'ATIVO', 'ESTOQUE'],
            'LINKIMAGEM': ['LINKIMAGEM', 'IMAGEM', 'IMG', 'FOTO', 'LINK'],
            'DESCRICAOCURTA': ['DESCRICAOCURTA', 'DESCRIÇÃOCURTA', 'DESC CURTA'],
            'DESCRICAOLONGA': ['DESCRICAOLONGA', 'DESCRIÇÃOLONGA', 'DESC LONGA', 'DESCRIÇÃO']
        }
        
        rename_cols = {}
        df_cols_normalized = { _normalize_header(c): c for c in df.columns }

        for std_name, variations in expected_map.items():
            for var in variations:
                if var in df_cols_normalized:
                    rename_cols[df_cols_normalized[var]] = std_name
                    break
        
        df.rename(columns=rename_cols, inplace=True)

        for required in ['ID', 'NOME', 'PRECO', 'DISPONIVEL']:
            if required not in df.columns:
                st.error(f"Coluna obrigatória '{required}' não encontrada na planilha. Verifique os cabeçalhos.")
                return pd.DataFrame(), client

        df['DISPONIVEL'] = df['DISPONIVEL'].apply(_guess_yes)
        df = df[df['DISPONIVEL'] == True].copy()
        df['PRECO'] = pd.to_numeric(df['PRECO'], errors='coerce').fillna(0) # Converte para número, erro vira 0
        df['ID'] = df['ID'].astype(str)
        
        # A LINHA PROBLEMÁTICA FOI REMOVIDA DAQUI

        for optional in ['LINKIMAGEM', 'DESCRICAOCURTA', 'DESCRICAOLONGA']:
            if optional not in df.columns:
                df[optional] = ""

        return df, client

    except Exception as e:
        st.error(f"Erro Crítico de Conexão. ❌ Verifique se o e-mail da Service Account está como 'Editor' na Planilha e se o secrets.toml está correto. Detalhe: {e}")
        return pd.DataFrame(), None

# Carrega os dados e o objeto cliente (que será usado para salvar pedidos)
df_produtos, gsheets_client = load_data()

# --- 4. Função para Salvar o Pedido ---
def salvar_pedido(nome_cliente, contato_cliente, pedido_df, total):
    if gsheets_client is None:
        st.error("Não foi possível salvar o pedido. Erro na conexão com o Google Sheets.")
        return False
    try:
        relatorio = "; ".join([f"{row['Qtd']}x {row['Produto']} (R$ {row['Subtotal']:.2f})" for index, row in pedido_df.iterrows()])
        spreadsheet_pedidos = gsheets_client.open_by_url(st.secrets["gsheets"]["pedidos_url"])
        worksheet_pedidos = spreadsheet_pedidos.worksheet("Pedidos")
        linha_pedido = [datetime.now().strftime("%d/%m/%Y %H:%M:%S"), nome_cliente, contato_cliente, f"{total:.2f}", relatorio]
        worksheet_pedidos.append_row(linha_pedido)
        st.session_state.pedido_enviado = True
        return True
    except Exception as e:
        st.error(f"Erro ao salvar o pedido. Verifique o secrets.toml (chave 'pedidos_url') e a permissão na Planilha de Pedidos. Detalhe: {e}")
        return False

# --- LÓGICA DE EXIBIÇÃO DAS PÁGINAS ---

# TELA DE SUCESSO
if st.session_state.pedido_enviado:
    st.balloons()
    st.success("🎉 Pedido Enviado com Sucesso!")
    st.info("Obrigado por comprar conosco! Entraremos em contato em breve para confirmar os detalhes da entrega e pagamento.")
    if st.button("Fazer Novo Pedido"):
        limpar_carrinho()

# TELA DE FINALIZAÇÃO
elif st.session_state.finalizando:
    st.title("Finalizar Pedido")
    st.markdown("---")
    total_valor = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho)
    pedido_final_df = pd.DataFrame(st.session_state.carrinho)
    pedido_final_df['Subtotal'] = pedido_final_df['preco'] * pedido_final_df['quantidade']
    pedido_final_df.rename(columns={'nome': 'Produto', 'quantidade': 'Qtd', 'preco': 'Preço Un.'}, inplace=True)
    
    with st.form("Formulario_Finalizacao"):
        st.subheader("1. Seus Dados")
        nome_cliente = st.text_input("Seu Nome Completo:", placeholder="Ex: Maria da Silva")
        contato_cliente = st.text_input("Seu WhatsApp ou E-mail:", placeholder="(XX) XXXXX-XXXX ou email@exemplo.com")
        
        st.subheader("2. Resumo do Pedido")
        st.dataframe(pedido_final_df[['Produto', 'Qtd', 'Preço Un.', 'Subtotal']].style.format({
            'Preço Un.': 'R$ {:.2f}', 'Subtotal': 'R$ {:.2f}'
        }), use_container_width=True, hide_index=True)
        st.markdown(f"### Valor Final: R$ {total_valor:.2f}")

        enviado = st.form_submit_button("✅ ENVIAR PEDIDO", type="primary", use_container_width=True)
        if enviado:
            if nome_cliente and contato_cliente:
                if salvar_pedido(nome_cliente, contato_cliente, pedido_final_df, total_valor):
                    st.rerun()
            else:
                st.error("Por favor, preencha seu nome e contato para finalizar.")

    if st.button("⬅️ Voltar ao Catálogo"):
        st.session_state.finalizando = False
        st.rerun()

# TELA PRINCIPAL (CATÁLOGO)
elif not df_produtos.empty:
    st.image("https://placehold.co/200x50/F06292/ffffff?text=Doce&Bella") 
    st.title("💖 Nossos Produtos")
    st.markdown("---")
    
    cols = st.columns(3)
    for index, row in df_produtos.iterrows():
        col = cols[index % 3]
        with col:
            img = row.get('LINKIMAGEM', '')
            if img:
                st.image(img, use_container_width=True)
            else:
                st.image("https://placehold.co/400x300/F0F0F0/AAAAAA?text=Sem+imagem", use_container_width=True)

            st.markdown(f"**{row.get('NOME', '')}**")
            st.markdown(f"R$ {row.get('PRECO', 0.0):.2f}")
            st.caption(row.get('DESCRICAOCURTA', ''))

            with st.popover("Ver Detalhes/Adicionar", use_container_width=True):
                st.subheader(row.get('NOME', ''))
                st.markdown(f"**Preço:** R$ {row.get('PRECO', 0.0):.2f}")
                st.markdown(f"**Descrição:** {row.get('DESCRICAOLONGA', '')}")
                quantidade = st.number_input("Quantidade:", min_value=1, value=1, step=1, key=f"qty_{row.get('ID')}")
                if st.button(f"➕ Adicionar ao Pedido", key=f"add_{row.get('ID')}", type="primary"):
                    adicionar_ao_carrinho(row.get('ID'), row.get('NOME'), row.get('PRECO'), quantidade)
                    st.rerun()

# --- ÍCONE DO CARRINHO FLUTUANTE (DEVE SER O ÚLTIMO ELEMENTO) ---
total_itens = sum(item['quantidade'] for item in st.session_state.carrinho)
total_valor = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho)

if not st.session_state.finalizando and not st.session_state.pedido_enviado:
    st.markdown(f'<div data-badge="{total_itens if total_itens > 0 else ""}"></div>', unsafe_allow_html=True)

    with st.popover("🛒", use_container_width=False):
        st.header("Meu Carrinho")
        st.markdown("---")
        if not st.session_state.carrinho:
            st.write("Seu carrinho está vazio.")
        else:
            for item in st.session_state.carrinho:
                col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
                with col1:
                    st.text(item['nome'])
                    st.caption(f"Qtd: {item['quantidade']} | R$ {item['preco'] * item['quantidade']:.2f}")
                with col3:
                    if st.button("🗑️", key=f"remove_{item['id']}", help="Remover item"):
                        remover_do_carrinho(item['id'])
                        st.rerun()
            
            st.markdown("---")
            st.markdown(f"**Valor Total:** R$ {total_valor:.2f}")

            if st.button("✅ FINALIZAR PEDIDO", use_container_width=True, type="primary"):
                st.session_state.finalizando = True
                st.rerun()
            if st.button("Limpar Carrinho", use_container_width=True):
                limpar_carrinho()
