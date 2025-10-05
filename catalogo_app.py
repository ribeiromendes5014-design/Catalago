# catalogo_app.py
import streamlit as st
import pandas as pd
from datetime import datetime
import json

# --- Configurações de Dados ---
SHEET_NAME_CATALOGO = "CATALOGO"
SHEET_NAME_PEDIDOS = "PEDIDOS"

# Inicialização do Carrinho de Compras
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {} # {id_produto: {'nome': str, 'preco': float, 'quantidade': int}}

# --- Funções de Persistência Segura ---

@st.cache_data(ttl=600) # Recarrega a cada 10 minutos
def carregar_catalogo():
    """Carrega o catálogo de produtos do Google Sheets."""
    try:
        # Usa a conexão segura configurada em st.secrets
        conn = st.connection("gsheets", type=st.connections.SnowflakeConnection)
        df = conn.read(worksheet=SHEET_NAME_CATALOGO, ttl=600)
        
        # Converte tipos e filtra
        df['PRECO'] = pd.to_numeric(df['PRECO'], errors='coerce').fillna(0.0)
        df['ID'] = pd.to_numeric(df['ID'], errors='coerce').astype('Int64')
        df_filtrado = df[df['DISPONIVEL'].str.lower() == 'sim'].copy()
        
        return df_filtrado.set_index('ID')
    except Exception as e:
        st.error(f"Erro ao carregar o catálogo: {e}")
        return pd.DataFrame()

def salvar_pedido(nome_cliente: str, contato_cliente: str, valor_total: float, itens_json: str):
    """Salva um novo pedido na planilha de PEDIDOS."""
    try:
        conn = st.connection("gsheets", type=st.connections.SnowflakeConnection)
        
        novo_registro = pd.DataFrame([{
            'ID_PEDIDO': int(datetime.now().timestamp()), # ID único
            'DATA_HORA': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'NOME_CLIENTE': nome_cliente,
            'CONTATO_CLIENTE': contato_cliente,
            'ITENS_JSON': itens_json,
            'VALOR_TOTAL': valor_total
        }])
        
        conn.insert(worksheet=SHEET_NAME_PEDIDOS, data=novo_registro)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar o pedido: {e}")
        return False

# --- Funções de Lógica do Carrinho ---

def adicionar_ao_carrinho(produto_id, quantidade, produto_nome, produto_preco):
    if quantidade > 0:
        st.session_state.carrinho[produto_id] = {
            'nome': produto_nome,
            'preco': produto_preco,
            'quantidade': quantidade
        }
        st.toast(f"✅ {quantidade}x {produto_nome} adicionado(s) ao pedido!")

def remover_do_carrinho(produto_id):
    if produto_id in st.session_state.carrinho:
        nome = st.session_state.carrinho[produto_id]['nome']
        del st.session_state.carrinho[produto_id]
        st.toast(f"❌ {nome} removido do pedido.")

# --- Layout do Aplicativo ---

st.set_page_config(
    page_title="Catálogo Doce&Bella", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

st.title("💖 Catálogo de Pedidos Doce&Bella")
st.markdown("---")

# 1. Carregamento e Filtro
df_catalogo = carregar_catalogo()

if df_catalogo.empty:
    st.warning("O catálogo está vazio ou indisponível no momento. Tente novamente mais tarde.")
    st.stop()
    
# 2. Exibição do Catálogo em Grade (e-commerce style)
st.subheader("Nossos Produtos Disponíveis")

cols = st.columns(3) # Grade de 3 colunas
carrinho_vazio = not st.session_state.carrinho

for i, (prod_id, row) in enumerate(df_catalogo.iterrows()):
    col = cols[i % 3]
    
    with col:
        with st.container(border=True):
            
            # Título e Preço
            st.markdown(f"**{row['NOME']}**", unsafe_allow_html=True)
            st.markdown(f"<h3 style='color: #E91E63;'>R$ {row['PRECO']:.2f}</h3>", unsafe_allow_html=True)

            # Imagem
            if row['LINKIMAGEM']:
                st.image(row['LINKIMAGEM'], use_column_width="always")
            else:
                st.markdown("*(Sem Imagem)*")
            
            # Descrição Curta
            st.caption(row['DESCRICAOCURTA'])
            
            # --- Zoom do Produto e Adicionar ao Pedido (st.popover) ---
            with st.popover("✨ Detalhes e Pedido"):
                st.markdown(f"### {row['NOME']}")
                
                # Descrição Longa
                st.markdown(row['DESCRICAOLONGA'])
                st.markdown("---")
                
                # Formulário para Quantidade
                quantidade = st.number_input(
                    "Quantidade:", 
                    min_value=1, 
                    step=1, 
                    key=f'qtd_{prod_id}', 
                    value=1
                )
                
                if st.button("➕ Adicionar ao Pedido", key=f'add_{prod_id}', use_container_width=True):
                    adicionar_ao_carrinho(
                        prod_id, 
                        quantidade, 
                        row['NOME'], 
                        row['PRECO']
                    )
                    # Força o fechamento do popover (opcional, mas melhora a UX)
                    # st.rerun() 


# 3. Carrinho de Compras (Sidebar Flutuante)
total_acumulado = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho.values())
num_itens = sum(item['quantidade'] for item in st.session_state.carrinho.values())

with st.sidebar:
    st.header("🛒 Seu Pedido")
    
    if carrinho_vazio:
        st.info("Seu carrinho está vazio. Adicione itens do catálogo!")
    else:
        st.metric(label="Total de Itens", value=f"{num_itens} unidade(s)")
        st.metric(label="Valor Total", value=f"R$ {total_acumulado:.2f}")
        st.markdown("---")
        
        st.subheader("Itens no Carrinho")
        
        # Tabela simples de itens
        for prod_id, item in st.session_state.carrinho.items():
            col_nome, col_qtd, col_remover = st.columns([3, 1.5, 1])
            col_nome.write(f"*{item['nome']}*")
            col_qtd.write(f"**{item['quantidade']}x**")
            if col_remover.button("Remover", key=f'rem_{prod_id}', type='primary', help=f"Remover {item['nome']}"):
                remover_do_carrinho(prod_id)
                st.rerun()
                
        st.markdown("---")
        
        # 4. Finalização de Pedido
        st.subheader("Finalizar Pedido")
        with st.form("form_finalizar_pedido", clear_on_submit=True):
            nome = st.text_input("Seu Nome Completo:", key='nome_cliente')
            contato = st.text_input("Seu Contato (WhatsApp/E-mail):", key='contato_cliente')
            
            st.markdown(f"**Total a Pagar: R$ {total_acumulado:.2f}** (Pagamento será combinado após o envio.)")
            
            submitted = st.form_submit_button("✅ Enviar Pedido", type="primary")
            
            if submitted:
                if not nome or not contato:
                    st.error("Por favor, preencha seu nome e contato para finalizar.")
                else:
                    # Preparar o relatório em texto/JSON
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
                        st.success("🎉 Pedido enviado com sucesso! Entraremos em contato para combinar o pagamento e a entrega.")
                        st.session_state.carrinho = {} # Limpa o carrinho
                        st.rerun()


# NOTA: O arquivo admin_app.py deve ser criado separadamente,
# usando o mesmo st.connection para acessar ambas as planilhas.
