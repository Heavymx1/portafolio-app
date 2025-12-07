import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro (MXN)", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px;}
    .stButton>button {width: 100%; background-color: #00CC96; color: white; border: none;}
    .stButton>button:hover {background-color: #00AA80;}
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Patrimonial: 100% MXN")

# --- CONEXIÓN ---
# 👇👇👇 ¡TU LINK AQUÍ! 👇👇👇
URL_HOJA = "https://docs.google.com/spreadsheets/d/1UpgDIh3nuhxz83NQg7KYPu_Boj4C-nP0rrw9YgTjWEo/edit?gid=1838439399#g" 
# 👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆

# --- CACHÉ INTELIGENTE ---
@st.cache_data(ttl=60) 
def cargar_datos_google():
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
        st.error(f"Error cargando Google Sheets: {e}")
        return None

# --- MOTOR DE DATOS (CON CONVERSOR DE DIVISAS) 💱 ---
def obtener_datos_mercado(tickers):
    data_dict = {}
    progreso = st.progress(0)
    
    # 1. OBTENER TIPO DE CAMBIO (Dólar a Peso)
    try:
        usd_mxn = yf.Ticker("USDMXN=X").history(period="1d")['Close'].iloc[-1]
    except:
        usd_mxn = 17.00 # Valor por defecto si falla la conexión (Seguridad)

    # 2. DICCIONARIO DE CORRECCIONES
    CORRECCIONES = {
        'SPYL': 'SPLG',
        'IVVPESO': 'IVVPESO.MX',
        'NAFTRAC': 'NAFTRAC.MX'
    }
    
    for i, t_original in enumerate(tickers):
        t_clean = str(t_original).replace('*', '').replace(' N', '').strip()
        
        if t_clean in CORRECCIONES:
            t_busqueda = CORRECCIONES[t_clean]
        else:
            t_busqueda = t_clean
            
        info = {'precio': 0, 'div_rate': 0, 'div_yield': 0, 'moneda_origen': 'MXN'}
        
        try:
            # ESTRATEGIA DE CONVERSIÓN:
            # Paso A: Buscar directo en México (.MX). Si existe, es MXN.
            stock_mx = yf.Ticker(t_busqueda + ".MX")
            hist_mx = stock_mx.history(period="1d")
            
            if not hist_mx.empty:
                # ENCONTRADO EN MÉXICO (PRECIO YA ES PESOS)
                info['precio'] = hist_mx['Close'].iloc[-1]
                stock_final = stock_mx
            
            else:
                # Paso B: Buscar en origen (EE.UU.). Si existe, es USD.
                # Aplicamos conversión USD -> MXN
                stock_us = yf.Ticker(t_busqueda)
                hist_us = stock_us.history(period="1d")
                
                if not hist_us.empty:
                    precio_dolares = hist_us['Close'].iloc[-1]
                    info['precio'] = precio_dolares * usd_mxn # <--- AQUÍ LA MAGIA
                    info['moneda_origen'] = 'USD (Convertido)'
                    stock_final = stock_us
            
            # Extraer Dividendos (Si existen)
            if info['precio'] > 0:
                try:
                    # El rate suele venir en la moneda de origen, hay que convertirlo también si fue USD
                    rate = stock_final.info.get('dividendRate', 0)
                    yld = stock_final.info.get('dividendYield', 0)
                    
                    if rate is None: rate = 0
                    if yld is None: yld = 0
                    
                    if info['moneda_origen'] == 'USD (Convertido)':
                        info['div_rate'] = rate * usd_mxn # Convertir dividendo a pesos
                    else:
                        info['div_rate'] = rate
                        
                    info['div_yield'] = yld
                except: pass

        except: pass  
        
        data_dict[t_original] = info
        progreso.progress((i + 1) / len(tickers))
    
    progreso.empty()
    st.caption(f"💵 Tipo de Cambio usado para conversión: ${usd_mxn:.2f} MXN/USD") # Info visual
    return data_dict

# --- PANEL DE CONTROL ---
with st.sidebar:
    st.header("⚙️ Control")
    if st.button('🔄 FORZAR ACTUALIZACIÓN'):
        st.cache_data.clear()
        st.rerun()
    st.write(f"Actualizado: {datetime.now().strftime('%H:%M:%S')}")

# --- PROCESAMIENTO ---
df_raw = cargar_datos_google()

if df_raw is not None and not df_raw.empty:
    # 1. Limpieza
    df_raw.columns = df_raw.columns.str.lower().str.strip()
    mapa = {'emisora': 'ticker', 'titulos': 'cantidad', 'costo promedio': 'costo', 
            'sector': 'sector', 'tipo': 'tipo', 'notas': 'notas'}
    df_raw.rename(columns=mapa, inplace=True)
    df_raw.columns = df_raw.columns.str.capitalize()
    
    # 2. Sanitizar
    def limpiar_num(x):
        try: return float(str(x).replace('$','').replace(',','').strip())
        except: return 0.0
    
    df_raw['Cantidad'] = df_raw['Cantidad'].apply(limpiar_num)
    df_raw['Costo'] = df_raw['Costo'].apply(limpiar_num)
    
    # Rellenar vacíos
    for c in ['Tipo','Sector','Notas']: 
        if c not in df_raw.columns: df_raw[c] = ""
    df_raw['Sector'] = df_raw['Sector'].replace('', 'Otros')

    # 3. Agrupación
    df_raw['Inversion_Total'] = df_raw['Cantidad'] * df_raw['Costo']
    df = df_raw.groupby('Ticker', as_index=False).agg({
        'Tipo': 'first', 'Sector': 'first', 'Cantidad': 'sum', 
        'Inversion_Total': 'sum', 'Notas': 'first'
    })
    df['Costo'] = df.apply(lambda x: x['Inversion_Total'] / x['Cantidad'] if x['Cantidad'] > 0 else 0, axis=1)

    # 4. Mercado
    with st.spinner('Cotizando en Pesos Mexicanos...'):
        mercado = obtener_datos_mercado(df['Ticker'].unique())

    # 5. Cálculos
    df['Precio_Actual'] = df['Ticker'].map(lambda x: mercado[x]['precio'])
    df['Div_Pago_Accion'] = df['Ticker'].map(lambda x: mercado[x]['div_rate'])
    df['Div_Yield_%'] = df['Ticker'].map(lambda x: mercado[x]['div_yield'] * 100 if mercado[x]['div_yield'] else 0)

    df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
    df['Costo_Total'] = df['Cantidad'] * df['Costo']
    df['Ganancia'] = df['Valor_Mercado'] - df['Costo_Total']
    df['Rendimiento_%'] = df.apply(lambda x: (x['Ganancia']/x['Costo_Total']*100) if x['Costo_Total']>0 else 0, axis=1)
    df['Pago_Anual_Total'] = df['Cantidad'] * df['Div_Pago_Accion']
    df['Pago_Mensual_Est'] = df['Pago_Anual_Total'] / 12 

    # DataFrames Finales
    df_real = df[df['Cantidad'] > 0].copy()
    df_watch = df[df['Cantidad'] == 0].copy()

    # --- VISUAL ---
    tab_dash, tab_divs, tab_watch = st.tabs(["📊 Dashboard MXN", "💸 Dividendos", "🎯 Watchlist"])
    
    def estilo_tabla(dataframe):
        return dataframe.style.format({
            'Costo': "${:,.2f}", 'Precio_Actual': "${:,.2f}", 
            'Ganancia': "${:,.2f}", 'Rendimiento_%': "{:,.2f}%"
        }).applymap(lambda v: f'background-color: {"#113311" if v>=0 else "#331111"}', subset=['Ganancia', 'Rendimiento_%'])

    with tab_dash:
        # KPIs
        k1, k2, k3 = st.columns(3)
        k1.metric("Patrimonio Total (MXN)", f"${df_real['Valor_Mercado'].sum():,.2f}")
        k2.metric("Ganancia Total (MXN)", f"${df_real['Ganancia'].sum():,.2f}", delta=f"{df_real['Ganancia'].sum():,.2f}")
        rend = (df_real['Ganancia'].sum()/df_real['Costo_Total'].sum()*100) if df_real['Costo_Total'].sum() > 0 else 0
        k3.metric("Rendimiento Global", f"{rend:.2f}%")
        st.markdown("---")
        
        c1, c2, c3 = st.columns(3)
        
        def bloque_activo(titulo, tipo):
            st.header(titulo)
            d = df_real[df_real['Tipo'].str.upper().str.contains(tipo)]
            if not d.empty:
                st.metric(f"Total {tipo}", f"${d['Valor_Mercado'].sum():,.2f}")
                
                # Barras
                fig_bar = px.bar(d, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', 
                             color_continuous_scale=['#FF4B4B', '#1E1E1E', '#00CC96'], color_continuous_midpoint=0)
                fig_bar.update_layout(coloraxis_showscale=False, margin=dict(l=0,r=0,t=0,b=0), height=200)
                st.plotly_chart(fig_bar, use_container_width=True)
                
                # Pastel (Solo si hay valor positivo)
                if d['Valor_Mercado'].sum() > 1:
                    fig_sun = px.sunburst(d, path=['Sector', 'Ticker'], values='Valor_Mercado')
                    fig_sun.update_layout(margin=dict(l=0,r=0,t=0,b=0), height=200)
                    st.plotly_chart(fig_sun, use_container_width=True)
                
                # Tabla
                st.dataframe(estilo_tabla(d[['Ticker','Cantidad','Costo','Precio_Actual','Ganancia','Rendimiento_%']]), use_container_width=True)
            else:
                st.info(f"Sin activos {tipo}")

        with c1: bloque_activo("🌍 SIC (Pesificados)", "SIC")
        with c2: bloque_activo("🇲🇽 BMV", "BMV")
        with c3: bloque_activo("🛡️ ETFs", "ETF")

    with tab_divs:
        d = df_real[df_real['Pago_Anual_Total'] > 0].copy()
        if not d.empty:
            c1, c2 = st.columns(2)
            c1.metric("Ingreso Anual (MXN)", f"${d['Pago_Anual_Total'].sum():,.2f}")
            c2.metric("Ingreso Mensual (MXN)", f"${d['Pago_Mensual_Est'].sum():,.2f}")
            
            st.dataframe(d[['Ticker','Div_Yield_%','Pago_Mensual_Est','Pago_Anual_Total']]
                         .sort_values('Pago_Mensual_Est', ascending=False)
                         .style.format({'Div_Yield_%': "{:.2f}%", 'Pago_Mensual_Est': "${:,.2f}", 'Pago_Anual_Total': "${:,.2f}"})
                         .bar(subset=['Pago_Mensual_Est'], color='#00CC96'), use_container_width=True)
        else: st.info("Sin dividendos.")

    with tab_watch:
        if not df_watch.empty:
            st.dataframe(df_watch[['Ticker','Sector','Precio_Actual','Notas']].style.format({'Precio_Actual': "${:,.2f}"}), use_container_width=True)
        else: st.info("Lista vacía.")

else:
    st.info("Conectando...")
