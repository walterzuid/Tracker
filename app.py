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

# Hulpmiddel om getallen uit DeGiro CSV netjes om te zetten
def maak_numeriek(val):
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip().replace('.', '').replace(',', '.')
    try:
        return float(val_str)
    except ValueError:
        return 0.0

# 3. CONTROLE: Zijn de bestanden geüpload?
if transacties_file is not None and rekening_file is not None:
    try:
        # Bestanden inlezen
        df_tx = pd.read_csv(transacties_file, sep=',', encoding='utf-8')
        df_rek = pd.read_csv(rekening_file, sep=',', encoding='utf-8')
        
        # Kolomnamen opschonen
        df_tx.columns = df_tx.columns.str.strip()
        df_rek.columns = df_rek.columns.str.strip()
        
        st.success("✅ Beide bestanden succesvol ingeladen! Data wordt verwerkt...")

        # --- BEREKENING 1: POSITIES BEREKENEN UIT TRANSACTIES ---
        df_tx['Datum_Tijd'] = pd.to_datetime(df_tx['Datum'] + ' ' + df_tx['Tijd'], errors='coerce')
        df_tx = df_tx.sort_values('Datum_Tijd').reset_index(drop=True)
        
        df_tx['Aantal'] = df_tx['Aantal'].apply(maak_numeriek)
        df_tx['Totaal (EUR)'] = df_tx['Totaal (EUR)'].apply(maak_numeriek)
        
        posities_lijst = []
        for product, groep in df_tx.groupby('Product'):
            huidig_aantal = groep['Aantal'].sum()
            totale_investering = groep[groep['Aantal'] > 0]['Totaal (EUR)'].sum()
            
            isin = groep['ISIN'].iloc[0] if 'ISIN' in groep.columns and not groep['ISIN'].isna().all() else ""
            product_str = str(product).upper()
            
            if "UCITS" in product_str or "ETF" in product_str:
                product_type = "ETF"
                sector = "ETF"
            elif "CRYPTO" in str(isin) or product_str in ["BITCOIN", "ETHEREUM"]:
                product_type = "Crypto"
                sector = "Crypto"
            elif any(optie_kenmerk in product_str for optie_kenmerk in [" C", " P", "CALL", "PUT"]) or len(product_str.split()) >= 3:
                product_type = "Optie"
                sector = "Optie"
            else:
                product_type = "Aandeel"
                sector = groep['Sector'].iloc[0] if 'Sector' in groep.columns and not pd.isna(groep['Sector'].iloc[0]) else "Aandelen"
            
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
        df_div = df_rek[df_rek['Omschrijving'].str.contains('Dividend|dividend', case=False, na=False)].copy()
        if not df_div.empty:
            kolom_bedrag = 'Bedrag (EUR)' if 'Bedrag (EUR)' in df_div.columns else 'Netto (EUR)'
            df_div['Netto (EUR)'] = df_div[kolom_bedrag].apply(maak_numeriek)
            df_div['Maand'] = pd.to_datetime(df_div['Datum'], errors='coerce').dt.to_period('M').astype(str)
            totaal_ontvangen_dividend = df_div['Netto (EUR)'].sum()
        else:
            totaal_ontvangen_dividend = 0.0

        # --- INTERFACE: HOOFD-KPI'S ---
        st.markdown("---")
        kpi1, kpi2, kpi3 = st.columns(3)
        totale_kostenbasis = df_posities['Kostenbasis (EUR)'].sum() if not df_posities.empty else 0.0
        
        kpi1.metric(label="📉 Totale Kostenbasis (Open Posities)", value=f"€ {totale_kostenbasis:,.2f}")
        kpi2.metric(label="💰 Totaal Dividend Ontvangen", value=f"€ {abs(totaal_ontvangen_dividend):,.2f}")
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
                if not df_div.empty:
                    df_div_maand = df_div.groupby('Maand')['Netto (EUR)'].sum().reset_index()
                    df_div_maand['Netto (EUR)'] = df_div_maand['Netto (EUR)'].abs()
                    fig_div = px.bar(
                        df_div_maand, x='Maand', y='Netto (EUR)', 
                        title='Ontvangen Dividend per Maand', color_discrete_sequence=['#2ecc71']
                    )
                    st.plotly_chart(fig_div, use_container_width=True)
                else:
                    st.info("Geen dividendgegevens gevonden in het rekeningoverzicht.")

            # --- SLIMME OPTIESTRATEGIE HERKENNER ---
            st.markdown("---")
            st.subheader("🧠 Geautomatiseerde Optiestrategie Herkenner")
            df_opties = df_gefilterd[df_gefilterd['Type'] == 'Optie'].copy()
            
            if not df_opties.empty:
                def split_optie_naam(naam):
                    delen = str(naam).split()
                    if len(delen) >= 3:
                        aandeel = delen[0]
                        type_optie = "Call" if any("C" in d for d in delen) else "Put"
                        expiratie = delen[-1]
                        return pd.Series([aandeel, type_optie, expiratie])
                    return pd.Series(["Onbekend", "Onbekend", "Onbekend"])

                df_opties[['Aandeel', 'Type_Optie', 'Expiratie']] = df_opties['Product'].apply(split_optie_naam)
                
                gecombineerde_strategieen = []
                for (aandeel, expiratie, type_optie), groep in df_opties.groupby(['Aandeel', 'Expiratie', 'Type_Optie']):
                    aantal_poten = len(groep)
                    totale_kosten = groep['Kostenbasis (EUR)'].sum()
                    
                    if aantal_poten >= 2:
                        strategie_naam = f"🟢 Gecombineerde {aandeel} {type_optie} Spread (Expiratie: {expiratie})"
                    else:
                        strategie_naam = f"📄 Losse {aandeel} {type_optie} Poot"
                        
                    gecombineerde_strategieen.append({
                        "Onderliggend": aandeel,
                        "Expiratie": expiratie,
                        "Berekende Strategie": strategie_naam,
                        "Aantal Contracten": aantal_poten,
                        "Kostenbasis Spreads (EUR)": totale_kosten
                    })
                st.dataframe(pd.DataFrame(gecombineerde_strategieen), use_container_width=True, hide_index=True)
            else:
                st.info("Selecteer 'Optie' in de zijbalk of voeg optietransacties toe om strategieën te zien.")

            # --- ALGEMENE TABEL ---
            st.markdown("---")
            st.subheader("📋 Lopende Posities (Gehaald uit je CSV)")
            st.dataframe(df_gefilterd, use_container_width=True, hide_index=True)
        else:
            st.warning("Geen open posities kunnen herleiden uit de transactiegeschiedenis.")
            
    except Exception as e:
        st.error(f"Er ging iets mis bij het verwerken van de bestanden: {e}")
else:
    st.info("ℹ️ **Instructie:** Exporteer je 'Transacties' en 'Rekeningoverzicht' als CSV-bestand uit je DeGiro-account en upload ze aan de linkerkant om je portfolio direct live te analyseren!")
