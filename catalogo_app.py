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
SHEET_NAME_CATALOGO = "produtos" # CORRIGIDO: Nome da sua aba de produtos (minúsculo)
SHEET_NAME_PEDIDOS = "PEDIDOS"

# Inicialização do Carrinho de Compras e Estado
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {} # {id_produto: {'nome': str, 'preco': float, 'quantidade': int}}

# --- Funções de Conexão GSpread (Seguras e Cache) ---

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

# Adiciona CSS para o carrinho customizado (simulando um badge)
st.markdown("""
<style>
/* Remove a margem superior padrão do Streamlit */
div.block-container {
    padding-top: 2rem;
}

/* Esconde o botão padrão do popover para que possamos usar um customizado */
div[data-testid="stPopover"] > div:first-child > button {
    display: none;
}

/* Estiliza o placeholder para o popover, para parecer um botão flutuante */
.st-emotion-cache-163l75u { /* Este seletor pode mudar dependendo da versão do Streamlit */
    position: fixed; /* Tenta fixar o botão na tela */
    top: 20px;
    right: 20px;
    z-index: 9999; /* Garante que fique acima de outros elementos */
}


/* Estiliza o botão do carrinho para parecer um badge rosa de e-commerce */
.cart-badge-button {
    background-color: #E91E63; /* Cor primária Doce&Bella */
    color: white;
    border-radius: 12px; /* Cantos arredondados */
    padding: 8px 15px; /* Preenchimento */
    font-size: 16px;
    font-weight: bold;
    cursor: pointer;
    border: none;
    transition: background-color 0.3s;
    display: inline-flex;
    align-items: center;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    min-width: 150px; /* Garante largura mínima para o texto */
    justify-content: center;
}

.cart-badge-button:hover {
    background-color: #C2185B; /* Cor mais escura no hover */
}

/* Estiliza o contador de itens */
.cart-count {
    background-color: white;
    color: #E91E63;
    border-radius: 50%;
    padding: 2px 7px;
    margin-left: 8px;
    font-size: 14px;
    line-height: 1;
}
</style>
""", unsafe_allow_html=True)


# --- 1. CABEÇALHO DO APLICATIVO (Título + Carrinho Customizado) ---

col_titulo, col_carrinho = st.columns([4, 1])

with col_titulo:
    st.title("💖 Catálogo de Pedidos Doce&Bella")

# 2. Lógica do Carrinho Customizado (Badge)

total_acumulado = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho.values())
num_itens = sum(item['quantidade'] for item in st.session_state.carrinho.values())
carrinho_vazio = not st.session_state.carrinho

with col_carrinho:
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True) # Espaçamento vertical
    
    # O st.popover agora terá um título de texto simples, mas usaremos CSS para escondê-lo
    # e um st.markdown para criar o botão visual que queremos.
    
    # Criamos o botão HTML/CSS customizado
    custom_cart_button = f"""
        <div class='cart-badge-button' onclick='document.querySelector("[data-testid=\"stPopover\"] > div:first-child > button").click();'>
            🛒 SEU PEDIDO 
            <span class='cart-count'>{num_itens}</span>
        </div>
    """
    
    # Usamos st.markdown para exibir o botão customizado
    st.markdown(custom_cart_button, unsafe_allow_html=True)

    # O popover real é ativado por um "clique simulado" no botão oculto.
    # O título do popover pode ser vazio ou um espaço em branco para não aparecer.
    with st.popover(" ", use_container_width=False, help="Clique para ver os itens e finalizar o pedido"):
        
        st.header("🛒 Detalhes do Seu Pedido")

        if carrinho_vazio:
            st.info("Seu carrinho está vazio. Adicione itens do catálogo!")
        else:
            # Mostra o total na parte superior do popover
            st.markdown(f"<h3 style='color: #E91E63; margin-top: 0;'>Total: R$ {total_acumulado:.2f}</h3>", unsafe_allow_html=True)
            st.markdown("---")
            
            # Visualização e remoção de itens
            for prod_id, item in st.session_state.carrinho.items():
                col_nome, col_qtd, col_preco, col_remover = st.columns([3, 1.5, 2, 1])
                
                col_nome.write(f"*{item['nome']}*")
                col_qtd.markdown(f"**{item['quantidade']}x**")
                col_preco.markdown(f"R$ {item['preco'] * item['quantidade']:.2f}")

                # Botão de remoção
                if col_remover.button("X", key=f'rem_{prod_id}_popover', help=f"Remover {item['nome']}"):
                    remover_do_carrinho(prod_id)
                    st.rerun()
                    
            st.markdown("---")
            
            # 3. Finalização de Pedido
            st.subheader("Finalizar Pedido")
            with st.form("form_finalizar_pedido_popover", clear_on_submit=True):
                nome = st.text_input("Seu Nome Completo:", key='nome_cliente_popover')
                contato = st.text_input("Seu Contato (WhatsApp/E-mail):", key='contato_cliente_popover')
                
                submitted = st.form_submit_button("✅ Enviar Pedido", type="primary", use_container_width=True)
                
                if submitted:
                    if not nome or not contato:
                        st.error("Por favor, preencha seu nome e contato para finalizar.")
                    else:
                        # Prepara o relatório em JSON e salva
                        detalhes_pedido = {
                            "total": total_acumulado,
                            "itens": [
                                {
                                    "id": int(prod_id),
                                    "nome": item['nome'],
                                    "preco": item['preco'],
                                    "qtd": item['quantidade'],
                                    "subtotal": item['preco'] * item['quantidade']
                                } for prod_id, item in st.session_state.carrinho.items()
                            ]
                        }
                        
                        if salvar_pedido(nome, contato, total_acumulado, json.dumps(detalhes_pedido)):
                            st.balloons() 
                            st.success("🎉 Pedido enviado com sucesso! Entraremos em contato em breve para combinar o pagamento e a entrega.")
                            st.session_state.carrinho = {} 
                            st.rerun()
                        else:
                            st.error("Falha ao salvar o pedido. Tente novamente.")


# --- Exibição do Catálogo em Grade ---
st.markdown("---")
st.subheader("Nossos Produtos Disponíveis")

df_catalogo = carregar_catalogo()

cols_per_row = 3
cols = st.columns(cols_per_row) 

for i, (prod_id, row) in enumerate(df_catalogo.iterrows()):
    col = cols[i % cols_per_row]
    
    with col:
        with st.container(border=True):
            
            # Título e Preço
            st.markdown(f"**{row['NOME']}**", unsafe_allow_html=True)
            st.markdown(f"<h3 style='color: #E91E63; margin-top: 0;'>R$ {row['PRECO']:.2f}</h3>", unsafe_allow_html=True)

            # Imagem
            if row['LINKIMAGEM']:
                try:
                    st.image(row['LINKIMAGEM'], use_column_width="always")
                except:
                    st.markdown("*(Erro ao carregar imagem)*")
            else:
                st.markdown("*(Sem Imagem)*")
            
            # Descrição Curta
            st.caption(row['DESCRICAOCURTA'])
            
            # --- Zoom do Produto e Adicionar ao Pedido (st.popover) ---
            with st.popover("✨ Detalhes e Pedido", use_container_width=True):
                st.markdown(f"### {row['NOME']}")
                
                # Descrição Longa
                st.markdown(row['DESCRICAOLONGA'])
                st.markdown("---")
                
                quantidade_inicial = st.session_state.carrinho.get(prod_id, {}).get('quantidade', 1)
                
                # Formulário para Quantidade
                quantidade = st.number_input(
                    "Quantidade:", 
                    min_value=1, 
                    step=1, 
                    key=f'qtd_{prod_id}_popover_item', 
                    value=quantidade_inicial
                )
                
                if st.button("➕ Adicionar/Atualizar Pedido", key=f'add_{prod_id}', type="primary", use_container_width=True):
                    adicionar_ao_carrinho(
                        prod_id, 
                        quantidade, 
                        row['NOME'], 
                        row['PRECO']
                    )
                    st.rerun()
