<#
.SYNOPSIS
  Zweite Backup-Kopie: holt die nächtlichen Portal-Backups vom Server.

.DESCRIPTION
  Läuft auf einem Rechner an der JLU (Windows-Aufgabenplanung, siehe
  infra/backup-pull/README.md). Holt jede Sicherung, die lokal noch fehlt,
  prüft sie per SHA-256 gegen das Original auf dem Server und hebt sie
  $KeepDays Tage auf.

  Bewusst "Holen" statt "Schicken": Auf dem Server liegen keine Zugangs-
  daten zu diesem Rechner. Wer den Server übernimmt, kommt an diese Kopien
  nicht heran.

  Exit-Codes: 0 = in Ordnung, 1 = Fehler, 2 = neueste Kopie zu alt.
  Protokoll: <LocalDir>\pull.log
#>
param(
    [string]$Remote = "forge",
    [string]$RemoteDir = "/opt/ref4ep-backups",
    [string]$LocalDir = (Join-Path $env:USERPROFILE "Ref4EP-Backups"),
    # Wie auf dem Server und so in der Datenschutzerklärung (Abschnitt 8.5).
    [int]$KeepDays = 14,
    # Dateien, die jünger sind, werden evtl. gerade noch geschrieben.
    [int]$MinAgeMinutes = 15,
    # Ab diesem Alter der neuesten Kopie wird gewarnt.
    [int]$WarnAfterDays = 3
)

$ErrorActionPreference = "Stop"
$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$scp = Join-Path $env:WINDIR "System32\OpenSSH\scp.exe"
$pattern = '^ref4ep-backup-(\d{8})-(\d{6})\.tar\.gz$'

New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null
$logFile = Join-Path $LocalDir "pull.log"

function Write-Log([string]$msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Output $line
}

function Invoke-Remote([string]$command) {
    $out = & $ssh -o BatchMode=yes -o ConnectTimeout=20 $Remote $command
    if ($LASTEXITCODE -ne 0) { throw "ssh-Befehl fehlgeschlagen (Exit $LASTEXITCODE): $command" }
    return $out
}

function Get-BackupDate([string]$name) {
    $m = [regex]::Match($name, $pattern)
    if (-not $m.Success) { return $null }
    return [datetime]::ParseExact($m.Groups[1].Value + $m.Groups[2].Value, "yyyyMMddHHmmss", $null)
}

try {
    # 1. Fertige Sicherungen auf dem Server auflisten.
    $listCmd = "find '$RemoteDir' -maxdepth 1 -name 'ref4ep-backup-*.tar.gz' -mmin +$MinAgeMinutes -printf '%f\n' | sort"
    $remoteFiles = @(Invoke-Remote $listCmd | Where-Object { $_ -match $pattern })
    if ($remoteFiles.Count -eq 0) { throw "Keine Sicherungen auf dem Server gefunden ($RemoteDir)." }

    # 2. Fehlende holen und prüfen. Was älter als die Aufbewahrungsfrist
    #    ist, wird nicht mehr geholt (der Server löscht etwas später).
    $cutoff = (Get-Date).AddDays(-$KeepDays)
    $fetched = 0
    foreach ($name in $remoteFiles) {
        $target = Join-Path $LocalDir $name
        if (Test-Path $target) { continue }
        if ((Get-BackupDate $name) -lt $cutoff) { continue }
        $part = "$target.part"
        & $scp -q -p -o BatchMode=yes "${Remote}:$RemoteDir/$name" $part
        if ($LASTEXITCODE -ne 0) { throw "Kopieren fehlgeschlagen: $name" }
        $remoteHash = ((Invoke-Remote "sha256sum '$RemoteDir/$name'") -split '\s+')[0].ToLower()
        $localHash = (Get-FileHash -Algorithm SHA256 -Path $part).Hash.ToLower()
        if ($remoteHash -ne $localHash) {
            Remove-Item $part -Force
            throw "Prüfsumme stimmt nicht: $name"
        }
        Move-Item $part $target -Force
        $sizeMb = [math]::Round((Get-Item $target).Length / 1MB, 1)
        Write-Log "geholt und geprüft: $name ($sizeMb MB)"
        $fetched++
    }

    # 3. Alte Kopien entfernen (nach Datum im Dateinamen).
    foreach ($f in Get-ChildItem $LocalDir -Filter "ref4ep-backup-*.tar.gz") {
        $d = Get-BackupDate $f.Name
        if ($d -and $d -lt $cutoff) {
            Remove-Item $f.FullName -Force
            Write-Log "gelöscht (älter als $KeepDays Tage): $($f.Name)"
        }
    }
    Get-ChildItem $LocalDir -Filter "*.part" | Remove-Item -Force

    # 4. Ist die neueste Kopie frisch genug?
    $local = @(Get-ChildItem $LocalDir -Filter "ref4ep-backup-*.tar.gz" |
        ForEach-Object { Get-BackupDate $_.Name } | Where-Object { $_ } | Sort-Object)
    $newest = $local[-1]
    $ageDays = [math]::Round(((Get-Date) - $newest).TotalDays, 1)
    Write-Log ("fertig: $fetched neu, $($local.Count) Kopien lokal, neueste vom {0:dd.MM.yyyy HH:mm}" -f $newest)
    if ($ageDays -gt $WarnAfterDays) {
        Write-Log "WARNUNG: neueste Kopie ist $ageDays Tage alt — läuft das Backup auf dem Server?"
        exit 2
    }
    exit 0
}
catch {
    Write-Log "FEHLER: $($_.Exception.Message)"
    exit 1
}
