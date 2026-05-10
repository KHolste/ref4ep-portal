# Rollen- und Rechtemodell

Diese Doku beschreibt das aktuelle Rollen- und Rechtemodell des
Ref4EP-Portals (Stand Patch 0042) sowie das vereinbarte Zielmodell für
die Einführung einer expliziten Partnerleitung. Code-Änderungen und
Permission-Logik folgen in eigenständigen Folgepatches (0043 ff.).

Diese Datei ist **lebende Projektdokumentation**, kein historisches
Planungsdokument — bei künftigen Rechteänderungen mit aktualisieren.

## 1. Ist-Zustand Rollenmodell

### Technisch verankerte Rollen

| Quelle | Werte | Verankerung |
| --- | --- | --- |
| `Person.platform_role` | `admin`, `member` | Check-Constraint `ck_person_platform_role`, Tupel `PLATFORM_ROLES` |
| `Membership.wp_role` | `wp_lead`, `wp_member` | Check-Constraint `ck_membership_wp_role`, Tupel `WP_ROLES`, eindeutig pro (`person_id`, `workpackage_id`) |
| `PartnerContact.is_project_lead` | Bool-Flag | rein **deskriptives** Adressbuch-Flag an Kontakteinträgen (oft externe Personen ohne Login-Account); **keine** Rechtewirkung |
| `Workpackage.lead_partner_id` | FK auf `partner` | markiert den lead-führenden **Partner** eines WP, **keine** Personenrolle |

### Permission-Helfer

`services/permissions.py` definiert den `AuthContext`
(`person_id`, `email`, `platform_role`, `memberships`) und Helfer wie
`can_admin`, `is_member_of`, `is_wp_lead`, sowie die Dokument-Pfade
`can_read_document`, `can_write_document`, `can_set_status`,
`can_release`, `can_unrelease`, `can_set_visibility`,
`can_soft_delete_document`, `can_comment_document`,
`can_view_audit_log`. Testkampagnen-Beteiligung über
`is_campaign_participant`.

Der `AuthContext` wird in `api/deps.py:get_auth_context` aus
`Person.memberships` hydratisiert und trägt **keine** partnerbezogene
Rolleninformation.

### Quasi-Partnerleitung über `/api/lead/...`

Der Lead-Router öffnet sich für jede Person, die **mindestens eine**
`wp_lead`-Membership hat (oder Admin ist). Daraus ergibt sich heute
eine implizite Partnerleitung:

- `GET/POST /api/lead/persons` — Personen des **eigenen Partners**
  (`actor.partner_id`) lesen und anlegen (Plattformrolle hartcodiert
  `member`).
- `GET /api/lead/workpackages` und Membership-CRUD in eigenen Lead-WPs.
- `PATCH /api/partners/{id}` — Partnerstammdaten des eigenen Partners
  über `update_by_wp_lead` (eingeschränkte Feldmenge).

Diese Brücke funktioniert, ist aber an die WP-Lead-Mitgliedschaft
geknüpft. Partner ohne WP-Lead haben heute **keinen** lokalen
Verwalter (nur Admin).

## 2. Ist-Zustand Rechte-Matrix

| Aktion | Admin | WP-Lead | WP-Member | Eingeloggt | Anon |
| --- | --- | --- | --- | --- | --- |
| Personen plattformweit anlegen, Rolle setzen | ✓ | ✗ | ✗ | ✗ | ✗ |
| Person für eigenen Partner anlegen (immer `member`) | ✓ | ✓ | ✗ | ✗ | ✗ |
| Personen aktivieren / deaktivieren / Passwort-Reset | ✓ | ✗ | ✗ | ✗ | ✗ |
| Partner anlegen | ✓ | ✗ | ✗ | ✗ | ✗ |
| Partner alle Felder ändern | ✓ | ✗ | ✗ | ✗ | ✗ |
| Partner eingeschränkt ändern (eigener Partner) | ✓ | ✓ | ✗ | ✗ | ✗ |
| Partnerkontakte CRUD | ✓ | ✓ eigener Partner | ✗ | ✗ | ✗ |
| Workpackage anlegen / Stammdaten | ✓ | ✗ | ✗ | ✗ | ✗ |
| WP-Status / Zeitplan ändern | ✓ | ✓ eigene Lead-WP | ✗ | ✗ | ✗ |
| Meilenstein patchen / Doku verknüpfen | ✓ | ✓ WP-bezogen, eigene Lead-WP | ✗ | ✗ | ✗ |
| WP-Dokument lesen | ✓ | ✓ Membership | ✓ Membership | (`internal`) | (`public+released`) |
| WP-Dokument schreiben / Version hochladen | ✓ | ✓ (Member reicht) | ✓ | ✗ | ✗ |
| Library-Dokument ohne WP anlegen | ✓ | ✗ | ✗ | ✗ | ✗ |
| Dokument freigeben (release) | ✓ | ✓ WP-Lead | ✗ | ✗ | ✗ |
| Dokument unrelease | ✓ | ✗ | ✗ | ✗ | ✗ |
| Dokument-Soft-Delete | ✓ | ✗ | ✗ | ✗ | ✗ |
| Sichtbarkeit auf `public` setzen | ✓ | ✓ WP-Lead | ✗ | ✗ | ✗ |
| Testkampagne anlegen / bearbeiten | ✓ | ✓ wenn alle WP-Links eigene Lead-WPs | ✗ | ✗ | ✗ |
| Kampagnenfoto / Notiz pflegen | ✓ | Participant | Participant | ✗ | ✗ |
| Meeting anlegen / bearbeiten | ✓ | ✓ wenn alle WP-Links eigene Lead-WPs | ✗ | ✗ | ✗ |
| Meeting löschen | ✓ | ✗ | ✗ | ✗ | ✗ |
| Backup auslösen | ✓ | ✗ | ✗ | ✗ | ✗ |
| Audit / Systemstatus | ✓ | ✗ | ✗ | ✗ | ✗ |

## 3. Zielmodell

Vier additive Ebenen:

1. **Admin** — technische und fachliche Vollrechte; verwaltet
   Plattformrollen, Stammdaten, System-/Backup-Funktionen, Audit.
2. **Partnerleitung** (intern `partner_lead`) — pro Partner eine oder
   mehrere benannte Personen mit Login-Account. Verwaltet Mitarbeiter,
   Stammdaten und (perspektivisch) Schreibrechte für WPs des eigenen
   Partners.
3. **WP-Lead** — fachliche Leitung eines Arbeitspakets, orthogonal zur
   Partnerleitung. Bleibt unverändert.
4. **WP-Member / Mitglied** — Lesen und Mitarbeiten innerhalb seiner
   WPs; minimale Verwaltungsrechte.

Eine Person kann gleichzeitig Admin, Partnerleitung und WP-Lead sein;
die Rechte addieren sich.

## 4. Festgelegte Entscheidungen

- **Interner Rollenname:** `partner_lead`
- **UI-Label:** „Projektleitung" (sprachlich passender für die
  Konsortialkommunikation)
- **`PartnerContact.is_project_lead` bleibt** unverändert als
  deskriptive Kontaktmarkierung ohne Berechtigungswirkung. Externe
  Kontakte (oft ohne Login-Account) dürfen weiter so markiert sein.
  Doku-Hinweis im Schema-Kommentar wird in einem späteren Polish-Patch
  geschärft.
- **Mehrere Projektleitungen pro Partner sind zulässig** (z. B.
  Vertretung). Keine harte Obergrenze.
- **Mindestanzahl** wird **weich** überprüft: UI-Warnung im
  Partnerdetail und im Admin-Cockpit. **Kein DB-Trigger.**
- **Dokument-Leserechte werden durch Partnerleitung NICHT automatisch
  erweitert.** Sichtbarkeit bleibt `Membership`-basiert plus
  `visibility=internal`/`public`-Pfad. Nur Schreib-/Patch-/Release-
  Pfad bekommt eine zusätzliche Partnerlead-Schwelle.
- **WP-Lead und Partnerleitung** sind unabhängig modelliert und
  additiv in der Permission-Auswertung.

## 5. Datenmodell-Vorschlag

Neue Tabelle `partner_role` (Migration in Patch 0043):

| Spalte | Typ | Zwang |
| --- | --- | --- |
| `id` | `String(36)` | PK, UUID |
| `person_id` | `String(36)` | FK → `person.id`, NOT NULL, Index |
| `partner_id` | `String(36)` | FK → `partner.id`, NOT NULL, Index |
| `role` | `String` | NOT NULL, CHECK `IN ('partner_lead')` |
| `created_at` | `DateTime(tz)` | NOT NULL, Default `now` |
| `created_by_person_id` | `String(36)` | FK → `person.id`, NOT NULL |

`UNIQUE (person_id, partner_id, role)` verhindert Duplikate.

`role` als String + CHECK belässt Raum für künftige Werte ohne
Schema-Änderung. AuthContext wird in einem späteren Patch um
`partner_roles: list[PartnerRoleInfo]` erweitert, analog zur
bestehenden `memberships`-Hydratation.

## 6. Vorgeschlagene Rechte für Partnerleitung

Für ihren eigenen Partner-ID `X` **darf** die Partnerleitung:

- Personen mit `partner_id = X` listen, anlegen, aktivieren/deaktivieren
  (Plattformrolle hart `member`)
- Partner-Stammdaten von `X` ändern, außer `short_name` und
  `lead_partner_id`-Relationen
- Partner-Kontakte von `X` CRUD
- *(perspektivisch, ab Patch 0046)* WP-Status / Zeitplan ändern für
  WPs, in denen `lead_partner_id == X`
- *(perspektivisch)* Meilensteine eines WP mit `lead_partner_id == X`
  patchen und Dokumente verknüpfen
- *(perspektivisch)* Dokumente und Versionen in WPs mit
  `lead_partner_id == X` hochladen / patchen / freigeben
- *(perspektivisch)* Meetings und Testkampagnen anlegen/bearbeiten,
  deren WP-Links allesamt `lead_partner_id == X` haben

**Darf nicht:**

- Plattformrolle ändern, Admins ernennen
- Personen anderer Partner sehen oder anlegen
- Partner-Stammdaten anderer Partner ändern
- Backup auslösen, Audit / Systemstatus ansehen
- WP anlegen, WP-Hierarchie ändern, `lead_partner_id` umstellen
- Dokument-Leserechte ausweiten (Sichtbarkeit bleibt
  Membership-basiert)
- Dokumente unrelease oder soft-delete (sofern nicht in einem späteren
  Patch explizit anders entschieden)
- Meeting löschen

## 7. Patch-Aufteilung

| Patch | Inhalt | Status |
| --- | --- | --- |
| **0042** | Diese Doku (`docs/role_model.md`) + optionaler Verweis in `README.md`; keine Code-Logik | **dieser Patch** |
| **0043** | Migration `0022_partner_roles` + ORM-Klasse `PartnerRole` + `PartnerRoleService` (list / add / remove / `is_partner_lead_for`) + Audit-Aktionen. Reine Datenebene, noch keine Permission-Wirkung. | offen |
| **0044** | Admin-/Partner-UI zur Pflege der Partnerleitung: Endpunkte `GET/POST/DELETE /api/admin/partners/{id}/leads`, Partnerdetail-Sektion, UI-Warnung bei null Leitungen | offen |
| **0045** | Permission-Umstellung A — Personen- und Partner-Stammdatenrechte: `/api/lead/persons` und `update_by_wp_lead` öffnen sich zusätzlich für Partnerleitung; AuthContext-Hydratation um `partner_roles` | offen |
| **0046** | Permission-Umstellung B — WP-/Meilenstein-/Dokument-Schreibrechte: `WorkpackageService.update_status`, `MilestoneService.can_edit`, `can_write_document`, `can_release`, `can_set_visibility` erweitern. **Lese-Pfad unverändert.** | offen |
| **0047** | Polish: Schema-Kommentar an `PartnerContact.is_project_lead` schärfen, Audit-Übersicht „Wer ist aktuell Partnerleitung?" | offen |
| **0048** | Admin-Cockpit-Warnung „Partner ohne Projektleitung" | offen |

## 8. Risiken

- **Rechteeskalation:** Personen-Anlegen muss serverseitig die
  Plattformrolle hart auf `member` setzen — Partnerlead darf keinen
  Admin erzeugen. Pattern aus `PersonService.create_by_wp_lead`
  übernehmen.
- **Sichtbarkeitslecks bei Dokumenten:** Eine Leseerweiterung über
  `lead_partner_id` würde Drafts in fremden WPs aufdecken, sobald der
  eigene Partner als Lead-Partner geführt wird, aber keine
  Membership besteht. **Lese-Pfad daher unverändert lassen.**
- **Namensverwechslung `PartnerContact.is_project_lead` vs.
  `partner_role`:** Im UI klar trennen — „Projektleitung des Partners
  (Login-Account)" gegenüber „Projektleitung-Kontaktmarkierung".
- **Falsche Partnerzuordnung einer Person:** Person mit falschem
  `partner_id` taucht in der falschen „Mein Team"-Sicht auf. Heilung
  über Admin-UI; Audit deckt Verschiebungen auf.
- **Testaufwand:** moderat. Bestehende Permission-Tests bleiben grün,
  weil Partnerlead ein **additiver** Pfad ist; neue Tests pro Patch
  ergänzen.
- **Migration:** rein additiv, kein Datenverlust. Seed kann optional je
  einen initialen Partnerlead pro Partner setzen, sollte aber
  idempotent sein.

## 9. Bezugnehmende Stellen

Für die spätere Umsetzung sind diese Code-Stellen die wesentlichen
Anlaufpunkte:

- `backend/src/ref4ep/domain/models.py` — `Person`, `Partner`,
  `Membership`, `PartnerContact`, `Workpackage`
- `backend/src/ref4ep/services/permissions.py` — zentrale
  Permission-Helfer
- `backend/src/ref4ep/services/person_service.py` — Personen-CRUD,
  `create_by_wp_lead` als Vorlage für Partnerlead
- `backend/src/ref4ep/services/partner_service.py` —
  `update_by_wp_lead`, `is_wp_lead_for_partner`
- `backend/src/ref4ep/services/workpackage_service.py`,
  `milestone_service.py`, `document_service.py`,
  `meeting_service.py`, `test_campaign_service.py` — schreibende
  Pfade
- `backend/src/ref4ep/api/routes/lead.py` — bestehende Lead-Brücke
- `backend/src/ref4ep/api/deps.py:get_auth_context` —
  AuthContext-Hydratation
