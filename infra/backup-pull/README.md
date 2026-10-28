# Zweite Backup-Kopie (Rechner an der JLU)

Der Server legt jede Nacht um 03:30 ein Backup unter
`/opt/ref4ep-backups/` an (Datenbank, hochgeladene Dateien,
`backend/.env`) und hebt es 14 Tage auf. Damit Portal und Backups nicht
gemeinsam verloren gehen können, holt ein Rechner an der JLU täglich
eine Kopie.

**Holen statt Schicken:** Der Rechner zieht die Dateien per SSH vom
Server. Auf dem Server liegen keine Zugangsdaten zu diesem Rechner —
wer den Server übernimmt, kommt an diese Kopien nicht heran.

## Was eingerichtet ist

| | |
|---|---|
| Skript | `infra/backup-pull/Pull-Ref4epBackups.ps1` |
| Ablage | `C:\Users\<name>\Ref4EP-Backups\` — bewusst **nicht** in OneDrive oder einem anderen Cloud-Ordner |
| Protokoll | `Ref4EP-Backups\pull.log` |
| Aufgabe | Windows-Aufgabenplanung: „Ref4EP Backup-Kopie", täglich 10:00 und 5 min nach der Anmeldung, verpasste Läufe werden nachgeholt |
| Aufbewahrung | 14 Tage (wie auf dem Server, so in der Datenschutzerklärung) |

Jede geholte Datei wird per SHA-256 mit dem Original auf dem Server
verglichen. Ist der Rechner einige Tage aus, holt der nächste Lauf alles
nach, was auf dem Server noch liegt.

Exit-Codes (sichtbar in der Aufgabenplanung als „Letztes Ergebnis"):
`0` in Ordnung, `1` Fehler (siehe Protokoll), `2` neueste Kopie älter
als 3 Tage — dann läuft vermutlich das Backup auf dem Server nicht.

## Prüfen

```powershell
Get-Content $env:USERPROFILE\Ref4EP-Backups\pull.log -Tail 5
Get-ScheduledTaskInfo -TaskName "Ref4EP Backup-Kopie"
```

## Einrichten auf einem anderen Rechner

Voraussetzung: `ssh forge` funktioniert ohne Passwortabfrage
(Eintrag in `~\.ssh\config`, Schlüssel ohne Passphrase oder über den
ssh-agent). Dann in PowerShell:

```powershell
$script = "<Pfad>\ref4ep-portal\infra\backup-pull\Pull-Ref4epBackups.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$daily  = New-ScheduledTaskTrigger -Daily -At 10:00
$logon  = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"; $logon.Delay = "PT5M"
$set    = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
$who    = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "Ref4EP Backup-Kopie" -Action $action -Trigger @($daily, $logon) -Settings $set -Principal $who
```

Das Skript muss als UTF-8 **mit BOM** gespeichert bleiben, sonst zeigt
Windows PowerShell 5.1 die Umlaute im Protokoll falsch an.

## Zurückspielen

Eine Kopie von hier auf den Server bringen und dann wie in
`/opt/ref4ep-backups/RESTORE.txt` beschrieben entpacken:

```powershell
scp $env:USERPROFILE\Ref4EP-Backups\ref4ep-backup-JJJJMMTT-HHMMSS.tar.gz forge:/opt/ref4ep-backups/
```

Getestet am 28.10.2026: Backup entpackt, Datenbank unbeschädigt
(`integrity_check`), Schema auf dem aktuellen Stand, alle 34
Dateiverweise vorhanden, Portal startet auf den Daten. Beim Start
entfernt das Portal wieder IP-Adressen, die älter als 90 Tage sind —
auch wenn ein älteres Backup sie noch enthielt.

## Hinweis zur Vertraulichkeit

Die Backups enthalten personenbezogene Daten und `backend/.env` mit dem
Sitzungs-Schlüssel des Portals. Der Ordner gehört deshalb nur auf einen
Rechner, auf den allein du Zugriff hast — nicht in einen Cloud-Ordner,
nicht auf einen USB-Stick.
