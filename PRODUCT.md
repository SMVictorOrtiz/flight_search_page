# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML/CSS/JS, no build step, served by GitHub Pages (user's choice). Data lives as JSON in the same repo; a GitHub Actions workflow writes it.

## Users

- Victor (owner): product analyst, technical. Checks flight prices for a family trip from his phone and laptop, edits search parameters, triggers fresh searches, decides when to buy.
- Travel group (viewers, read-only): 3 people flying from Puebla plus one optional 4th from CDMX. They look at the current best price and the trend; they do not edit or trigger searches.

## Product Purpose

Personal fare monitor for one trip: Puebla/CDMX ⇄ Mérida, around Dec 22–29 2026 (±2 days, 5–9 nights, direct flights only). It answers three questions: what is the cheapest valid combination right now, how have prices moved, and is it time to buy. Success = buying the tickets at or under the target total.

## Positioning

Not a generic flight search: it knows this trip's rules (3 travelers from Puebla who may bus to MEX/NLU and pay the bus, a 4th who flies from CDMX on the same dates, excluded dates Dec 24 out / Dec 31 back) and compares totals for the whole group including ground transfer.

## Operating Context

- Scraping runs on Victor's Mac (residential IP, launchd, hourly / every 20 min at night) with fast-flights; results are published to the GitHub repo through the Contents API. GitHub Actions is the backup and powers an on-demand "search now" button (falls back to SerpApi if Google blocks the datacenter IP).
- Repo is public (`SMVictorOrtiz/flight_search_page`), so no secret ever enters it: alert and SerpApi keys live in `~/vuelos-monitor/config.local.json` on the Mac and in GitHub Secrets for CI.
- Prices are Google Flights totals for the whole party, taxes included, without bags or seats.

## Capabilities and Constraints

- Show all date × airport options, the top combinations, the best Puebla-only option, and price history per route/date.
- Editable config: travelers from Puebla, 4th traveler on/off and airports, date center/flex, nights range, excluded dates, alert threshold, bus cost per airport, bag cost.
- Changing the number of travelers needs a new search (fares are not linear per person); other edits can recompute in the browser instantly.
- Writes (config commit, workflow dispatch) need a GitHub fine-grained token stored only in Victor's browser. Viewers never see edit controls.
- Undecided: final alert threshold for 4 people (provisional $16,000 MXN).

## Evidence on Hand

Real history since Sep 26 2026 in `datos/busquedas_v2.csv` and `datos/estado.json` (lowest seen for 3 people: $10,756 on Sep 28). No invented prices.

## Product Principles

1. One number first: the best total for the whole group, and whether it beats the target.
2. Every total is decomposable: flights per group, bus, bags — never an unexplained figure.
3. Freshness is visible: when each price was seen and whether the search engine is healthy.
4. Viewer-safe by default: editing is a mode that only appears with a token.

## Accessibility & Inclusion

Spanish UI, readable on a phone in daylight; WCAG AA contrast.
