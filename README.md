# MacLua — giochi Steam su macOS, senza hook nel client

CLI standalone nativa macOS. Importa `.lua` in Steam, gestisce licenze
offline (`packageinfo.vdf`), manifest e chiavi depot, scarica i contenuti
dai CDN Steam in anonimo e li adotta nell'installazione. Nessun processo
residente, nessuna iniezione CEF, nessuna dylib: Steam resta vanilla e gli
update del client non rompono niente.

## Requisiti

- macOS + Python 3.9+
- `pip install -r requirements.txt` (solo `pycryptodome`, `zstandard`;
  tutto il resto è stdlib). `pytest` per i test.

## Uso

```
python3 maclua.py search stray
python3 maclua.py config set-key            # una volta sola (file 0600)
python3 maclua.py add --appid 1332010       # scarica il lua dalla sorgente
python3 maclua.py add --appid 1332010 --lua Stray.lua   # oppure da file locale
python3 maclua.py install 1332010           # apre il dialogo Installa di Steam
python3 maclua.py install 1332010           # apre il dialogo Installa di Steam (opzionale)
python3 maclua.py update 1332010        # crea l'appmanifest se manca e scarica/aggiorna
python3 maclua.py verify 1332010
python3 maclua.py status [appid]
python3 maclua.py remove 1332010
python3 maclua.py ensure                # riapplica licenze (dopo update Steam)
python3 maclua.py agent install         # ensure automatico a ogni login
python3 maclua.py doctor
```

`update` su gioco già installato scarica solo i chunk cambiati (validazione
Adler su disco) e aggiorna il manifest puntato: gli aggiornamenti non
richiedono disinstallazione.

## Come funziona

1. **license**: `package0` di `packageinfo.vdf` riceve appids+depotids gestiti
   (+ rehash SHA1, changenumber invariato); package forgiato `4000001` per
   la sidebar. Tutto idempotente, con backup implicito (scritture atomiche).
2. **manifests**: gli `<depot>_<gid>.manifest` vengono staged in
   `Steam/depotcache/` così il client li trova su disco.
3. **fetch**: chunk da CDN Steam in anonimo (`/depot/<id>/chunk/<sha1>`),
   decrypt AES-256 con le chiavi del lua, decompress VZa/VSZa/ZIP, verifica
   Adler chunk per chunk, resume incrementale.
4. **install**: file in `steamapps/common/<gioco>`, +x su Mach-O/script,
   patch `appmanifest` (Fully Installed + InstalledDepots). Poi Gioca da Steam.

## Test

```
python3 -m pytest tests/
```

Suite hermetica (server HTTP locali, fixture sintetiche); solo `catalog`
viene anche verificato live contro le Store API.

## GUI nativa macOS (consigliata)

App macOS moderna e reattiva scritta in SwiftUI (macOS 14+), con design ispirato a Steam:
- **Layout Steam-Like**: Side rail compatto, hero banner dinamico con artwork Steam CDN, schede di stato real-time (Licenze, Steam, Download), carosello orizzontale e catalogo con filtri rapidi.
- **Gestione Completa**: Ricerca e aggiunta automatica giochi con riavvio Steam immediato opzionale, verifica integrità manifest/ACF, monitoraggio download con progress bar live.
- **Motore di Personalizzazione**: Temi (Steam Dark, Deep Charcoal, OLED Black, macOS System), sfondi (mesh gradient, solido, vibrante traslucido), palette colori d'accento, densità layout, raggio angoli personalizzabile, dimensione card e scala testo.
- **Zero bloat**: Impostazioni ripulite da log e percorsi tecnici interni per l'utente finale, con diagnostica "Doctor" pulita e controlli di riparazione licenze one-click.
- **Compatibilità CLT**: Architettura reattiva senza dipendenze da macro esterne private (`UIState` con binding trasparente).

```bash
cd native && ./package.sh          # 32 verifiche + build release + bundle firmato MacLua.app
open MacLua.app                    # Avvio normale (oppure doppio clic dal Finder)
MACLUA_CHECK=1 .build/release/MacApp  # Esecuzione harness verifiche integrate (32/32 passate)
```

## GUI web (alternativa)

Desktop app Electron + React + Tailwind in `app/` (stesso backend `--json`).
Solo se serve l'interfaccia web invece di quella nativa:

```
cd app && npm install
npm run app                # build + avvio (un solo comando, mai finestra vuota)
npm test                   # vitest
```
