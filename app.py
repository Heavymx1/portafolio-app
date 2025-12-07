import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro V20", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 10px; border-radius: 8px;}
    .stButton>button {width: 100%; background-color: #00CC96; color: white; border: none; font-weight: bold;}
    
    /* Estilos para las tarjetas de Watchlist */
    .watch-card {
        background-color: #262730;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 15px;
        border-left: 5px solid #555;
    }
    .priority-alta { border-left-color: #FF4B4B !important; } /* Rojo */
    .priority-media { border-left-color: #FFD700 !important; } /* Amarillo */
    .priority-baja { border-left-color: #00CC96 !important; } /* Verde */
    
    .ticker-title { font-size: 1.2em; font-weight: bold; color: white; }
    .price-tag { float: right; font-weight: bold; color: #aaa; }
    .note-content { margin-top: 10px; font-size: 0.9em; color: #ddd; white-space: pre-wrap;}
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Patrimonial: Estrategia & Prioridades")

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
        return pd.DataFrame(sh.sheet1.get_all_records()).astype(str)
    except Exception as e:
        st.error(f"Error Google Sheets: {e}")
        return None

# --- MOTOR DE HISTORIA ---
@st.cache_data(ttl=300)
def generar_grafico_historico(df_real):
    try:
        hist_usd = yf.Ticker("USDMXN=X").history(period="6mo")['Close']
    except:
        fechas = pd.date_range(end=datetime.now(), periods=180)
        hist_usd = pd.Series([20.0]*180, index=fechas)

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
    except: usd_now = 20.00
    
    # DICCIONARIO MAESTRO (Incluye tus correcciones anteriores)
    CORRECCIONES = {
        'SPYL': 'SPLG', 'IVVPESO': 'IVVPESO.MX', 'NAFTRAC': 'NAFTRAC.MX', 'GLD': 'GLD.MX',
        'FIBRAPL 14': 'FIBRAPL14.MX', 'FIBRAMQ 12': 'FIBRAMQ12.MX', 'FIHO 12': 'FIHO12.MX',
        'FMTY 14': 'FMTY14.MX', 'FMX 23': 'FMX.MX', 'TERRA 13': 'TERRA13.MX',
        'ASUR B': 'ASURB.MX', 'GAP B': 'GAPB.MX', 'OMA B': 'OMAB.MX', 'AUTLAN B': 'AUTLANB.MX',
        'CHDRAUI B': 'CHDRAUIB.MX', 'VOLAR A': 'VOLARA.MX', 'KOF UBL': 'KOFUBL.MX',
        'MEGA CPO': 'MEGACPO.MX', 'CEMEXCPO': 'CEMEXCPO.MX', 'BIMBO A': 'BIMBOA.MX',
        'WALMEX *': 'WALMEX.MX', 'AMX L': 'AMXL.MX', 'MFRISCO A-1': 'MFRISCO.MX', 
        'HOTEL *': 'HOTEL.MX', 'R A': 'R.MX', 'NUTRISA A': 'NUTRISA.MX', 'NEMAK A': 'NEMAKA.MX'
    }
    
    for t_original in tickers:
        info = {'precio': 0, 'div_rate': 0, 'div_yield': 0}
        
        t_clean = str(t_original).strip()
        if t_clean in CORRECCIONES:
            t_busqueda = CORRECCIONES[t_clean]
        else:
            t_busqueda = t_clean.replace('*', '').replace(' N', '').strip()

        # Búsqueda Robusta
        candidatos = [t_busqueda]
        if ".MX" not in t_busqueda: candidatos.append(t_busqueda + ".MX")
        sin_espacios = t_busqueda.replace(" ", "") + ".MX"
        if sin_espacios not in candidatos: candidatos.append(sin_espacios)

        encontrado = False
        for ticker_test in candidatos:
            if encontrado: break
            try:
                stock = yf.Ticker(ticker_test)
                hist = stock.history(period="1d")
                if not hist.empty:
                    encontrado = True
                    precio = hist['Close'].iloc[-1]
                    if ".MX" in ticker_test: info['precio'] = precio
                    else: info['precio'] = precio * usd_now
                    
                    try:
                        r = stock.info.get('dividendRate', 0) or 0
                        y = stock.info.get('dividendYield', 0) or 0
                        if ".MX" not in ticker_test: r = r * usd_now
                        info['div_rate'] = r
                        info['div_yield'] = y
                    except: pass
            except: pass
        data_dict[t_original] = info
    return data_dict

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Control")
    if st.button('🔄 ACTUALIZAR'):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Actualizado: {datetime.now().strftime('%H:%M:%S')}")

# --- LÓGICA PRINCIPAL ---
df_raw = cargar_datos_google()

if df_raw is not None and not df_raw.empty:
    # 1. NORMALIZACIÓN
    df_raw.columns = df_raw.columns.str.lower().str.strip()
    mapa_gbm = {
        'emisora': 'Ticker', 'emisora/serie': 'Ticker', 'ticker': 'Ticker',
        'titulos': 'Cantidad', 'títulos': 'Cantidad', 'cantidad': 'Cantidad',
        'costo promedio': 'Costo_Unitario', 'costo': 'Costo_Unitario',
        'tipo': 'Tipo', 'sector': 'Sector', 'notas': 'Notas', 'prioridad': 'Prioridad'
    }
    df_raw.rename(columns=mapa_gbm, inplace=True)
    
    # 2. LIMPIEZA
    df_raw['Ticker'] = df_raw['Ticker'].astype(str).str.strip()
    
    def clean_money(x): 
        try: return float(str(x).replace('$','').replace(',','').strip())
        except: return 0.0
    
    df_raw['Cantidad'] = df_raw['Cantidad'].apply(clean_money)
    df_raw['Costo_Unitario'] = df_raw['Costo_Unitario'].apply(clean_money)

    for c in ['Tipo','Sector','Notas','Prioridad']: 
        if c not in df_raw.columns: df_raw[c] = ""
    
    df_raw['Sector'] = df_raw['Sector'].replace('', 'General')
    df_raw['Tipo'] = df_raw['Tipo'].replace('', 'General')
    df_raw['Prioridad'] = df_raw['Prioridad'].replace('', 'Baja') # Default Baja

    # 3. AGRUPACIÓN
    df_raw['Inversion_Fila'] = df_raw['Cantidad'] * df_raw['Costo_Unitario']
    
    df = df_raw.groupby('Ticker', as_index=False).agg({
        'Tipo': 'first', 'Sector': 'first', 'Cantidad': 'sum', 
        'Inversion_Fila': 'sum', 'Notas': 'first', 'Prioridad': 'first'
    })
    
    df.rename(columns={'Inversion_Fila': 'Inversion_Total_Real'}, inplace=True)
    df['Costo_Promedio_Real'] = df.apply(lambda x: x['Inversion_Total_Real'] / x['Cantidad'] if x['Cantidad'] > 0 else 0, axis=1)

    # 4. MERCADO
    mercado = obtener_datos_mercado(df['Ticker'].unique())
    
    df['Precio_Actual'] = df['Ticker'].map(lambda x: mercado[x]['precio'])
    df['Div_Rate'] = df['Ticker'].map(lambda x: mercado[x]['div_rate'])
    df['Div_Yield'] = df['Ticker'].map(lambda x: mercado[x]['div_yield']*100)

    # 5. RESULTADOS
    df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
    df['Ganancia'] = df['Valor_Mercado'] - df['Inversion_Total_Real']
    df['Rend_%'] = df.apply(lambda x: (x['Ganancia']/x['Inversion_Total_Real']*100) if x['Inversion_Total_Real']>0 else 0, axis=1)
    df['Pago_Anual'] = df['Cantidad'] * df['Div_Rate']
    df['Pago_Mensual'] = df['Pago_Anual'] / 12

    df_real = df[df['Cantidad'] > 0.001].copy()
    df_watch = df[df['Cantidad'] == 0].copy()

    # --- TABS ---
    tab1, tab2, tab3 = st.tabs(["📊 Balance", "💸 Dividendos", "🎯 Watchlist (Estrategia)"])

    def estilo(df_in):
        return df_in.style.format({
            'Costo_Promedio_Real': "${:,.2f}", 'Precio_Actual': "${:,.2f}", 
            'Inversion_Total_Real': "${:,.2f}", 'Valor_Mercado': "${:,.2f}", 
            'Ganancia': "${:,.2f}", 'Rend_%': "{:,.2f}%"
        }).applymap(lambda x: f'background-color: {"#113311" if x>=0 else "#331111"}', subset=['Ganancia', 'Rend_%'])

    with tab1:
        # Historia
        st.subheader("📈 Evolución Patrimonial")
        with st.spinner("Calculando..."):
            historia = generar_grafico_historico(df_real)
        if not historia.empty:
            fig_hist = px.area(historia, y='Valor_Total')
            fig_hist.update_layout(xaxis_title="", yaxis_title="MXN", height=250, showlegend=False, margin=dict(l=0, r=0, t=0, b=0))
            fig_hist.update_xaxes(rangeslider_visible=False, rangeselector=dict(buttons=list([dict(count=1, label="1M", step="month", stepmode="backward"), dict(count=6, label="6M", step="month", stepmode="backward"), dict(step="all", label="Todo")])))
            st.plotly_chart(fig_hist, use_container_width=True)

        k1, k2, k3 = st.columns(3)
        t_val = df_real['Valor_Mercado'].sum()
        t_inv = df_real['Inversion_Total_Real'].sum()
        t_gan = df_real['Ganancia'].sum()
        k1.metric("Valor Actual", f"${t_val:,.2f}")
        k2.metric("Inversión Total", f"${t_inv:,.2f}")
        k3.metric("Ganancia Total", f"${t_gan:,.2f}", delta=f"{(t_gan/t_inv*100):.2f}%" if t_inv>0 else "0%")
        
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
                st.dataframe(estilo(d[['Ticker','Cantidad','Costo_Promedio_Real','Precio_Actual','Inversion_Total_Real','Ganancia','Rend_%']]), use_container_width=True)
        
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

    # === TAB 3: WATCHLIST INTELIGENTE ===
    with tab3:
        if not df_watch.empty:
            st.subheader("🎯 Oportunidades de Inversión")
            st.markdown("Clasificadas por tu columna de **Prioridad** en Excel.")

            # Dividimos visualmente por prioridad
            col_alta, col_media, col_baja = st.columns(3)
            
            # --- FUNCIÓN PARA GENERAR TARJETAS ---
            def render_cards(column, priority_label, css_class):
                # Filtramos por prioridad (insensible a mayúsculas)
                subset = df_watch[df_watch['Prioridad'].str.lower() == priority_label.lower()]
                
                with column:
                    st.markdown(f"#### Prioridad {priority_label.capitalize()}")
                    if subset.empty:
                        st.caption("Vacío")
                    else:
                        for _, row in subset.iterrows():
                            # Formateamos la nota para que respete saltos de línea
                            nota_fmt = row['Notas'].replace('\n', '<br>')
                            
                            html_card = f"""
                            <div class="watch-card {css_class}">
                                <span class="ticker-title">{row['Ticker']}</span>
                                <span class="price-tag">${row['Precio_Actual']:,.2f}</span>
                                <div style="clear:both;"></div>
                                <div style="color: #888; font-size: 0.8em; margin-bottom: 5px;">{row['Sector']} • {row['Tipo']}</div>
                                <div class="note-content">{nota_fmt}</div>
                            </div>
                            """
                            st.markdown(html_card, unsafe_allow_html=True)

            # Renderizamos las 3 columnas
            render_cards(col_alta, "Alta", "priority-alta")
            render_cards(col_media, "Media", "priority-media")
            render_cards(col_baja, "Baja", "priority-baja")

        else:
            st.info("Tu Watchlist está vacía. Agrega acciones con 'Títulos' = 0 en tu Excel.")

else:
    st.info("Cargando...")
