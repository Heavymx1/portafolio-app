import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro", layout="wide", page_icon="🏦")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px;}
    .news-card {background-color: #262730; padding: 15px; border-radius: 10px; margin-bottom: 10px; border-left: 5px solid #00CC96;}
    </style>
    """, unsafe_allow_html=True)

st.title("🏦 Terminal Financiera Personal")

# --- CONEXIÓN (TU LINK) ---
# 👇👇👇 ¡VERIFICA QUE ESTE SEA TU LINK! 👇👇👇
URL_HOJA = "https://docs.google.com/spreadsheets/d/1UpgDIh3nuhxz83NQg7KYPu_Boj4C-nP0rrw9YgTjWEo/edit?gid=1838439399#gid=1838439399" 
# 👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆

@st.cache_data(ttl=300) # Caché de 5 minutos para noticias
def cargar_datos_completos():
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
        st.error(f"Error de conexión: {e}")
        return None

# --- FUNCIONES DE ENRIQUECIMIENTO (PRECIO, DIVIDENDOS, NOTICIAS) ---
def obtener_info_mercado(df):
    tickers_unicos = df['Ticker'].unique()
    datos_extra = {}
    
    # Barra de progreso
    progreso = st.progress(0)
    total = len(tickers_unicos)
    
    for i, ticker in enumerate(tickers_unicos):
        t_clean = str(ticker).strip()
        info = {'precio': 0, 'div_yield': 0, 'div_rate': 0, 'news': []}
        
        # Intentar obtener objeto Ticker
        try:
            stock = yf.Ticker(t_clean)
            hist = stock.history(period="1d")
            
            # Si falla, intentar con .MX
            if hist.empty:
                stock = yf.Ticker(t_clean + ".MX")
                hist = stock.history(period="1d")
            
            if not hist.empty:
                info['precio'] = hist['Close'].iloc[-1]
                # Intentar sacar dividendos
                try:
                    info['div_yield'] = stock.info.get('dividendYield', 0)
                    info['div_rate'] = stock.info.get('dividendRate', 0)
                except: pass
                # Intentar sacar noticias
                try:
                    info['news'] = stock.news[:3] # Top 3 noticias
                except: pass
                
        except: pass
        
        datos_extra[ticker] = info
        progreso.progress((i + 1) / total)
    
    progreso.empty()
    return datos_extra

# --- LÓGICA PRINCIPAL ---
if st.button('🔄 Actualizar Terminal'):
    st.cache_data.clear()
    st.rerun()

df = cargar_datos_completos()

if df is not None and not df.empty:
    # 1. Limpieza inicial
    df.columns = df.columns.str.lower().str.strip()
    mapa = {'emisora': 'ticker', 'titulos': 'cantidad', 'costo promedio': 'costo', 'sector': 'sector'}
    df.rename(columns=mapa, inplace=True)
    df.columns = df.columns.str.capitalize()

    # 2. Descargar Info Mercado
    with st.spinner('Analizando mercado, dividendos y noticias...'):
        info_dict = obtener_info_mercado(df)

    # 3. Mapear datos al DataFrame
    df['Precio_Actual'] = df['Ticker'].map(lambda t: info_dict[t]['precio'])
    df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
    df['Costo_Total'] = df['Cantidad'] * df['Costo']
    df['Ganancia_$'] = df['Valor_Mercado'] - df['Costo_Total']
    
    # Calcular Dividendos Anuales Estimados
    df['Div_Tasa'] = df['Ticker'].map(lambda t: info_dict[t]['div_rate'] if info_dict[t]['div_rate'] else 0)
    df['Div_Yield'] = df['Ticker'].map(lambda t: info_dict[t]['div_yield'] if info_dict[t]['div_yield'] else 0)
    df['Pago_Anual_Est'] = df['Cantidad'] * df['Div_Tasa']

    # --- PESTAÑAS (TABS) ---
    tab1, tab2, tab3 = st.tabs(["📊 Portafolio", "💸 Dividendos", "📰 Noticias"])

    # === TAB 1: PORTAFOLIO GENERAL ===
    with tab1:
        total_valor = df['Valor_Mercado'].sum()
        total_ganancia = df['Ganancia_$'].sum()
        
        c1, c2 = st.columns(2)
        c1.metric("Patrimonio Total", f"${total_valor:,.2f}")
        c2.metric("Ganancia Neta", f"${total_ganancia:,.2f}", delta=f"{total_ganancia:,.2f}")
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Distribución")
            path = ['Sector', 'Ticker'] if 'Sector' in df.columns and str(df['Sector'].iloc[0]) != "" else ['Ticker']
            st.plotly_chart(px.sunburst(df, path=path, values='Valor_Mercado'), use_container_width=True)
        with col2:
            st.subheader("Rendimiento")
            st.plotly_chart(px.bar(df, x='Ganancia_$', y='Ticker', orientation='h', color='Ganancia_$'), use_container_width=True)

    # === TAB 2: CALENDARIO DE DIVIDENDOS ===
    with tab2:
        st.subheader("💰 Proyección de Ingresos Pasivos")
        st.info("Nota: Estos valores son estimaciones anuales basadas en el último dividendo declarado.")
        
        total_divs = df['Pago_Anual_Est'].sum()
        yield_promedio = df[df['Pago_Anual_Est']>0]['Div_Yield'].mean() * 100
        
        m1, m2 = st.columns(2)
        m1.metric("Ingreso Pasivo Anual (Estimado)", f"${total_divs:,.2f}")
        m2.metric("Yield Promedio Portafolio", f"{yield_promedio:.2f}%")
        
        # Tabla de Dividendos
        df_divs = df[df['Pago_Anual_Est'] > 0][['Ticker', 'Cantidad', 'Div_Tasa', 'Div_Yield', 'Pago_Anual_Est']]
        df_divs['Div_Yield'] = df_divs['Div_Yield'].apply(lambda x: f"{x*100:.2f}%")
        
        st.dataframe(
            df_divs.sort_values('Pago_Anual_Est', ascending=False)
            .style.format({'Div_Tasa': "${:.2f}", 'Pago_Anual_Est': "${:,.2f}"}),
            use_container_width=True
        )

    # === TAB 3: NOTICIAS INTELIGENTES ===
    with tab3:
        st.subheader("📰 Noticias Relevantes de tus Acciones")
        
        hay_noticias = False
        for ticker in df['Ticker'].unique():
            news = info_dict[ticker]['news']
            if news:
                hay_noticias = True
                with st.expander(f"Noticias de {ticker}", expanded=True):
                    for n in news:
                        # Crear tarjeta de noticia
                        titulo = n.get('title', 'Sin título')
                        link = n.get('link', '#')
                        publicador = n.get('publisher', 'Yahoo Finance')
                        
                        st.markdown(f"""
                        <div class="news-card">
                            <a href="{link}" target="_blank" style="text-decoration: none; color: white;">
                                <strong>{titulo}</strong>
                            </a>
                            <br>
                            <span style="font-size: 0.8em; color: #aaa;">Fuente: {publicador}</span>
                        </div>
                        """, unsafe_allow_html=True)
        
        if not hay_noticias:
            st.warning("No se encontraron noticias recientes para tus activos hoy.")

else:
    st.info("Cargando base de datos...")
