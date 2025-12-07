import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="DASHBOARD PRO", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px;}
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Patrimonial: Maestra")

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

# --- MOTOR DE DATOS ---
def obtener_datos_mercado(tickers):
    data_dict = {}
    progreso = st.progress(0)
    
    for i, t in enumerate(tickers):
        t = str(t).strip()
        info = {'precio': 0, 'div_rate': 0, 'div_yield': 0}
        try:
            stock = yf.Ticker(t + ".MX")
            hist = stock.history(period="1d")
            if hist.empty:
                stock = yf.Ticker(t)
                hist = stock.history(period="1d")
            
            if not hist.empty:
                info['precio'] = hist['Close'].iloc[-1]
                try:
                    info['div_rate'] = stock.info.get('dividendRate', 0)
                    info['div_yield'] = stock.info.get('dividendYield', 0)
                    if info['div_rate'] is None: info['div_rate'] = 0
                    if info['div_yield'] is None: info['div_yield'] = 0
                except: pass
        except: pass  
        data_dict[t] = info
        progreso.progress((i + 1) / len(tickers))
    
    progreso.empty()
    return data_dict

if st.button('🔄 Recargar Mercado'):
    st.cache_data.clear()
    st.rerun()

# --- PROCESAMIENTO ---
df_raw = cargar_datos()

if df_raw is not None and not df_raw.empty:
    # 1. Limpieza
    df_raw.columns = df_raw.columns.str.lower().str.strip()
    mapa = {'emisora': 'ticker', 'titulos': 'cantidad', 'costo promedio': 'costo', 'sector': 'sector', 'tipo': 'tipo'}
    df_raw.rename(columns=mapa, inplace=True)
    df_raw.columns = df_raw.columns.str.capitalize()
    
    # 2. Sanitizar
    def limpiar_num(x):
        try: return float(str(x).replace('$','').replace(',','').strip())
        except: return 0.0
    
    df_raw['Cantidad'] = df_raw['Cantidad'].apply(limpiar_num)
    df_raw['Costo'] = df_raw['Costo'].apply(limpiar_num)
    if 'Tipo' not in df_raw.columns: df_raw['Tipo'] = "General"
    if 'Sector' not in df_raw.columns: df_raw['Sector'] = "Otros"

    # 3. Agrupación (Consolidar Tickers Duplicados)
    df_raw['Inversion_Total'] = df_raw['Cantidad'] * df_raw['Costo']
    df = df_raw.groupby('Ticker', as_index=False).agg({
        'Tipo': 'first',
        'Sector': 'first',
        'Cantidad': 'sum',
        'Inversion_Total': 'sum'
    })
    df['Costo'] = df['Inversion_Total'] / df['Cantidad']

    # 4. Descargar Mercado
    with st.spinner('Actualizando precios y dividendos...'):
        mercado = obtener_datos_mercado(df['Ticker'].unique())

    # 5. Cálculos
    df['Precio_Actual'] = df['Ticker'].map(lambda x: mercado[x]['precio'])
    df['Div_Pago_Accion'] = df['Ticker'].map(lambda x: mercado[x]['div_rate'])
    df['Div_Yield_%'] = df['Ticker'].map(lambda x: mercado[x]['div_yield'] * 100 if mercado[x]['div_yield'] else 0)

    df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
    df['Costo_Total'] = df['Cantidad'] * df['Costo']
    df['Ganancia'] = df['Valor_Mercado'] - df['Costo_Total']
    df['Rendimiento_%'] = df.apply(lambda x: (x['Ganancia']/x['Costo_Total']*100) if x['Costo_Total']>0 else 0, axis=1)
    
    # --- CÁLCULOS NUEVOS DE DIVIDENDOS ---
    df['Pago_Anual_Total'] = df['Cantidad'] * df['Div_Pago_Accion']
    df['Pago_Mensual_Est'] = df['Pago_Anual_Total'] / 12  # <--- NUEVO: Promedio Mensual

    # --- PESTAÑAS ---
    tab_dash, tab_divs = st.tabs(["📊 Dashboard Consolidado", "💸 Estrategia de Dividendos"])

    # Estilos de color (Sin gradientes locos)
    def color_fondo(val):
        color = '#113311' if val >= 0 else '#331111' 
        return f'background-color: {color}'

    # ==========================
    # PESTAÑA 1: DASHBOARD
    # ==========================
    with tab_dash:
        # KPIs
        k1, k2, k3 = st.columns(3)
        k1.metric("Patrimonio Total", f"${df['Valor_Mercado'].sum():,.2f}")
        k2.metric("Ganancia Total", f"${df['Ganancia'].sum():,.2f}", delta=f"{df['Ganancia'].sum():,.2f}")
        rend_global = (df['Ganancia'].sum()/df['Costo_Total'].sum()*100) if df['Costo_Total'].sum() > 0 else 0
        k3.metric("Rendimiento Global", f"{rend_global:.2f}%")
        
        st.markdown("---")
        
        # Gráficos
        c_sic, c_bmv = st.columns(2)
        with c_sic:
            st.header("🌍 SIC")
            df_sic = df[df['Tipo'].str.upper().str.contains('SIC')]
            if not df_sic.empty:
                st.metric("Valor SIC", f"${df_sic['Valor_Mercado'].sum():,.2f}")
                st.plotly_chart(px.sunburst(df_sic, path=['Sector', 'Ticker'], values='Valor_Mercado'), use_container_width=True)
        with c_bmv:
            st.header("🇲🇽 BMV")
            df_bmv = df[df['Tipo'].str.upper().str.contains('BMV')]
            if not df_bmv.empty:
                st.metric("Valor BMV", f"${df_bmv['Valor_Mercado'].sum():,.2f}")
                st.plotly_chart(px.sunburst(df_bmv, path=['Sector', 'Ticker'], values='Valor_Mercado'), use_container_width=True)

        st.subheader("📋 Resumen Consolidado")
        cols_show = ['Ticker', 'Tipo', 'Cantidad', 'Costo', 'Precio_Actual', 'Ganancia', 'Rendimiento_%']
        st.dataframe(
            df[cols_show].style.format({
                'Costo': "${:,.2f}", 'Precio_Actual': "${:,.2f}", 
                'Ganancia': "${:,.2f}", 'Rendimiento_%': "{:,.2f}%"
            }).applymap(color_fondo, subset=['Ganancia', 'Rendimiento_%']),
            use_container_width=True
        )

    # ==========================
    # PESTAÑA 2: DIVIDENDOS (MEJORADA)
    # ==========================
    with tab_divs:
        st.subheader("💰 Flujo de Efectivo (Cashflow)")
        
        # Filtramos solo las que pagan
        df_divs = df[df['Pago_Anual_Total'] > 0].copy()
        
        # 1. KPIs DE DIVIDENDOS
        total_anual = df_divs['Pago_Anual_Total'].sum()
        total_mensual = df_divs['Pago_Mensual_Est'].sum()
        capital_generador = df_divs['Valor_Mercado'].sum() # Cuánto dinero tienes trabajando en dividendos
        
        col_d1, col_d2, col_d3 = st.columns(3)
        col_d1.metric("Ingreso Anual (Proyectado)", f"${total_anual:,.2f}")
        col_d2.metric("Ingreso Mensual (Promedio)", f"${total_mensual:,.2f}", delta="Disponible al mes")
        col_d3.metric("Capital Generador", f"${capital_generador:,.2f}", help="Valor total de las acciones que te pagan dividendos")

        st.markdown("---")
        
        # 2. TABLA DETALLADA CON MENSUALIDAD
        st.markdown("#### 📅 Desglose de Pagos")
        
        cols_divs = ['Ticker', 'Cantidad', 'Div_Yield_%', 'Pago_Anual_Total', 'Pago_Mensual_Est']
        
        st.dataframe(
            df_divs.sort_values('Pago_Mensual_Est', ascending=False)[cols_divs]
            .style
            .format({
                'Div_Yield_%': "{:.2f}%",
                'Pago_Anual_Total': "${:,.2f}",
                'Pago_Mensual_Est': "${:,.2f}" # <--- Nueva Columna Formateada
            })
            .bar(subset=['Pago_Mensual_Est'], color='#00CC96'), # Barra visual para ver cuál paga más
            use_container_width=True
        )
        
        if df_divs.empty:
            st.info("Actualmente tus acciones no reportan dividendos en Yahoo Finance.")

else:
    st.info("Cargando portafolio...")

