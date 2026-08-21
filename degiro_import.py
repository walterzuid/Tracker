"""
DeGiro CSV-import
------------------
Parseert de twee CSV-exports die je bij DeGiro kunt downloaden onder
Activiteit -> Exporteren:

  1. "Transactieoverzicht" -- elke koop/verkoop, met aantal, koers, ISIN.
  2. "Rekeningoverzicht"   -- alle overige boekingen: dividend,
     dividendbelasting, transactiekosten, stortingen/opnames, interne
     overboekingen, effecten-uitleeninkomsten, etc.

Beide bestanden hebben een aantal eigenaardigheden waar deze module
rekening mee houdt:
  - Bedragen staan in een aparte kolom van hun valuta (bv. een kolom met
    het bedrag en een naamloze kolom ernaast met "EUR"/"USD"). Welke van
    de twee het bedrag is en welke de valuta, verschilt per bestand --
    deze module detecteert dat automatisch per kolomparen op basis van de
    inhoud, in plaats van een vaste volgorde aan te nemen.
  - Getallen staan in NL-notatie: komma als decimaalteken, punt als
    duizendtal-scheiding (bv. "1.234,56").
  - DeGiro identificeert instrumenten met een ISIN, niet met een ticker.
    Deze module biedt daarom een aparte mapping-stap: ISIN -> ticker,
    die je eenmalig per aandeel invult.
"""

from __future__ import annotations

import re
import pandas as pd


# ---------------------------------------------------------------------------
# Gedeelde hulpfuncties
# ---------------------------------------------------------------------------

def _hernoem_ongenaamde_kolommen(kolommen: list[str]) -> list[str]:
    """Geeft elke naamloze kolom ('Unnamed: N') een neutrale naam op basis
    van de voorgaande kolom, bv. 'Mutatie' + naamloze buur -> 'Mutatie_paar'.
    Legt nog geen betekenis (bedrag vs. valuta) vast -- dat gebeurt later."""
    nieuwe_namen: list[str] = []
    for i, naam in enumerate(kolommen):
        naam_schoon = str(naam).strip()
        if naam_schoon == "" or naam_schoon.lower().startswith("unnamed"):
            vorige = nieuwe_namen[-1] if nieuwe_namen else f"kolom_{i}"
            nieuwe_namen.append(f"{vorige}_paar")
        else:
            basis = naam_schoon
            teller = 1
            while basis in nieuwe_namen:
                teller += 1
                basis = f"{naam_schoon}_{teller}"
            nieuwe_namen.append(basis)
    return nieuwe_namen


def _naar_float(serie: pd.Series) -> pd.Series:
    """Zet DeGiro-getalnotatie om naar float: '1234.56', '1.234,56' of
    '-12,34' worden allemaal correct herkend."""

    def _parse_waarde(waarde) -> float | None:
        if pd.isna(waarde):
            return None
        tekst = str(waarde).strip()
        if tekst == "":
            return None
        if re.match(r"^-?\d{1,3}(\.\d{3})*,\d+$", tekst):
            tekst = tekst.replace(".", "").replace(",", ".")
        elif re.match(r"^-?\d+,\d+$", tekst):
            tekst = tekst.replace(",", ".")
        try:
            return float(tekst)
        except ValueError:
            return None

    return serie.apply(_parse_waarde)


def _is_valutacode(waarde) -> bool:
    return isinstance(waarde, str) and bool(re.fullmatch(r"[A-Z]{3}", waarde.strip()))


def _splits_bedrag_en_valuta(kolom_a: pd.Series, kolom_b: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Twee kolommen vormen samen een (bedrag, valuta)-paar, maar de
    volgorde verschilt per DeGiro-bestand. Deze functie kijkt naar de
    daadwerkelijke inhoud (lijkt het op een 3-letterige valutacode zoals
    'EUR'?) om te bepalen welke kolom het bedrag is en welke de valuta,
    en geeft (bedrag_als_float, valuta_als_tekst) terug."""
    score_a = kolom_a.dropna().apply(_is_valutacode).mean() if kolom_a.notna().any() else 0.0
    score_b = kolom_b.dropna().apply(_is_valutacode).mean() if kolom_b.notna().any() else 0.0

    if score_a >= score_b:
        valuta, bedrag_ruw = kolom_a, kolom_b
    else:
        bedrag_ruw, valuta = kolom_a, kolom_b

    return _naar_float(bedrag_ruw), valuta


def _vind_kolom(kolommen: list[str], bevat_alles: list[str], bevat_niets: list[str] | None = None) -> str | None:
    """Zoekt de eerste kolomnaam die (case-insensitief) alle woorden in
    `bevat_alles` bevat en geen enkel woord uit `bevat_niets`."""
    bevat_niets = bevat_niets or []
    for naam in kolommen:
        naam_lager = naam.lower()
        if all(w.lower() in naam_lager for w in bevat_alles) and not any(w.lower() in naam_lager for w in bevat_niets):
            return naam
    return None


# ---------------------------------------------------------------------------
# Transactieoverzicht -- koop/verkoop
# ---------------------------------------------------------------------------

def parse_degiro_transacties_csv(bestand) -> pd.DataFrame:
    """Leest een DeGiro-transactieoverzicht in en normaliseert de kolommen.

    Returns
    -------
    pd.DataFrame met kolommen: datum, tijd, product, isin, aantal,
    koers, koers_valuta, lokale_waarde, lokale_waarde_valuta, waarde_eur,
    wisselkoers, transactiekosten_eur, totaal_eur, order_id.
    """
    ruw = pd.read_csv(bestand, dtype=str)
    ruw.columns = _hernoem_ongenaamde_kolommen(list(ruw.columns))
    kolommen = list(ruw.columns)

    datum_kolom = _vind_kolom(kolommen, ["datum"])
    product_kolom = _vind_kolom(kolommen, ["product"])
    isin_kolom = _vind_kolom(kolommen, ["isin"])
    aantal_kolom = _vind_kolom(kolommen, ["aantal"])
    koers_kolom = _vind_kolom(kolommen, ["koers"])
    koers_paar_kolom = _vind_kolom(kolommen, ["koers_paar"])
    lokale_kolom = _vind_kolom(kolommen, ["lokale", "waarde"])
    lokale_paar_kolom = _vind_kolom(kolommen, ["lokale", "waarde_paar"])
    waarde_eur_kolom = _vind_kolom(kolommen, ["waarde"], bevat_niets=["lokale"])

    verplicht = {
        "Datum": datum_kolom, "Product": product_kolom, "ISIN": isin_kolom,
        "Aantal": aantal_kolom, "Koers": koers_kolom, "Lokale waarde": lokale_kolom,
        "Waarde": waarde_eur_kolom,
    }
    ontbrekend = [naam for naam, kol in verplicht.items() if kol is None]
    if ontbrekend:
        raise ValueError(
            "Dit bestand lijkt niet op een DeGiro-transactieoverzicht. "
            f"Kon deze kolommen niet vinden: {ontbrekend}. Gevonden kolommen: {kolommen}"
        )

    datum = pd.to_datetime(ruw[datum_kolom], dayfirst=True, errors="coerce")
    aantal = _naar_float(ruw[aantal_kolom])
    koers_bedrag, koers_valuta = _splits_bedrag_en_valuta(ruw[koers_kolom], ruw[koers_paar_kolom])
    lokale_bedrag, lokale_valuta = _splits_bedrag_en_valuta(ruw[lokale_kolom], ruw[lokale_paar_kolom])

    # 'Waarde EUR' kan standalone staan (valuta al in de kolomnaam) of nog
    # een naastgelegen valutakolom hebben, afhankelijk van export-versie.
    waarde_paar_kolom = f"{waarde_eur_kolom}_paar"
    if waarde_paar_kolom in kolommen:
        waarde_eur, _ = _splits_bedrag_en_valuta(ruw[waarde_eur_kolom], ruw[waarde_paar_kolom])
    else:
        waarde_eur = _naar_float(ruw[waarde_eur_kolom])

    wisselkoers_kolom = _vind_kolom(kolommen, ["wisselkoers"])
    kosten_kolom = _vind_kolom(kolommen, ["transactiekosten"])
    totaal_kolom = _vind_kolom(kolommen, ["totaal"])
    order_kolom = _vind_kolom(kolommen, ["order"])
    tijd_kolom = _vind_kolom(kolommen, ["tijd"])

    resultaat = pd.DataFrame({
        "datum": datum,
        "tijd": ruw[tijd_kolom] if tijd_kolom else None,
        "product": ruw[product_kolom],
        "isin": ruw[isin_kolom],
        "aantal": aantal,
        "koers": koers_bedrag,
        "koers_valuta": koers_valuta,
        "lokale_waarde": lokale_bedrag,
        "lokale_waarde_valuta": lokale_valuta,
        "waarde_eur": waarde_eur,
        "wisselkoers": _naar_float(ruw[wisselkoers_kolom]) if wisselkoers_kolom else None,
        "transactiekosten_eur": _naar_float(ruw[kosten_kolom]) if kosten_kolom else None,
        "totaal_eur": _naar_float(ruw[totaal_kolom]) if totaal_kolom else None,
        "order_id": ruw[order_kolom] if order_kolom else None,
    })

    return resultaat.sort_values("datum").reset_index(drop=True)


def degiro_naar_portfolio_formaat(
    bestand, valuta: str = "eur", negeer_opties: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Zet een DeGiro-transactieoverzicht om naar het transactieformaat van
    de portfolio tracker: kolommen [datum, isin, product, ticker, type,
    aantal, prijs, order_id]. De 'ticker'-kolom is leeg -- vul die in via de
    ISIN-naar-ticker mapping voordat je de rijen aan de portfolio toevoegt.

    Parameters
    ----------
    bestand : str, pad, of file-achtig object
        De DeGiro-transactie-CSV.
    valuta : {"eur", "lokaal"}
        "eur" (standaard) gebruikt de EUR-waarde per aandeel, zodat alle
        posities in dezelfde valuta staan. "lokaal" gebruikt de koers in
        de handelsvaluta van het aandeel zelf (bv. USD voor Apple).
    negeer_opties : bool
        Als True (standaard) worden optie-/derivatentransacties eruit
        gefilterd -- deze tracker volgt alleen aandelenposities.

    Returns
    -------
    (aandelen_df, opties_df) : tuple van twee DataFrames. `opties_df` is
    leeg als `negeer_opties=False`, en bevat anders de overgeslagen
    optietransacties (voor eigen inzicht -- deze worden niet geïmporteerd).
    """
    ruw = parse_degiro_transacties_csv(bestand)
    transacties = ruw[ruw["isin"].notna() & ruw["aantal"].notna() & (ruw["aantal"] != 0)].copy()

    opties = pd.DataFrame(columns=transacties.columns)
    if negeer_opties and not transacties.empty:
        transacties, opties = splits_aandelen_en_opties(transacties)

    if transacties.empty:
        leeg = pd.DataFrame(columns=["datum", "isin", "product", "ticker", "type", "aantal", "prijs", "order_id"])
        return leeg, opties

    transacties["type"] = transacties["aantal"].apply(lambda x: "Koop" if x > 0 else "Verkoop")
    transacties["aantal_abs"] = transacties["aantal"].abs()

    if valuta == "lokaal":
        transacties["prijs"] = transacties["koers"].abs()
    else:
        transacties["prijs"] = (transacties["waarde_eur"].abs() / transacties["aantal_abs"]).round(4)

    resultaat = pd.DataFrame({
        "datum": transacties["datum"],
        "isin": transacties["isin"],
        "product": transacties["product"],
        "ticker": "",
        "type": transacties["type"],
        "aantal": transacties["aantal_abs"],
        "prijs": transacties["prijs"],
        "order_id": transacties["order_id"],
    })

    return resultaat.sort_values("datum").reset_index(drop=True), opties


def unieke_isins(portfolio_df: pd.DataFrame) -> pd.DataFrame:
    """Geeft een tabel met elke unieke ISIN + productnaam, als basis voor
    de ticker-mapping. Dedupliceert op ISIN (niet op productnaam) -- soms
    gebruikt DeGiro voor dezelfde ISIN een net iets andere productomschrijving
    (bv. bij een 'non-tradeable' variant tijdens een beursnotering-wijziging),
    en die moeten toch als één ISIN behandeld worden."""
    return (
        portfolio_df[["isin", "product"]]
        .drop_duplicates(subset="isin", keep="first")
        .sort_values("product")
        .reset_index(drop=True)
    )


def pas_ticker_mapping_toe(portfolio_df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """Vult de 'ticker'-kolom in op basis van een {isin: ticker}-dictionary."""
    resultaat = portfolio_df.copy()
    resultaat["ticker"] = resultaat["isin"].map(mapping).fillna(resultaat["ticker"])
    return resultaat


# ---------------------------------------------------------------------------
# Opties / derivaten herkennen
# ---------------------------------------------------------------------------

# DeGiro noemt optieproducten volgens het patroon "<onderliggende> C|P<strike> <expiratiedatum>",
# bv. "SBM C25.00 19JUN26", "AEX C980 19DEC25" of "HEY P28.00 18OKT24". Deze
# tracker volgt alleen aandelenposities, dus dit soort rijen wordt herkend
# en apart gehouden. Het patroon wordt overal in de productnaam gezocht
# (niet alleen aan het begin), want de onderliggende-ticker staat ervoor.
_OPTIE_PATROON = re.compile(r"[CP]\d+(?:[.,]\d+)?\s+\d{1,2}[A-Z]{3}\d{2}\b")


def is_optie_transactie(product: str) -> bool:
    return isinstance(product, str) and bool(_OPTIE_PATROON.search(product.strip()))


def splits_aandelen_en_opties(ruw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Splitst een geparsed transactieoverzicht in (aandelen_df, opties_df)
    op basis van de productnaam."""
    is_optie = ruw["product"].apply(is_optie_transactie)
    return ruw[~is_optie].copy(), ruw[is_optie].copy()


# ---------------------------------------------------------------------------
# Automatische ISIN -> ticker opzoeken
# ---------------------------------------------------------------------------

def zoek_ticker_via_isin(isin: str) -> str | None:
    """Probeert automatisch een yfinance-compatibele ticker te vinden voor
    een ISIN via Yahoo Finance's zoek-endpoint. Vereist internetverbinding;
    geeft None terug als er niets gevonden wordt of bij een fout (bv. geen
    verbinding, rate limiting), zodat de aanroeper altijd op handmatige
    invoer kan terugvallen."""
    try:
        import requests
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": isin, "quotesCount": 1, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=6,
        )
        resp.raise_for_status()
        kandidaten = resp.json().get("quotes", [])
        if kandidaten:
            return kandidaten[0].get("symbol")
    except Exception:
        return None
    return None


def vul_ticker_suggesties_aan(isins_df: pd.DataFrame) -> pd.DataFrame:
    """Vult de 'ticker'-kolom van een unieke-ISIN-tabel aan met automatisch
    opgezochte suggesties voor rijen die nog geen ticker hebben. Rijen die
    al een ticker hebben (bv. uit een eerdere mapping) blijven ongewijzigd."""
    resultaat = isins_df.copy()
    for i, rij in resultaat.iterrows():
        if not rij.get("ticker"):
            suggestie = zoek_ticker_via_isin(rij["isin"])
            if suggestie:
                resultaat.at[i, "ticker"] = suggestie
    return resultaat


# ---------------------------------------------------------------------------
# Rekeningoverzicht -- dividend, kosten, stortingen/opnames, overig
# ---------------------------------------------------------------------------

# Volgorde is belangrijk: specifiekere/uitsluitende patronen staan boven
# algemenere, want de eerste match wint.
_CATEGORIE_PATRONEN = [
    ("Interne overboeking", re.compile(r"geldrekening bij flatex|cash sweep", re.I)),
    ("Reservering", re.compile(r"reservation|reservering", re.I)),
    ("Dividendbelasting", re.compile(r"dividendbelasting", re.I)),
    ("Dividend", re.compile(r"\bdividend\b", re.I)),
    ("Uitleeninkomsten", re.compile(r"securities lending|effecten.?uitleen", re.I)),
    ("Transactiekosten", re.compile(r"transactiekosten|koersopslag|handling|aansluitings?kosten", re.I)),
    ("Koop", re.compile(r"^\s*koop\b", re.I)),
    ("Verkoop", re.compile(r"^\s*verkoop\b", re.I)),
    ("Storting", re.compile(r"\bideal\b|\bstorting\b|\bsofort\b|\bdeposit\b", re.I)),
    ("Opname", re.compile(r"\bopname\b|terugstorting|\bwithdraw", re.I)),
    ("Valutatransactie", re.compile(r"valuta.?(creditering|debitering)|fx (credit|debit)", re.I)),
    ("Rente", re.compile(r"\brente\b|\binterest\b", re.I)),
]

# Categorieën die GEEN externe geldstroom vertegenwoordigen (voor
# inleg-/kasstroomberekeningen moeten deze uitgesloten blijven).
INTERNE_CATEGORIEEN = ["Interne overboeking", "Reservering"]


def _categoriseer(omschrijving: str) -> str:
    if not isinstance(omschrijving, str) or not omschrijving.strip():
        return "Overig"
    for categorie, patroon in _CATEGORIE_PATRONEN:
        if patroon.search(omschrijving):
            return categorie
    return "Overig"


def parse_degiro_account_csv(bestand) -> pd.DataFrame:
    """Leest een DeGiro-rekeningoverzicht in en normaliseert de kolommen.
    Bevat ALLE boekingen: koop/verkoop, dividend, dividendbelasting,
    transactiekosten, stortingen, opnames, interne overboekingen, etc.

    Returns
    -------
    pd.DataFrame met kolommen: datum, tijd, product, isin, omschrijving,
    categorie, mutatie, mutatie_valuta, saldo, saldo_valuta, order_id.
    """
    ruw = pd.read_csv(bestand, dtype=str)
    ruw.columns = _hernoem_ongenaamde_kolommen(list(ruw.columns))
    kolommen = list(ruw.columns)

    datum_kolom = _vind_kolom(kolommen, ["datum"])
    omschrijving_kolom = _vind_kolom(kolommen, ["omschrijving"])
    mutatie_kolom = _vind_kolom(kolommen, ["mutatie"])
    mutatie_paar_kolom = _vind_kolom(kolommen, ["mutatie_paar"])
    saldo_kolom = _vind_kolom(kolommen, ["saldo"])
    saldo_paar_kolom = _vind_kolom(kolommen, ["saldo_paar"])

    ontbrekend = [naam for naam, kol in {
        "Datum": datum_kolom, "Omschrijving": omschrijving_kolom,
        "Mutatie": mutatie_kolom, "Saldo": saldo_kolom,
    }.items() if kol is None]
    if ontbrekend:
        raise ValueError(
            "Dit bestand lijkt niet op een DeGiro-rekeningoverzicht. "
            f"Verwachte kolommen ontbreken: {ontbrekend}. Gevonden kolommen: {kolommen}"
        )

    datum = pd.to_datetime(ruw[datum_kolom], dayfirst=True, errors="coerce")
    mutatie, mutatie_valuta = _splits_bedrag_en_valuta(ruw[mutatie_kolom], ruw[mutatie_paar_kolom]) \
        if mutatie_paar_kolom else (_naar_float(ruw[mutatie_kolom]), None)
    saldo, saldo_valuta = _splits_bedrag_en_valuta(ruw[saldo_kolom], ruw[saldo_paar_kolom]) \
        if saldo_paar_kolom else (_naar_float(ruw[saldo_kolom]), None)

    tijd_kolom = _vind_kolom(kolommen, ["tijd"])
    product_kolom = _vind_kolom(kolommen, ["product"])
    isin_kolom = _vind_kolom(kolommen, ["isin"])
    order_kolom = _vind_kolom(kolommen, ["order"])

    resultaat = pd.DataFrame({
        "datum": datum,
        "tijd": ruw[tijd_kolom] if tijd_kolom else None,
        "product": ruw[product_kolom] if product_kolom else None,
        "isin": ruw[isin_kolom] if isin_kolom else None,
        "omschrijving": ruw[omschrijving_kolom],
        "mutatie": mutatie,
        "mutatie_valuta": mutatie_valuta,
        "saldo": saldo,
        "saldo_valuta": saldo_valuta,
        "order_id": ruw[order_kolom] if order_kolom else None,
    })
    resultaat["categorie"] = resultaat["omschrijving"].apply(_categoriseer)

    return resultaat.sort_values("datum").reset_index(drop=True)


def degiro_account_samenvatting(account_df: pd.DataFrame) -> pd.DataFrame:
    """Groepeert het rekeningoverzicht per categorie: totaalbedrag en
    aantal boekingen. Handig overzicht van dividend, kosten, stortingen etc."""
    return (
        account_df.groupby("categorie")["mutatie"]
        .agg(totaal="sum", aantal="count")
        .reset_index()
        .sort_values("totaal", ascending=False)
    )


def degiro_kasstroom(account_df: pd.DataFrame) -> pd.DataFrame:
    """Filtert alleen stortingen en opnames -- de echte externe geldstroom
    die je nodig hebt om je werkelijke inleg (en dus rendement) correct te
    berekenen. Interne overboekingen en reserveringen (die netto op nul
    uitkomen) worden hier bewust buiten gehouden."""
    return account_df[account_df["categorie"].isin(["Storting", "Opname"])].reset_index(drop=True)


if __name__ == "__main__":
    print("=== Transacties ===")
    df = degiro_naar_portfolio_formaat("/mnt/user-data/uploads/Transactieoverzicht.csv")
    print(df.to_string())
    print()
    print("Unieke ISINs om te mappen naar tickers:")
    print(unieke_isins(df).to_string())

    print()
    print("=== Rekeningoverzicht ===")
    account_df = parse_degiro_account_csv("/mnt/user-data/uploads/Rekeningoverzicht.csv")
    print(account_df[["datum", "omschrijving", "categorie", "mutatie", "saldo"]].to_string())
    print()
    print("Samenvatting per categorie:")
    print(degiro_account_samenvatting(account_df).to_string())
    print()
    print("Kasstroom (stortingen/opnames):")
    print(degiro_kasstroom(account_df)[["datum", "omschrijving", "mutatie"]].to_string())
