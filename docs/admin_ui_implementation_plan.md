# Umsetzungsplan: Admin-Oberfläche für Personen, Partner und Mitgliedschaften

Dieser Plan beschreibt den nächsten Block: die bisher nur per CLI
verfügbaren Verwaltungsaufgaben werden im Browser für
Plattform-Admins zugänglich gemacht. Stack bleibt FastAPI +
serverseitig ausgelieferte SPA + Vanilla-JS, keine neue
Build-Kette. Bestehende Services (`PartnerService`,
`PersonService`, `WorkpackageService`) und der CLI-Audit-Pfad
werden wiederverwendet — keine Logik wird doppelt geschrieben.

---

## 1. Ziel

Eine eingeloggte Person mit Plattformrolle `admin` kann unter
`/portal/admin/...` im Browser:

- die Personenliste sehen und Personen anlegen, bearbeiten,
  aktivieren/deaktivieren und ihr Passwort zurücksetzen;
- die Plattformrolle einer Person zwischen `member` und `admin`
  umschalten;
- die WP-Mitgliedschaften einer Person sehen, hinzufügen und
  entfernen sowie die WP-Rolle zwischen `wp_lead` und
  `wp_member` umschalten;
- die Partnerliste sehen und Partner anlegen, ändern und
  soft-löschen.

Alle Aktionen laufen durch die bestehenden Services und schreiben
weiterhin Audit-Einträge mit dem aktuellen Akteur. Passwörter
werden nie im Klartext zurückgegeben oder geloggt.

---

## 2. Nicht-Ziele

- **Keine** E-Mail-Einladung oder Selbstregistrierung. Personen
  werden weiterhin durch Admins angelegt; Initialpasswort wird im
  UI vergeben und einmalig im Antwort-Body angezeigt
  (analog zum heutigen CLI-Output).
- **Keine** SSO-/OIDC-Integration in diesem Block.
- **Keine** Workpackage-CRUD-UI (Anlegen/Editieren von WPs bleibt
  Aufgabe einer späteren Iteration; aktuell genügt der Initial-
  Seed plus die CLI).
- **Kein** Sub-WP-Editor, keine Lead-Partner-Änderung von
  Workpackages über die UI.
- **Kein** Massen-Import (CSV o. ä.).
- **Kein** Profilbearbeiten durch die Person selbst über die
  Admin-Seite (Self-Service-Pfad `/portal/account` bleibt
  unverändert).
- **Kein** Hard-Delete von Personen oder Partnern; Personen
  werden über Deaktivieren ausgeblendet, Partner über Soft-Delete.

---

## 3. Benötigte API-Endpunkte

Alle Endpunkte unter `/api/admin/...`, JSON, CSRF-pflichtig für
nicht-GET, **Plattformrolle `admin` zwingend**. Das Antwort-Schema
für Personen enthält **nie** `password_hash` oder `password` —
Initialpasswort wird ausschließlich beim `create` und beim
`reset-password` einmalig im Response-Body als
`initial_password` zurückgegeben.

### Personen

| Methode | Pfad                                        | Service-Aufruf                          | Antwort                              |
| ------- | ------------------------------------------- | --------------------------------------- | ------------------------------------ |
| GET     | `/api/admin/persons`                        | `PersonService.list_persons()`          | `list[AdminPersonOut]`               |
| GET     | `/api/admin/persons/{id}`                   | `PersonService.get_by_id(id)`           | `AdminPersonDetailOut` mit Memberships |
| POST    | `/api/admin/persons`                        | `PersonService.create(...)`             | `AdminPersonCreatedOut` (mit `initial_password`) |
| PATCH   | `/api/admin/persons/{id}`                   | `PersonService.update_*` (Name, Partner) | `AdminPersonOut`                     |
| POST    | `/api/admin/persons/{id}/reset-password`    | `PersonService.reset_password(...)`     | `{"initial_password": "<klartext, einmalig>"}` |
| POST    | `/api/admin/persons/{id}/set-role`          | `PersonService.set_role(...)`           | `AdminPersonOut`                     |
| POST    | `/api/admin/persons/{id}/enable`            | `PersonService.enable(...)`             | `AdminPersonOut`                     |
| POST    | `/api/admin/persons/{id}/disable`           | `PersonService.disable(...)`            | `AdminPersonOut`                     |

Initial- und Reset-Passwort:

- Server generiert das Passwort mit `secrets.token_urlsafe(12)`,
  übergibt es an `PersonService.create`/`reset_password`,
  gibt den Klartext **einmalig** im Response-Body zurück.
- Optional kann der Admin ein eigenes Passwort übergeben (Feld
  `initial_password` im Request; Mindestlänge 10 Zeichen, vom
  Service bereits validiert).
- Im Audit-Eintrag erscheint der Passwortwert **nicht** —
  weiterhin nur `must_change_password = true` als Effekt.

### Partner

| Methode | Pfad                              | Service-Aufruf                | Antwort                |
| ------- | --------------------------------- | ----------------------------- | ---------------------- |
| GET     | `/api/admin/partners`             | `PartnerService.list_partners(include_deleted=True)` | `list[AdminPartnerOut]` |
| POST    | `/api/admin/partners`             | `PartnerService.create(...)`  | `AdminPartnerOut`      |
| PATCH   | `/api/admin/partners/{id}`        | `PartnerService.update(...)`  | `AdminPartnerOut`      |
| DELETE  | `/api/admin/partners/{id}`        | `PartnerService.soft_delete(...)` | `204 No Content`   |

### Mitgliedschaften

Mitgliedschaften werden im Person-Detail bearbeitet; Endpunkte:

| Methode | Pfad                                          | Service-Aufruf                              | Body / Antwort                          |
| ------- | --------------------------------------------- | ------------------------------------------- | --------------------------------------- |
| POST    | `/api/admin/persons/{id}/memberships`         | `WorkpackageService.add_membership(...)`    | `{"workpackage_code": "WP3", "wp_role": "wp_member"}` → `AdminMembershipOut` |
| PATCH   | `/api/admin/persons/{id}/memberships/{wp_code}` | Service-Roundtrip (siehe unten)           | `{"wp_role": "wp_lead"}` → `AdminMembershipOut` |
| DELETE  | `/api/admin/persons/{id}/memberships/{wp_code}` | `WorkpackageService.remove_membership(...)` | `204 No Content`                        |

Rollenwechsel ohne dedizierte Service-Methode: PATCH liest die
bestehende Membership; falls `wp_role` neu, wird die alte über
`remove_membership` gelöscht und über `add_membership` neu
angelegt. **Beide** Audit-Einträge entstehen wie bei manuellem
Wechsel — bewusst, damit die Spur in beide Richtungen vollständig
bleibt. Alternativ kann eine kleine
`WorkpackageService.set_membership_role(person_id, wp_id, wp_role)`-
Methode ergänzt werden, die einen einzigen
`membership.set_role`-Audit-Eintrag schreibt; der Code sollte sie
nur dann hinzufügen, wenn die zwei separaten Einträge im UI
störend wirken (offene Designentscheidung, siehe §7).

---

## 4. Benötigte Web-Module

Drei neue SPA-Routen. Alle nutzen den bestehenden History-Router
und werden im `app.js` registriert; die Sichtbarkeit der Admin-
Links (Header-Navigation) ist an
`currentMe.person.platform_role === "admin"` gebunden — der
existierende Audit-Link nutzt dieselbe Logik.

| SPA-Pfad                                | Modul (`web/modules/...`)            | Inhalt                                                                  |
| --------------------------------------- | ------------------------------------ | ----------------------------------------------------------------------- |
| `/portal/admin/users`                   | `admin_users.js`                     | Personenliste mit Filter (Name/E-Mail/Partner/Rolle/aktiv-inaktiv) und Button „Person anlegen …". |
| `/portal/admin/users/{id}`              | `admin_user_detail.js`               | Detail einer Person mit Aktionen: Bearbeiten, Rolle ändern, Aktivieren/Deaktivieren, Passwort zurücksetzen, Mitgliedschaften-Block. |
| `/portal/admin/partners`                | `admin_partners.js`                  | Partnerliste mit Anlage- und Bearbeitungs-Dialog, Soft-Delete.          |

Anpassungen an bestehenden Dateien:

- `web/index.html`: zwei neue Header-Links (`Personen`,
  `Partner`), beide mit `hidden`-Attribut; werden in `app.js` für
  Admins eingeblendet (Konvention wie beim Audit-Link).
- `web/app.js`: drei neue Route-Patterns; Modul-Loader funktioniert
  unverändert.
- `web/style.css`: kleine Ergänzungen für die Mitgliedschafts-
  Tabelle (badge-ähnliche Rollen-Marker, evtl. `danger`-Button für
  „Soft-Delete" beim Partner). Keine grundsätzliche Stil-Umstellung.

UI-Konventionen folgen dem Praxistest-Korrekturlauf:

- Buttontext-Konvention: Dialog-Trigger mit `…` am Ende, Submit
  als konkretes Verb (`Anlegen`, `Speichern`, `Übernehmen`,
  `Bestätigen`, `Soft-Delete bestätigen`).
- Pflichtfelder mit klarem Label, Optionalfelder mit
  `(optional)`-Suffix und `field-hint`-Hilfetext.
- Datumsanzeigen deutsch (`toLocaleDateString("de-DE")` bzw.
  `toLocaleString("de-DE")`).
- **Initialpasswort-Anzeige**: nach `create` oder
  `reset-password` zeigt der Dialog einen einmaligen Hinweis
  („Bitte sicher übermitteln, wird nicht erneut angezeigt") mit
  Kopier-Button. Beim Schließen verschwindet der Wert; das
  Frontend hält ihn nicht persistent.

---

## 5. Rechteprüfung

Zwei Schichten, beide bestehend, nur erweiterte Aufrufer:

1. **API**: alle `/api/admin/...`-Endpunkte konsumieren den
   `get_auth_context`-Dependency und prüfen
   `can_admin(auth.platform_role)`. Bei Verstoß HTTP 403 mit
   `{"error":{"code":"forbidden", ...}}`. Anonyme Aufrufe geben
   weiterhin 401 (Auth-Layer greift früher).
2. **Service**: die bestehenden Schreibmethoden in
   `PersonService` / `PartnerService` / `WorkpackageService`
   prüfen bereits intern auf Plattformrolle `admin` (siehe
   `_require_admin`); die API ruft sie unverändert auf — keine
   doppelte Permission-Logik.

CSRF: alle nicht-GET-Endpunkte nutzen `Depends(require_csrf)` wie
in den vorherigen Sprints.

Frontend-Sichtbarkeit: Admin-Nav-Links sind im HTML defaultmäßig
`hidden` und werden nur eingeblendet, wenn `platform_role ===
"admin"`. Nicht-Admins, die die Pfade direkt aufrufen, bekommen
vom Modul beim Render einen 403-Hinweis (analog zur
Audit-Ansicht); der echte Schutz liegt im API-Layer.

---

## 6. Tests

Bestehende Service-Tests bleiben und werden nicht dupliziert.
Neue Tests konzentrieren sich auf API-Routen und Auth-Boundary:

### `tests/api/test_admin_persons.py`

- `GET /api/admin/persons` als Admin → 200 mit Liste; als Member → 403; anonym → 401.
- `POST /api/admin/persons` mit minimalem Body → 201, Antwort
  enthält `initial_password` (Klartext), DB-Hash ist Argon2id
  (kein Klartext gespeichert).
- `POST /api/admin/persons/{id}/reset-password` → 200 mit neuem
  `initial_password`; `must_change_password = true`.
- `POST /api/admin/persons/{id}/set-role` mit `role="admin"` →
  200, neuer Wert in Antwort; ungültiger Wert → 422.
- `POST /api/admin/persons/{id}/disable` → 200, danach Login mit
  diesem Account → 401.
- `PATCH /api/admin/persons/{id}` ändert `display_name` und
  `partner_id` → 200.
- Negativfall: Member-Client darf keinen einzigen dieser
  Endpunkte ausführen → 403 für jeden Pfad.
- Sicherheitsfall: Antwort-Schemas enthalten weder
  `password_hash` noch das im Request übergebene `initial_password`
  (außer im 201-Response-Feld selbst).

### `tests/api/test_admin_partners.py`

- `GET`/`POST`/`PATCH`/`DELETE` als Admin grün; als Nicht-Admin → 403.
- Soft-Delete blendet Partner aus `GET /api/partners` aus
  (existierender Sprint-1-Test bleibt grün).

### `tests/api/test_admin_memberships.py`

- `POST /api/admin/persons/{id}/memberships` legt Mitgliedschaft
  an, `GET /api/admin/persons/{id}` listet sie.
- `PATCH /api/admin/persons/{id}/memberships/{wp_code}` von
  `wp_member` auf `wp_lead` → 200. Audit-Log zeigt entweder
  `membership.set_role` (falls Service-Methode ergänzt) oder
  zwei Einträge `membership.remove` + `membership.add`.
- `DELETE /api/admin/persons/{id}/memberships/{wp_code}` → 204,
  Mitgliedschaft verschwindet aus `GET /api/me` der betroffenen
  Person.

### Audit-Coverage

- Alle Schreibaktionen erzeugen Audit-Einträge — kein neuer Test
  zwingend nötig, weil bestehende Service-Tests den Hook bereits
  abdecken; eine Stichprobe in den API-Tests
  (`assert audit_count_increased_by(...)`) reicht.

### Bestandstests

- Sprint-1-CLI-Tests bleiben unverändert; CLI-Pfad ändert sich
  nicht.
- Keine Migration nötig (alle benötigten Felder existieren).

---

## 7. Definition of Done

- [ ] **Keine Migration** für diesen Block — Schema ist
  vollständig vorhanden.
- [ ] **API-Endpunkte aus §3 implementiert**, alle CSRF-pflichtig
  bei nicht-GET, alle Admin-only-geprüft.
- [ ] `AdminPersonOut`/`AdminPersonDetailOut`/
  `AdminPersonCreatedOut`/`AdminPartnerOut`/`AdminMembershipOut`
  als Pydantic-Schemas; **Passwort-Hash erscheint in keinem
  Response-Schema**.
- [ ] Initial- und Reset-Passwort werden vom Server generiert und
  einmalig zurückgegeben; im Audit-Log steht **kein** Klartext-
  Passwort.
- [ ] Drei neue Web-Module (`admin_users.js`,
  `admin_user_detail.js`, `admin_partners.js`) sind angelegt und
  in `app.js` als Routen registriert.
- [ ] Header-Navigation zeigt für Admins „Personen" und „Partner"
  (zusätzlich zum bestehenden „Audit").
- [ ] Member- und Anonyme-Aufrufe der Admin-API erhalten 401/403;
  Tests bestätigen das.
- [ ] Bestehende Service-Tests laufen unverändert grün.
- [ ] Neue API-Tests aus §6 grün; Coverage über
  `routes/admin_*` ≥ 80 %.
- [ ] `ruff check` und `ruff format --check` grün.
- [ ] Manuelle Smoke-Probe (Admin-Login → `/portal/admin/users`):
      - neue Person anlegen, Initialpasswort kopieren;
      - Person zur Mitgliedschaft in WP3 hinzufügen mit
        `wp_member`, dann auf `wp_lead` umschalten;
      - Person deaktivieren, anschließend reaktivieren;
      - Audit-Log unter `/portal/admin/audit` zeigt alle
        Aktionen mit dem korrekten Akteur.

### Designentscheidung, vor Umsetzung zu klären

- **Rollenwechsel als ein oder zwei Audit-Einträge?** Variante A
  (PATCH = remove+add, zwei Einträge) ist mit Bestandscode sofort
  möglich. Variante B (neue
  `WorkpackageService.set_membership_role`-Methode mit eigenem
  `membership.set_role`-Audit-Eintrag) ist stilistisch sauberer im
  Audit-Log. Empfehlung: Variante B für UX/Audit-Klarheit, kostet
  etwa 20 Zeilen Servicecode + ein Test.
