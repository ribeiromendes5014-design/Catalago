import streamlit as st
import pandas as pd
import gspread # Biblioteca principal para interagir com o Google Sheets
import math
from oauth2client.service_account import ServiceAccountCredentials # Para autenticação
from datetime import datetime # Para registrar a data do pedido (função salvar)

# --- 1. Configuração da Página e Inicialização do Carrinho ---
st.set_page_config(
    page_title="Catálogo de Produtos | Doce&Bella",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializa o carrinho na memória (session_state) se ele ainda não existir
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = []
if 'finalizando' not in st.session_state:
    st.session_state.finalizando = False
if 'pedido_enviado' not in st.session_state:
    st.session_state.pedido_enviado = False

# --- 2. Funções de Carrinho ---
def adicionar_ao_carrinho(produto_id, nome, preco, quantidade):
    # Verifica se o produto já está no carrinho
    for item in st.session_state.carrinho:
        if item['id'] == produto_id:
            # Se estiver, apenas soma a quantidade
            item['quantidade'] += quantidade
            break
    else:
        # Se não estiver, adiciona o novo item
        st.session_state.carrinho.append({
            'id': produto_id,
            'nome': nome,
            'preco': preco,
            'quantidade': quantidade
        })

def limpar_carrinho():
    st.session_state.carrinho = []
    st.session_state.finalizando = False
    st.session_state.pedido_enviado = False
    st.experimental_rerun()


# --- 3. Função de Cache para Carregar os Dados (CONEXÃO COM GOOGLE SHEETS) ---
@st.cache_data(ttl=600)
def load_data():
    try:
        # 1. AUTENTICAÇÃO E PREPARAÇÃO DA CHAVE SECRETA
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
        
        # O escopo define as permissões que a Service Account terá
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        # CORREÇÃO FINAL: from_json_keyfile_dict é a função universal para dicionários JSON
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        
        # 3. ABRIR A PLANILHA E LER OS DADOS
        spreadsheet = client.open_by_url(st.secrets["gsheets"]["sheets_url"])
        
        # *** LINHA CRÍTICA (135): SUBSTITUA "Sheet1" PELO NOME EXATO DA SUA ABA DE PRODUTOS ***
        # Se o erro persistir, o nome da aba AQUI deve ser a causa!
        worksheet = spreadsheet.worksheet("produtos") 
        
        # 4. CONVERTER PARA DATAFRAME
        df = pd.DataFrame(worksheet.get_all_records())
                       
        # (Lógica de limpeza e filtro)
        df = df[df['DISPONIVEL'].astype(str).str.lower() == 'sim'].copy()
        df['PRECO'] = pd.to_numeric(df['PRECO'], errors='coerce')
        df['ID'] = df['ID'].astype(str) 
        
        return df, client # Retorna os produtos e o objeto cliente para futuras operações
        
    except Exception as e:
        # Mensagem de erro mais clara em caso de falha de autenticação/conexão
        st.error(f"Erro Crítico de Conexão. ❌ Verifique se o e-mail da Service Account está como 'Editor' na Planilha e se o secrets.toml está correto. Detalhe: {e}")
        return pd.DataFrame(), None 
        
# Carrega os dados e o objeto cliente (que será usado para salvar pedidos)
df_produtos, gsheets_client = load_data()


# --- 4. Função para Salvar o Pedido (IMPLEMENTAÇÃO) ---
def salvar_pedido(nome_cliente, contato_cliente, pedido_df, total):
    if gsheets_client is None:
        st.error("Não foi possível salvar o pedido. Erro na conexão com o Google Sheets.")
        return

    try:
        # 1. Montar a string do relatório detalhado
        relatorio = ""
        for index, row in pedido_df.iterrows():
            relatorio += f"- {row['Qtd']}x {row['Produto']} (R$ {row['Subtotal']:.2f}); "
        
        # 2. Abrir a Planilha de Pedidos
        # ATENÇÃO: A Planilha de Pedidos precisa ter a chave 'pedidos_url' no secrets.toml
        spreadsheet_pedidos = gsheets_client.open_by_url(st.secrets["gsheets"]["pedidos_url"])
        worksheet_pedidos = spreadsheet_pedidos.worksheet("Pedidos") # Nome da aba: Pedidos
        
        # 3. Montar a linha de dados (deve coincidir com o cabeçalho da Planilha de Pedidos)
        linha_pedido = [
            datetime.now().strftime("%d/%m/%Y %H:%M:%S"), # Data/Hora
            nome_cliente,
            contato_cliente,
            f"{total:.2f}", # Salva o total como número (sem R$)
            relatorio.strip()
        ]
        
        # 4. Adicionar a linha (o relatório) à Planilha
        worksheet_pedidos.append_row(linha_pedido)
        
        # 5. Sucesso e limpeza
        st.session_state.pedido_enviado = True
        return True
        
    except Exception as e:
        st.error(f"Erro ao salvar o pedido. Verifique o secrets.toml (chave 'pedidos_url') e a permissão na Planilha de Pedidos. Detalhe: {e}")
        return False


# --- 5. Sidebar (O Botão Flutuante de Pedido) ---
with st.sidebar:
    st.image("https://placehold.co/200x50/F06292/ffffff?text=Doce&Bella", use_container_width=True) # Logo Placeholder
    st.header("🛒 Seu Pedido")
    st.markdown("---")
    
    total_itens = sum(item['quantidade'] for item in st.session_state.carrinho)
    total_valor = sum(item['preco'] * item['quantidade'] for item in st.session_state.carrinho)
    
    # Exibe o resumo no sidebar
    col1, col2 = st.columns(2)
    col1.metric(label="Total de Produtos", value=total_itens)
    col2.metric(label="Valor Total", value=f"R$ {total_valor:.2f}")
    st.markdown("---")

    if st.session_state.carrinho:
        st.subheader("Detalhes:")
        
        carrinho_df = pd.DataFrame(st.session_state.carrinho)
        carrinho_df['Subtotal'] = carrinho_df['preco'] * carrinho_df['quantidade']
        carrinho_df.rename(columns={'nome': 'Produto', 'quantidade': 'Qtd', 'preco': 'Preço Un.'}, inplace=True)
        
        # Exibe os itens de forma simplificada na sidebar
        st.dataframe(carrinho_df[['Produto', 'Qtd', 'Subtotal']].style.format({
            'Subtotal': 'R$ {:.2f}'
        }), use_container_width=True, hide_index=True)
        
        # O botão de finalização
        if st.button("✅ FINALIZAR PEDIDO", use_container_width=True, type="primary"):
            st.session_state.finalizando = True # Define que a cliente está finalizando
            st.experimental_rerun()
        
        # Botão para limpar o carrinho
        if st.button("Limpar Pedido", use_container_width=True):
            limpar_carrinho()
    else:
        st.info("Seu pedido está vazio. Adicione produtos ao lado!")


# --- 6. Lógica de Finalização de Pedido ---
if st.session_state.pedido_enviado:
    st.balloons()
    st.success("🎉 Pedido Enviado com Sucesso! Um resumo foi enviado para você (admin) e entraremos em contato com o cliente.")
    st.info("Obrigado por usar o catálogo! Você pode fazer um novo pedido.")
    if st.button("Fazer Novo Pedido"):
        limpar_carrinho()
        
elif st.session_state.finalizando:
    st.title("Finalizar Pedido")
    st.markdown("## 1. Confirme seus dados para envio:")
    
    # Formata o resumo para exibição
    pedido_final_df = pd.DataFrame(st.session_state.carrinho)
    pedido_final_df['Subtotal'] = pedido_final_df['preco'] * pedido_final_df['quantidade']
    pedido_final_df.rename(columns={'nome': 'Produto', 'quantidade': 'Qtd', 'preco': 'Preço Un.'}, inplace=True)
    
    st.markdown(f"### Valor Final: R$ {total_valor:.2f}")
    
    with st.form("Formulario_Finalizacao"):
        nome_cliente = st.text_input("Seu Nome Completo:", placeholder="Ex: Maria da Silva")
        contato_cliente = st.text_input("Seu WhatsApp ou E-mail:", placeholder="(XX) XXXXX-XXXX ou email@exemplo.com")
        
        st.markdown("---")
        st.subheader("Resumo do Pedido:")
        st.dataframe(pedido_final_df[['Produto', 'Qtd', 'Preço Un.', 'Subtotal']].style.format({
            'Preço Un.': 'R$ {:.2f}',
            'Subtotal': 'R$ {:.2f}'
        }), use_container_width=True, hide_index=True)

        enviado = st.form_submit_button("✅ ENVIAR PEDIDO", type="primary", use_container_width=True)
        
        if enviado:
            if nome_cliente and contato_cliente:
                # Chama a função para salvar/enviar o relatório
                salvar_pedido(nome_cliente, contato_cliente, pedido_final_df, total_valor)
                st.experimental_rerun()
            else:
                st.error("Por favor, preencha seu nome e contato para finalizar.")

    if st.button("Voltar ao Catálogo"):
        st.session_state.finalizando = False
        st.experimental_rerun()
        
# --- 7. Exibição do Catálogo (Home) ---
elif not df_produtos.empty:
    st.title("💖 Nossos Produtos")
    st.markdown("---")
    
    # Layout em colunas (3 produtos por linha)
    cols = st.columns(3)
    
    for index, row in df_produtos.iterrows():
        col = cols[index % 3] 
        
        with col:
            # 7.1. Exibição do Card
            st.image(row['LINKIMAGEM'], use_container_width=True)
            st.markdown(f"**{row['NOME']}**")
            st.markdown(f"R$ {row['PRECO']:.2f}")
            st.caption(row['DESCRICAOCURTA'])
            
            # 7.2. Detalhe e Adição ao Carrinho usando st.popover (Zoom)
            with st.popover("Ver Detalhes/Adicionar ao Pedido", use_container_width=True):
                st.subheader(row['NOME'])
                st.markdown(f"**Preço:** R$ {row['PRECO']:.2f}")
                st.write("---")
                st.markdown(f"**Descrição Completa:** {row['DESCRICAOLONGA']}")
                
                # Campo de quantidade
                quantidade = st.number_input("Quantidade:", min_value=1, value=1, step=1, key=f"qty_{row['ID']}")
                
                if st.button(f"➕ Adicionar {quantidade} ao Pedido", key=f"add_{row['ID']}", type="primary"):
                    adicionar_ao_carrinho(row['ID'], row['NOME'], row['PRECO'], quantidade)
                    st.success(f"{quantidade}x {row['NOME']} adicionado(s)!")
                    st.experimental_rerun() # Atualiza a sidebar para mostrar o carrinho

