import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Terminal Pro V10", layout="wide", page_icon="🦁")
st.markdown("""
    <style>
    .stMetric {background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px;}
    </style>
    """, unsafe_allow_html=True)

st.title("🦁 Terminal Patrimonial: Pro V10")

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
    
    for i, t_original in enumerate(tickers):
        # Limpieza de tickers (* y N)
        t_clean = str(t_original).replace('*', '').replace(' N', '').strip()
        info = {'precio': 0, 'div_rate': 0, 'div_yield': 0}
        
        try:
            # Prioridad MX > US
            stock = yf.Ticker(t_clean + ".MX")
            hist = stock.history(period="1d")
            
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
    # 1. Limpieza
    df_raw.columns = df_raw.columns.str.lower().str.strip()
    mapa = {'emisora': 'ticker', 'titulos': 'cantidad', 'costo promedio': 'costo', 
            'sector': 'sector', 'tipo': 'tipo', 'notas': 'notas'} # Agregamos Notas
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
    if 'Notas' not in df_raw.columns: df_raw['Notas'] = "" # Crear col vacía si no existe

    # 3. SEPARAR PORTAFOLIO ACTIVO vs WATCHLIST (CANTIDAD 0)
    # Agrupamos primero todo
    df_raw['Inversion_Total'] = df_raw['Cantidad'] * df_raw['Costo']
    
    # Agrupación inteligente
    df = df_raw.groupby('Ticker', as_index=False).agg({
        'Tipo': 'first',
        'Sector': 'first',
        'Cantidad': 'sum',
        'Inversion_Total': 'sum',
        'Notas': 'first' # Traemos la nota
    })
    
    df['Costo'] = df.apply(lambda x: x['Inversion_Total'] / x['Cantidad'] if x['Cantidad'] > 0 else 0, axis=1)

    # 4. Descargar Mercado
    with st.spinner('Analizando Mercado...'):
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

    # --- SEPARACIÓN DE DATAFRAMES ---
    # Portafolio Real (Tienes acciones)
    df_real = df[df['Cantidad'] > 0].copy()
    # Watchlist (Tienes 0 acciones)
    df_watch = df[df['Cantidad'] == 0].copy()

    # --- PESTAÑAS ---
    tab_dash, tab_divs, tab_watch = st.tabs(["📊 Dashboard Principal", "💸 Dividendos", "🎯 Oportunidades (Watchlist)"])

    def estilo_tabla(dataframe):
        return dataframe.style.format({
            'Costo': "${:,.2f}", 'Precio_Actual': "${:,.2f}", 
            'Ganancia': "${:,.2f}", 'Rendimiento_%': "{:,.2f}%"
        }).applymap(lambda v: f'background-color: {"#113311" if v>=0 else "#331111"}', subset=['Ganancia', 'Rendimiento_%'])

    # ==========================
    # PESTAÑA 1: DASHBOARD
    # ==========================
    with tab_dash:
        # KPIs Globales
        k1, k2, k3 = st.columns(3)
        k1.metric("Patrimonio Total", f"${df_real['Valor_Mercado'].sum():,.2f}")
        k2.metric("Ganancia Total", f"${df_real['Ganancia'].sum():,.2f}", delta=f"{df_real['Ganancia'].sum():,.2f}")
        rend_global = (df_real['Ganancia'].sum()/df_real['Costo_Total'].sum()*100) if df_real['Costo_Total'].sum() > 0 else 0
        k3.metric("Rendimiento Global", f"{rend_global:.2f}%")
        
        st.markdown("---")
        
        # 3 COLUMNAS: SIC | BMV | ETF
        col_sic, col_bmv, col_etf = st.columns(3)
        
        # --- COLUMNA 1: SIC ---
        with col_sic:
            st.header("🌍 SIC")
            df_sic = df_real[df_real['Tipo'].str.upper().str.contains('SIC')]
            if not df_sic.empty:
                st.metric("Total SIC", f"${df_sic['Valor_Mercado'].sum():,.2f}")
                # Gráfico Rojo/Verde Estricto
                fig = px.bar(df_sic, x='Ganancia', y='Ticker', orientation='h', 
                             color='Ganancia', 
                             color_continuous_scale=['#FF4B4B', '#1E1E1E', '#00CC96'], # Rojo -> Negro -> Verde
                             color_continuous_midpoint=0) # El 0 es el centro exacto
                fig.update_layout(coloraxis_showscale=False) # Ocultar barra de color lateral
                st.plotly_chart(fig, use_container_width=True)
                
                # TABLA SOLO SIC
                cols = ['Ticker', 'Cantidad', 'Costo', 'Precio_Actual', 'Ganancia', 'Rendimiento_%']
                st.dataframe(estilo_tabla(df_sic[cols]), use_container_width=True)
            else:
                st.info("Sin acciones SIC")

        # --- COLUMNA 2: BMV ---
        with col_bmv:
            st.header("🇲🇽 BMV")
            df_bmv = df_real[df_real['Tipo'].str.upper().str.contains('BMV')]
            if not df_bmv.empty:
                st.metric("Total BMV", f"${df_bmv['Valor_Mercado'].sum():,.2f}")
                fig = px.bar(df_bmv, x='Ganancia', y='Ticker', orientation='h', 
                             color='Ganancia', 
                             color_continuous_scale=['#FF4B4B', '#1E1E1E', '#00CC96'], 
                             color_continuous_midpoint=0)
                fig.update_layout(coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
                
                # TABLA SOLO BMV
                cols = ['Ticker', 'Cantidad', 'Costo', 'Precio_Actual', 'Ganancia', 'Rendimiento_%']
                st.dataframe(estilo_tabla(df_bmv[cols]), use_container_width=True)
            else:
                st.info("Sin acciones BMV")

        # --- COLUMNA 3: ETFs ---
        with col_etf:
            st.header("🛡️ ETFs")
            df_etf = df_real[df_real['Tipo'].str.upper().str.contains('ETF')]
            if not df_etf.empty:
                st.metric("Total ETFs", f"${df_etf['Valor_Mercado'].sum():,.2f}")
                fig = px.bar(df_etf, x='Ganancia', y='Ticker', orientation='h', 
                             color='Ganancia', 
                             color_continuous_scale=['#FF4B4B', '#1E1E1E', '#00CC96'], 
                             color_continuous_midpoint=0)
                fig.update_layout(coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
                
                # TABLA SOLO ETF
                cols = ['Ticker', 'Cantidad', 'Costo', 'Precio_Actual', 'Ganancia', 'Rendimiento_%']
                st.dataframe(estilo_tabla(df_etf[cols]), use_container_width=True)
            else:
                st.info("Sin ETFs")

    # ==========================
    # PESTAÑA 2: DIVIDENDOS
    # ==========================
    with tab_divs:
        st.subheader("💰 Flujo de Efectivo")
        df_divs = df_real[df_real['Pago_Anual_Total'] > 0].copy()
        
        if not df_divs.empty:
            d1, d2 = st.columns(2)
            d1.metric("Ingreso Anual", f"${df_divs['Pago_Anual_Total'].sum():,.2f}")
            d2.metric("Ingreso Mensual", f"${df_divs['Pago_Mensual_Est'].sum():,.2f}")

            st.dataframe(
                df_divs.sort_values('Pago_Mensual_Est', ascending=False)[['Ticker', 'Tipo', 'Div_Yield_%', 'Pago_Mensual_Est']]
                .style.format({'Div_Yield_%': "{:.2f}%", 'Pago_Mensual_Est': "${:,.2f}"})
                .bar(subset=['Pago_Mensual_Est'], color='#00CC96'),
                use_container_width=True
            )
        else:
            st.info("No hay dividendos reportados.")

    # ==========================
    # PESTAÑA 3: WATCHLIST (NUEVO)
    # ==========================
    with tab_watch:
        st.subheader("🎯 Oportunidades de Compra (Watchlist)")
        st.markdown("Agrega acciones con **Cantidad 0** en tu Excel para verlas aquí.")
        
        if not df_watch.empty:
            # Mostrar tabla de seguimiento con Notas
            cols_watch = ['Ticker', 'Tipo', 'Sector', 'Precio_Actual', 'Notas']
            
            st.dataframe(
                df_watch[cols_watch].style.format({'Precio_Actual': "${:,.2f}"}),
                use_container_width=True
            )
            
            # Tarjetas de resumen para Watchlist
            col_w = st.columns(len(df_watch) if len(df_watch) < 4 else 4)
            for i, (_, row) in enumerate(df_watch.iterrows()):
                with col_w[i % 4]:
                    st.metric(label=row['Ticker'], value=f"${row['Precio_Actual']:,.2f}", delta=row['Sector'])
                    if row['Notas']:
                        st.caption(f"📝 {row['Notas']}")
        else:
            st.info("Tu lista de seguimiento está vacía. Agrega una fila en Google Sheets con Cantidad = 0.")

else:
    st.info("Cargando portafolio...")
