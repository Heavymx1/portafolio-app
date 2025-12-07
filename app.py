import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro V4", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px;}
    .news-card {
        background-color: #262730; 
        padding: 15px; 
        border-radius: 10px; 
        margin-bottom: 10px; 
        border-left: 5px solid #00CC96;
        transition: transform 0.2s;
    }
    .news-card:hover { transform: scale(1.02); }
    a { text-decoration: none; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Financiera: SIC vs BMV")

# --- CONEXIÓN ---
# 👇👇👇 ¡TU LINK AQUÍ! 👇👇👇
URL_HOJA = "https://docs.google.com/spreadsheets/d/1UpgDIh3nuhxz83NQg7KYPu_Boj4C-nP0rrw9YgTjWEo/edit?gid=1838439399#gid=1838439399" 
# 👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆

@st.cache_data(ttl=300) 
def cargar_datos():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        if "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        else:
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        
        client = gspread.authorize(creds)
        sh = client.open_by_url(URL_HOJA)
        # Convertir a string para evitar errores de lectura
        return pd.DataFrame(sh.sheet1.get_all_records()).astype(str)
    except Exception as e:
        st.error(f"Error conexión: {e}")
        return None

# --- MOTOR DE DATOS (Precios y Noticias) ---
def obtener_datos_mercado(tickers):
    data_dict = {}
    progreso = st.progress(0)
    
    for i, t in enumerate(tickers):
        t = str(t).strip()
        info = {'precio': 0, 'news': []}
        
        try:
            # 1. Estrategia de Precio:
            # Intentamos buscar primero como .MX (para tener precio en pesos si estás en México)
            # Si no, buscamos directo (EE.UU.)
            stock_mx = yf.Ticker(t + ".MX")
            hist_mx = stock_mx.history(period="1d")
            
            stock_us = yf.Ticker(t)
            hist_us = stock_us.history(period="1d")

            # Decidir precio (Preferimos MXN si existe, si no USD)
            if not hist_mx.empty:
                info['precio'] = hist_mx['Close'].iloc[-1]
            elif not hist_us.empty:
                info['precio'] = hist_us['Close'].iloc[-1]
            
            # 2. Estrategia de Noticias (CORRECCIÓN):
            # Para noticias, preferimos el ticker de EE.UU. (sin .MX) porque tiene más fuentes
            # Si es una empresa 100% mexicana (ej: CEMEX), usamos la de MX.
            
            # Intentamos sacar noticias del ticker US primero (más robusto)
            try:
                noticias = stock_us.news
                if not noticias and not hist_mx.empty: # Si falla US, probamos MX
                     noticias = stock_mx.news
                info['news'] = noticias[:3] if noticias else []
            except:
                info['news'] = []

        except Exception as e:
            print(f"Error con {t}: {e}")
            
        data_dict[t] = info
        progreso.progress((i + 1) / len(tickers))
    
    progreso.empty()
    return data_dict

if st.button('🔄 Recargar Mercado'):
    st.cache_data.clear()
    st.rerun()

# --- PROCESAMIENTO ---
df = cargar_datos()

if df is not None and not df.empty:
    # Limpieza
    df.columns = df.columns.str.lower().str.strip()
    mapa = {'emisora': 'ticker', 'titulos': 'cantidad', 'costo promedio': 'costo', 'sector': 'sector', 'tipo': 'tipo'}
    df.rename(columns=mapa, inplace=True)
    df.columns = df.columns.str.capitalize()
    
    # Sanitizar números
    def limpiar_num(x):
        try: return float(str(x).replace('$','').replace(',','').strip())
        except: return 0.0
    
    df['Cantidad'] = df['Cantidad'].apply(limpiar_num)
    df['Costo'] = df['Costo'].apply(limpiar_num)
    
    # Si no creaste la columna Tipo, la rellenamos con "General" para que no falle
    if 'Tipo' not in df.columns:
        df['Tipo'] = "General"

    # Descargar datos
    with st.spinner('Conectando con las Bolsas de Valores...'):
        mercado = obtener_datos_mercado(df['Ticker'].unique())

    # Mapear
    df['Precio_Actual'] = df['Ticker'].map(lambda x: mercado[x]['precio'])
    df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
    df['Costo_Total'] = df['Cantidad'] * df['Costo']
    df['Ganancia'] = df['Valor_Mercado'] - df['Costo_Total']
    
    # --- VISUALIZACIÓN ---
    
    # KPIs Globales
    st.markdown("### 🌎 Visión Global")
    k1, k2, k3 = st.columns(3)
    k1.metric("Patrimonio Total", f"${df['Valor_Mercado'].sum():,.2f}")
    k2.metric("Ganancia Total", f"${df['Ganancia'].sum():,.2f}")
    
    # Separación por Bolsa (SIC vs BMV)
    st.markdown("---")
    
    tipos = df['Tipo'].unique()
    
    # Creamos pestañas dinámicas para separar noticias y gráficos
    tab_portafolio, tab_noticias = st.tabs(["📊 Análisis por Bolsa", "📰 Noticias Relevantes"])
    
    with tab_portafolio:
        # Dividimos la pantalla en 2 columnas: SIC a la izquierda, BMV a la derecha (si existen)
        col_sic, col_bmv = st.columns(2)
        
        # --- COLUMNA 1: SIC ---
        with col_sic:
            st.header("🌍 SIC (Internacional)")
            df_sic = df[df['Tipo'].str.upper().str.contains('SIC')]
            
            if not df_sic.empty:
                val_sic = df_sic['Valor_Mercado'].sum()
                gan_sic = df_sic['Ganancia'].sum()
                st.metric("Valor SIC", f"${val_sic:,.2f}", delta=f"${gan_sic:,.2f}")
                
                # Gráficos SIC
                fig1 = px.sunburst(df_sic, path=['Sector', 'Ticker'], values='Valor_Mercado', title="Distribución SIC")
                fig1.update_layout(margin=dict(t=30, l=0, r=0, b=0), height=300)
                st.plotly_chart(fig1, use_container_width=True)
                
                fig2 = px.bar(df_sic, x='Ganancia', y='Ticker', color='Ganancia', title="Ganancias SIC")
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("No hay acciones clasificadas como 'SIC'.")

        # --- COLUMNA 2: BMV ---
        with col_bmv:
            st.header("🇲🇽 BMV (México)")
            df_bmv = df[df['Tipo'].str.upper().str.contains('BMV')]
            
            if not df_bmv.empty:
                val_bmv = df_bmv['Valor_Mercado'].sum()
                gan_bmv = df_bmv['Ganancia'].sum()
                st.metric("Valor BMV", f"${val_bmv:,.2f}", delta=f"${gan_bmv:,.2f}")
                
                # Gráficos BMV
                fig3 = px.sunburst(df_bmv, path=['Sector', 'Ticker'], values='Valor_Mercado', title="Distribución BMV")
                fig3.update_layout(margin=dict(t=30, l=0, r=0, b=0), height=300)
                st.plotly_chart(fig3, use_container_width=True)
                
                fig4 = px.bar(df_bmv, x='Ganancia', y='Ticker', color='Ganancia', title="Ganancias BMV")
                st.plotly_chart(fig4, use_container_width=True)
            else:
                st.info("No hay acciones clasificadas como 'BMV'.")

    # --- PESTAÑA NOTICIAS (CORREGIDA) ---
    with tab_noticias:
        st.subheader("Últimas Noticias")
        
        col_n1, col_n2 = st.columns(2)
        
        with col_n1:
            st.markdown("#### 🌍 Noticias SIC")
            for t in df_sic['Ticker'].unique():
                news = mercado[t]['news']
                if news:
                    with st.expander(f"📌 {t}", expanded=False):
                        for n in news:
                            st.markdown(f"""
                            <div class="news-card">
                                <a href="{n.get('link')}" target="_blank"><strong>{n.get('title')}</strong></a><br>
                                <small style="color:#aaa">{n.get('publisher')} • {t}</small>
                            </div>
                            """, unsafe_allow_html=True)

        with col_n2:
            st.markdown("#### 🇲🇽 Noticias BMV")
            for t in df_bmv['Ticker'].unique():
                news = mercado[t]['news']
                if news:
                    with st.expander(f"📌 {t}", expanded=False):
                        for n in news:
                            st.markdown(f"""
                            <div class="news-card">
                                <a href="{n.get('link')}" target="_blank"><strong>{n.get('title')}</strong></a><br>
                                <small style="color:#aaa">{n.get('publisher')} • {t}</small>
                            </div>
                            """, unsafe_allow_html=True)

else:
    st.info("Esperando conexión a Google Sheets...")
