# Manuelle Smoke-Test-Checkliste

Stand: Block 0011 (UX-Feinschliff). Diese Checkliste ist die
Schnellprüfung **vor** jedem Praxistest oder Deployment. Sie
dauert ~5 Minuten und deckt Cockpit, Workpackages und
Meilensteine inklusive Rollenmatrix ab.

Voraussetzungen:

- Frischer Lauf gegen die lokale SQLite-DB:
  `alembic upgrade head` und Seed eingespielt
  (`python -m ref4ep.cli.admin seed`).
- Mindestens drei Test-Accounts vorhanden:
  - **Admin** (`admin@test.example` / `Adm1nP4ssword!`)
  - **WP-Lead** (Member-Account mit Membership `wp_lead` in
    einem konkreten WP, z. B. `WP3.1`)
  - **Member ohne Lead-Rolle** (Member, nur `wp_member` oder
    gar nicht eingetragen)

Symbol-Konvention: ✅ = erwartet sichtbar, ⛔ = darf nicht
auftauchen / nicht möglich sein.

---

## 1. Login (alle Rollen)

- [ ] `/login` zeigt das Anmeldeformular ohne Fehler.
- [ ] Login mit gültigen Daten leitet auf `/portal/` um.
- [ ] Login mit falschem Passwort liefert eine sichtbare
      Fehlermeldung (`.error`-Box).
- [ ] Eingeloggte Person sieht oben rechts ihren Namen
      und das Partner-Kürzel.
- [ ] Logout-Button im Header funktioniert.

## 2. Projektcockpit (`/portal/`)

- [ ] Während des Ladens steht eine sichtbare Loading-Zeile
      („Cockpit-Daten werden geladen …").
- [ ] Nach dem Laden sind **vier Karten** sichtbar:
  1. ✅ Nächste Meilensteine
  2. ✅ Überfällige Meilensteine
  3. ✅ Offene Punkte aus Arbeitspaketen
  4. ✅ Arbeitspaket-Statusübersicht
- [ ] Jede Karte hat einen verständlichen Empty-State,
      wenn keine Daten vorliegen.
- [ ] Die Cross-Nav-Leiste am Seitenfuß zeigt
      „**Projektcockpit** · Arbeitspakete · Meilensteine"
      (aktive Seite fett, kein Link).
- [ ] Klick auf einen WP-Code in einer Karte führt auf das
      WP-Detail.
- [ ] Klick auf „Alle Meilensteine ansehen" führt auf
      `/portal/milestones`.
- ⛔ Es taucht **kein** Wort „Deliverable" auf.

## 3. Arbeitspaket-Liste (`/portal/workpackages`)

- [ ] Spalten: Code, Titel, Parent, Lead.
- [ ] Loading-Zeile vor dem Laden, Empty-State falls leer.
- [ ] Klick auf einen WP-Code öffnet das WP-Detail.
- [ ] Cross-Nav am Fuß; aktiver Eintrag „Arbeitspakete".

## 4. Arbeitspaket-Detail (`/portal/workpackages/<code>`)

- [ ] Status-Badge im Header (z. B. „geplant"/„in Arbeit"/…).
- [ ] Sektion „Cockpit" mit Kurzbeschreibung, Nächsten
      Schritten und Offenen Punkten — leere Felder zeigen
      ein graues „—".
- [ ] Sektion „Kontaktpersonen des Lead-Partners" listet
      aktive interne Kontakte (Hauptkontakt /
      Projektleitung als Badge).
- [ ] Sektion „Mitglieder" listet alle Memberships;
      sonst Empty-State.
- [ ] Sektion „Meilensteine" zeigt alle MS dieses WPs;
      sonst Empty-State.
- [ ] Sektion „Dokumente" wie bisher; Empty-State, wenn keine
      Dokumente vorliegen.
- [ ] Cross-Nav am Fuß.
- [ ] Klick auf den Lead-Partner-Namen führt auf die
      Partner-Detailseite.
- [ ] Klick auf „Zur Meilensteinübersicht" führt auf
      `/portal/milestones`.

## 5. Cockpit-Felder bearbeiten (Admin / WP-Lead)

- [ ] Als **Admin** auf einem beliebigen WP-Detail:
  - ✅ Button „Cockpit bearbeiten …" sichtbar.
  - ✅ Form mit Status-Select + drei Textareas öffnet sich.
  - ✅ Speichern aktualisiert die Anzeige sofort; bei
        ungültigem Status erscheint eine Fehlerzeile.
- [ ] Als **WP-Lead des WP**: gleiche Bearbeitungs-UX.
- [ ] Als **Member ohne Lead-Rolle in diesem WP**:
  - ⛔ Button „Cockpit bearbeiten …" fehlt.
  - ⛔ PATCH per `curl`/Devtools liefert 403.
- [ ] Als **anonymer Aufruf**: GET liefert 401.

## 6. Meilensteinliste (`/portal/milestones`)

- [ ] Loading-Zeile vor dem Laden.
- [ ] Tabelle mit Code, Titel, Arbeitspaket, Plandatum,
      Istdatum, Status, Notiz, Aktion.
- [ ] MS4 (Gesamtprojekt) zeigt „Gesamtprojekt" statt eines
      WP-Links.
- [ ] Cross-Nav am Fuß; aktiver Eintrag „Meilensteine".

## 7. Meilensteinstatus ändern

- [ ] Als **Admin**: „Bearbeiten …"-Button bei jedem MS
      (auch MS4); Form öffnet, Speichern aktualisiert die
      Tabelle.
- [ ] Als **WP-Lead** des MS-Arbeitspakets: „Bearbeiten …"
      sichtbar; Speichern funktioniert.
- [ ] Als WP-Lead eines **anderen** Arbeitspakets oder
      eines **Member ohne Lead-Rolle**: kein
      „Bearbeiten …"-Button (`can_edit=false`).
- [ ] Als WP-Lead eines beliebigen WP, Versuch MS4 zu
      patchen: ⛔ 403.
- [ ] Status auf „erreicht" ohne Istdatum: ✅ Server trägt
      automatisch das heutige Datum ein.

## 8. Rechteprüfung — Querschnitt

| Bereich               | Admin | WP-Lead (eigenes WP) | Member ohne Lead | Anonym |
| --------------------- | :---: | :------------------: | :--------------: | :----: |
| Cockpit lesen         |  ✅   |          ✅          |        ✅        |   ⛔   |
| Workpackages lesen    |  ✅   |          ✅          |        ✅        |   ⛔   |
| WP-Cockpit ändern     |  ✅   |          ✅          |        ⛔        |   ⛔   |
| Meilensteine lesen    |  ✅   |          ✅          |        ✅        |   ⛔   |
| Meilensteinstatus     |  ✅   |    ✅ (eigenes WP)   |        ⛔        |   ⛔   |
| MS4 (Gesamtprojekt)   |  ✅   |          ⛔          |        ⛔        |   ⛔   |
| Partner-Stammdaten    |  ✅   |    ✅ (eigener)      |        ⛔        |   ⛔   |
| Partnerkontakte CRUD  |  ✅   |    ✅ (eigener)      |    nur lesen     |   ⛔   |
| Internal Notes lesen  |  ✅   |          ⛔          |        ⛔        |   ⛔   |

## 9. Negativtests (kurz)

- [ ] PATCH ohne CSRF-Header → 403.
- [ ] PATCH auf unbekannte UUID → 404.
- [ ] PATCH mit ungültigem Status (`erledigt` statt
      `achieved`) → 422.
- [ ] Cockpit-Endpoint mit `upcoming_limit=0` oder `=999` → 422.

---

## Was ist absichtlich nicht Teil dieser Checkliste

- **Keine Deliverables.** Ref4EP führt sie nicht. Wenn auf
  irgendeiner Seite das Wort „Deliverable" als eigene
  Sektion oder Endpoint auftaucht, ist das ein Bug.
- **Kein Hard-Delete.** Soft-Delete oder `is_active=false`
  sind die einzigen „Lösch"-Pfade — die UI darf nirgends
  einen echten Delete anbieten.
- **Kein automatischer Test der UI.** Wir haben Asset-Tests,
  die sicherstellen, dass die richtigen Begriffe und
  Endpoints im JS auftauchen — aber kein Browser-Smoke-Test.
  Diese Checkliste ist die manuelle Ergänzung dazu.
