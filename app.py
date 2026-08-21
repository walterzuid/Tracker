import streamlit as st
import pandas as pd
import plotly.express as px
import io
import re

# 1. Pagina-instellingen
st.set_page_config(page_title="DeGiro Live Tracker", layout="wide", page_icon="📊")

st.title("📊 DeGiro Live Portefeuille Dashboard")
st.markdown("Sleep je DeGiro CSV-bestanden hieronder om je dashboard live bij te werken.")

# 2. CSV Bestandinvoer in de zijbalk (Sidebar)
st.sidebar.header("📁 DeGiro Data Upload")
transacties_file = st.sidebar.file_uploader("Upload Transacties.csv", type=["csv"])
rekening_file = st.sidebar.file_uploader("Upload Rekeningoverzicht.csv", type=["csv"])

# Handmatige woordenlijst om sectoren toe te wijzen op basis van Productnaam
SECTOR_MAP = {
    "SHELL": "Energie", "ASML": "Technologie", "ASM INTERNATIONAL": "Technologie",
    "HEINEKEN": "Consumptiegoederen", "ADYEN": "Financiële dienstverlening",
    "HEIJMANS": "Bouw & Vastgoed", "BAM GROEP": "Bouw & Vastgoed", "EBUSCO": "Industrie",
    "MICROSOFT": "Technologie", "CADELER": "Industrie", "RHEINMETALL": "Industrie",
    "MARVELL": "Technologie", "BARRICK": "Grondstoffen", "IMCD": "Grondstoffen",
    "AIRBUS": "Industrie", "NSI": "Vastgoed", "ASR": "Financiële dienstverlening",
    "EXOR": "Financiële dienstverlening", "EMERSON": "Industrie", "GENMAB": "Gezondheidszorg",
    "NUCOR": "Grondstoffen", "MAGNUM": "Consumptiegoederen", "ONDAS": "Technologie",
    "SPACE EXPLORATION": "Industrie", "SPACEX": "Industrie", "SIEMENS": "Industrie",
    "ECOLAB": "Industrie", "S&P GLOBAL": "Financiële dienstverlening", "CORBION": "Grondstoffen",
    "SUSS MICROTEC": "Technologie", "INDUTRADE": "Industrie", "TAKEAWAY": "Consumentendiensten"
}

# Hulpmiddel om getallen uit DeGiro CSV netjes om te zetten naar Python-floats
def maak_numeriek(val):
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip().replace('"', '').replace('.', '').replace(',', '.')
    try:
        return float(val_str)
    except ValueError:
        return 0.0

# Functie om te controleren of een productnaam een optie is en de details te filteren
def parse_optie_naam(naam):
    naam_str = str(naam).strip()
    # Dit patroon zoekt naar patronen zoals: Ticker + Spatie + C of P + Getal + Spatie + Datum
    # Voorbeelden: "SBM C25.00 19JUN26", "AEX C980 19DEC25", "AMG C25.00 19APR24"
    match = re.search(r'^([A-Z0-9]+)\s+([CP])(\d+(?:\.\d+)?)\s+(.+)$', naam_str, re.IGNORECASE)
    
    if match:
        aandeel = match.group(1).upper()
        type_optie = "Call" if match.group(2).upper() == "C" else "Put"
        strike = float(match.group(3))
        expiratie = match.group(4).strip()
        return True, aandeel, type_optie, strike, expiratie
    return False, None, None, 0.0, None

# 3. CONTROLE: Zijn de bestanden geüpload?
if transacties_file is not None and rekening_file is not None:
    try:
        # Bestanden inlezen
        df_tx = pd.read_csv(transacties_file, sep=',', encoding='utf-8')
        df_rek = pd.read_csv(rekening_file, sep=',', encoding='utf-8')
        
        # Kolomnamen opschonen
        df_tx.columns = df_tx.columns.str.strip()
        df_rek.columns = df_rek.columns.str.strip()
        
        st.success("✅ Beide bestanden succesvol ingeladen!")

        # --- BEREKENING 1: POSITIES BEREKENEN UIT TRANSACTIES ---
        df_tx['Datum_Tijd'] = pd.to_datetime(df_tx['Datum'] + ' ' + df_tx['Tijd'], format='%d-%m-%Y %H:%M', errors='coerce')
        df_tx = df_tx.sort_values('Datum_Tijd').reset_index(drop=True)
        
        df_tx['Aantal'] = df_tx['Aantal'].apply(maak_numeriek)
        df_tx['Waarde EUR'] = df_tx['Waarde EUR'].apply(maak_numeriek)
        
        posities_lijst = []
        for product, groep in df_tx.groupby('Product'):
            huidig_aantal = groep['Aantal'].sum()
            totale_investering = groep[groep['Aantal'] > 0]['Waarde EUR'].sum()
            
            isin = groep['ISIN'].iloc[0] if 'ISIN' in groep.columns and not grupo_isin_na else ""
            product_str = str(product).upper()
            
            # Controleer via onze nieuwe slimme functie of het een optie is
            is_optie, optie_aandeel, optie_type, optie_strike, optie_exp = parse_optie_naam(product)
            
            if is_optie:
                product_type = "Optie"
                sector = "Optie"
            elif "UCITS" in product_str or "ETF" in product_str:
                product_type = "ETF"
                sector = "ETF"
            elif "CRYPTO" in str(isin) or product_str in ["BITCOIN", "ETHEREUM"]:
                product_type = "Crypto"
                sector = "Crypto"
            else:
                product_type = "Aandeel"
                sector = "Overig"
                for sleutel, sector_naam in SECTOR_MAP.items():
                    if sleutel in product_str:
                        sector = sector_naam
                        break
            
            if "SUBSCRIPTION" in product_str:
                continue

            if abs(huidig_aantal) > 0.000001:
                posities_lijst.append({
                    "Product": product,
                    "ISIN": isin,
                    "Huidig aantal": huidig_aantal,
                    "Kostenbasis (EUR)": abs(totale_investering),
                    "Type": product_type,
                    "Sector": sector
                })
                
        df_posities = pd.DataFrame(posities_lijst)
        # --- BEREKENING 2: DIVIDENDEN FILTEREN ---
        df_rek['Omschrijving'] = df_rek['Omschrijving'].astype(str)
        df_rek['Mutatie_Num'] = df_rek['Mutatie'].apply(maak_numeriek)
        
        df_only_dividends = df_rek[df_rek['Omschrijving'].str.contains('Dividend', case=False, na=False)]
        totaal_netto_dividend = df_only_dividends['Mutatie_Num'].sum()

        df_div_cards = df_rek[df_rek['Omschrijving'] == 'Dividend'].copy()
        df_div_cards['Maand'] = pd.to_datetime(df_div_cards['Datum'], format='%d-%m-%Y', errors='coerce').dt.to_period('M').astype(str)

        # --- INTERFACE: HOOFD-KPI'S ---
        st.markdown("---")
        kpi1, kpi2, kpi3 = st.columns(3)
        totale_kostenbasis = df_posities['Kostenbasis (EUR)'].sum() if not df_posities.empty else 0.0
        
        kpi1.metric(label="📉 Totale Kostenbasis (Open Posities)", value=f"€ {totale_kostenbasis:,.2f}")
        kpi2.metric(label="💰 Totaal Netto Dividend Ontvangen", value=f"€ {totaal_netto_dividend:,.2f}")
        kpi3.metric(label="📦 Aantal Open Producten", value=len(df_posities) if not df_posities.empty else 0)

        # --- LIVE FILTERS EN GRAFIEKEN ---
        if not df_posities.empty:
            soorten_in_portefeuille = df_posities['Type'].unique()
            gekozen_types = st.sidebar.multiselect("Filter op Type:", options=soorten_in_portefeuille, default=soorten_in_portefeuille)
            df_gefilterd = df_posities[df_posities['Type'].isin(gekozen_types)]
            
            st.subheader("Visualisaties & Allocatie")
            links, rechts = st.columns(2)
            
            with links:
                fig_allocatie = px.pie(
                    df_gefilterd, values='Kostenbasis (EUR)', names='Product', 
                    title='Portefeuille-allocatie (o.b.v. Kostenbasis)', hole=0.4
                )
                st.plotly_chart(fig_allocatie, use_container_width=True)
                
            with rechts:
                if not df_div_cards.empty:
                    df_div_maand = df_div_cards.groupby('Maand')['Mutatie_Num'].sum().reset_index()
                    fig_div = px.bar(
                        df_div_maand, x='Maand', y='Mutatie_Num', 
                        title='Ontvangen Bruto Dividend per Maand', color_discrete_sequence=['#2ecc71']
                    )
                    st.plotly_chart(fig_div, use_container_width=True)
                else:
                    st.info("Geen dividendgegevens gevonden.")

            # --- SLIMME OPTIESTRATEGIE HERKENNER (VERBETERD) ---
            st.markdown("---")
            st.subheader("🧠 Geautomatiseerde Optiestrategie Herkenner")
            
            # Filter alle transacties of open posities die een optie zijn
            df_opties_open = df_gefilterd[df_gefilterd['Type'] == 'Optie'].copy()
            
            if not df_opties_open.empty:
                optie_details = []
                for idx, row in df_opties_open.iterrows():
                    is_optie, aandeel, type_optie, strike, expiratie = parse_optie_naam(row['Product'])
                    optie_details.append({
                        "Product": row['Product'],
                        "Aandeel": aandeel,
                        "Type_Optie": type_optie,
                        "Strike": strike,
                        "Expiratie": expiratie,
                        "Kostenbasis": row['Kostenbasis (EUR)'],
                        "Aantal": row['Huidig aantal']
                    })
                df_opties_parsed = pd.DataFrame(optie_details)
                
                gecombineerde_strategieen = []
                # Groepeer op Onderliggend aandeel en Expiratiedatum om spreads te vinden
                for (aandeel, expiratie), groep in df_opties_parsed.groupby(['Aandeel', 'Expiratie']):
                    groep = groep.sort_values('Strike')
                    aantal_poten = len(groep)
                    totale_kosten = groep['Kostenbasis'].sum()
                    strikes_str = "/".join([f"{s:.2f}" for s in groep['Strike'].tolist()])
                    
                    if aantal_poten == 2:
                        aantallen = groep['Aantal'].tolist()
                        type_optie = groep['Type_Optie'].iloc[0]
                        if aantallen[0] > 0 and aantallen[1] < 0:
                            strategie_naam = f"🟢 Bull {type_optie} Spread ({strikes_str})"
                        elif aantallen[0] < 0 and aantallen[1] > 0:
                            strategie_naam = f"🔴 Bear {type_optie} Spread ({strikes_str})"
                        else:
                            strategie_naam = f"📦 {aandeel} Custom Spread ({strikes_str})"
                    elif aantal_poten >= 3:
                        strategie_naam = f"🦋 Geavanceerde {aandeel} Vlinder/Ratio Spread ({strikes_str})"
                    else:
                        row_opt = groep.iloc[0]
                        richting = "Long" if row_opt['Aantal'] > 0 else "Short"
                        strategie_naam = f"📄 Losse {richting} {row_opt['Type_Optie']} {row_opt['Strike']:.2f}"
                        
                    gecombineerde_strategieen.append({
                        "Onderliggend": aandeel,
                        "Expiratie": expiratie,
                        "Herkende Strategie": strategie_naam,
                        "Aantal Contracten": aantal_poten,
                        "Totale Kostenbasis (EUR)": totale_kosten
                    })
                
                st.dataframe(pd.DataFrame(gecombineerde_strategieen), use_container_width=True, hide_index=True)
            else:
                st.info("Geen open optieposities gedetecteerd in de gefilterde selectie.")

            # --- ALGEMENE TABEL ---
            st.markdown("---")
            st.subheader("📋 Lopende Posities (Gehaald uit je CSV)")
            st.dataframe(df_gefilterd, use_container_width=True, hide_index=True)
        else:
            st.warning("Geen open posities kunnen herleiden uit de transactiegeschiedenis.")
            
    except Exception as e:
        st.error(f"Er ging iets mis bij het verwerken van de bestanden: {e}")
else:
    st.info("ℹ️ **Instructie:** Exporteer je 'Transacties' en 'Rekeningoverzicht' als CSV-bestand uit je DeGiro-account und upload ze aan de linkerkant.")
