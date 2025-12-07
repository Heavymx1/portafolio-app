import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro V5", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px;}
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Patrimonial: Dividendos & Valor")

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
        return pd.DataFrame(sh.sheet1.get_all_records()).astype(str)
    except Exception as e:
        st.error(f"Error conexión: {e}")
        return None

# --- MOTOR DE DATOS (Precios y Dividendos) ---
def obtener_datos_mercado(tickers):
    data_dict = {}
    progreso = st.progress(0)
    
    for i, t in enumerate(tickers):
        t = str(t).strip()
        info = {'precio': 0, 'div_rate': 0, 'div_yield': 0}
        
        try:
            # Lógica: Intentar MX primero, luego US
            stock = yf.Ticker(t + ".MX")
            hist = stock.history(period="1d")
            usado_mx = True
            
            if hist.empty:
                stock = yf.Ticker(t)
                hist = stock.history(period="1d")
                usado_mx = False
            
            if not hist.empty:
                info['precio'] = hist['Close'].iloc[-1]
                
                # Intentar obtener dividendos
                # Yahoo a veces guarda esto en 'info'
                try:
                    info['div_rate'] = stock.info.get('dividendRate', 0) # Dinero anual por acción
                    info['div_yield'] = stock.info.get('dividendYield', 0) # Porcentaje
                    
                    # Fix: A veces div_rate viene None
                    if info['div_rate'] is None: info['div_rate'] = 0
                    if info['div_yield'] is None: info['div_yield'] = 0
                    
                except: pass

        except Exception as e:
            print(f"Error {t}: {e}")
            
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
    # 1. Limpieza
    df.columns = df.columns.str.lower().str.strip()
    mapa = {'emisora': 'ticker', 'titulos': 'cantidad', 'costo promedio': 'costo', 'sector': 'sector', 'tipo': 'tipo'}
    df.rename(columns=mapa, inplace=True)
    df.columns = df.columns.str.capitalize()
    
    # 2. Sanitizar números (Quitar $ y ,)
    def limpiar_num(x):
        try: return float(str(x).replace('$','').replace(',','').strip())
        except: return 0.0
    
    df['Cantidad'] = df['Cantidad'].apply(limpiar_num)
    df['Costo'] = df['Costo'].apply(limpiar_num)
    
    if 'Tipo' not in df.columns: df['Tipo'] = "General"

    # 3. Descargar datos
    with st.spinner('Analizando Dividendos y Precios...'):
        mercado = obtener_datos_mercado(df['Ticker'].unique())

    # 4. Mapear resultados
    df['Precio_Actual'] = df['Ticker'].map(lambda x: mercado[x]['precio'])
    df['Div_Pago_Accion'] = df['Ticker'].map(lambda x: mercado[x]['div_rate'])
    df['Div_Yield_%'] = df['Ticker'].map(lambda x: mercado[x]['div_yield'] * 100 if mercado[x]['div_yield'] else 0)

    # 5. Cálculos Financieros
    df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
    df['Costo_Total'] = df['Cantidad'] * df['Costo']
    df['Ganancia'] = df['Valor_Mercado'] - df['Costo_Total']
    
    # Cálculo seguro de Rendimiento %
    df['Rendimiento_%'] = df.apply(lambda x: (x['Ganancia']/x['Costo_Total']*100) if x['Costo_Total']>0 else 0, axis=1)
    
    # Cálculo de Ingreso Pasivo Anual (Estimado)
    df['Pago_Anual_Total'] = df['Cantidad'] * df['Div_Pago_Accion']

    # --- PESTAÑAS ---
    tab_dash, tab_divs = st.tabs(["📊 Dashboard General", "💸 Dividendos"])

    # ==========================================
    # PESTAÑA 1: DASHBOARD GENERAL (SIC vs BMV)
    # ==========================================
    with tab_dash:
        # KPIs Globales
        k1, k2, k3 = st.columns(3)
        k1.metric("Patrimonio Total", f"${df['Valor_Mercado'].sum():,.2f}")
        k2.metric("Ganancia Total", f"${df['Ganancia'].sum():,.2f}", delta=f"{df['Ganancia'].sum():,.2f}")
        k3.metric("Rendimiento Global", f"{(df['Ganancia'].sum()/df['Costo_Total'].sum()*100):.2f}%")
        
        st.markdown("---")
        
        # Separación visual SIC vs BMV
        col_sic, col_bmv = st.columns(2)
        
        # -- LADO SIC --
        with col_sic:
            st.header("🌍 SIC (Internacional)")
            df_sic = df[df['Tipo'].str.upper().str.contains('SIC')]
            if not df_sic.empty:
                st.metric("Valor SIC", f"${df_sic['Valor_Mercado'].sum():,.2f}")
                st.plotly_chart(px.sunburst(df_sic, path=['Sector', 'Ticker'], values='Valor_Mercado'), use_container_width=True)
                st.plotly_chart(px.bar(df_sic, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', color_continuous_scale='RdYlGn'), use_container_width=True)
        
        # -- LADO BMV --
        with col_bmv:
            st.header("🇲🇽 BMV (México)")
            df_bmv = df[df['Tipo'].str.upper().str.contains('BMV')]
            if not df_bmv.empty:
                st.metric("Valor BMV", f"${df_bmv['Valor_Mercado'].sum():,.2f}")
                st.plotly_chart(px.sunburst(df_bmv, path=['Sector', 'Ticker'], values='Valor_Mercado'), use_container_width=True)
                st.plotly_chart(px.bar(df_bmv, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', color_continuous_scale='RdYlGn'), use_container_width=True)

        # -- TABLA GENERAL CON MAPA DE CALOR CORREGIDO --
        st.subheader("📋 Resumen de Acciones")
        
        # Seleccionamos columnas
        cols_dash = ['Ticker', 'Tipo', 'Cantidad', 'Costo', 'Precio_Actual', 'Ganancia', 'Rendimiento_%']
        df_show = df[cols_dash].copy()
        
        # Aplicamos estilo (Aquí está el truco para que no falle el color)
        st.dataframe(
            df_show.style
            .format({
                'Costo': "${:,.2f}",
                'Precio_Actual': "${:,.2f}",
                'Ganancia': "${:,.2f}",
                'Rendimiento_%': "{:,.2f}%"
            })
            # El gradiente se aplica sobre los NÚMEROS, no sobre el texto formateado
            .background_gradient(subset=['Ganancia', 'Rendimiento_%'], cmap='RdYlGn'),
            use_container_width=True
        )

    # ==========================================
    # PESTAÑA 2: DIVIDENDOS
    # ==========================================
    with tab_divs:
        st.subheader("💰 Calendario de Pagos & Proyección")
        
        total_income = df['Pago_Anual_Total'].sum()
        yield_avg = df[df['Pago_Anual_Total']>0]['Div_Yield_%'].mean()
        
        d1, d2 = st.columns(2)
        d1.metric("Ingreso Pasivo Anual (Estimado)", f"${total_income:,.2f}", help="Suma de (Tus Acciones * Dividendo Anual)")
        d2.metric("Yield Promedio", f"{yield_avg:.2f}%")
        
        st.markdown("#### 💎 Acciones que pagan dividendos")
        
        # Filtramos solo las que pagan > 0
        df_divs = df[df['Pago_Anual_Total'] > 0].copy()
        
        # Seleccionamos columnas relevantes para dividendos
        cols_divs = ['Ticker', 'Cantidad', 'Div_Yield_%', 'Div_Pago_Accion', 'Pago_Anual_Total']
        df_divs_show = df_divs[cols_divs].sort_values('Pago_Anual_Total', ascending=False)
        
        # Tabla específica de dividendos
        st.dataframe(
            df_divs_show.style
            .format({
                'Div_Yield_%': "{:.2f}%",
                'Div_Pago_Accion': "${:.2f}",
                'Pago_Anual_Total': "${:,.2f}"
            })
            .bar(subset=['Pago_Anual_Total'], color='#00CC96'), # Barra de progreso verde
            use_container_width=True
        )
        
        if df_divs.empty:
            st.warning("Yahoo Finance no reporta dividendos para tus acciones actuales o no pagan dividendos.")

else:
    st.info("Cargando portafolio...")
