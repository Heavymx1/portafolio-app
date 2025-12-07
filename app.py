import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Master Portfolio", layout="wide", page_icon="🦁")
st.markdown("""<style>.stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px;}</style>""", unsafe_allow_html=True)
st.title("🦁 Dashboard de Inversiones Profesional")

# --- CONEXIÓN ---
# 👇👇👇 ¡PEGAR AQUÍ TU LINK! 👇👇👇
URL_HOJA = "https://docs.google.com/spreadsheets/d/1UpgDIh3nuhxz83NQg7KYPu_Boj4C-nP0rrw9YgTjWEo/edit?gid=1838439399#gid=1838439399" 
# 👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆

@st.cache_data(ttl=60)
def cargar_datos():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        if "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        else:
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_url(URL_HOJA)
        return pd.DataFrame(sh.sheet1.get_all_records())
    except Exception as e:
        st.error(f"Error: {e}")
        return None

if st.button('🔄 Actualizar Mercado'):
    st.cache_data.clear()
    st.rerun()

# --- PROCESO ---
df = cargar_datos()

if df is not None and not df.empty:
    try:
        # Limpieza
        df.columns = df.columns.str.lower().str.strip()
        mapa = {'emisora': 'ticker', 'titulos': 'cantidad', 'costo promedio': 'costo', 'sector': 'sector'}
        df.rename(columns=mapa, inplace=True)
        df.columns = df.columns.str.capitalize()

        # Precios
        def get_price(ticker):
            try: return yf.Ticker(str(ticker).strip()).history(period="1d")['Close'].iloc[-1]
            except: 
                try: return yf.Ticker(str(ticker).strip() + ".MX").history(period="1d")['Close'].iloc[-1]
                except: return 0

        with st.spinner('Cargando datos...'):
            df['Precio_Actual'] = df['Ticker'].apply(get_price)

        df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
        df['Costo_Total'] = df['Cantidad'] * df['Costo']
        df['Ganancia_$'] = df['Valor_Mercado'] - df['Costo_Total']
        df['Rendimiento_%'] = df.apply(lambda x: (x['Ganancia_$']/x['Costo_Total']*100) if x['Costo_Total']>0 else 0, axis=1)

        # --- VISUALES ---
        c1, c2 = st.columns(2)
        c1.metric("💰 Patrimonio", f"${df['Valor_Mercado'].sum():,.2f}")
        c2.metric("💵 Ganancia", f"${df['Ganancia_$'].sum():,.2f}")
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Diversificación")
            path = ['Sector', 'Ticker'] if 'Sector' in df.columns and str(df['Sector'].iloc[0]) != "" else ['Ticker']
            st.plotly_chart(px.sunburst(df, path=path, values='Valor_Mercado'), use_container_width=True)
        with col2:
            st.subheader("Ganancias")
            st.plotly_chart(px.bar(df, x='Ganancia_$', y='Ticker', orientation='h', color='Ganancia_$'), use_container_width=True)

        # --- TABLA SEGURA (SIN ERROR DE PARÉNTESIS) ---
        st.subheader("Detalle")
        
        # 1. Seleccionar columnas
        datos = df[['Ticker', 'Cantidad', 'Costo', 'Precio_Actual', 'Ganancia_$', 'Rendimiento_%']]
        
        # 2. Crear objeto de estilo (paso por paso)
        estilo = datos.style.format({
            'Costo': "${:,.2f}", 
            'Precio_Actual': "${:,.2f}", 
            'Ganancia_$': "${:,.2f}", 
            'Rendimiento_%': "{:,.2f}%"
        })
        
        # 3. Aplicar color (Intenta usar matplotlib, si falla no rompe la app)
        try:
            estilo = estilo.background_gradient(subset=['Ganancia_$'], cmap='RdYlGn')
        except:
            pass # Si falla el color, muestra la tabla normal
            
        # 4. Mostrar
        st.dataframe(estilo, use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Configura tu link de Google Sheets en el código.")
