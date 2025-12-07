import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro V19", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 10px; border-radius: 8px;}
    .stButton>button {width: 100%; background-color: #00CC96; color: white; border: none; font-weight: bold;}
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Patrimonial: Precios Corregidos")

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

# --- MOTOR DE PRECIOS (ULTRA ROBUSTO) ---
def obtener_datos_mercado(tickers):
    data_dict = {}
    
    # Obtener Dólar
    try: usd_now = yf.Ticker("USDMXN=X").history(period="1d")['Close'].iloc[-1]
    except: usd_now = 20.00

    # 🚨 DICCIONARIO MAESTRO DE CORRECCIONES (Basado en tus imágenes) 🚨
    # Aquí traducimos "Idioma GBM" a "Idioma Yahoo"
    CORRECCIONES = {
        # ETFs y Especiales
        'SPYL': 'SPLG',
        'IVVPESO': 'IVVPESO.MX',
        'NAFTRAC': 'NAFTRAC.MX',
        'GLD': 'GLD.MX',
        
        # FIBRAS y Series Numéricas (GBM pone espacio, Yahoo no)
        'FIBRAPL 14': 'FIBRAPL14.MX',
        'FIBRAMQ 12': 'FIBRAMQ12.MX',
        'FIHO 12': 'FIHO12.MX',
        'FMTY 14': 'FMTY14.MX',
        'FMX 23': 'FMX.MX',
        'TERRA 13': 'TERRA13.MX',
        
        # Acciones Mexicanas con Serie (GBM pone espacio, Yahoo no)
        'ASUR B': 'ASURB.MX',
        'GAP B': 'GAPB.MX',
        'OMA B': 'OMAB.MX',
        'AUTLAN B': 'AUTLANB.MX',
        'CHDRAUI B': 'CHDRAUIB.MX',
        'VOLAR A': 'VOLARA.MX',
        'KOF UBL': 'KOFUBL.MX',
        'MEGA CPO': 'MEGACPO.MX',
        'CEMEXCPO': 'CEMEXCPO.MX',
        'BIMBO A': 'BIMBOA.MX',
        'WALMEX *': 'WALMEX.MX',
        'AMX L': 'AMXL.MX',
        
        # Casos Raros de tus imágenes
        'MFRISCO A-1': 'MFRISCO.MX', 
        'HOTEL *': 'HOTEL.MX',
        'R A': 'R.MX',
        'NUTRISA A': 'NUTRISA.MX', # Si cotiza, si no dará 0
        'NEMAK A': 'NEMAKA.MX'
    }
    
    progreso = st.progress(0)
    total = len(tickers)
    
    for i, t_original in enumerate(tickers):
        info = {'precio': 0, 'div_rate': 0, 'div_yield': 0}
        
        # 1. Limpieza Básica
        t_clean = str(t_original).strip()
        
        # 2. Verificar Diccionario Maestro
        if t_clean in CORRECCIONES:
            t_busqueda = CORRECCIONES[t_clean]
        else:
            # Limpieza estándar si no está en el diccionario
            t_busqueda = t_clean.replace('*', '').replace(' N', '').strip()

        # ESTRATEGIA DE BÚSQUEDA TRIPLE
        # Intento A: Búsqueda exacta (Diccionario o Limpia)
        candidatos = [t_busqueda]
        
        # Intento B: Si no tiene punto, agregamos .MX
        if ".MX" not in t_busqueda:
            candidatos.append(t_busqueda + ".MX")
            
        # Intento C: Quitar TODOS los espacios y agregar .MX (Para arreglar casos como "AC *")
        sin_espacios = t_busqueda.replace(" ", "") + ".MX"
        if sin_espacios not in candidatos:
            candidatos.append(sin_espacios)

        # Ejecutar búsqueda
        encontrado = False
        for ticker_test in candidatos:
            if encontrado: break
            try:
                stock = yf.Ticker(ticker_test)
                hist = stock.history(period="1d")
                
                if not hist.empty:
                    encontrado = True
                    precio = hist['Close'].iloc[-1]
                    
                    # Convertir a Pesos si es necesario
                    # Si termina en .MX es pesos, si no, asumimos USD y convertimos
                    if ".MX" in ticker_test:
                        info['precio'] = precio
                    else:
                        info['precio'] = precio * usd_now
                    
                    # Dividendos
                    try:
                        r = stock.info.get('dividendRate', 0) or 0
                        y = stock.info.get('dividendYield', 0) or 0
                        if ".MX" not in ticker_test: r = r * usd_now
                        info['div_rate'] = r
                        info['div_yield'] = y
                    except: pass
            except: pass
        
        data_dict[t_original] = info
        progreso.progress((i+1)/total)
        
    progreso.empty()
    return data_dict

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Control")
    if st.button('🔄 ACTUALIZAR PRECIOS'):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Actualizado: {datetime.now().strftime('%H:%M:%S')}")

# --- LÓGICA PRINCIPAL ---
df_raw = cargar_datos_google()

if df_raw is not None and not df_raw.empty:
    # 1. NORMALIZACIÓN GBM
    df_raw.columns = df_raw.columns.str.lower().str.strip()
    mapa_gbm = {
        'emisora': 'Ticker', 'emisora/serie': 'Ticker', 'ticker': 'Ticker',
        'titulos': 'Cantidad', 'títulos': 'Cantidad', 'cantidad': 'Cantidad',
        'costo promedio': 'Costo_Unitario', 'costo': 'Costo_Unitario',
        'tipo': 'Tipo', 'sector': 'Sector', 'notas': 'Notas'
    }
    df_raw.rename(columns=mapa_gbm, inplace=True)
    
    # 2. LIMPIEZA DATOS
    df_raw['Ticker'] = df_raw['Ticker'].astype(str).str.strip() # Limpieza simple inicial
    
    def clean_money(x): 
        try: return float(str(x).replace('$','').replace(',','').strip())
        except: return 0.0
    
    df_raw['Cantidad'] = df_raw['Cantidad'].apply(clean_money)
    df_raw['Costo_Unitario'] = df_raw['Costo_Unitario'].apply(clean_money)

    for c in ['Tipo','Sector','Notas']: 
        if c not in df_raw.columns: df_raw[c] = ""
    df_raw['Sector'] = df_raw['Sector'].replace('', 'General')
    df_raw['Tipo'] = df_raw['Tipo'].replace('', 'General')

    # 3. CÁLCULO DE INVERSIÓN
    df_raw['Inversion_Fila'] = df_raw['Cantidad'] * df_raw['Costo_Unitario']
    
    # Agrupamos sumando el dinero total invertido
    # NOTA: Agrupamos por el Ticker ORIGINAL de GBM para no mezclar peras con manzanas por error de limpieza
    df = df_raw.groupby('Ticker', as_index=False).agg({
        'Tipo': 'first', 'Sector': 'first', 'Cantidad': 'sum', 
        'Inversion_Fila': 'sum', 'Notas': 'first'
    })
    
    df.rename(columns={'Inversion_Fila': 'Inversion_Total_Real'}, inplace=True)
    df['Costo_Promedio_Real'] = df.apply(lambda x: x['Inversion_Total_Real'] / x['Cantidad'] if x['Cantidad'] > 0 else 0, axis=1)

    # 4. BUSCAR PRECIOS (CON EL NUEVO MOTOR)
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
    tab1, tab2, tab3 = st.tabs(["📊 Balance & Gráficos", "💸 Dividendos", "🎯 Watchlist"])

    def estilo(df_in):
        return df_in.style.format({
            'Costo_Promedio_Real': "${:,.2f}", 'Precio_Actual': "${:,.2f}", 
            'Inversion_Total_Real': "${:,.2f}", 'Valor_Mercado': "${:,.2f}", 
            'Ganancia': "${:,.2f}", 'Rend_%': "{:,.2f}%"
        }).applymap(lambda x: f'background-color: {"#113311" if x>=0 else "#331111"}', subset=['Ganancia', 'Rend_%'])

    with tab1:
        # KPIs
        k1, k2, k3 = st.columns(3)
        t_val = df_real['Valor_Mercado'].sum()
        t_inv = df_real['Inversion_Total_Real'].sum()
        t_gan = df_real['Ganancia'].sum()
        
        k1.metric("Valor Actual", f"${t_val:,.2f}")
        k2.metric("Inversión Total", f"${t_inv:,.2f}")
        k3.metric("Ganancia Total", f"${t_gan:,.2f}", delta=f"{(t_gan/t_inv*100):.2f}%" if t_inv>0 else "0%")
        
        st.markdown("---")

        c1, c2, c3 = st.columns(3)
        def bloque(titulo, tipo):
            st.markdown(f"### {titulo}")
            d = df_real[df_real['Tipo'].str.upper().str.contains(tipo)]
            if not d.empty:
                st.metric(f"Total {tipo}", f"${d['Valor_Mercado'].sum():,.2f}")
                # Gráfico
                if d['Valor_Mercado'].sum() > 0:
                    fig = px.sunburst(d, path=['Sector', 'Ticker'], values='Valor_Mercado')
                    fig.update_layout(margin=dict(l=0,r=0,t=0,b=0), height=200)
                    st.plotly_chart(fig, use_container_width=True)
                # Tabla
                st.dataframe(estilo(d[['Ticker','Cantidad','Costo_Promedio_Real','Precio_Actual','Inversion_Total_Real','Ganancia','Rend_%']]), use_container_width=True)
            else:
                st.info(f"Sin activos {tipo}")
        
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
        else: st.info("Sin dividendos detectados.")

    with tab3:
        if not df_watch.empty:
            df_watch['Precio_MXN'] = df_watch['Ticker'].map(lambda x: mercado[x]['precio'])
            st.dataframe(df_watch[['Ticker','Sector','Precio_MXN','Notas']].style.format({'Precio_MXN': "${:,.2f}"}), use_container_width=True)

else:
    st.info("Cargando...")
