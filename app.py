"""
Aandelenportfolio Tracker
--------------------------
Een Streamlit-app om aandelentransacties bij te houden, live koersen op te
halen (via yfinance), je rendement en verdeling te visualiseren, en
transacties + rekeningoverzicht rechtstreeks vanuit DeGiro te importeren.

Starten:
    pip install -r requirements.txt
    streamlit run app.py
"""

import os
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from degiro_import import (
    degiro_naar_portfolio_formaat,
    unieke_isins,
    pas_ticker_mapping_toe,
    vul_ticker_suggesties_aan,
    parse_degiro_account_csv,
    degiro_account_samenvatting,
    degiro_kasstroom,
)

try:
    import yfinance as yf
    YFINANCE_BESCHIKBAAR = True
except ImportError:
    YFINANCE_BESCHIKBAAR = False

# ---------------------------------------------------------------------------
# Configuratie
# ---------------------------------------------------------------------------
DATA_BESTAND = "transacties.csv"
MAPPING_BESTAND = "isin_ticker_mapping.csv"
ACCOUNT_BESTAND = "rekeningoverzicht.csv"

KOLOMMEN = ["datum", "ticker", "type", "aantal", "prijs", "isin", "product", "order_id"]

st.set_page_config(page_title="Portfolio Tracker", page_icon="📈", layout="wide")


# ---------------------------------------------------------------------------
# Data laden / opslaan -- transacties
# ---------------------------------------------------------------------------
def laad_transacties() -> pd.DataFrame:
    if os.path.exists(DATA_BESTAND):
        df = pd.read_csv(DATA_BESTAND, parse_dates=["datum"])
        for kolom in KOLOMMEN:
            if kolom not in df.columns:
                df[kolom] = None
        return df[KOLOMMEN]
    return pd.DataFrame(columns=KOLOMMEN)


def sla_transacties_op(df: pd.DataFrame) -> None:
    df.to_csv(DATA_BESTAND, index=False)


if "transacties" not in st.session_state:
    st.session_state.transacties = laad_transacties()


# ---------------------------------------------------------------------------
# Data laden / opslaan -- ISIN -> ticker mapping
# ---------------------------------------------------------------------------
def laad_isin_mapping() -> dict:
    if os.path.exists(MAPPING_BESTAND):
        df = pd.read_csv(MAPPING_BESTAND, dtype=str)
        return dict(zip(df["isin"], df["ticker"]))
    return {}


def sla_isin_mapping_op(mapping: dict) -> None:
    pd.DataFrame({"isin": list(mapping.keys()), "ticker": list(mapping.values())}).to_csv(
        MAPPING_BESTAND, index=False
    )


if "isin_mapping" not in st.session_state:
    st.session_state.isin_mapping = laad_isin_mapping()


# ---------------------------------------------------------------------------
# Data laden / opslaan -- rekeningoverzicht
# ---------------------------------------------------------------------------
def laad_account_overzicht() -> pd.DataFrame:
    if os.path.exists(ACCOUNT_BESTAND):
        return pd.read_csv(ACCOUNT_BESTAND, parse_dates=["datum"])
    return pd.DataFrame(columns=["datum", "tijd", "product", "isin", "omschrijving",
                                  "mutatie", "mutatie_valuta", "saldo", "saldo_valuta",
                                  "order_id", "categorie"])


def sla_account_overzicht_op(df: pd.DataFrame) -> None:
    df.to_csv(ACCOUNT_BESTAND, index=False)


if "account_overzicht" not in st.session_state:
    st.session_state.account_overzicht = laad_account_overzicht()

# Tellers gebruikt om file_uploader-widgets te kunnen "resetten" na een
# succesvolle import (Streamlit-widgets houden hun waarde vast op basis van
# hun key; een nieuwe key geeft een lege uploader).
if "degiro_transactie_upload_teller" not in st.session_state:
    st.session_state.degiro_transactie_upload_teller = 0
if "degiro_account_upload_teller" not in st.session_state:
    st.session_state.degiro_account_upload_teller = 0


# ---------------------------------------------------------------------------
# Koersen ophalen
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def haal_huidige_koers(ticker: str) -> float | None:
    if not YFINANCE_BESCHIKBAAR:
        return None
    try:
        info = yf.Ticker(ticker).history(period="1d")
        if info.empty:
            return None
        return float(info["Close"].iloc[-1])
    except Exception:
        return None


@st.cache_data(ttl=300)
def haal_historie(ticker: str, periode: str = "6mo") -> pd.DataFrame:
    if not YFINANCE_BESCHIKBAAR:
        return pd.DataFrame()
    try:
        return yf.Ticker(ticker).history(period=periode)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Portfolio berekeningen
# ---------------------------------------------------------------------------
def bereken_posities(transacties: pd.DataFrame) -> pd.DataFrame:
    if transacties.empty:
        return pd.DataFrame(
            columns=["ticker", "aantal", "gem_aankoopprijs", "kostprijs",
                     "huidige_koers", "waarde", "resultaat", "resultaat_pct"]
        )

    rijen = []
    for ticker, groep in transacties.groupby("ticker"):
        aantal = 0.0
        totale_kosten = 0.0
        for _, rij in groep.sort_values("datum").iterrows():
            if rij["type"] == "Koop":
                totale_kosten += rij["aantal"] * rij["prijs"]
                aantal += rij["aantal"]
            else:  # Verkoop
                if aantal > 0:
                    gem_prijs = totale_kosten / aantal
                    totale_kosten -= gem_prijs * rij["aantal"]
                aantal -= rij["aantal"]

        if aantal <= 0:
            continue

        gem_aankoopprijs = totale_kosten / aantal if aantal else 0
        huidige_koers = haal_huidige_koers(ticker)
        waarde = aantal * huidige_koers if huidige_koers else None
        resultaat = (waarde - totale_kosten) if waarde is not None else None
        resultaat_pct = (resultaat / totale_kosten * 100) if resultaat is not None and totale_kosten else None

        rijen.append({
            "ticker": ticker,
            "aantal": aantal,
            "gem_aankoopprijs": gem_aankoopprijs,
            "kostprijs": totale_kosten,
            "huidige_koers": huidige_koers,
            "waarde": waarde,
            "resultaat": resultaat,
            "resultaat_pct": resultaat_pct,
        })

    return pd.DataFrame(rijen)


def voeg_transacties_samen(nieuw: pd.DataFrame) -> int:
    """Voegt geïmporteerde transacties toe aan de portfolio, met
    deduplicatie zodat je hetzelfde DeGiro-bestand meerdere keren kunt
    importeren zonder dubbele posities te krijgen. 'order_id' alleen is
    geen betrouwbare sleutel (DeGiro hergebruikt hetzelfde order_id bij
    deelorders/partial fills), dus de dedup-sleutel is de combinatie van
    datum + isin + type + aantal + prijs. Geeft het aantal daadwerkelijk
    toegevoegde rijen terug."""
    bestaand = st.session_state.transacties
    sleutel = ["datum", "isin", "type", "aantal", "prijs"]

    if bestaand.empty:
        bestaande_sleutels = set()
    else:
        bestaande_sleutels = set(bestaand[sleutel].apply(tuple, axis=1))

    if not nieuw.empty:
        nieuw = nieuw[~nieuw[sleutel].apply(tuple, axis=1).isin(bestaande_sleutels)]

    if nieuw.empty:
        return 0

    for kolom in KOLOMMEN:
        if kolom not in nieuw.columns:
            nieuw[kolom] = None

    st.session_state.transacties = pd.concat(
        [bestaand, nieuw[KOLOMMEN]], ignore_index=True
    )
    sla_transacties_op(st.session_state.transacties)
    return len(nieuw)


# ---------------------------------------------------------------------------
# Sidebar: transactie toevoegen (handmatig)
# ---------------------------------------------------------------------------
st.sidebar.header("➕ Transactie toevoegen")

if not YFINANCE_BESCHIKBAAR:
    st.sidebar.warning("`yfinance` is niet geïnstalleerd. Voer `pip install yfinance` uit voor live koersen.")

with st.sidebar.form("transactie_form", clear_on_submit=True):
    ticker_input = st.text_input("Ticker (bv. AAPL, ASML.AS)").upper().strip()
    type_input = st.selectbox("Type", ["Koop", "Verkoop"])
    aantal_input = st.number_input("Aantal", min_value=0.0, step=1.0, format="%.4f")
    prijs_input = st.number_input("Prijs per aandeel (€)", min_value=0.0, step=0.01, format="%.2f")
    datum_input = st.date_input("Datum", value=date.today())
    verzonden = st.form_submit_button("Toevoegen")

    if verzonden:
        if not ticker_input or aantal_input <= 0 or prijs_input <= 0:
            st.sidebar.error("Vul alle velden correct in.")
        else:
            nieuwe_rij = pd.DataFrame([{
                "datum": pd.to_datetime(datum_input),
                "ticker": ticker_input,
                "type": type_input,
                "aantal": aantal_input,
                "prijs": prijs_input,
                "isin": None,
                "product": None,
                "order_id": None,
            }])
            st.session_state.transacties = pd.concat(
                [st.session_state.transacties, nieuwe_rij], ignore_index=True
            )
            sla_transacties_op(st.session_state.transacties)
            st.sidebar.success(f"{type_input} van {aantal_input} {ticker_input} toegevoegd.")

st.sidebar.divider()
st.sidebar.subheader("🗑️ Transactie verwijderen")
if not st.session_state.transacties.empty:
    idx_te_verwijderen = st.sidebar.selectbox(
        "Selecteer rij-index",
        st.session_state.transacties.index,
        format_func=lambda i: (
            f"{st.session_state.transacties.loc[i, 'datum'].date()} - "
            f"{st.session_state.transacties.loc[i, 'type']} "
            f"{st.session_state.transacties.loc[i, 'aantal']} "
            f"{st.session_state.transacties.loc[i, 'ticker']}"
        ),
    )
    if st.sidebar.button("Verwijder geselecteerde transactie"):
        st.session_state.transacties = st.session_state.transacties.drop(idx_te_verwijderen).reset_index(drop=True)
        sla_transacties_op(st.session_state.transacties)
        st.sidebar.success("Transactie verwijderd.")
        st.rerun()
else:
    st.sidebar.caption("Nog geen transacties om te verwijderen.")


# ---------------------------------------------------------------------------
# Sidebar: DeGiro-import
# ---------------------------------------------------------------------------
st.sidebar.divider()
st.sidebar.header("📥 Importeer van DeGiro")
st.sidebar.caption("DeGiro -> Activiteit -> Transacties / Rekeningoverzicht -> Exporteren")

# --- Transactieoverzicht ---
transactie_bestand = st.sidebar.file_uploader(
    "Transactieoverzicht.csv",
    type="csv",
    key=f"degiro_transactie_upload_{st.session_state.degiro_transactie_upload_teller}",
)

if transactie_bestand is not None:
    try:
        geimporteerd, opties = degiro_naar_portfolio_formaat(transactie_bestand)
    except ValueError as fout:
        st.sidebar.error(str(fout))
        geimporteerd, opties = None, None

    if opties is not None and not opties.empty:
        st.sidebar.info(
            f"ℹ️ {len(opties)} optietransactie(s) gevonden en overgeslagen "
            "(opties worden nog niet ondersteund door deze tracker)."
        )
        with st.sidebar.expander("Bekijk overgeslagen optietransacties"):
            st.dataframe(opties[["datum", "product", "aantal", "koers", "koers_valuta"]],
                         hide_index=True, use_container_width=True)

    if geimporteerd is not None and not geimporteerd.empty:
        st.sidebar.success(f"{len(geimporteerd)} aandelentransactie(s) gevonden in het bestand.")

        # Ticker-mapping: vul bekende tickers in op basis van eerdere mapping,
        # en probeer de rest automatisch op te zoeken via Yahoo Finance.
        isins = unieke_isins(geimporteerd)
        isins["ticker"] = isins["isin"].map(st.session_state.isin_mapping).fillna("")

        nog_niet_gekoppeld = int((isins["ticker"] == "").sum())
        if nog_niet_gekoppeld and "isin_auto_opgezocht" not in st.session_state:
            with st.sidebar.status(f"🔍 {nog_niet_gekoppeld} ticker(s) automatisch opzoeken..."):
                isins = vul_ticker_suggesties_aan(isins)
            st.session_state.isin_auto_opgezocht = True
            st.session_state.isin_suggesties = dict(zip(isins["isin"], isins["ticker"]))
        elif "isin_suggesties" in st.session_state:
            isins["ticker"] = isins.apply(
                lambda r: r["ticker"] or st.session_state.isin_suggesties.get(r["isin"], ""), axis=1
            )

        st.sidebar.markdown(
            "**Controleer de ticker per ISIN** (automatisch opgezochte suggesties zijn al ingevuld). "
            "Laat een ticker **leeg** om die ISIN over te slaan (bv. claimrechten, "
            "niet-verhandelbare posities of andere bijzondere boekingen)."
        )
        bewerkte_mapping = st.sidebar.data_editor(
            isins,
            column_config={
                "isin": st.column_config.TextColumn("ISIN", disabled=True),
                "product": st.column_config.TextColumn("Product", disabled=True),
                "ticker": st.column_config.TextColumn(
                    "Ticker", help="Leeg laten = deze ISIN overslaan bij het importeren."
                ),
            },
            hide_index=True,
            use_container_width=True,
            key="isin_mapping_editor",
        )

        if st.sidebar.button("✅ Bevestig mapping en importeer transacties"):
            bewerkte_mapping["ticker"] = bewerkte_mapping["ticker"].fillna("").str.strip().str.upper()
            nieuwe_mapping = {
                isin: ticker for isin, ticker in zip(bewerkte_mapping["isin"], bewerkte_mapping["ticker"])
                if ticker
            }
            overgeslagen_isins = set(bewerkte_mapping["isin"]) - set(nieuwe_mapping.keys())

            st.session_state.isin_mapping.update(nieuwe_mapping)
            sla_isin_mapping_op(st.session_state.isin_mapping)

            te_importeren = geimporteerd[~geimporteerd["isin"].isin(overgeslagen_isins)].copy()
            te_importeren = pas_ticker_mapping_toe(te_importeren, st.session_state.isin_mapping)
            aantal_toegevoegd = voeg_transacties_samen(te_importeren)

            st.session_state.degiro_transactie_upload_teller += 1  # reset uploader
            st.session_state.pop("isin_auto_opgezocht", None)
            st.session_state.pop("isin_suggesties", None)

            berichten = []
            if aantal_toegevoegd:
                berichten.append(f"{aantal_toegevoegd} nieuwe transactie(s) geïmporteerd.")
            else:
                berichten.append("Geen nieuwe transacties geïmporteerd (al aanwezig of overgeslagen).")
            if overgeslagen_isins:
                berichten.append(f"{len(overgeslagen_isins)} ISIN(s) overgeslagen (lege ticker).")
            st.sidebar.success(" ".join(berichten))
            st.rerun()

# --- Rekeningoverzicht ---
account_bestand = st.sidebar.file_uploader(
    "Rekeningoverzicht.csv",
    type="csv",
    key=f"degiro_account_upload_{st.session_state.degiro_account_upload_teller}",
)

if account_bestand is not None:
    try:
        nieuw_account_df = parse_degiro_account_csv(account_bestand)
    except ValueError as fout:
        st.sidebar.error(str(fout))
        nieuw_account_df = None

    if nieuw_account_df is not None and not nieuw_account_df.empty:
        bestaand = st.session_state.account_overzicht
        samengevoegd = pd.concat([bestaand, nieuw_account_df], ignore_index=True)
        dedup_kolommen = ["datum", "tijd", "omschrijving", "mutatie", "saldo"]
        voor = len(samengevoegd)
        samengevoegd = samengevoegd.drop_duplicates(subset=dedup_kolommen).reset_index(drop=True)
        aantal_nieuw = len(samengevoegd) - len(bestaand)

        st.session_state.account_overzicht = samengevoegd
        sla_account_overzicht_op(samengevoegd)
        st.session_state.degiro_account_upload_teller += 1  # reset uploader

        if aantal_nieuw > 0:
            st.sidebar.success(f"{aantal_nieuw} nieuwe boeking(en) uit het rekeningoverzicht geïmporteerd.")
        else:
            st.sidebar.info("Alle boekingen in dit bestand waren al geïmporteerd.")
        st.rerun()


# ---------------------------------------------------------------------------
# Hoofdscherm
# ---------------------------------------------------------------------------
st.title("📈 Aandelenportfolio Tracker")

transacties = st.session_state.transacties

if transacties.empty:
    st.info("Voeg links een eerste transactie toe, of importeer je DeGiro-bestanden, om je portfolio te starten.")
    st.stop()

posities = bereken_posities(transacties)

if posities.empty:
    st.info("Alle posities zijn gesloten. Voeg een nieuwe koop toe om te starten.")
    st.stop()

# --- Kerncijfers ---
totale_waarde = posities["waarde"].sum(skipna=True)
totale_kosten = posities["kostprijs"].sum()
totaal_resultaat = totale_waarde - totale_kosten if totale_waarde else None
totaal_resultaat_pct = (totaal_resultaat / totale_kosten * 100) if totaal_resultaat is not None and totale_kosten else None

col1, col2, col3, col4 = st.columns(4)
col1.metric("Totale waarde", f"€ {totale_waarde:,.2f}" if totale_waarde else "n.v.t.")
col2.metric("Inleg (kostprijs posities)", f"€ {totale_kosten:,.2f}")
col3.metric(
    "Resultaat",
    f"€ {totaal_resultaat:,.2f}" if totaal_resultaat is not None else "n.v.t.",
    delta=f"{totaal_resultaat_pct:.2f}%" if totaal_resultaat_pct is not None else None,
)
col4.metric("Aantal posities", len(posities))

st.divider()

# --- Posities tabel ---
st.subheader("Huidige posities")
weergave = posities.copy()
weergave.columns = ["Ticker", "Aantal", "Gem. aankoopprijs", "Kostprijs",
                     "Huidige koers", "Waarde", "Resultaat", "Resultaat %"]
st.dataframe(
    weergave.style.format({
        "Aantal": "{:.4f}",
        "Gem. aankoopprijs": "€ {:.2f}",
        "Kostprijs": "€ {:.2f}",
        "Huidige koers": "€ {:.2f}",
        "Waarde": "€ {:.2f}",
        "Resultaat": "€ {:.2f}",
        "Resultaat %": "{:.2f}%",
    }, na_rep="n.v.t."),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# --- Grafieken ---
col_links, col_rechts = st.columns(2)

with col_links:
    st.subheader("Verdeling per aandeel")
    posities_met_waarde = posities.dropna(subset=["waarde"])
    if not posities_met_waarde.empty:
        fig_taart = px.pie(posities_met_waarde, values="waarde", names="ticker", hole=0.4)
        fig_taart.update_traces(textinfo="label+percent")
        st.plotly_chart(fig_taart, use_container_width=True)
    else:
        st.caption("Geen koersdata beschikbaar voor de verdeling.")

with col_rechts:
    st.subheader("Resultaat per aandeel")
    if not posities_met_waarde.empty:
        fig_bar = px.bar(
            posities_met_waarde, x="ticker", y="resultaat",
            color="resultaat", color_continuous_scale=["red", "grey", "green"],
            labels={"ticker": "Ticker", "resultaat": "Resultaat (€)"},
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.caption("Geen koersdata beschikbaar.")

st.divider()

# --- Koershistorie per aandeel ---
st.subheader("Koershistorie")
gekozen_ticker = st.selectbox("Kies een aandeel", posities["ticker"].tolist())
periode = st.select_slider("Periode", options=["1mo", "3mo", "6mo", "1y", "2y", "5y"], value="6mo")

historie = haal_historie(gekozen_ticker, periode)
if not historie.empty:
    fig_lijn = px.line(historie, x=historie.index, y="Close", labels={"Close": "Slotkoers", "index": "Datum"})
    st.plotly_chart(fig_lijn, use_container_width=True)
else:
    st.caption("Geen historische data beschikbaar (controleer de ticker of je internetverbinding).")

st.divider()

# --- Kasstroom & kosten (rekeningoverzicht) ---
account_df = st.session_state.account_overzicht
if not account_df.empty:
    st.subheader("💰 Dividend, kosten & kasstroom")
    st.caption("Gebaseerd op het geïmporteerde DeGiro-rekeningoverzicht.")

    samenvatting = degiro_account_samenvatting(account_df)

    def _totaal(categorie: str) -> float:
        rij = samenvatting[samenvatting["categorie"] == categorie]
        return float(rij["totaal"].iloc[0]) if not rij.empty else 0.0

    kasstroom = degiro_kasstroom(account_df)
    totale_stortingen = kasstroom[kasstroom["categorie"] == "Storting"]["mutatie"].sum() if "categorie" in kasstroom.columns else kasstroom["mutatie"].sum()

    cA, cB, cC, cD = st.columns(4)
    cA.metric("Ontvangen dividend", f"€ {_totaal('Dividend'):,.2f}")
    cB.metric("Dividendbelasting", f"€ {_totaal('Dividendbelasting'):,.2f}")
    cC.metric("Transactiekosten", f"€ {_totaal('Transactiekosten'):,.2f}")
    cD.metric("Totaal gestort", f"€ {totale_stortingen:,.2f}")

    with st.expander("📊 Samenvatting per categorie"):
        st.dataframe(
            samenvatting.rename(columns={"categorie": "Categorie", "totaal": "Totaal (€)", "aantal": "Aantal boekingen"}),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("📋 Volledig rekeningoverzicht bekijken"):
        st.dataframe(
            account_df.sort_values("datum", ascending=False)[
                ["datum", "product", "omschrijving", "categorie", "mutatie", "saldo"]
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

# --- Alle transacties ---
with st.expander("📋 Alle transacties bekijken"):
    st.dataframe(
        transacties.sort_values("datum", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
