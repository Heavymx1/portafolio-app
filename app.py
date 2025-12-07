import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro V9", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px;}
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Patrimonial: Multi-Activos")

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

# --- MOTOR DE DATOS (LIMPIEZA PARA ETFS Y ACCIONES) ---
def obtener_datos_mercado(tickers):
    data_dict = {}
    progreso = st.progress(0)
    
    for i, t_original in enumerate(tickers):
        # 🚨 LIMPIEZA TOTAL: Esto arregla "AMZN N", "CSCO *" y también ETFs raros
        t_clean = str(t_original).replace('*', '').replace(' N', '').strip()
        
        info = {'precio': 0, 'div_rate': 0, 'div_yield': 0}
        
        try:
            # 1. Prioridad México (.MX) para tener precios en PESOS
            stock = yf.Ticker(t_clean + ".MX")
            hist = stock.history(period="1d")
            
            # 2. Si falla, busca en EE.UU.
            if hist.empty:
                stock = yf.Ticker(t_clean)
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
        
        data_dict[t_original] = info
        progreso.progress((i + 1) / len(tickers))
    
    progreso.empty()
    return data_dict

if st.button('🔄 Recargar Mercado'):
    st.cache_data.clear()
    st.rerun()

# --- PROCESAMIENTO ---
df_raw = cargar_datos()

if df_raw is not None and not df_raw.empty:
    # 1. Limpieza Columnas
    df_raw.columns = df_raw.columns.str.lower().str.strip()
    mapa = {'emisora': 'ticker', 'titulos': 'cantidad', 'costo promedio': 'costo', 'sector': 'sector', 'tipo': 'tipo'}
    df_raw.rename(columns=mapa, inplace=True)
    df_raw.columns = df_raw.columns.str.capitalize()
    
    # 2. Sanitizar Números
    def limpiar_num(x):
        try: return float(str(x).replace('$','').replace(',','').strip())
        except: return 0.0
    
    df_raw['Cantidad'] = df_raw['Cantidad'].apply(limpiar_num)
    df_raw['Costo'] = df_raw['Costo'].apply(limpiar_num)
    if 'Tipo' not in df_raw.columns: df_raw['Tipo'] = "General"
    if 'Sector' not in df_raw.columns: df_raw['Sector'] = "Otros"

    # 3. Agrupación Inteligente
    df_raw['Inversion_Total'] = df_raw['Cantidad'] * df_raw['Costo']
    df = df_raw.groupby('Ticker', as_index=False).agg({
        'Tipo': 'first',
        'Sector': 'first',
        'Cantidad': 'sum',
        'Inversion_Total': 'sum'
    })
    df['Costo'] = df.apply(lambda x: x['Inversion_Total'] / x['Cantidad'] if x['Cantidad'] > 0 else 0, axis=1)

    # 4. Descargar Mercado
    with st.spinner('Analizando Acciones y ETFs...'):
        mercado = obtener_datos_mercado(df['Ticker'].unique())

    # 5. Cálculos Finales
    df['Precio_Actual'] = df['Ticker'].map(lambda x: mercado[x]['precio'])
    df['Div_Pago_Accion'] = df['Ticker'].map(lambda x: mercado[x]['div_rate'])
    df['Div_Yield_%'] = df['Ticker'].map(lambda x: mercado[x]['div_yield'] * 100 if mercado[x]['div_yield'] else 0)

    df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
    df['Costo_Total'] = df['Cantidad'] * df['Costo']
    df['Ganancia'] = df['Valor_Mercado'] - df['Costo_Total']
    df['Rendimiento_%'] = df.apply(lambda x: (x['Ganancia']/x['Costo_Total']*100) if x['Costo_Total']>0 else 0, axis=1)
    df['Pago_Anual_Total'] = df['Cantidad'] * df['Div_Pago_Accion']
    df['Pago_Mensual_Est'] = df['Pago_Anual_Total'] / 12 

    # --- VISUALIZACIÓN ---
    tab_dash, tab_divs = st.tabs(["📊 Dashboard General", "💸 Dividendos"])

    def color_fondo(val):
        color = '#113311' if val >= 0 else '#331111' 
        return f'background-color: {color}'

    # ==========================
    # PESTAÑA 1: DASHBOARD (AHORA CON 3 COLUMNAS)
    # ==========================
    with tab_dash:
        # KPIs Globales
        k1, k2, k3 = st.columns(3)
        k1.metric("Patrimonio Total", f"${df['Valor_Mercado'].sum():,.2f}")
        k2.metric("Ganancia Total", f"${df['Ganancia'].sum():,.2f}", delta=f"{df['Ganancia'].sum():,.2f}")
        rend_global = (df['Ganancia'].sum()/df['Costo_Total'].sum()*100) if df['Costo_Total'].sum() > 0 else 0
        k3.metric("Rendimiento Global", f"{rend_global:.2f}%")
        
        st.markdown("---")
        
        # 🚨 AQUÍ ESTÁ EL CAMBIO: 3 COLUMNAS 🚨
        col_sic, col_bmv, col_etf = st.columns(3)
        
        # --- COLUMNA 1: SIC (Internacional) ---
        with col_sic:
            st.header("🌍 SIC")
            df_sic = df[df['Tipo'].str.upper().str.contains('SIC')]
            if not df_sic.empty:
                st.metric("Total SIC", f"${df_sic['Valor_Mercado'].sum():,.2f}")
                st.plotly_chart(px.sunburst(df_sic, path=['Sector', 'Ticker'], values='Valor_Mercado'), use_container_width=True)
                st.plotly_chart(px.bar(df_sic, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', color_continuous_scale='RdYlGn'), use_container_width=True)
            else:
                st.info("Sin acciones tipo SIC")

        # --- COLUMNA 2: BMV (Nacional) ---
        with col_bmv:
            st.header("🇲🇽 BMV")
            df_bmv = df[df['Tipo'].str.upper().str.contains('BMV')]
            if not df_bmv.empty:
                st.metric("Total BMV", f"${df_bmv['Valor_Mercado'].sum():,.2f}")
                st.plotly_chart(px.sunburst(df_bmv, path=['Sector', 'Ticker'], values='Valor_Mercado'), use_container_width=True)
                st.plotly_chart(px.bar(df_bmv, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', color_continuous_scale='RdYlGn'), use_container_width=True)
            else:
                st.info("Sin acciones tipo BMV")

        # --- COLUMNA 3: ETFs (Fondos) ---
        with col_etf:
            st.header("🛡️ ETFs")
            df_etf = df[df['Tipo'].str.upper().str.contains('ETF')]
            if not df_etf.empty:
                st.metric("Total ETFs", f"${df_etf['Valor_Mercado'].sum():,.2f}")
                # Gráfico Solar para ETFs
                st.plotly_chart(px.sunburst(df_etf, path=['Ticker'], values='Valor_Mercado'), use_container_width=True)
                # Barras para ETFs
                st.plotly_chart(px.bar(df_etf, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', color_continuous_scale='RdYlGn'), use_container_width=True)
            else:
                st.info("Sin activos tipo ETF")

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
    # PESTAÑA 2: DIVIDENDOS
    # ==========================
    with tab_divs:
        st.subheader("💰 Flujo de Efectivo")
        df_divs = df[df['Pago_Anual_Total'] > 0].copy()
        
        if not df_divs.empty:
            t_anual = df_divs['Pago_Anual_Total'].sum()
            t_mensual = df_divs['Pago_Mensual_Est'].sum()
            
            d1, d2, d3 = st.columns(3)
            d1.metric("Ingreso Anual", f"${t_anual:,.2f}")
            d2.metric("Ingreso Mensual", f"${t_mensual:,.2f}")
            d3.metric("Capital Generador", f"${df_divs['Valor_Mercado'].sum():,.2f}")

            st.dataframe(
                df_divs.sort_values('Pago_Mensual_Est', ascending=False)[['Ticker', 'Tipo', 'Div_Yield_%', 'Pago_Mensual_Est']]
                .style.format({'Div_Yield_%': "{:.2f}%", 'Pago_Mensual_Est': "${:,.2f}"})
                .bar(subset=['Pago_Mensual_Est'], color='#00CC96'),
                use_container_width=True
            )
        else:
            st.info("No hay dividendos reportados.")

else:
    st.info("Cargando portafolio...")
