# Turanské Fitko iOS Direct WebView v1

Toto je prvý jednoduchý iOS projekt pre Xcode. Funguje podobne ako Android Direct WebView: otvorí mobilnú TFM appku z webu v natívnom iPhone WebView.

## Čo potrebuješ

- Mac alebo MacBook
- Xcode z Mac App Store
- iPhone + USB kábel
- prihlásený Apple ID v Xcode
- pre TestFlight/App Store bude treba Apple Developer Program

## Prvý test na iPhone

1. Rozbaľ ZIP.
2. Na Macu otvor `TuranskeFitkoApp.xcodeproj`.
3. V Xcode klikni na projekt `TuranskeFitkoApp`.
4. V `Signing & Capabilities` vyber svoj Apple účet / Team.
5. Pripoj iPhone cez USB.
6. Hore vyber pripojený iPhone.
7. Klikni `Run`.

Ak Xcode zahlási problém s Bundle Identifier, zmeň ho napríklad na:

`sk.turanskefitko.app.peter`

## TestFlight / App Store

Pre TestFlight a App Store treba:

1. Apple Developer Program.
2. Xcode → Product → Archive.
3. Distribute App → App Store Connect → Upload.
4. V App Store Connect potom zapnúť TestFlight.

## Dôležité

Appka načítava URL:

`https://turanskefitko.sk/?tfm_mobile_app=1&native=ios&tfma_v=4.73`

Ak pripravíme novší WordPress plugin, zmeníme verziu v URL alebo použijeme tlačidlo Aktualizovať appku.
