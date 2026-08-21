import streamlit as st
import pandas as pd
import plotly.express as px
import io

# 1. Pagina-instellingen
st.set_page_config(page_title="DeGiro Portefeuille Tracker", layout="wide", page_icon="📊")

# 2. Handmatige data-input (gebaseerd op jouw spreadsheet-export)
# Om het script direct te laten werken, laden we de belangrijkste data in via tekst-strings.
@st.cache_data
def laad_posities_data():
    aandelen_data = """ISIN,Product,Huidig aantal,Kostenbasis huidige positie (EUR),Marktwaarde (EUR),Ongerealiseerd resultaat (EUR),Sector
GB00BP6MXD84,SHELL PLC,70,1831.6,2795.8,964.2,Energie
NL0010273215,ASML HOLDING N.V.,3,1520.5,4522.8,3002.3,Technologie
NL0000009165,HEINEKEN NV,10,769.95,719.8,-50.15,Consumptiegoederen
NL0012969182,ADYEN N.V.,1,1418.8,1054.6,-364.2,Financiële dienstverlening
NL0009269109,KONINKLIJKE HEIJMANS NV,100,1700,8860,7160,Bouw & Vastgoed
NL0015002AG2,EBUSCO HOLDING N.V.,60,71.16,14.91,-56.25,Industrie
US5949181045,MICROSOFT CORPORATION,7,2814.95,2919.79,104.84,Technologie
DK0061412772,CADELER A/S,300,1427.35,1513.61,86.26,Industrie
DE0007030009,RHEINMETALL AG,4,2534.5,4725.6,2191.1,Industrie
NL0010773842,NN GROUP N.V.,30,1373.8,2313.6,939.8,Financiële dienstverlening
US5738741041,MARVELL TECHNOLOGY, INC.,10,648.97,2043.49,1394.52,Technologie
NL0000334118,ASM INTERNATIONAL NV,4,1835.4,3288.8,1453.4,Technologie
CH0360826991,COMET HOLDING AG,5,1109.06,1867.09,758.03,Technologie
CA06849F1080,BARRICK MINING CORPORATION,75,1275.88,2915.77,1639.89,Grondstoffen
NL0010801007,IMCD N.V.,15,1552.12,1455.6,-96.52,Grondstoffen
NL0000337319,KONINKLIJKE BAM GROEP NV,100,744.5,1158,413.5,Bouw & Vastgoed
NL0000235190,AIRBUS SE,5,851.8,1035.25,183.45,Industrie
NL0012365084,NSI NV,40,973,665.6,-307.4,Vastgoed
NL0011872643,ASR NEDERLAND N.V.,15,928.3,1039.2,110.9,Financiële dienstverlening
NL0012059018,EXOR NV,10,835.5,696.5,-139.0,Financiële dienstverlening
US2910111044,EMERSON ELECTRIC CO,6,670.93,814.45,143.52,Industrie
DK0010272202,GENMAB A/S,4,958.45,1151.43,192.98,Gezondheidszorg
US6703461052,NUCOR CORP,8,1104.25,1713.69,609.44,Grondstoffen
NL0015002MS2,THE MAGNUM ICE CREAM COMPANY N.V.,40,513.72,665.68,151.96,Consumptiegoederen
US68236H2040,ONDAS INC,100,800.07,766.51,-33.56,Technologie
US84615Q1031,SPACE EXPLORATION TECHNOLOGIES CORP,4,465.91,481.10,15.19,Industrie
DE000ENER6Y0,SIEMENS ENERGY AG,8,1244.9,1229.92,-14.98,Industrie
US2788651006,ECOLAB INC.,5,1184.35,1229.95,45.60,Industrie
US78409V1044,S&P GLOBAL INC,6,2176.01,2205.75,29.74,Financiële dienstverlening
NL0010583399,CORBION N.V. CLASS C,40,794.4,797.6,3.20,Grondstoffen
DE000A1K0235,SUSS MICROTEC SE,10,784.9,732.0,-52.90,Technologie
SE0001515552,INDUTRADE AB,40,880.77,877.93,-2.84,Industrie"""
    
    etf_data = """ISIN,Product,Huidig aantal,Kostenbasis huidige positie (EUR),Marktwaarde (EUR),Ongerealiseerd resultaat (EUR),Sector
IE00BQQP9F84,VANECK GOLD MINERS UCITS ETF,30,918.9,2813.4,1894.5,ETF
IE000YYE6WK5,VANECK DEFENSE UCITS ETF,30,843.6,1712.7,869.1,ETF
IE00BDFBTQ78,VANECK S&P GLOBAL MINING UCITS ETF,30,849.3,1760.7,911.4,ETF
NL0011683594,VANECK MS DEVELOPED MARKETS DIV LEAD,25,965.75,1384.0,418.25,ETF
IE00BMC38736,VANECK SEMICONDUCTOR UCITS ETF,20,677.9,1796.4,1118.5,ETF
IE000UL6CLP7,GLOBAL X SILVER MINERS UCITS ETF,40,682.44,1555.2,872.76,ETF
NL0009272749,VANECK AEX UCITS ETF,10,917.0,1114.8,197.8,ETF
IE000M7V94E1,VANECK URANIUM AND NUCLEAR UCITS ETF,10,433.05,461.75,28.7,ETF
IE0002PG6CA6,VANECK RARE EARTH AND STRATEGIC METALS,40,595.4,513.2,-82.2,ETF"""

    df_aandelen = pd.read_csv(io.StringIO(aandelen_data))
    df_aandelen['Type'] = 'Aandeel'
    df_etf = pd.read_csv(io.StringIO(etf_data))
    df_etf['Type'] = 'ETF'
    
    return pd.concat([df_aandelen, df_etf], ignore_index=True)

df_posities = laad_posities_data()

# 3. Applicatie Header & KPI's uit jouw Overzicht
st.title("📊 DeGiro Portefeuille Rendement Tracker")
st.caption("Peildatum: 20 augustus 2026 | Alle bedragen in EUR") [source: 1]

# Belangrijkste cijfers berekenen (of hardcoded uit jouw spreadsheet overnemen)
totale_kostenbasis = 45565.75 [source: 1]
totale_marktwaarde = 71860.04 [source: 1]
ongerealiseerd_res = 26294.29 [source: 1]
ongerealiseerd_rend = 0.5771 * 100 # 57.7% [source: 1]
netto_resultaat = 27523.68 [source: 1]
xirr = 0.2511 * 100 # 25.11% [source: 1]

# KPI Kaarten weergeven
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric(label="💰 Totale Marktwaarde", value=f"€ {totale_marktwaarde:,.2f}")
kpi2.metric(label="📉 Kostenbasis", value=f"€ {totale_kostenbasis:,.2f}")
kpi3.metric(label="📈 Ongerealiseerd Resultaat", value=f"€ {ongerealiseerd_res:,.2f}", delta=f"{ongerealiseerd_rend:.2f}%")
kpi4.metric(label="⏱️ Jaarlijks Rendement (XIRR)", value=f"{xirr:.2f}%") [source: 1]

st.markdown("---")

# 4. Interactieve Zijbalk (Sidebar) voor Filters
st.sidebar.header("🔍 Portefeuille Filters")
product_type = st.sidebar.multiselect(
    "Kies Product Type:", 
    options=df_posities['Type'].unique(), 
    default=df_posities['Type'].unique()
)

sectoren = df_posities['Sector'].unique()
gekozen_sectoren = st.sidebar.multiselect(
    "Filter op Sector:", 
    options=sectoren, 
    default=sectoren
)

# Data filteren op basis van keuzes
df_gefilterd = df_posities[
    (df_posities['Type'].isin(product_type)) & 
    (df_posities['Sector'].isin(gekozen_sectoren))
]

# 5. Visualisaties (Grafieken tabblad)
st.subheader("Visualisaties & Allocatie")
links, rechts = st.columns(2)

with links:
    # Grafiek 1: Portefeuille-allocatie (o.b.v. Marktwaarde) [source: 1]
    fig_allocatie = px.pie(
        df_gefilterd, 
        values='Marktwaarde (EUR)', 
        names='Product', 
        title='Portefeuille-allocatie (Huidige Posities)',
        hole=0.4
    )
    st.plotly_chart(fig_allocatie, use_container_width=True)

with rechts:
    # Grafiek 2: Sector-allocatie [source: 1]
    df_sector = df_gefilterd.groupby('Sector')['Marktwaarde (EUR)'].sum().reset_index()
    fig_sector = px.bar(
        df_sector, 
        x='Sector', 
        y='Marktwaarde (EUR)', 
        title='Blootstelling per Sector',
        text_auto='.2s',
        color='Sector'
    )
    st.plotly_chart(fig_sector, use_container_width=True)

st.markdown("---")

# 6. Interactieve Data Dataframes (De tabellen zelf)
st.subheader("📋 Lopende Posities")
st.dataframe(
    df_gefilterd[['Product', 'ISIN', 'Huidig aantal', 'Kostenbasis huidige positie (EUR)', 'Marktwaarde (EUR)', 'Ongerealiseerd resultaat (EUR)', 'Sector']], 
    use_container_width=True,
    hide_index=True
)

# Waarschuwing uit de Excel-sheet tonen [source: 1]
st.info("⚠️ **Concentratierisico-vuistregel:** Een sector die meer dan ~25% van je aandelenportefeuille beslaat, geeft een verhoogd concentratierisico. Een sectorbrede tegenvaller raakt dan een groot deel van je vermogen.") [source: 1]
