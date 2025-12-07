import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro V14", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px;}
    .stButton>button {width: 100%; background-color: #00CC96; color: white; border: none; font-weight: bold;}
    .stButton>button:hover {background-color: #00AA80;}
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Patrimonial: Histórico & Tiempo Real")

# --- CONEXIÓN ---
# 👇👇👇 ¡TU LINK AQUÍ! 👇👇👇
URL_HOJA = "https://docs.google.com/spreadsheets/d/1UpgDIh3nuhxz83NQg7KYPu_Boj4C-nP0rrw9YgTjWEo/edit?gid=1838439399#gid=1838439399" 
# 👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆

@st.cache_data(ttl=0) # TTL 0 = NO GUARDAR CACHÉ (Siempre fresco al recargar)
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
        st.error(f"Error Google Sheets: {e}")
        return None

# --- MOTOR DE HISTORIA (LA MÁQUINA DEL TIEMPO) ⏳ ---
@st.cache_data(ttl=300)
def generar_grafico_historico(df_real):
    # 1. Descargar historia del Dólar (3 meses)
    hist_usd = yf.Ticker("USDMXN=X").history(period="3mo")['Close']
    
    # Crear un DataFrame base con las fechas (índice)
    df_historia = pd.DataFrame(index=hist_usd.index)
    df_historia['Valor_Total'] = 0.0 # Empezamos en 0
    
    # 2. Recorrer cada acción y sumar su historia
    CORRECCIONES = {'SPYL': 'SPLG', 'IVVPESO': 'IVVPESO.MX', 'NAFTRAC': 'NAFTRAC.MX'}
    
    progreso = st.progress(0)
    total = len(df_real)
    
    for i, row in df_real.iterrows():
        t = row['Ticker']
        qty = row['Cantidad']
        
        # Limpieza
        t_clean = str(t).replace('*', '').replace(' N', '').strip()
        t_busqueda = CORRECCIONES.get(t_clean, t_clean)
        
        try:
            # Intentar MX primero
            hist = yf.Ticker(t_busqueda + ".MX").history(period="3mo")['Close']
            es_mxn = True
            
            if hist.empty:
                # Si no, US
                hist = yf.Ticker(t_busqueda).history(period="3mo")['Close']
                es_mxn = False
            
            if not hist.empty:
                # Normalizar fechas (quitar hora) para que coincidan
                hist.index = hist.index.tz_localize(None) 
                # Alinear con el índice del dólar
                hist = hist.reindex(df_historia.index, method='ffill').fillna(0)
                
                if not es_mxn:
                    # Convertir a pesos usando el dólar histórico de CADA DÍA
                    hist = hist * hist_usd.values
                
                # Sumar al total: (Precio Histórico * Cantidad Actual)
                df_historia['Valor_Total'] += (hist * qty)
                
        except: pass
        progreso.progress((i+1)/total)
    
    progreso.empty()
    return df_historia

# --- MOTOR DE PRECIOS ACTUALES ---
def obtener_datos_mercado(tickers):
    data_dict = {}
    
    # Dólar Hoy
    try: usd_now = yf.Ticker("USDMXN=X").history(period="1d")['Close'].iloc[-1]
    except: usd_now = 17.50
    
    CORRECCIONES = {'SPYL': 'SPLG', 'IVVPESO': 'IVVPESO.MX', 'NAFTRAC': 'NAFTRAC.MX'}
    
    for t_original in tickers:
        t_clean = str(t_original).replace('*', '').replace(' N', '').strip()
        t_busqueda = CORRECCIONES.get(t_clean, t_clean)
            
        info = {'precio': 0, 'div_rate': 0, 'div_yield': 0}
        
        try:
            # MX
            stock = yf.Ticker(t_busqueda + ".MX")
            hist = stock.history(period="1d")
            es_mxn = True
            
            # US
            if hist.empty:
                stock = yf.Ticker(t_busqueda)
                hist = stock.history(period="1d")
                es_mxn = False
                
            if not hist.empty:
                precio = hist['Close'].iloc[-1]
                # Conversión
                if not es_mxn:
                    info['precio'] = precio * usd_now
                else:
                    info['precio'] = precio
                
                # Dividendos
                try:
                    r = stock.info.get('dividendRate', 0) or 0
                    y = stock.info.get('dividendYield', 0) or 0
                    if not es_mxn: r = r * usd_now # Convertir divisa del dividendo
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
    st.caption(f"Última actualización: {datetime.now().strftime('%H:%M:%S')}")

# --- LOGICA ---
df_raw = cargar_datos_google()

if df_raw is not None and not df_raw.empty:
    # 1. Limpieza y Agrupación
    df_raw.columns = df_raw.columns.str.lower().str.strip()
    mapa = {'emisora': 'ticker', 'titulos': 'cantidad', 'costo promedio': 'costo', 
            'sector': 'sector', 'tipo': 'tipo', 'notas': 'notas'}
    df_raw.rename(columns=mapa, inplace=True)
    
    def clean(x): 
        try: return float(str(x).replace('$','').replace(',','').strip())
        except: return 0.0
    
    df_raw['Cantidad'] = df_raw['Cantidad'].apply(clean)
    df_raw['Costo'] = df_raw['Costo'].apply(clean)
    
    for c in ['Tipo','Sector','Notas']: 
        if c not in df_raw.columns: df_raw[c] = ""
    df_raw['Sector'] = df_raw['Sector'].replace('', 'Otros')

    df_raw['Inversion_Total'] = df_raw['Cantidad'] * df_raw['Costo']
    df = df_raw.groupby('ticker', as_index=False).agg({
        'tipo': 'first', 'sector': 'first', 'Cantidad': 'sum', 
        'Inversion_Total': 'sum', 'notas': 'first'
    })
    df.rename(columns={'ticker': 'Ticker', 'tipo': 'Tipo', 'sector': 'Sector', 'notas': 'Notas'}, inplace=True)
    df['Costo'] = df.apply(lambda x: x['Inversion_Total'] / x['Cantidad'] if x['Cantidad'] > 0 else 0, axis=1)

    # 2. DataFrames
    df_real = df[df['Cantidad'] > 0].copy()
    df_watch = df[df['Cantidad'] == 0].copy()

    # 3. Descargar Datos Actuales
    mercado = obtener_datos_mercado(df['Ticker'].unique())
    
    df_real['Precio_Actual'] = df_real['Ticker'].map(lambda x: mercado[x]['precio'])
    df_real['Valor_Mercado'] = df_real['Cantidad'] * df_real['Precio_Actual']
    df_real['Ganancia'] = df_real['Valor_Mercado'] - df_real['Inversion_Total']
    df_real['Rend_%'] = df_real.apply(lambda x: (x['Ganancia']/x['Inversion_Total']*100) if x['Inversion_Total']>0 else 0, axis=1)
    
    # Dividendos
    df_real['Div_Rate'] = df_real['Ticker'].map(lambda x: mercado[x]['div_rate'])
    df_real['Div_Yield'] = df_real['Ticker'].map(lambda x: mercado[x]['div_yield']*100)
    df_real['Pago_Anual'] = df_real['Cantidad'] * df_real['Div_Rate']
    df_real['Pago_Mensual'] = df_real['Pago_Anual'] / 12

    # --- PESTAÑAS ---
    tab1, tab2, tab3 = st.tabs(["📊 Histórico & Balance", "💸 Dividendos", "🎯 Watchlist"])

    # === TAB 1: GRÁFICA DE RENDIMIENTO ===
    with tab1:
        # 1. GRÁFICA DE HISTORIA (NUEVO)
        st.subheader("📈 Evolución de tu Portafolio (90 Días)")
        
        with st.spinner("Reconstruyendo historia..."):
            historia = generar_grafico_historico(df_real)
        
        if not historia.empty:
            # Gráfico de Área bonito
            fig_hist = px.area(historia, y='Valor_Total', title="Valor Total del Portafolio en el Tiempo")
            fig_hist.update_layout(xaxis_title="", yaxis_title="Valor MXN", height=350)
            # Selector de rango (1M, 3M, Todo)
            fig_hist.update_xaxes(
                rangeslider_visible=False,
                rangeselector=dict(
                    buttons=list([
                        dict(count=7, label="1S", step="day", stepmode="backward"),
                        dict(count=1, label="1M", step="month", stepmode="backward"),
                        dict(count=3, label="3M", step="month", stepmode="backward"),
                        dict(step="all")
                    ])
                )
            )
            st.plotly_chart(fig_hist, use_container_width=True)

        st.markdown("---")

        # 2. KPIs y SECCIONES
        k1, k2, k3 = st.columns(3)
        total_val = df_real['Valor_Mercado'].sum()
        total_gan = df_real['Ganancia'].sum()
        k1.metric("Patrimonio Actual", f"${total_val:,.2f}")
        k2.metric("Ganancia Total", f"${total_gan:,.2f}", delta=f"{total_gan:,.2f}")
        k3.metric("Rendimiento", f"{(total_gan/df_real['Inversion_Total'].sum()*100):.2f}%")

        def estilo(df_in):
            return df_in.style.format({
                'Costo': "${:,.2f}", 'Precio_Actual': "${:,.2f}", 'Ganancia': "${:,.2f}", 'Rend_%': "{:,.2f}%"
            }).applymap(lambda x: f'background-color: {"#113311" if x>=0 else "#331111"}', subset=['Ganancia', 'Rend_%'])

        c1, c2, c3 = st.columns(3)
        
        with c1: 
            st.markdown("### 🌍 SIC")
            d = df_real[df_real['Tipo'].str.upper().str.contains('SIC')]
            if not d.empty:
                st.metric("Total SIC", f"${d['Valor_Mercado'].sum():,.2f}")
                fig = px.bar(d, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', color_continuous_scale=['#FF4B4B','#222','#00CC96'], color_continuous_midpoint=0)
                fig.update_layout(coloraxis_showscale=False, height=200, margin=dict(l=0,r=0,t=0,b=0))
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(estilo(d[['Ticker','Cantidad','Costo','Precio_Actual','Ganancia','Rend_%']]), use_container_width=True)

        with c2:
            st.markdown("### 🇲🇽 BMV")
            d = df_real[df_real['Tipo'].str.upper().str.contains('BMV')]
            if not d.empty:
                st.metric("Total BMV", f"${d['Valor_Mercado'].sum():,.2f}")
                fig = px.bar(d, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', color_continuous_scale=['#FF4B4B','#222','#00CC96'], color_continuous_midpoint=0)
                fig.update_layout(coloraxis_showscale=False, height=200, margin=dict(l=0,r=0,t=0,b=0))
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(estilo(d[['Ticker','Cantidad','Costo','Precio_Actual','Ganancia','Rend_%']]), use_container_width=True)
        
        with c3:
            st.markdown("### 🛡️ ETFs")
            d = df_real[df_real['Tipo'].str.upper().str.contains('ETF')]
            if not d.empty:
                st.metric("Total ETFs", f"${d['Valor_Mercado'].sum():,.2f}")
                fig = px.bar(d, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', color_continuous_scale=['#FF4B4B','#222','#00CC96'], color_continuous_midpoint=0)
                fig.update_layout(coloraxis_showscale=False, height=200, margin=dict(l=0,r=0,t=0,b=0))
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(estilo(d[['Ticker','Cantidad','Costo','Precio_Actual','Ganancia','Rend_%']]), use_container_width=True)

    # === TAB 2: DIVIDENDOS ===
    with tab2:
        d = df_real[df_real['Pago_Anual'] > 0].copy()
        if not d.empty:
            c1, c2 = st.columns(2)
            c1.metric("Ingreso Anual", f"${d['Pago_Anual'].sum():,.2f}")
            c2.metric("Ingreso Mensual", f"${d['Pago_Mensual'].sum():,.2f}")
            st.dataframe(d[['Ticker','Div_Yield','Pago_Mensual','Pago_Anual']].sort_values('Pago_Mensual', ascending=False)
                         .style.format({'Div_Yield': "{:.2f}%", 'Pago_Mensual': "${:,.2f}", 'Pago_Anual': "${:,.2f}"})
                         .bar(subset=['Pago_Mensual'], color='#00CC96'), use_container_width=True)
        else: st.info("Sin dividendos reportados.")

    # === TAB 3: WATCHLIST ===
    with tab3:
        if not df_watch.empty:
            df_watch['Precio_MXN'] = df_watch['Ticker'].map(lambda x: mercado[x]['precio'])
            st.dataframe(df_watch[['Ticker','Sector','Precio_MXN','Notas']].style.format({'Precio_MXN': "${:,.2f}"}), use_container_width=True)
        else: st.info("Lista vacía.")

else:
    st.info("Cargando...")
