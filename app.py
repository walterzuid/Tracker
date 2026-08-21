import streamlit as st
import pandas as pd
import plotly.express as px
import io
import re
import yfinance as yf

# 1. Pagina-instellingen
st.set_page_config(page_title="DeGiro Live Tracker", layout="wide", page_icon="📊")

# Paginamenu aanmaken in de zijbalk
st.sidebar.title("📱 Menu")
pagina = st.sidebar.selectbox("Kies een pagina:", ["🔮 Open Posities & Dashboard", "💰 Gesloten Transacties"])

st.title(f"📊 DeGiro Portfolio Dashboard - {pagina}")
st.markdown("Sleep je DeGiro CSV-bestanden hieronder om je data live te analyseren.")

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

# Woordenlijst om DeGiro namen te koppelen aan live tickers op Yahoo Finance
TICKER_MAP = {
    "SHELL PLC": "SHELL.AS",
    "ASML HOLDING N.V.": "ASML.AS",
    "HEINEKEN NV": "HEIA.AS",
    "ADYEN N.V.": "ADYEN.AS",
    "KONINKLIJKE HEIJMANS NV": "HEIJ.AS",
    "MICROSOFT CORPORATION": "MSFT",
    "RHEINMETALL AG": "RHM.DE",
    "NN GROUP N.V.": "NN.AS",
    "ASM INTERNATIONAL NV": "ASM.AS",
    "KONINKLIJKE BAM GROEP NV": "BAMNB.AS",
    "AIRBUS SE": "AIR.PA",
    "ASR NEDERLAND N.V.": "ASRNL.AS",
    "BITCOIN": "BTC-EUR",
    "ETHEREUM": "ETH-EUR",
    "VANECK GOLD MINERS UCITS ETF USD A": "GDX",
    "VANECK AEX UCITS ETF": "IAEX.AS"
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
    match = re.search(r'^([A-Z0-9\.\-\s]+)\s+([CP])(\d+(?:\.\d+)?)\s+(.+)$', naam_str, re.IGNORECASE)
    
    if match:
        aandeel = match.group(1).strip().upper()
        type_optie = "Call" if match.group(2).upper() == "C" else "Put"
        strike = float(match.group(3))
        expiratie = match.group(4).strip()
        return True, aandeel, type_optie, strike, expiratie
    return False, None, None, 0.0, None
# Centrale functie om optiestrategieën te groeperen en het rendement te berekenen
def groepeer_optiestrategieen(df_opties_raw, is_open_pagina=True):
    optie_details = []
    for idx, row in df_opties_raw.iterrows():
        is_optie, aandeel, type_optie, strike, expiratie = parse_optie_naam(row['Product'])
        if is_optie:
            optie_details.append({
                "Product": row['Product'], "Aandeel": aandeel, "Type_Optie": type_optie,
                "Strike": strike, "Expiratie": expiratie, 
                "Investering": row['Kostenbasis (EUR)'] if is_open_pagina else row['Totale Aankopen (EUR)'],
                "Resultaat": 0.0 if is_open_pagina else row['Gerealiseerd Resultaat (EUR)'],
                "Aantal": row['Huidig aantal'] if is_open_pagina else 1.0
            })
    
    if not optie_details:
        return pd.DataFrame()
        
    df_parsed = pd.DataFrame(optie_details)
    gecombineerde_strategieen = []
    
    for (aandeel, expiratie), groep in df_parsed.groupby(['Aandeel', 'Expiratie']):
        groep = groep.sort_values('Strike')
        aantal_poten = len(groep)
        totale_kosten = groep['Investering'].sum()
        totaal_resultaat = groep['Resultaat'].sum()
        strikes_str = "/".join([f"{s:.2f}" for s in groep['Strike'].tolist()])
        
        if aantal_poten == 2:
            aantallen = groep['Aantal'].tolist()
            type_optie = groep['Type_Optie'].iloc
            has_long = any(x > 0 for x in aantallen)
            has_short = any(x < 0 for x in aantallen)
            
            if has_long and has_short:
                strategie_naam = f"🟢 {type_optie} Spread ({strikes_str})"
            else:
                strategie_naam = f"📦 {aandeel} Custom Spread ({strikes_str})"
        elif aantal_poten >= 3:
            strategie_naam = f"🦋 Geavanceerde {aandeel} Vlinder/Ratio Spread ({strikes_str})"
        else:
            row_opt = groep.iloc
            richting = "Long" if row_opt['Aantal'] > 0 else "Short"
            strategie_naam = f"📄 Losse {richting} {row_opt['Type_Optie']} {row_opt['Strike']:.2f}"
            
        data_item = {
            "Onderliggend": aandeel, "Expiratie": expiratie, "Herkende Strategie": strategie_naam,
            "Aantal Contracten": aantal_poten, "Totale Aankopen/Investering (EUR)": totale_kosten
        }
        if not is_open_pagina:
            data_item["Gerealiseerd Resultaat (EUR)"] = totaal_resultaat
            data_item["Rendement (%)"] = (totaal_resultaat / totale_kosten * 100) if totale_kosten > 0 else 0.0
            
        gecombineerde_strategieen.append(data_item)
        
    return pd.DataFrame(gecombineerde_strategieen)

# Live koers ophaalfunctie via Yahoo Finance (yfinance)
@st.cache_data(ttl=3600)
def haal_live_koers(product_naam):
    product_naam = str(product_naam).strip()
    if product_naam in TICKER_MAP:
        ticker_symbol = TICKER_MAP[product_naam]
        try:
            ticker = yf.Ticker(ticker_symbol)
            data = ticker.history(period="1d")
            if not data.empty:
                return float(data['Close'].iloc[-1])
        except Exception:
            return None
    return None

# 3. CONTROLE: Zijn de bestanden geüpload?
if transacties_file is not None and rekening_file is not None:
    try:
        df_tx = pd.read_csv(transacties_file, sep=',', encoding='utf-8')
        df_rek = pd.read_csv(rekening_file, sep=',', encoding='utf-8')
        
        df_tx.columns = df_tx.columns.str.strip()
        df_rek.columns = df_rek.columns.str.strip()
        
        df_rek = df_rek.rename(columns={
            'Mutatie': 'Munt_Mutatie', 'Unnamed: 8': 'Bedrag_Mutatie',
            'Saldo': 'Munt_Saldo', 'Unnamed: 10': 'Bedrag_Saldo'
        })
        
        st.success("✅ Beide bestanden succesvol ingeladen!")

        df_tx['Datum_Tijd'] = pd.to_datetime(df_tx['Datum'] + ' ' + df_tx['Tijd'], format='%d-%m-%Y %H:%M', errors='coerce')
        df_tx = df_tx.sort_values('Datum_Tijd').reset_index(drop=True)
        
        df_tx['Waarde EUR'] = df_tx['Waarde EUR'].apply(maak_numeriek)
        df_tx['Koers'] = df_tx['Koers'].apply(maak_numeriek)
        df_tx['Transactiekosten en/of kosten van derden EUR'] = df_tx['Transactiekosten en/of kosten van derden EUR'].apply(maak_numeriek)
        df_tx['Totaal EUR'] = df_tx['Totaal EUR'].apply(maak_numeriek)

        aantal_gecorrigeerd = []
        for idx, row in df_tx.iterrows():
            prod_upper = str(row['Product']).upper()
            if prod_upper in ["BITCOIN", "ETHEREUM"] and (pd.isna(row['Aantal']) or row['Aantal'] == "" or maak_numeriek(row['Aantal']) == 0.0):
                berekend_aantal = abs(row['Waarde EUR']) / row['Koers'] if row['Koers'] > 0 else 0.0
                aantal_gecorrigeerd.append(berekend_aantal)
            else:
                aantal_gecorrigeerd.append(maak_numeriek(row['Aantal']))
        df_tx['Aantal'] = aantal_gecorrigeerd

        open_posities_lijst = []
        gesloten_posities_lijst = []
        
        for product, groep in df_tx.groupby('Product'):
            huidig_aantal = groep['Aantal'].sum()
            totale_aankopen_eur = groep[groep['Aantal'] > 0]['Waarde EUR'].sum()
            totale_verkopen_eur = groep[groep['Aantal'] < 0]['Waarde EUR'].sum()
            totaal_kosten = groep['Transactiekosten en/of kosten van derden EUR'].sum()
            netto_resultaat_tx = groep['Totaal EUR'].sum()
            
            isin = str(groep['ISIN'].iloc) if 'ISIN' in groep.columns and not groep['ISIN'].isna().all() else ""
            product_str = str(product).upper()
            
            is_optie, optie_aandeel, optie_type, optie_strike, optie_exp = parse_optie_naam(product)
            
            if is_optie:
                product_type = "Optie"
                sector = "Optie"
            elif "UCITS" in product_str or "ETF" in product_str:
                product_type = "ETF"
                sector = "ETF"
            elif "CRYPTO" in isin or product_str in ["BITCOIN", "ETHEREUM"]:
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
                # GEFIXT: Hier staat nu de correcte functienaam haal_live_koers() met een 's'
                actuele_koer_val = haal_live_koer(product) if 'haal_live_koer' in globals() else haal_live_koers(product)
                kostenbasis = abs(totale_aankopen_eur)
                
                if actuele_koer_val is not None:
                    marktwaarde = huidig_aantal * actuele_koer_val
                    ongerealiseerd_res = marktwaarde - kostenbasis
                    ongerealiseerd_rend = (ongerealiseerd_res / kostenbasis * 100) if kostenbasis > 0 else 0.0
                else:
                    marktwaarde = 0.0
                    ongerealiseerd_res = 0.0
                    ongerealiseerd_rend = 0.0
                
                open_posities_lijst.append({
                    "Product": product, "ISIN": isin, "Huidig aantal": huidig_aantal,
                    "Kostenbasis (EUR)": kostenbasis, "Actuele Koers": actuele_koer_val if actuele_koer_val else 0.0,
                    "Marktwaarde (EUR)": marktwaarde, "Ongerealiseerd resultaat (EUR)": ongerealiseerd_res,
                    "Ongerealiseerd rendement (%)": ongerealiseerd_rend,
                    "Type": product_type, "Sector": sector
                })
            else:
                gesloten_posities_lijst.append({
                    "Product": product, "ISIN": isin, "Totale Aankopen (EUR)": abs(totale_aankopen_eur),
                    "Totale Verkopen (EUR)": abs(totale_verkopen_eur), "Betaalde Kosten (EUR)": abs(totaal_kosten),
                    "Gerealiseerd Resultaat (EUR)": netto_resultaat_tx, "Type": product_type, "Sector": sector,
                    "Huidig aantal": 0.0
                })
                
        df_posities = pd.DataFrame(open_posities_lijst)
        df_gesloten = pd.DataFrame(gesloten_posities_lijst)
        # --- BEREKENING 2: DIVIDENDEN BEREKENEN ---
        df_rek['Omschrijving'] = df_rek['Omschrijving'].astype(str)
        df_rek['Bedrag_Mutatie_Num'] = df_rek['Bedrag_Mutatie'].apply(maak_numeriek)
        
        df_only_dividends = df_rek[df_rek['Omschrijving'].str.contains('Dividend', case=False, na=False)]
        totaal_netto_dividend = df_only_dividends['Bedrag_Mutatie_Num'].sum()

        df_div_cards = df_rek[df_rek['Omschrijving'] == 'Dividend'].copy()
        df_div_cards['Maand'] = pd.to_datetime(df_div_cards['Datum'], format='%d-%m-%Y', errors='coerce').dt.to_period('M').astype(str)

        # ----------------------------------------------------
        # PAGINA 1: OPEN POSITIES & DASHBOARD
        # ----------------------------------------------------
        if pagina == "🔮 Open Posities & Dashboard":
            st.markdown("---")
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            
            totale_kostenbasis = df_posities['Kostenbasis (EUR)'].sum() if not df_posities.empty else 0.0
            totale_marktwaarde = df_posities['Marktwaarde (EUR)'].sum() if not df_posities.empty else 0.0
            totaal_ongerealiseerd = totale_marktwaarde - totale_kostenbasis
            totaal_ongerealiseerd_rend = (totaal_ongerealiseerd / totale_kostenbasis * 100) if totale_kostenbasis > 0 else 0.0
            
            kpi1.metric(label="📉 Totale Kostenbasis", value=f"€ {totale_kostenbasis:,.2f}")
            kpi2.metric(label="💰 Actuele Marktwaarde Live", value=f"€ {totale_marktwaarde:,.2f}")
            kpi3.metric(label="📈 Live Ongerealiseerd Resultaat", value=f"€ {totaal_ongerealiseerd:,.2f}", delta=f"{totaal_ongerealiseerd_rend:.2f}%")
            kpi4.metric(label="💶 Netto Dividend", value=f"€ {totaal_netto_dividend:,.2f}")

            if not df_posities.empty:
                soorten_in_portefeuille = df_posities['Type'].unique()
                gekozen_types = st.sidebar.multiselect("Filter op Type:", options=soorten_in_portefeuille, default=soorten_in_portefeuille)
                df_gefilterd = df_posities[df_posities['Type'].isin(gekozen_types)]
                
                st.subheader("Visualisaties & Live Allocatie")
                links, rechts = st.columns(2)
                
                with links:
                    fig_allocatie = px.pie(
                        df_gefilterd[df_gefilterd['Marktwaarde (EUR)'] > 0], values='Marktwaarde (EUR)', names='Product', 
                        title='Portefeuille-allocatie (Live Marktwaarde)', hole=0.4
                    )
                    st.plotly_chart(fig_allocatie, use_container_width=True)
                    
                with rechts:
                    if not df_div_cards.empty:
                        df_div_maand = df_div_cards.groupby('Maand')['Bedrag_Mutatie_Num'].sum().reset_index()
                        fig_div = px.bar(
                            df_div_maand, x='Maand', y='Bedrag_Mutatie_Num', 
                            title='Ontvangen Bruto Dividend per Maand', color_discrete_sequence=['#2ecc71']
                        )
                        st.plotly_chart(fig_div, use_container_width=True)
                    else:
                        st.info("Geen dividendgegevens gevonden.")

                st.markdown("---")
                st.subheader("🧠 Geautomatiseerde Optiestrategie Herkenner (Open Spreads)")
                df_opties_open = df_gefilterd[df_gefilterd['Type'] == 'Optie'].copy()
                
                if not df_opties_open.empty:
                    df_open_spreads = groepeer_optiestrategieen(df_opties_open, is_open_pagina=True)
                    if not df_open_spreads.empty:
                        st.dataframe(df_open_spreads, use_container_width=True, hide_index=True)
                else:
                    st.info("Geen open optieposities gedetecteerd.")
                
                st.markdown("---")
                st.subheader("📋 Lopende Posities met Live Koersen (Yahoo Finance)")
                st.dataframe(
                    df_gefilterd[['Product', 'ISIN', 'Huidig aantal', 'Kostenbasis (EUR)', 'Actuele Koers', 'Marktwaarde (EUR)', 'Ongerealiseerd resultaat (EUR)', 'Ongerealiseerd rendement (%)', 'Sector']],
                    column_config={
                        "Kostenbasis (EUR)": st.column_config.NumberColumn(format="€ %.2f"),
                        "Actuele Koers": st.column_config.NumberColumn(format="€ %.4f"),
                        "Marktwaarde (EUR)": st.column_config.NumberColumn(format="€ %.2f"),
                        "Ongerealiseerd resultaat (EUR)": st.column_config.NumberColumn(format="€ %.2f"),
                        "Ongerealiseerd rendement (%)": st.column_config.NumberColumn(format="%.2f %%")
                    },
                    use_container_width=True, hide_index=True
                )

        # ----------------------------------------------------
        # PAGINA 2: GESLOTEN TRANSACTIES
        # ----------------------------------------------------
        elif pagina == "💰 Gesloten Transacties":
            st.markdown("---")
            st.subheader("🏁 Volledig Gesloten Posities (Historisch resultaat)")
            
            if not df_gesloten.empty:
                totaal_gerealiseerd = df_gesloten['Gerealiseerd Resultaat (EUR)'].sum()
                st.metric(
                    label="📈 Totaal Gerealiseerd Resultaat (Winst / Verlies)", 
                    value=f"€ {totaal_gerealiseerd:,.2f}",
                    delta=f"Resultaat sinds start" if totaal_gerealiseerd >= 0 else f"Verlies sinds start",
                    delta_color="normal" if totaal_gerealiseerd >= 0 else "inverse"
                )
                
                df_gesloten_aandelen = df_gesloten[df_gesloten['Type'] != 'Optie'].copy()
                df_gesloten_opties_raw = df_gesloten[df_gesloten['Type'] == 'Optie'].copy()
                
                st.subheader("🧠 Historisch Gesloten Optiestrategieën & Rendement")
                if not df_gesloten_opties_raw.empty:
                    df_gesloten_spreads = groepeer_optiestrategieen(df_gesloten_opties_raw, is_open_pagina=False)
                    if not df_gesloten_spreads.empty:
                        st.dataframe(
                            df_gesloten_spreads,
                            column_config={
                                "Totale Aankopen/Investering (EUR)": st.column_config.NumberColumn(format="€ %.2f"),
                                "Gerealiseerd Resultaat (EUR)": st.column_config.NumberColumn(format="€ %.2f"),
                                "Rendement (%)": st.column_config.NumberColumn(format="%.2f %%")
                            },
                            use_container_width=True, hide_index=True
                        )
                else:
                    st.info("Geen gesloten optieposities gevonden.")
                
                st.markdown("---")
                st.subheader("📈 Gesloten Aandelen, ETF's & Crypto")
                if not df_gesloten_aandelen.empty:
                    df_gesloten_aandelen['Rendement (%)'] = (df_gesloten_aandelen['Gerealiseerd Resultaat (EUR)'] / df_gesloten_aandelen['Totale Aankopen (EUR)'] * 100)
                    st.dataframe(
                        df_gesloten_aandelen[['Product', 'ISIN', 'Totale Aankopen (EUR)', 'Totale Verkopen (EUR)', 'Betaalde Kosten (EUR)', 'Gerealiseerd Resultaat (EUR)', 'Rendement (%)', 'Sector']],
                        column_config={
                            "Totale Aankopen (EUR)": st.column_config.NumberColumn(format="€ %.2f"),
                            "Totale Verkopen (EUR)": st.column_config.NumberColumn(format="€ %.2f"),
                            "Betaalde Kosten (EUR)": st.column_config.NumberColumn(format="€ %.2f"),
                            "Gerealiseerd Resultaat (EUR)": st.column_config.NumberColumn(format="€ %.2f"),
                            "Rendement (%)": st.column_config.NumberColumn(format="%.2f %%")
                        },
                        use_container_width=True, hide_index=True
                    )
                
                st.markdown("---")
                st.subheader("📊 Gerealiseerde Resultaten per Product")
                fig_gesloten = px.bar(
                    df_gesloten, x='Product', y='Gerealiseerd Resultaat (EUR)',
                    title="Winst / Verlies per gesloten positie", color='Gerealiseerd Resultaat (EUR)',
                    color_continuous_scale=px.colors.sequential.RdBu_r
                )
                st.plotly_chart(fig_gesloten, use_container_width=True)
            else:
                st.info("Geen volledig gesloten posities gevonden.")

    except Exception as e:
        st.error(f"Er ging iets mis bij het verwerken van de bestanden: {e}")
else:
    st.info("ℹ️ **Instructie:** Exporteer je 'Transacties' en 'Rekeningoverzicht' als CSV-bestand uit je DeGiro-account en upload ze aan de linkerkant.")
