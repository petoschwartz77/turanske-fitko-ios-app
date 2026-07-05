# Build iOS appky na Macu

1. Nainštaluj Xcode.
2. Otvor `TuranskeFitkoApp.xcodeproj`.
3. Otvor nastavenie targetu `TuranskeFitkoApp`.
4. `Signing & Capabilities` → vyber Apple Team.
5. Pripoj iPhone.
6. Vyber iPhone ako cieľ.
7. Klikni `Run`.

## TestFlight

1. Product → Archive.
2. Archives okno → Distribute App.
3. Vyber App Store Connect → Upload.
4. V App Store Connect otvor appku a TestFlight.

## Časté chyby

- `No signing certificate`: prihlás Apple ID v Xcode.
- `Bundle identifier is not available`: zmeň bundle id na unikátne, napr. `sk.turanskefitko.app.peter`.
- iPhone neverí developerovi: iPhone → Nastavenia → Všeobecné → VPN a správa zariadenia → dôverovať developerovi.
