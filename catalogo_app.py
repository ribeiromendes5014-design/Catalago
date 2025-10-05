import streamlit as st
import pandas as pd
import gspread
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials

# --- Configuração Mínima ---
st.set_page_config(layout="wide")
st.title("Teste de Diagnóstico de Layout")

# --- Função de Carregar Dados (Simplificada) ---
@st.cache_data
def load_data_test():
    try:
        creds_json = st.secrets["gsheets"]["creds"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        worksheet = client.open_by_url(st.secrets["gsheets"]["sheets_url"]).worksheet("produtos")
        df = pd.DataFrame(worksheet.get_all_records())
        if df.empty: return pd.DataFrame()

        def _normalize(s): return unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('ASCII').upper().strip()
        df.columns = [_normalize(col) for col in df.columns]

        rename_map = {'PRODUTO': 'NOME', 'PRECO': 'PRECO', 'IMAGEM': 'LINKIMAGEM'}
        df.rename(columns=lambda c: rename_map.get(c, c), inplace=True)

        if 'DISPONIVEL' in df.columns:
            df = df[df['DISPONIVEL'].astype(str).str.lower().isin(['sim', 's', 'true', '1'])].copy()

        return df
    except Exception as e:
        st.error(f"Erro ao carregar a planilha: {e}")
        return pd.DataFrame()

# --- Teste de Layout ---
df_produtos = load_data_test()

if not df_produtos.empty:
    st.success(f"Planilha lida com sucesso! Encontrados {len(df_produtos)} produtos.")
    st.write("---")
    st.subheader("Tentando exibir em 4 colunas:")

    # O teste fundamental: criar 4 colunas
    cols = st.columns(4)

    for index, row in df_produtos.iterrows():
        # Distribui cada item em uma coluna
        with cols[index % 4]:
            st.markdown(f"**{row.get('NOME', 'Sem Nome')}**")
            st.markdown(f"R$ {row.get('PRECO', 0.0)}")
            
            if 'LINKIMAGEM' in row and row.get('LINKIMAGEM'):
                st.image(row.get('LINKIMAGEM'), use_container_width=True)
            else:
                st.caption("Sem imagem")
            
            st.divider()
else:
    st.error("Nenhum produto foi carregado da planilha para o teste.")
