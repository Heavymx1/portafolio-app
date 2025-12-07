import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro V11", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px;}
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Patrimonial: Corrección Total")

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

# --- MOTOR DE DATOS (CON TRADUCTOR) ---
def obtener_datos_mercado(tickers):
    data_dict = {}
    progreso = st.progress(0)
    
    # 🚨 DICCIONARIO DE TRADUCCIÓN 🚨
    # Formato: 'NOMBRE_EN_TU_EXCEL': 'NOMBRE_REAL_YAHOO'
    CORRECCIONES_MANUALES = {
        'SPYL': 'SPLG',         # Corregimos SPYL -> SPLG
        'IVVPESO': 'IVVPESO.MX',# Forzamos .MX para IVVPESO
        'NAFTRAC': 'NAFTRAC.MX',# Forzamos .MX para NAFTRAC
        'CSPX': 'CSPX.L',       # Ejemplo Europa
        'VWRA': 'VWRA.L'        # Ejemplo Europa
    }
    
    for i, t_original in enumerate(tickers):
        # 1. Limpieza básica (* y N)
        t_clean = str(t_original).replace('*', '').replace(' N', '').strip()
        
        # 2. Aplicar Traducción Manual (Si existe en el diccionario, lo cambiamos)
        if t_clean in CORRECCIONES_MANUALES:
            t_busqueda = CORRECCIONES_MANUALES[t_clean]
        else:
            t_busqueda = t_clean # Si no está en la lista, usamos el normal
            
        info = {'precio': 0, 'div_rate': 0, 'div_yield': 0}
        
        try:
            # Estrategia de Búsqueda:
            # A. Usamos el nombre traducido o limpio
            # B. Si falla y no tiene punto, probamos agregar .MX
            
            # Intento 1: Búsqueda exacta (Ideal para lo que definiste en el diccionario)
            stock = yf.Ticker(t_busqueda)
            hist = stock.history(period="1d")
            
            # Intento 2: Si falló y no le pusimos .MX manual, probamos agregarlo
            if hist.empty and ".MX" not in t_busqueda:
                stock = yf.Ticker(t_busqueda + ".MX")
                hist = stock.history(period="1d")
                
            # Intento 3: Si falló y era algo raro, probamos el original limpio
            if hist.empty and t_busqueda != t_clean:
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
    for col in ['Tipo', 'Sector', 'Notas']:
        if col not in df_raw.columns: df_raw[col] = ""

    # 3. Agrupación Watchlist vs Real
    df_raw['Inversion_Total'] = df_raw['Cantidad'] * df_raw['Costo']
    
    df = df_raw.groupby('Ticker', as_index=False).agg({
        'Tipo': 'first', 'Sector': 'first', 'Cantidad': 'sum', 
        'Inversion_Total': 'sum', 'Notas': 'first'
    })
    
    df['Costo'] = df.apply(lambda x: x['Inversion_Total'] / x['Cantidad'] if x['Cantidad'] > 0 else 0, axis=1)

    # 4. Descargar Mercado
    with st.spinner('Analizando Mercado...'):
        mercado = obtener_datos_mercado(df['Ticker'].unique())

    # 5. Mapear
    df['Precio_Actual'] = df['Ticker'].map(lambda x: mercado[x]['precio'])
    df['Div_Pago_Accion'] = df['Ticker'].map(lambda x: mercado[x]['div_rate'])
    df['Div_Yield_%'] = df['Ticker'].map(lambda x: mercado[x]['div_yield'] * 100 if mercado[x]['div_yield'] else 0)

    df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
    df['Costo_Total'] = df['Cantidad'] * df['Costo']
    df['Ganancia'] = df['Valor_Mercado'] - df['Costo_Total']
    df['Rendimiento_%'] = df.apply(lambda x: (x['Ganancia']/x['Costo_Total']*100) if x['Costo_Total']>0 else 0, axis=1)
    df['Pago_Anual_Total'] = df['Cantidad'] * df['Div_Pago_Accion']
    df['Pago_Mensual_Est'] = df['Pago_Anual_Total'] / 12 

    # Separar
    df_real = df[df['Cantidad'] > 0].copy()
    df_watch = df[df['Cantidad'] == 0].copy()

    # --- PESTAÑAS ---
    tab_dash, tab_divs, tab_watch = st.tabs(["📊 Dashboard Principal", "💸 Dividendos", "🎯 Watchlist"])

    def estilo_tabla(dataframe):
        return dataframe.style.format({
            'Costo': "${:,.2f}", 'Precio_Actual': "${:,.2f}", 
            'Ganancia': "${:,.2f}", 'Rendimiento_%': "{:,.2f}%"
        }).applymap(lambda v: f'background-color: {"#113311" if v>=0 else "#331111"}', subset=['Ganancia', 'Rendimiento_%'])

    # === DASHBOARD ===
    with tab_dash:
        k1, k2, k3 = st.columns(3)
        k1.metric("Patrimonio Total", f"${df_real['Valor_Mercado'].sum():,.2f}")
        k2.metric("Ganancia Total", f"${df_real['Ganancia'].sum():,.2f}", delta=f"{df_real['Ganancia'].sum():,.2f}")
        rend = (df_real['Ganancia'].sum()/df_real['Costo_Total'].sum()*100) if df_real['Costo_Total'].sum() > 0 else 0
        k3.metric("Rendimiento Global", f"{rend:.2f}%")
        st.markdown("---")
        
        c1, c2, c3 = st.columns(3)
        
        # SIC
        with c1:
            st.header("🌍 SIC")
            d = df_real[df_real['Tipo'].str.upper().str.contains('SIC')]
            if not d.empty:
                st.metric("Total SIC", f"${d['Valor_Mercado'].sum():,.2f}")
                fig = px.bar(d, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', 
                             color_continuous_scale=['#FF4B4B', '#1E1E1E', '#00CC96'], color_continuous_midpoint=0)
                fig.update_layout(coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(estilo_tabla(d[['Ticker','Cantidad','Costo','Precio_Actual','Ganancia','Rendimiento_%']]), use_container_width=True)

        # BMV
        with c2:
            st.header("🇲🇽 BMV")
            d = df_real[df_real['Tipo'].str.upper().str.contains('BMV')]
            if not d.empty:
                st.metric("Total BMV", f"${d['Valor_Mercado'].sum():,.2f}")
                fig = px.bar(d, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', 
                             color_continuous_scale=['#FF4B4B', '#1E1E1E', '#00CC96'], color_continuous_midpoint=0)
                fig.update_layout(coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(estilo_tabla(d[['Ticker','Cantidad','Costo','Precio_Actual','Ganancia','Rendimiento_%']]), use_container_width=True)

        # ETF
        with c3:
            st.header("🛡️ ETFs")
            d = df_real[df_real['Tipo'].str.upper().str.contains('ETF')]
            if not d.empty:
                st.metric("Total ETFs", f"${d['Valor_Mercado'].sum():,.2f}")
                fig = px.bar(d, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', 
                             color_continuous_scale=['#FF4B4B', '#1E1E1E', '#00CC96'], color_continuous_midpoint=0)
                fig.update_layout(coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(estilo_tabla(d[['Ticker','Cantidad','Costo','Precio_Actual','Ganancia','Rendimiento_%']]), use_container_width=True)

    # === DIVIDENDOS ===
    with tab_divs:
        d = df_real[df_real['Pago_Anual_Total'] > 0].copy()
        if not d.empty:
            c1, c2 = st.columns(2)
            c1.metric("Ingreso Anual", f"${d['Pago_Anual_Total'].sum():,.2f}")
            c2.metric("Ingreso Mensual", f"${d['Pago_Mensual_Est'].sum():,.2f}")
            st.dataframe(d[['Ticker','Div_Yield_%','Pago_Mensual_Est','Pago_Anual_Total']].sort_values('Pago_Mensual_Est', ascending=False).style.format({'Div_Yield_%': "{:.2f}%", 'Pago_Mensual_Est': "${:,.2f}", 'Pago_Anual_Total': "${:,.2f}"}).bar(subset=['Pago_Mensual_Est'], color='#00CC96'), use_container_width=True)
        else: st.info("Sin dividendos reportados.")

    # === WATCHLIST ===
    with tab_watch:
        if not df_watch.empty:
            st.dataframe(df_watch[['Ticker','Sector','Precio_Actual','Notas']].style.format({'Precio_Actual': "${:,.2f}"}), use_container_width=True)
        else: st.info("Lista vacía. Agrega acciones con Cantidad 0.")
else:
    st.info("Cargando...")
