import streamlit as st
import pandas as pd
import gspread # Biblioteca principal para interagir com o Google Sheets
import math
import unicodedata
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

# --- Helpers ---
def _normalize_header(s: str) -> str:
    if s is None:
        return ""
    # Remove acentos, transforma em ASCII, maiúsculas e strip
    s = str(s)
    s = unicodedata.normalize('NFKD', s)
    s = s.encode('ASCII', 'ignore').decode('ASCII')
    return s.upper().strip()

def _find_column(df_columns, target_normalized):
    """
    Procura uma coluna em df_columns cujo header normalizado
    seja igual ao target_normalized. Retorna o nome original da coluna
    ou None se não encontrar.
    """
    for col in df_columns:
        if _normalize_header(col) == target_normalized:
            return col
    return None

def _guess_yes(value):
    if pd.isna(value):
        return False
    v = str(value).strip().lower()
    return v in ('sim', 's', 'yes', 'y', 'true', '1', 'x')

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

        # from_json_keyfile_dict é a função universal para dicionários JSON
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)

        # 3. ABRIR A PLANILHA E LER OS DADOS
        spreadsheet = client.open_by_url(st.secrets["gsheets"]["sheets_url"])

        # tentativa 1: usar aba exatamente "Produtos" (conforme ajuste do usuário)
        worksheet = None
        try:
            worksheet = spreadsheet.worksheet("Produtos")
        except Exception:
            # fallback: usar primeira aba
            try:
                worksheet = spreadsheet.sheet1
            except Exception:
                # fallback final: tentar pegar a primeira disponível via worksheets()
                wss = spreadsheet.worksheets()
                if len(wss) > 0:
                    worksheet = wss[0]
                else:
                    raise Exception("Nenhuma aba encontrada na planilha.")

        # 4. CONVERTER PARA DATAFRAME (CORREÇÃO PARA EVITAR ERRO DE PLANILHA VAZIA)
        # Tenta ler os dados usando get_all_values() em vez de get_all_records() 
        # para lidar com cabeçalhos inconsistentes que causam df.empty.
        data = worksheet.get_all_values()
        
        if not data:
            st.error("A planilha foi acessada, mas está completamente vazia.")
            return pd.DataFrame(), client
            
        # A primeira linha é o cabeçalho, o restante são os dados
        header = data[0]
        records = data[1:]
        df = pd.DataFrame(records, columns=header)
        # FIM DA CORREÇÃO

        # Se dataframe vazio (apenas cabeçalho ou erro de leitura dos dados)
        if df.empty:
            st.error("A planilha foi acessada e o cabeçalho foi lido, mas não há registros de produtos.")
            return pd.DataFrame(), client

        # Normalizar e mapear cabeçalhos esperados
        normalized_to_original = { _normalize_header(c): c for c in df.columns.tolist() }

        # Lista de cabeçalhos esperados (normalizados)
        expected = {
            'DISPONIVEL': None,
            'PRECO': None,
            'ID': None,
            'NOME': None,
            'LINKIMAGEM': None,
            'DESCRICAOCURTA': None,
            'DESCRICAOLONGA': None
        }

        # Preencher o mapa expected com nomes reais encontrados (ou None)
        for key in expected.keys():
            expected[key] = normalized_to_original.get(key)

        # Se DISPONIVEL não encontrada, tentar encontrar variações ('DISPONÍVEL', 'DISPONIVEL?', 'EM ESTOQUE', etc.)
        if expected['DISPONIVEL'] is None:
            # procurar cabeçalhos que contenham a palavra DISPONIVEL / DISPONIVEL sem acento
            for norm, orig in normalized_to_original.items():
                if 'DISPON' in norm or 'ESTOC' in norm or 'ATIV' in norm:
                    expected['DISPONIVEL'] = orig
                    break

        # Se PRECO não encontrado, tentar variações
        if expected['PRECO'] is None:
            for norm, orig in normalized_to_original.items():
                if 'PRECO' in norm or 'PRICE' in norm:
                    expected['PRECO'] = orig
                    break

        # Se ID não encontrado, tentar variações
        if expected['ID'] is None:
            for norm, orig in normalized_to_original.items():
                if norm in ('ID', 'CODIGO', 'CODE', 'SKU'):
                    expected['ID'] = orig
                    break

        # Se NOME não encontrado, tentar variações
        if expected['NOME'] is None:
            for norm, orig in normalized_to_original.items():
                if 'NOME' in norm or 'NAME' in norm or 'PRODUTO' in norm:
                    expected['NOME'] = orig
                    break

        # Se LINKIMAGEM não encontrado, tentar variações
        if expected['LINKIMAGEM'] is None:
            for norm, orig in normalized_to_original.items():
                if 'IMG' in norm or 'LINK' in norm or 'IMAGE' in norm or 'FOTO' in norm:
                    expected['LINKIMAGEM'] = orig
                    break

        # Se DESCRICAOCURTA não encontrado, tentar variações
        if expected['DESCRICAOCURTA'] is None:
            for norm, orig in normalized_to_original.items():
                if 'CURTA' in norm or 'SHORT' in norm or ('DESC' in norm and 'CURT' in norm):
                    expected['DESCRICAOCURTA'] = orig
                    break

        # Se DESCRICAOLONGA não encontrado, tentar variações
        if expected['DESCRICAOLONGA'] is None:
            for norm, orig in normalized_to_original.items():
                if 'LONGA' in norm or 'LONG' in norm or ('DESC' in norm and 'COMP' in norm) or ('DESC' in norm and 'LONG' in norm):
                    expected['DESCRICAOLONGA'] = orig
                    break

        # Verificar se a coluna de disponibilidade foi encontrada
        if expected['DISPONIVEL'] is None:
            st.error(f"A coluna de disponibilidade não foi encontrada. Colunas disponíveis: {df.columns.tolist()}")
            return pd.DataFrame(), client

        # Renomear colunas encontradas para nomes padrão internos (se existirem)
        rename_map = {}
        for key, original in expected.items():
            if original is not None:
                rename_map[original] = key # ex: 'Disponível' -> 'DISPONIVEL'
        df.rename(columns=rename_map, inplace=True)

        # Agora garantir que as colunas PRECO e ID e NOME existam antes de usá-las
        missing_required = []
        for must in ['PRECO', 'ID', 'NOME']:
            if must not in df.columns:
                missing_required.append(must)
        if missing_required:
            st.error(f"As seguintes colunas obrigatórias não foram encontradas na planilha: {missing_required}. Colunas disponíveis: {df.columns.tolist()}")
            return pd.DataFrame(), client

        # Aplicar filtro de disponibilidade (aceita variações como SIM/YES/1/TRUE)
        df['DISPONIVEL'] = df['DISPONIVEL'].apply(_guess_yes)
        df = df[df['DISPONIVEL'] == True].copy()

        # Converter PRECO para numérico (coerce -> NaN)
        df['PRECO'] = pd.to_numeric(df['PRECO'], errors='coerce')

        # Converter ID para string
        df['ID'] = df['ID'].astype(str)

        # Se não existir LINKIMAGEM ou descrições, criar colunas vazias para evitar KeyError
        for optional in ['LINKIMAGEM', 'DESCRICAOCURTA', 'DESCRICAOLONGA']:
            if optional not in df.columns:
                df[optional] = ""

        # Retornar df e client
        return df, client # Retorna os produtos e o objeto cliente para futuras operações

    except Exception as e:
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
            # usar chaves defensivas caso o dataframe tenha nomes diferentes
            qtd = row.get('Qtd') if 'Qtd' in row.index else row.get('quantidade', 0)
            produto = row.get('Produto') if 'Produto' in row.index else row.get('nome', '')
            subtotal = row.get('Subtotal') if 'Subtotal' in row.index else (row.get('preco', 0) * qtd)
            relatorio += f"- {qtd}x {produto} (R$ {subtotal:.2f}); "

        # 2. Abrir a Planilha de Pedidos
        # ATENÇÃO: A Planilha de Pedidos precisa ter a chave 'pedidos_url' no secrets.toml
        spreadsheet_pedidos = gsheets_client.open_by_url(st.secrets["gsheets"]["pedidos_url"])
        worksheet_pedidos = None
        try:
            worksheet_pedidos = spreadsheet_pedidos.worksheet("Pedidos")
        except Exception:
            # tentar primeira aba como fallback
            try:
                worksheet_pedidos = spreadsheet_pedidos.sheet1
            except Exception:
                wss = spreadsheet_pedidos.worksheets()
                if len(wss) > 0:
                    worksheet_pedidos = wss[0]
                else:
                    raise Exception("Nenhuma aba disponível na planilha de pedidos.")

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
            # usar get para evitar KeyError se a coluna estiver vazia
            img = row.get('LINKIMAGEM', '') if isinstance(row, dict) else row.get('LINKIMAGEM', '')
            try:
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.image("https://placehold.co/400x300/F0F0F0/AAAAAA?text=Sem+imagem", use_container_width=True)
            except Exception:
                st.image("https://placehold.co/400x300/F0F0F0/AAAAAA?text=Imagem+inválida", use_container_width=True)

            nome_prod = row.get('NOME', '') if isinstance(row, dict) else row.get('NOME', '')
            preco_prod = row.get('PRECO', 0.0) if isinstance(row, dict) else row.get('PRECO', 0.0)
            desc_curta = row.get('DESCRICAOCURTA', '') if isinstance(row, dict) else row.get('DESCRICAOCURTA', '')

            st.markdown(f"**{nome_prod}**")
            st.markdown(f"R$ {preco_prod:.2f}")
            st.caption(desc_curta)

            # 7.2. Detalhe e Adição ao Carrinho usando st.popover (Zoom)
            with st.popover("Ver Detalhes/Adicionar ao Pedido", use_container_width=True):
                st.subheader(nome_prod)
                st.markdown(f"**Preço:** R$ {preco_prod:.2f}")
                st.write("---")
                desc_longa = row.get('DESCRICAOLONGA', '') if isinstance(row, dict) else row.get('DESCRICAOLONGA', '')
                st.markdown(f"**Descrição Completa:** {desc_longa}")

                # Campo de quantidade
                produto_id = row.get('ID', '') if isinstance(row, dict) else row.get('ID', '')
                quantidade = st.number_input("Quantidade:", min_value=1, value=1, step=1, key=f"qty_{produto_id}")

                if st.button(f"➕ Adicionar {quantidade} ao Pedido", key=f"add_{produto_id}", type="primary"):
                    adicionar_ao_carrinho(produto_id, nome_prod, preco_prod, quantidade)
                    st.success(f"{quantidade}x {nome_prod} adicionado(s)!")
                    st.experimental_rerun() # Atualiza a sidebar para mostrar o carrinho
