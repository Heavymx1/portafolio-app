import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro V12", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px;}
    .stButton>button {width: 100%; background-color: #00CC96; color: white; border: none;}
    .stButton>button:hover {background-color: #00AA80;}
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Patrimonial: Tiempo Real")

# --- CONEXIÓN ---
# 👇👇👇 ¡TU LINK AQUÍ! 👇👇👇
URL_HOJA = "https://docs.google.com/spreadsheets/d/1UpgDIh3nuhxz83NQg7KYPu_Boj4C-nP0rrw9YgTjWEo/edit?gid=1838439399#gid=1838439399" 
# 👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆

# --- GESTIÓN DE CACHÉ (SOLUCIÓN A DATOS VIEJOS) ---
# Usamos ttl=0 para forzar que los datos expiren rápido si no se usan,
# pero el botón es el que manda.
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
        # Convertimos todo a string para limpiarlo nosotros mismos
        return pd.DataFrame(sh.sheet1.get_all_records()).astype(str)
    except Exception as e:
        st.error(f"Error cargando Google Sheets: {e}")
        return None

# --- MOTOR DE DATOS (CON TRADUCTOR) ---
def obtener_datos_mercado(tickers):
    data_dict = {}
    progreso = st.progress(0)
    
    # DICCIONARIO DE CORRECCIONES
    CORRECCIONES = {
        'SPYL': 'SPLG',
        'IVVPESO': 'IVVPESO.MX',
        'NAFTRAC': 'NAFTRAC.MX',
        'CSPX': 'CSPX.L',
        'VWRA': 'VWRA.L'
    }
    
    for i, t_original in enumerate(tickers):
        t_clean = str(t_original).replace('*', '').replace(' N', '').strip()
        
        # Aplicar corrección manual si existe
        if t_clean in CORRECCIONES:
            t_busqueda = CORRECCIONES[t_clean]
        else:
            t_busqueda = t_clean
            
        info = {'precio': 0, 'div_rate': 0, 'div_yield': 0}
        
        try:
            # Estrategia: Buscamos nombre directo, si falla y no tiene punto, probamos .MX
            stock = yf.Ticker(t_busqueda)
            hist = stock.history(period="1d")
            
            if hist.empty and ".MX" not in t_busqueda:
                stock = yf.Ticker(t_busqueda + ".MX")
                hist = stock.history(period="1d")
                
            if not hist.empty:
                info['precio'] = hist['Close'].iloc[-1]
                try:
                    info['div_rate'] = stock.info.get('dividendRate', 0)
                    info['div_yield'] = stock.info.get('dividendYield', 0)
                    # Validación extra para dividendos None
                    if info['div_rate'] is None: info['div_rate'] = 0
                    if info['div_yield'] is None: info['div_yield'] = 0
                except: pass
        except: pass  
        
        data_dict[t_original] = info
        progreso.progress((i + 1) / len(tickers))
    
    progreso.empty()
    return data_dict

# --- BARRA LATERAL DE CONTROL ---
with st.sidebar:
    st.header("⚙️ Panel de Control")
    if st.button('🔄 FORZAR ACTUALIZACIÓN'):
        st.cache_data.clear() # ¡ESTO BORRA LA MEMORIA VIEJA!
        st.rerun()
    
    st.write(f"Última carga: {datetime.now().strftime('%H:%M:%S')}")
    st.info("👆 Presiona este botón después de editar tu Excel para ver los cambios.")

# --- PROCESAMIENTO ---
df_raw = cargar_datos_google()

if df_raw is not None and not df_raw.empty:
    # 1. Limpieza de nombres de columnas
    df_raw.columns = df_raw.columns.str.lower().str.strip()
    mapa = {'emisora': 'ticker', 'titulos': 'cantidad', 'costo promedio': 'costo', 
            'sector': 'sector', 'tipo': 'tipo', 'notas': 'notas'}
    df_raw.rename(columns=mapa, inplace=True)
    df_raw.columns = df_raw.columns.str.capitalize()
    
    # 2. Sanitizar Números (Quita signos de $)
    def limpiar_num(x):
        try: return float(str(x).replace('$','').replace(',','').strip())
        except: return 0.0
    
    df_raw['Cantidad'] = df_raw['Cantidad'].apply(limpiar_num)
    df_raw['Costo'] = df_raw['Costo'].apply(limpiar_num)
    
    # 3. Rellenar columnas faltantes (SOLUCIÓN GRÁFICOS INVISIBLES)
    if 'Tipo' not in df_raw.columns: df_raw['Tipo'] = "General"
    if 'Sector' not in df_raw.columns: df_raw['Sector'] = "Otros"
    if 'Notas' not in df_raw.columns: df_raw['Notas'] = ""
    
    # Si el sector está vacío, ponle "Otros" para que el gráfico no se rompa
    df_raw['Sector'] = df_raw['Sector'].replace('', 'Otros')

    # 4. Agrupación (Watchlist vs Real)
    df_raw['Inversion_Total'] = df_raw['Cantidad'] * df_raw['Costo']
    
    df = df_raw.groupby('Ticker', as_index=False).agg({
        'Tipo': 'first', 'Sector': 'first', 'Cantidad': 'sum', 
        'Inversion_Total': 'sum', 'Notas': 'first'
    })
    
    df['Costo'] = df.apply(lambda x: x['Inversion_Total'] / x['Cantidad'] if x['Cantidad'] > 0 else 0, axis=1)

    # 5. Descargar Mercado
    with st.spinner('Conectando con Bolsa...'):
        mercado = obtener_datos_mercado(df['Ticker'].unique())

    # 6. Mapear Resultados
    df['Precio_Actual'] = df['Ticker'].map(lambda x: mercado[x]['precio'])
    df['Div_Pago_Accion'] = df['Ticker'].map(lambda x: mercado[x]['div_rate'])
    df['Div_Yield_%'] = df['Ticker'].map(lambda x: mercado[x]['div_yield'] * 100 if mercado[x]['div_yield'] else 0)

    df['Valor_Mercado'] = df['Cantidad'] * df['Precio_Actual']
    df['Costo_Total'] = df['Cantidad'] * df['Costo']
    df['Ganancia'] = df['Valor_Mercado'] - df['Costo_Total']
    df['Rendimiento_%'] = df.apply(lambda x: (x['Ganancia']/x['Costo_Total']*100) if x['Costo_Total']>0 else 0, axis=1)
    df['Pago_Anual_Total'] = df['Cantidad'] * df['Div_Pago_Accion']
    df['Pago_Mensual_Est'] = df['Pago_Anual_Total'] / 12 

    # Separar DataFrames
    df_real = df[df['Cantidad'] > 0].copy()
    df_watch = df[df['Cantidad'] == 0].copy()

    # --- PESTAÑAS VISUALES ---
    tab_dash, tab_divs, tab_watch = st.tabs(["📊 Dashboard Principal", "💸 Dividendos", "🎯 Watchlist"])

    # Función de estilo
    def estilo_tabla(dataframe):
        return dataframe.style.format({
            'Costo': "${:,.2f}", 'Precio_Actual': "${:,.2f}", 
            'Ganancia': "${:,.2f}", 'Rendimiento_%': "{:,.2f}%"
        }).applymap(lambda v: f'background-color: {"#113311" if v>=0 else "#331111"}', subset=['Ganancia', 'Rendimiento_%'])

    # === TAB 1: DASHBOARD ===
    with tab_dash:
        # KPIs
        k1, k2, k3 = st.columns(3)
        k1.metric("Patrimonio Total", f"${df_real['Valor_Mercado'].sum():,.2f}")
        k2.metric("Ganancia Total", f"${df_real['Ganancia'].sum():,.2f}", delta=f"{df_real['Ganancia'].sum():,.2f}")
        rend = (df_real['Ganancia'].sum()/df_real['Costo_Total'].sum()*100) if df_real['Costo_Total'].sum() > 0 else 0
        k3.metric("Rendimiento Global", f"{rend:.2f}%")
        
        st.markdown("---")
        
        c1, c2, c3 = st.columns(3)
        
        # --- FUNCIÓN PARA MOSTRAR COLUMNA ---
        def mostrar_columna(titulo, filtro_tipo):
            st.header(titulo)
            d = df_real[df_real['Tipo'].str.upper().str.contains(filtro_tipo)]
            if not d.empty:
                st.metric(f"Total {filtro_tipo}", f"${d['Valor_Mercado'].sum():,.2f}")
                
                # GRÁFICO DE BARRAS (VERDE/ROJO)
                fig_bar = px.bar(d, x='Ganancia', y='Ticker', orientation='h', color='Ganancia', 
                             color_continuous_scale=['#FF4B4B', '#1E1E1E', '#00CC96'], color_continuous_midpoint=0)
                fig_bar.update_layout(coloraxis_showscale=False, margin=dict(l=0,r=0,t=0,b=0), height=200)
                st.plotly_chart(fig_bar, use_container_width=True)
                
                # GRÁFICO DE PASTEL (SOLUCIÓN A INVISIBILIDAD)
                # Solo graficamos si hay valor positivo
                if d['Valor_Mercado'].sum() > 0:
                    fig_sun = px.sunburst(d, path=['Sector', 'Ticker'], values='Valor_Mercado')
                    fig_sun.update_layout(margin=dict(l=0,r=0,t=0,b=0), height=250)
                    st.plotly_chart(fig_sun, use_container_width=True)
                
                # TABLA
                st.dataframe(estilo_tabla(d[['Ticker','Cantidad','Costo','Precio_Actual','Ganancia','Rendimiento_%']]), use_container_width=True)
            else:
                st.info(f"Sin activos {filtro_tipo}")

        with c1: mostrar_columna("🌍 SIC", "SIC")
        with c2: mostrar_columna("🇲🇽 BMV", "BMV")
        with c3: mostrar_columna("🛡️ ETFs", "ETF")

    # === TAB 2: DIVIDENDOS ===
    with tab_divs:
        d = df_real[df_real['Pago_Anual_Total'] > 0].copy()
        if not d.empty:
            c1, c2 = st.columns(2)
            c1.metric("Ingreso Anual", f"${d['Pago_Anual_Total'].sum():,.2f}")
            c2.metric("Ingreso Mensual", f"${d['Pago_Mensual_Est'].sum():,.2f}")
            
            st.dataframe(d[['Ticker','Div_Yield_%','Pago_Mensual_Est','Pago_Anual_Total']]
                         .sort_values('Pago_Mensual_Est', ascending=False)
                         .style.format({'Div_Yield_%': "{:.2f}%", 'Pago_Mensual_Est': "${:,.2f}", 'Pago_Anual_Total': "${:,.2f}"})
                         .bar(subset=['Pago_Mensual_Est'], color='#00CC96'), use_container_width=True)
        else: st.info("Sin dividendos reportados.")

    # === TAB 3: WATCHLIST ===
    with tab_watch:
        if not df_watch.empty:
            st.dataframe(df_watch[['Ticker','Sector','Precio_Actual','Notas']].style.format({'Precio_Actual': "${:,.2f}"}), use_container_width=True)
        else: st.info("Lista vacía. (Agrega acciones con Cantidad 0 en Excel)")

else:
    st.info("Cargando portafolio... Por favor espera.")
