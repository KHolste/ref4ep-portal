# Erscheinungsbild des Portals (hell / dunkel)

Stand: Asset-Version 0077. Aufbau wie im Labormanagement-Tool, Farben
bleiben die von Ref4EP (Marineblau als Markenfarbe, Petrol als Akzent).

## Drei Stylesheets, in dieser Reihenfolge

| Datei | Rolle | Von Hand ändern? |
|---|---|---|
| `web/style.css` | Layout und modul-spezifische Regeln (gewachsen über viele Ausbaustufen) | ja |
| `web/theme.css` | Erscheinungsbild: Tokens `--t-*`, Schrift, Kopfzeile, Seitenleiste mit Symbolen, Knöpfe, Karten, Felder | ja |
| `web/theme-dark.css` | dunkler Modus, greift nur unter `<html data-theme="dark">` | **nein**, wird erzeugt |

`theme.css` biegt die älteren `--rds-*`-Tokens aus `style.css` auf die
neuen `--t-*`-Tokens um. Neue Farben deshalb nur über `--t-*` einführen.

## Dunkler Modus

- Umschalter (Mond/Sonne) oben rechts in der Kopfzeile. Die Wahl gilt pro
  Browser (`localStorage` `ref4ep.theme`); hell ist die Voreinstellung.
- Ein kleines Skript im `<head>` von `index.html` setzt die gemerkte Wahl,
  bevor die Seite gezeichnet wird.
- Gedruckt wird immer hell (`beforeprint`/`afterprint` in `app.js`).

`theme-dark.css` wird erzeugt, nicht geschrieben:

```bash
cd backend
python scripts/build_dark_theme.py           # Datei neu schreiben
python scripts/build_dark_theme.py --check   # nur prüfen
```

Der Generator spiegelt die Helligkeit jeder fest notierten Farbe aus
`style.css`, setzt die dunklen Werte der `--t-*`-Tokens und wiederholt die
Farbregeln aus `theme.css`, damit sie das letzte Wort behalten. Die
Kopfbänder mit Bild bleiben unverändert (sie sind schon dunkel), ebenso
Druckregeln. Die SVG-Farben des Zeitplans (`modules/gantt.js`) bekommen
eigene Regeln.

**Nach jeder Änderung an `style.css`, `theme.css` oder den Farben in
`gantt.js` den Generator laufen lassen.** `tests/test_web_theme.py`
schlägt sonst an.

## Kopfbänder

Die Bildmotive (Raumfahrtbezug) bleiben, sind aber flacher: weniger
Innenabstand, kein Schatten. Cockpit und Zeitplan haben kein Bild und
zeigen eine schlichte Fläche mit Petrol-Kante. Das frühere feste
Hintergrundbild der Arbeitsfläche (`global-background.jpg`) und das
Bild hinter der Projektbibliothek werden nicht mehr gezeigt; die Dateien
liegen noch unter `static/images/`.

## Symbole und Schrift

- Strichsymbole als CSS-Masken (`--ico-*` in `theme.css`), eingefärbt über
  `currentColor`. Jeder Eintrag der Seitenleiste bekommt sein Symbol über
  `data-route`. Ein Test prüft, dass kein Eintrag ohne Symbol bleibt.
- IBM Plex Sans/Mono liegen lokal unter `web/fonts/` (SIL Open Font
  License), kein Abruf bei Dritten.

## Nicht enthalten

Die öffentlichen, server-gerenderten Seiten (Login, Impressum,
Datenschutz, Downloads) nutzen `static/style.css` und sind von dieser
Überarbeitung nicht berührt.
