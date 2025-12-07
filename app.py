import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro V17 (GBM)", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 10px; border-radius: 8px;}
    .stButton>button {width: 100%; background-color: #00CC96; color: white; border: none; font-weight: bold;}
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Patrimonial: Modo GBM")

# --- CONEXIÓN ---
# 👇👇👇 ¡TU LINK AQUÍ! 👇👇👇
URL_HOJA = "https://docs.google.com/spreadsheets/d/1UpgDIh3nuhxz83NQg7KYPu_Boj4C-nP0rrw9YgTjWEo/edit?gid=1838439399#gid=1838439399" 
# 👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆

@st.cache_data(ttl=0) 
def cargar_datos_google():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        if "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        else:
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        
        client = gspread.authorize(creds)
        sh = client.open_by_url(URL_HOJA)
        # Traemos todo como texto para limpiarlo con Python
        return pd.DataFrame(sh.sheet1.get_all_records()).astype(str)
    except Exception as e:
        st.error(f"Error Google Sheets: {e}")
        return None

# --- MOTOR DE HISTORIA ---
@st.cache_data(ttl=300)
def generar_grafico_historico(df_real):
    hist_usd = yf.Ticker("USDMXN=X").history(period="6mo")['Close']
    df_historia = pd.DataFrame(index=hist_usd.index)
    df_historia['Valor_Total'] = 0.0
    
    CORRECCIONES = {'SPYL': 'SPLG', 'IVVPESO': 'IVVPESO.MX', 'NAFTRAC': 'NAFTRAC.MX'}
    
    for i, row in df_real.iterrows():
        t = row['Ticker']
        qty = row['Cantidad']
        t_clean = str(t).replace('*', '').replace(' N', '').strip()
        t_busqueda = CORRECCIONES.get(t_clean, t_clean)
        
        try:
            hist = yf.Ticker(t_busqueda + ".MX").history(period="6mo")['Close']
            es_mxn = True
            if hist.empty:
                hist = yf.Ticker(t_busqueda).history(period="6mo")['Close']
                es_mxn = False
            
            if not hist.empty:
                hist.index = hist.index.tz_localize(None) 
                hist = hist.reindex(df_historia.index, method='ffill').fillna(0)
                if not es_mxn: hist = hist * hist_usd.values
                df_historia['Valor_Total'] += (hist * qty)
        except: pass
    return df_historia

# --- MOTOR DE PRECIOS ---
def obtener_datos_mercado(tickers):
    data_dict = {}
    try: usd_now = yf.Ticker("USDMXN=X").history(period="1d")['Close'].iloc[-1]
    except: usd_now = 17.50
    CORRECCIONES = {'SPYL': 'SPLG', 'IVVPESO': 'IVVPESO.MX', 'NAFTRAC': 'NAFTRAC.MX'}
    
    for t_original in tickers:
        t_clean = str(t_original).replace('*', '').replace(' N', '').strip()
        t_busqueda = CORRECCIONES.get(t_clean, t_clean)
        info = {'precio': 0, 'div_rate': 0, 'div_yield': 0}
        try:
            stock = yf.Ticker(t_busqueda + ".MX")
            hist = stock.history(period="1d")
            es_mxn = True
            if hist.empty:
                stock = yf.Ticker(t_busqueda)
                hist = stock.history(period="1d")
                es_mxn = False
                
            if not hist.empty:
                precio = hist['Close'].iloc[-1]
                if not es_mxn: info['precio'] = precio * usd_now
                else: info['precio'] = precio
                
                try:
                    r = stock.info.get('dividendRate', 0) or 0
                    y = stock.info.get('dividendYield', 0) or 0
                    if not es_mxn: r = r * usd_now
                    info['div_rate'] = r
                    info['div_yield'] = y
                except: pass
        except: pass  
        data_dict[t_original] = info
    return data_dict

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Control")
    if st.button('🔄 ACTUALIZAR AHORA'):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Actualizado: {datetime.now().strftime('%H:%M:%S')}")

# --- LÓGICA PRINCIPAL ---
df_raw = cargar_datos_google()

if df_raw is not None and not df_raw.empty:
    # 🚨 PASO 1: TRADUCCIÓN DE COLUMNAS GBM -> SISTEMA 🚨
    # Convertimos todo a minúsculas
    df_raw.columns = df_raw.columns.str.lower().str.strip()
    
    # Mapa Específico para GBM
    mapa_gbm = {
        'emisora': 'ticker',        # GBM usa "Emisora"
        'emisora/serie': 'ticker',  # A veces viene junto
        'titulos': 'cantidad',      # GBM usa "Títulos"
        'títulos': 'cantidad',
        'costo promedio': 'costo',  # GBM usa "Costo promedio"
        'costo prom.': 'costo',
        'tipo': 'tipo',             # Columna manual tuya
        'sector': 'sector',         # Columna manual tuya (opcional)
        'notas': 'notas'            # Columna manual tuya
    }
    df_raw.rename(columns=mapa_gbm, inplace=True)
    df_raw.columns = df_raw.columns.str.capitalize()
    
    # Validación: Si no encuentra las columnas clave, avisa pero no explota
    if 'Ticker' not in df_raw.columns or 'Cantidad' not in df_raw.columns:
        st.error("⚠️ No detecto las columnas de GBM ('Emisora', 'Títulos'). Revisa tu Excel.")
        st.stop()

    # 🚨 PASO 2: LIMPIEZA PROFUNDA DE NÚMEROS (FORMATO MONEDA GBM) 🚨
    def clean_gbm_money(x): 
        try:
            # Quitamos el signo $, las comas, y espacios
            clean_str = str(x).replace('$', '').replace(',', '').strip()
            return float(clean_str)
        except: return 0.0
    
    df_raw['Cantidad'] = df_raw['Cantidad'].apply(clean_gbm_money)
    df_raw['Costo'] = df_raw['Costo'].apply(clean_gbm_money)
    
    # Rellenar columnas manuales si no existen
    for c in ['Tipo','Sector','Notas']: 
        if c not in df_raw.columns: df_raw[c] = ""
    
    # Autoclasificación por defecto
    df_raw['Sector'] = df_raw['Sector'].replace('', 'General')
    df_raw['Tipo'] = df_raw['Tipo'].replace('', 'General')

    # 3. Agrupación (Consolidar filas de GBM)
    # Calculamos Inversión Total basada en el Costo Promedio que reporta GBM
    df_raw['Inversion_Total'] = df_raw['Cantidad'] * df_raw['Costo']
    
    df = df_raw.groupby('Ticker', as_index=False).agg({
        'Tipo': 'first', 'Sector': 'first', 'Cantidad': 'sum', 
        'Inversion_Total': 'sum', 'Notas': 'first'
    })
    
    # Costo Promedio Ponderado
    df['Costo'] = df.apply(lambda x: x['Inversion_Total'] / x['Cantidad'] if x['Cantidad'] > 0 else 0, axis=1)

    # 4. Mercado
    mercado = obtener_datos_mercado(df['Ticker'].unique())
    
    df['Precio_Actual'] = df['Ticker'].map(lambda x: mercado[x]['precio'])
    df['Div_Rate'] = df['Ticker'].map(lambda x: mercado[x]['div_rate'])
    df['Div_Yield'] = df['Ticker'].map(lambda x: mercado[x]['div_yield']*100)

    # 5. Cálculos Finales
    df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
    
    # Ganancia Real = Valor Mercado - Inversión (Calculada con datos de GBM)
    df['Ganancia'] = df['Valor_Mercado'] - df['Inversion_Total']
    
    df['Rend_%'] = df.apply(lambda x: (x['Ganancia']/x['Inversion_Total']*100) if x['Inversion_Total']>0 else 0, axis=1)
    df['Pago_Anual'] = df['Cantidad'] * df['Div_Rate']
    df['Pago_Mensual'] = df['Pago_Anual'] / 12

    # Separación
    df_real = df[df['Cantidad'] > 0].copy()
    df_watch = df[df['Cantidad'] == 0].copy()

    # --- PESTAÑAS ---
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard GBM", "💸 Dividendos", "🎯 Watchlist"])

    def estilo(df_in):
        return df_in.style.format({
            'Costo': "${:,.2f}", 'Precio_Actual': "${:,.2f}", 'Inversion_Total': "${:,.2f}",
            'Valor_Mercado': "${:,.2f}", 'Ganancia': "${:,.2f}", 'Rend_%': "{:,.2f}%"
        }).applymap(lambda x: f'background-color: {"#113311" if x>=0 else "#331111"}', subset=['Ganancia', 'Rend_%'])

    with tab1:
        # Historia
        with st.spinner("Procesando datos de GBM..."):
            historia = generar_grafico_historico(df_real)
        if not historia.empty:
            fig_hist = px.area(historia, y='Valor_Total')
            fig_hist.update_layout(xaxis_title="", yaxis_title="MXN", height=250, showlegend=False, margin=dict(l=0, r=0, t=0, b=0))
            fig_hist.update_xaxes(rangeslider_visible=False, rangeselector=dict(buttons=list([dict(count=1, label="1M", step="month", stepmode="backward"), dict(count=6, label="6M", step="month", stepmode="backward"), dict(step="all", label="Todo")])))
            st.plotly_chart(fig_hist, use_container_width=True)

        # KPIs
        k1, k2, k3 = st.columns(3)
        t_val = df_real['Valor_Mercado'].sum()
        t_inv = df_real['Inversion_Total'].sum()
        t_gan = df_real['Ganancia'].sum()
        
        k1.metric("Valor Actual", f"${t_val:,.2f}")
        k2.metric("Inversión (Costo GBM)", f"${t_inv:,.2f}")
        k3.metric("Ganancia Real", f"${t_gan:,.2f}", delta=f"{(t_gan/t_inv*100):.2f}%" if t_inv>0 else "0%")
        
        c1, c2, c3 = st.columns(3)
        
        def bloque(titulo, tipo):
            st.markdown(f"### {titulo}")
            d = df_real[df_real['Tipo'].str.upper().str.contains(tipo)]
            if not d.empty:
                st.metric(f"Total {tipo}", f"${d['Valor_Mercado'].sum():,.2f}")
                if d['Valor_Mercado'].sum() > 0:
                    fig = px.sunburst(d, path=['Sector', 'Ticker'], values='Valor_Mercado')
                    fig.update_layout(margin=dict(l=0,r=0,t=0,b=0), height=200)
                    st.plotly_chart(fig, use_container_width=True)
                # Tabla GBM limpia
                st.dataframe(estilo(d[['Ticker','Cantidad','Costo','Precio_Actual','Ganancia','Rend_%']]), use_container_width=True)
        
        with c1: bloque("🌍 SIC", "SIC")
        with c2: bloque("🇲🇽 BMV", "BMV")
        with c3: bloque("🛡️ ETFs", "ETF")

    with tab2:
        d = df_real[df_real['Pago_Anual'] > 0].copy()
        if not d.empty:
            c1, c2 = st.columns(2)
            c1.metric("Ingreso Anual", f"${d['Pago_Anual'].sum():,.2f}")
            c2.metric("Ingreso Mensual", f"${d['Pago_Mensual'].sum():,.2f}")
            st.dataframe(d[['Ticker','Div_Yield','Pago_Mensual','Pago_Anual']].sort_values('Pago_Mensual', ascending=False)
                         .style.format({'Div_Yield': "{:.2f}%", 'Pago_Mensual': "${:,.2f}", 'Pago_Anual': "${:,.2f}"})
                         .bar(subset=['Pago_Mensual'], color='#00CC96'), use_container_width=True)
        else: st.info("Sin dividendos.")

    with tab3:
        if not df_watch.empty:
            df_watch['Precio_MXN'] = df_watch['Ticker'].map(lambda x: mercado[x]['precio'])
            st.dataframe(df_watch[['Ticker','Sector','Precio_MXN','Notas']].style.format({'Precio_MXN': "${:,.2f}"}), use_container_width=True)
        else: st.info("Lista vacía.")

else:
    st.info("Cargando...")
