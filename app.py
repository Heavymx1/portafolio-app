import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURACIÓN VISUAL (ESTILO PROFESIONAL) ---
st.set_page_config(page_title="Master Portfolio", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {
        background-color: #1E1E1E;
        border: 1px solid #333;
        padding: 15px;
        border-radius: 10px;
    }
    div[data-testid="stExpander"] {
        background-color: #0E1117;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Dashboard de Inversiones Profesional")

# --- 2. CONFIGURACIÓN DE CONEXIÓN ---
# 👇👇👇 ¡PEGAR AQUÍ TU ENLACE DE GOOGLE SHEETS! 👇👇👇
URL_HOJA = "https://docs.google.com/spreadsheets/d/1UpgDIh3nuhxz83NQg7KYPu_Boj4C-nP0rrw9YgTjWEo/edit?gid=1838439399#gid=1838439399" 
# 👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆

@st.cache_data(ttl=60)
def cargar_datos():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        # --- AQUÍ ESTÁ LA MAGIA HÍBRIDA ---
        # 1. Intentamos leer desde los Secretos de la Nube (Streamlit Cloud)
        if "gcp_service_account" in st.secrets:
            # Si estamos en la nube, usamos la info secreta cargada en memoria
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], 
                scopes=scopes
            )
        # 2. Si no, intentamos leer el archivo local (Tu PC)
        else:
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        # ----------------------------------

        client = gspread.authorize(creds)
        sh = client.open_by_url(URL_HOJA)
        return pd.DataFrame(sh.sheet1.get_all_records())
        
    except Exception as e:
        st.error(f"❌ Error de Conexión: {e}")
        return None

# --- BOTÓN DE ACTUALIZAR ---
if st.button('🔄 Actualizar Mercado'):
    st.cache_data.clear()
    st.rerun()

# --- 3. PROCESAMIENTO DE DATOS ---
df = cargar_datos()

if df is not None and not df.empty:
    try:
        # A. Limpieza de columnas (Para que entienda Emisora/Ticker/Costo/Precio)
        df.columns = df.columns.str.lower().str.strip()
        mapa = {
            'emisora': 'ticker', 'simbolo': 'ticker',
            'titulos': 'cantidad', 'títulos': 'cantidad',
            'costo promedio': 'costo', 'costo': 'costo', 'precio compra': 'costo',
            'sector': 'sector'
        }
        df.rename(columns=mapa, inplace=True)
        df.columns = df.columns.str.capitalize() # Ticker, Cantidad, Costo, Sector

        # B. Descargar Precios en Vivo (Yahoo Finance)
        def get_price(ticker):
            ticker = str(ticker).strip()
            # Intento 1: EE.UU.
            try: return yf.Ticker(ticker).history(period="1d")['Close'].iloc[-1]
            except: pass
            # Intento 2: México
            try: return yf.Ticker(ticker + ".MX").history(period="1d")['Close'].iloc[-1]
            except: return 0

        with st.spinner('📡 Conectando con Wall Street y BMV...'):
            df['Precio_Actual'] = df['Ticker'].apply(get_price)

        # C. Matemática Financiera
        df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
        df['Costo_Total'] = df['Cantidad'] * df['Costo']
        df['Ganancia_$'] = df['Valor_Mercado'] - df['Costo_Total']
        
        # Evitar errores si costo es 0
        df['Rendimiento_%'] = df.apply(
            lambda x: (x['Ganancia_$'] / x['Costo_Total'] * 100) if x['Costo_Total'] > 0 else 0, 
            axis=1
        )

        # --- 4. VISUALIZACIÓN (DASHBOARD) ---
        
        # SECCIÓN 1: KPIs Principales
        total_valor = df['Valor_Mercado'].sum()
        total_ganancia = df['Ganancia_$'].sum()
        total_inversion = df['Costo_Total'].sum()
        total_rendimiento = (total_ganancia / total_inversion * 100) if total_inversion > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Patrimonio Total", f"${total_valor:,.2f}")
        c2.metric("💵 Ganancia Neta", f"${total_ganancia:,.2f}", delta=f"{total_ganancia:,.2f}")
        c3.metric("🚀 Rendimiento Global", f"{total_rendimiento:.2f}%", delta=f"{total_rendimiento:.2f}%")

        st.markdown("---")

        # SECCIÓN 2: Gráficos Estratégicos
        col_graf1, col_graf2 = st.columns(2)
        
        with col_graf1:
            st.subheader("🍰 Tu Diversificación")
            # Usa Sector si existe, si no, usa Ticker
            path = ['Sector', 'Ticker'] if 'Sector' in df.columns and str(df['Sector'].iloc[0]) != "" else ['Ticker']
            fig1 = px.sunburst(df, path=path, values='Valor_Mercado', color_discrete_sequence=px.colors.qualitative.Pastel)
            fig1.update_layout(paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig1, use_container_width=True)
            
        with col_graf2:
            st.subheader("🏆 Ranking de Ganancias")
            df_sorted = df.sort_values('Ganancia_$', ascending=True)
            # Colores: Verde para ganancia, Rojo para pérdida
            fig2 = px.bar(
                df_sorted, 
                x='Ganancia_$', 
                y='Ticker', 
                orientation='h',
                text='Rendimiento_%',
                color='Ganancia_$',
                color_continuous_scale=['#FF4B4B', '#222222', '#00FF7F'] # Rojo -> Oscuro -> Verde
            )
            fig2.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig2.update_layout(xaxis_title="Ganancia ($)", paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig2, use_container_width=True)

        # SECCIÓN 3: Tabla Detallada
        st.subheader("📋 Detalle de Posiciones")
        
        # Estilizar tabla con colores condicionales
        st.dataframe(
            df[['Ticker', 'Cantidad', 'Costo', 'Precio_Actual', 'Ganancia_$', 'Rendimiento_%']]
            .style
            .format({
                'Costo': "${:,.2f}", 'Precio_Actual': "${:,.2f}", 
                'Ganancia_$': "${:,.2f}", 'Rendimiento_%': "{:,.2f}%"
            })
            .background_gradient(subset=['Ganancia_$'], cmap='RdYlGn',