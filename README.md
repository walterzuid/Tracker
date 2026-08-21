# Aandelenportfolio Tracker

Een Streamlit-app om je aandelentransacties bij te houden, live koersen op te halen
en je rendement en verdeling te visualiseren.

## Installeren

```bash
pip install -r requirements.txt
```

## Starten

```bash
streamlit run app.py
```

De app opent automatisch in je browser op `http://localhost:8501`.

## Functionaliteit

- **Transacties toevoegen/verwijderen** — koop en verkoop van aandelen via het zijpaneel.
- **DeGiro-import** — upload je `Transactieoverzicht.csv` en `Rekeningoverzicht.csv`
  (DeGiro -> Activiteit -> Exporteren) rechtstreeks in de sidebar:
  - Transacties worden automatisch herkend; **optietransacties worden automatisch
    gedetecteerd en overgeslagen** (deze tracker volgt alleen aandelenposities).
  - Voor elke ISIN wordt automatisch geprobeerd een ticker op te zoeken via
    Yahoo Finance; je hoeft de suggestie alleen te controleren/corrigeren
    i.p.v. alles handmatig in te typen. Eenmaal bevestigde koppelingen worden
    onthouden voor volgende imports.
  - Het rekeningoverzicht wordt automatisch gecategoriseerd: dividend,
    dividendbelasting, transactiekosten, stortingen/opnames, interne
    overboekingen, effecten-uitleeninkomsten, etc.
  - Bestanden opnieuw uploaden (bv. een geüpdatete export) leidt niet tot
    dubbele transacties of boekingen — de app herkent wat al is geïmporteerd.
- **Live koersen** — opgehaald via `yfinance` (gratis, geen API-key nodig).
- **Automatische berekeningen** — gemiddelde aankoopprijs, huidige waarde,
  ongerealiseerd resultaat (€ en %) per positie en voor de totale portfolio.
- **Dividend & kasstroomoverzicht** — ontvangen dividend, bronbelasting,
  transactiekosten en totale stortingen op basis van je rekeningoverzicht.
- **Grafieken** — verdeling per aandeel (taartdiagram), resultaat per aandeel
  (staafdiagram) en koershistorie per aandeel (lijndiagram).
- **Opslag** — alles wordt lokaal opgeslagen (`transacties.csv`,
  `rekeningoverzicht.csv`, `isin_ticker_mapping.csv`), dus je portfolio en
  ticker-koppelingen blijven behouden tussen sessies.

## Tickers

Gebruik de tickers zoals Yahoo Finance ze kent, bijvoorbeeld:
- Amerikaanse aandelen: `AAPL`, `MSFT`, `TSLA`
- Nederlandse aandelen (Euronext Amsterdam): `ASML.AS`, `ADYEN.AS`, `INGA.AS`
- Andere Europese beurzen: `.DE` (Duitsland), `.PA` (Parijs), `.L` (Londen)

## Uitbreidingsideeën

- Portfolio-waarde over tijd (i.p.v. alleen huidig moment) door historische
  koersen te combineren met transactiedata.
- Dividend-tracking.
- Meerdere valuta's met automatische omrekening.
- Exporteren naar Excel/PDF-rapport.
