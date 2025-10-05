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

# Inicialização do Carrinho de Compras e Estado
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = {} # {id_produto: {'nome': str, 'preco': float, 'quantidade': int}}

# --- Funções de Conexão GSpread (Seguras e Cache) ---

@st.cache_resource(ttl=None) 
def get_gspread_client():
    """Cria um cliente GSpread autenticado usando o service account do st.secrets."""
    try:
        # Puxa as credenciais do secrets.toml (copiando as chaves do JSON)
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
        
        # Cria e autoriza o cliente
        creds = ServiceAccountCredentials.from_json_keyfile_dict(gcp_sa_credentials, scope)
        client = gspread.authorize(creds)
        sh = client.open_by_url(st.secrets["gsheets"]["sheet_url"])
        
        return sh
    except Exception as e:
        st.error("Erro na autenticação do Google Sheets. Verifique o secrets.toml ou se o service account tem acesso à planilha.")
        st.stop()
        
@st.cache_data(ttl=600) # Recarrega a cada 10 minutos
def carregar_catalogo():
    """Carrega o catálogo de produtos (aba CATALOGO) e prepara o DataFrame."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_CATALOGO)
        
        # Puxa todos os dados e converte para DataFrame
        data = worksheet.get_all_values()
        # Se a planilha tiver cabeçalho, remove a primeira linha
        if data:
            df = pd.DataFrame(data[1:], columns=data[0]) 
        else:
            return pd.DataFrame()
        
        # Converte tipos e filtra os disponíveis
        df['PRECO'] = pd.to_numeric(df['PRECO'], errors='coerce').fillna(0.0)
        df['ID'] = pd.to_numeric(df['ID'], errors='coerce').astype('Int64')
        df_filtrado = df[df['DISPONIVEL'].astype(str).str.lower() == 'sim'].copy()
        
        return df_filtrado.set_index('ID')
    except Exception as e:
        st.error(f"Erro ao carregar o catálogo: {e}")
        st.error("Dica: Verifique se o nome da aba da planilha está correto: 'CATALOGO'")
        return pd.DataFrame()

def salvar_pedido(nome_cliente: str, contato_cliente: str, valor_total: float, itens_json: str):
    """Salva um novo pedido na planilha de PEDIDOS."""
    try:
        sh = get_gspread_client()
        worksheet = sh.worksheet(SHEET_NAME_PEDIDOS)
        
        # Prepara a nova linha no formato de lista
        novo_registro = [
            int(datetime.now().timestamp()), # ID_PEDIDO
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), # DATA_HORA
            nome_cliente, # NOME_CLIENTE
            contato_cliente, # CONTATO_CLIENTE
            itens_json, # ITENS_JSON (string JSON)
            f"{valor_total:.2f}" # VALOR_TOTAL (formatado como string para GSheets)
        ]
        
        # Adiciona a linha ao final da planilha
        worksheet.append_row(novo_registro)
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
        # Adicionamos um pequeno atraso para que o toast apareça antes do possível rerun
        st.toast(f"✅ {quantidade}x {produto_nome} adicionado(s) ao pedido!", icon="🛍️")
        time.sleep(0.1) # Pausa rápida

def remover_do_carrinho(produto_id):
    if produto_id in st.session_state.carrinho:
        nome = st.session_state.carrinho[produto_id]['nome']
        del st.session_state.carrinho[produto_id]
        st.toast(f"❌ {nome} removido do pedido.", icon="🗑️")

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
    
# 2. Exibição do Catálogo em Grade
cols_per_row = 3 # Define a grade de 3 colunas
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
                
                # Recupera a quantidade atual do carrinho (se existir)
                quantidade_inicial = st.session_state.carrinho.get(prod_id, {}).get('quantidade', 1)
                
                # Formulário para Quantidade
                quantidade = st.number_input(
                    "Quantidade:", 
                    min_value=1, 
                    step=1, 
                    key=f'qtd_{prod_id}_popover', 
                    value=quantidade_inicial
                )
                
                if st.button("➕ Adicionar/Atualizar Pedido", key=f'add_{prod_id}', type="primary", use_container_width=True):
                    adicionar_ao_carrinho(
                        prod_id, 
                        quantidade, 
                        row['NOME'], 
                        row['PRECO']
                    )
                    st.rerun() # Recarrega para atualizar a sidebar


# 3. Carrinho de Compras (Sidebar Flutuante)
total_acumulado = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho.values())
num_itens = sum(item['quantidade'] for item in st.session_state.carrinho.values())
carrinho_vazio = not st.session_state.carrinho

with st.sidebar:
    st.header("🛒 Seu Pedido")
    
    if carrinho_vazio:
        st.info("Seu carrinho está vazio. Adicione itens do catálogo!")
    else:
        # Métricas visíveis
        st.metric(label="Total de Itens", value=f"{num_itens} unidade(s)")
        st.markdown(f"<h2 style='color: #E91E63;'>R$ {total_acumulado:.2f}</h2>", unsafe_allow_html=True)
        st.markdown("---")
        
        st.subheader("Itens no Pedido")
        
        # Visualização e remoção de itens
        for prod_id, item in st.session_state.carrinho.items():
            col_nome, col_qtd, col_remover = st.columns([3, 1.5, 1])
            col_nome.write(f"*{item['nome']}*")
            col_qtd.write(f"**{item['quantidade']}x**")
            # Botão de remoção
            if col_remover.button("Remover", key=f'rem_{prod_id}', type='secondary', help=f"Remover {item['nome']}"):
                remover_do_carrinho(prod_id)
                st.rerun()
                
        st.markdown("---")
        
        # 4. Finalização de Pedido
        st.subheader("Finalizar Pedido")
        with st.form("form_finalizar_pedido", clear_on_submit=True):
            nome = st.text_input("Seu Nome Completo:", key='nome_cliente')
            contato = st.text_input("Seu Contato (WhatsApp/E-mail):", key='contato_cliente')
            
            st.info(f"O valor total do pedido é de **R$ {total_acumulado:.2f}**. O pagamento será combinado após o envio.")
            
            submitted = st.form_submit_button("✅ Enviar Pedido", type="primary", use_container_width=True)
            
            if submitted:
                if not nome or not contato:
                    st.error("Por favor, preencha seu nome e contato para finalizar.")
                else:
                    # Preparar o relatório em JSON
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
                        st.balloons() # Efeito visual de sucesso
                        st.success("🎉 Pedido enviado com sucesso! Entraremos em contato em breve para combinar o pagamento e a entrega.")
                        st.session_state.carrinho = {} # Limpa o carrinho
                        st.rerun()
                    else:
                        st.error("Falha ao salvar o pedido. Tente novamente.")

