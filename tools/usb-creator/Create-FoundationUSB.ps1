<#
Create-FoundationUSB.ps1 — make a Foundation TerminalOS install USB on Windows.

This is the "program you download on a normal PC": it finds (or downloads) the
installer ISO and writes it onto a USB stick. Boot the target machine from
that stick and the on-screen installer takes it from there — no Linux
knowledge needed on either machine.

Easiest way to run it: double-click FoundationUSBCreator.cmd next to this
file. Or, from PowerShell:

    powershell -ExecutionPolicy Bypass -File .\Create-FoundationUSB.ps1
    powershell -ExecutionPolicy Bypass -File .\Create-FoundationUSB.ps1 -Iso C:\path\to\foundation-terminalos-....iso
    powershell -ExecutionPolicy Bypass -File .\Create-FoundationUSB.ps1 -NoModel
    powershell -ExecutionPolicy Bypass -File .\Create-FoundationUSB.ps1 -ForceFull

Safety: it only ever offers USB-bus disks (never your internal drive).
Writes are gated: ERASE (full wipe), UPDATE (ISO-only / keep AI), STAGE (AI-only).

Stick-aware modes (probes the stick before writing):
  full     — diskpart clean + ISO + AI sidecar (blank/unknown/both stale)
  iso_only — rewrite ISO only; leave AI sidecar past 2 GiB untouched
  ai_only  — write AI sidecar only; keep existing ISO
  skip     — ISO + AI already match; nothing to write
#>
[CmdletBinding()]
param(
  # Path to the installer ISO. If omitted, the script looks next to itself,
  # then in the repo's image/out/, then offers to download the latest release.
  [string]$Iso,
  # Skip staging Frank's local AI (model + llama-server) onto the stick.
  # Use only for faster stick refreshes when the target ALREADY has working
  # local AI. Fresh installs need full staging (default) for offline Assistant.
  [switch]$NoModel,
  # Always full wipe + rewrite even if the stick already matches.
  [switch]$ForceFull
)

$ErrorActionPreference = 'Stop'
$GitHubRepo = 'HankTheMan2828/Foundation-Terminal-OS'
# Raw-offset AI sidecar (must match create-foundation-usb.sh + foundation-install).
# Contract: ISO must stay under 2 GiB; sidecar lives at STAGE_OFFSET in free space.
$STAGE_OFFSET = [long]2147483648   # 2 GiB

function Say([string]$m)  { Write-Host "[*] $m" -ForegroundColor Yellow }
function Good([string]$m) { Write-Host "[+] $m" -ForegroundColor Green }
function Bad([string]$m)  { Write-Host "[!] $m" -ForegroundColor Red }

function Show-Banner {
  Write-Host ''
  Write-Host '  +--------------------------------------------------------------+' -ForegroundColor Yellow
  Write-Host '  |          FOUNDATION  TERMINALOS  -  USB  CREATOR             |' -ForegroundColor Yellow
  Write-Host '  |                  "From the Foundation."                      |' -ForegroundColor Yellow
  Write-Host '  +--------------------------------------------------------------+' -ForegroundColor Yellow
  Write-Host ''
  Write-Host '  This prepares a Foundation TerminalOS install USB.'
  Write-Host '  It probes the stick first: full wipe only when needed;'
  Write-Host '  otherwise it updates just the ISO and/or AI sidecar.'
  Write-Host '  Your computer itself is NOT touched - only the USB stick.'
  Write-Host ''
}

# ── elevation ────────────────────────────────────────────────────────────────
$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Say 'Writing a USB stick needs administrator rights - asking Windows now...'
  $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit',
               '-File', ('"{0}"' -f $PSCommandPath))
  if ($Iso) { $argList += @('-Iso', ('"{0}"' -f $Iso)) }
  if ($NoModel) { $argList += '-NoModel' }
  if ($ForceFull) { $argList += '-ForceFull' }
  Start-Process powershell -Verb RunAs -ArgumentList $argList
  exit 0
}

Show-Banner

# ── 1. find the ISO ──────────────────────────────────────────────────────────
function Get-ReleaseIso {
  # newest release ISO asset (+ its expected SHA256 when published); $null if
  # offline or nothing released
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    # the release list (not /latest, which 404s on a repo with no releases yet)
    $rels = @(Invoke-RestMethod -UseBasicParsing "https://api.github.com/repos/$GitHubRepo/releases")
  } catch { return $null }
  $asset = $rels | ForEach-Object { $_.assets } |
           Where-Object { $_.name -like '*.iso' } | Select-Object -First 1
  if (-not $asset) {
    return [pscustomobject]@{ ReleaseCount = $rels.Count; Name = $null }
  }
  $sha = $null
  $sums = $rels | ForEach-Object { $_.assets } |
          Where-Object { $_.name -eq 'SHA256SUMS' } | Select-Object -First 1
  if ($sums) {
    try {
      $raw = (Invoke-WebRequest -UseBasicParsing $sums.browser_download_url).Content
      if ($raw -is [byte[]]) { $raw = [Text.Encoding]::ASCII.GetString($raw) }
      $line = $raw -split "`n" | Where-Object { $_ -like "*$($asset.name)*" } | Select-Object -First 1
      if ($line) { $sha = ($line.Trim() -split '\s+')[0].ToLower() }
    } catch {}
  }
  [pscustomobject]@{ ReleaseCount = $rels.Count; Name = $asset.name
                     Url = $asset.browser_download_url; Size = $asset.size; Sha256 = $sha }
}

function Save-ReleaseIso {
  param($Asset)
  $dest = Join-Path (Join-Path $env:USERPROFILE 'Downloads') $Asset.Name
  Say ("Downloading {0} ({1:N0} MB) to your Downloads folder..." -f $Asset.Name, ($Asset.Size / 1MB))
  try {
    Start-BitsTransfer -Source $Asset.Url -Destination $dest `
      -DisplayName 'Foundation TerminalOS installer ISO'
  } catch {
    # BITS can be disabled; plain download works everywhere (just no progress bar)
    $old = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
    try { Invoke-WebRequest -UseBasicParsing $Asset.Url -OutFile $dest }
    finally { $ProgressPreference = $old }
  }
  Good "Downloaded: $dest"
  return $dest
}

function Find-Iso {
  param([string]$Given)
  if ($Given) {
    if (Test-Path $Given) { return (Resolve-Path $Given).Path }
    Bad "ISO not found at: $Given"
    exit 1
  }
  # a repo checkout two levels up (tools/usb-creator/ -> repo root): a dev's
  # own build, taken as-is with no freshness check
  $here = Split-Path -Parent $PSCommandPath
  $repoOut = Join-Path $here '..\..\image\out'
  if (Test-Path $repoOut) {
    $built = Get-ChildItem -Path $repoOut -Filter 'foundation-terminalos-*.iso' -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($built) { return $built.FullName }
  }
  # next to this script, or in Downloads (the normal end-user case)
  $cand = $null
  foreach ($dir in @($here, (Join-Path $env:USERPROFILE 'Downloads'))) {
    if (-not (Test-Path $dir)) { continue }
    $found = Get-ChildItem -Path $dir -Filter 'foundation-terminalos-*.iso' -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($found) { $cand = $found.FullName; break }
  }

  if ($cand) {
    # stale-ISO guard: compare with the current release so an old download
    # never gets written by mistake — and a current one is never re-downloaded
    $rel = Get-ReleaseIso
    if ($rel -and $rel.Name) {
      $stale = $false
      if ((Split-Path -Leaf $cand) -ne $rel.Name) {
        $stale = $true
      } elseif ($rel.Sha256) {
        Say 'Making sure your ISO matches the current release (takes a few seconds)...'
        $localSha = (Get-FileHash -Algorithm SHA256 -Path $cand).Hash.ToLower()
        if ($localSha -ne $rel.Sha256) { $stale = $true }
      }
      if ($stale) {
        Say 'The ISO on this computer is OUTDATED - fetching the current release...'
        return Save-ReleaseIso $rel
      }
      Good 'Your ISO matches the current release - no download needed.'
    }
    return $cand
  }

  # nothing local: offer to download the latest release
  Say 'No installer ISO found on this computer.'
  $ans = Read-Host '> download the latest release now? [Y/n]'
  if ($ans -and $ans.Trim().ToLower().StartsWith('n')) {
    Bad 'Nothing to write. Put the ISO next to this script, or pass -Iso <path>.'
    exit 1
  }
  $rel = Get-ReleaseIso
  if (-not $rel) {
    Bad 'Could not reach GitHub.'
    Bad 'Check your internet connection and try again, or download the ISO'
    Bad 'manually from the Releases page and put it next to this script.'
    exit 1
  }
  if (-not $rel.Name) {
    if ($rel.ReleaseCount -eq 0) {
      Bad "The project hasn't published a release yet, so there is no ISO to download."
    } else {
      Bad "No release of $GitHubRepo has an ISO attached."
    }
    Bad 'A maintainer publishes one by pushing a TerminalOS-v* tag (CI builds and attaches'
    Bad 'the ISO automatically). Until then: build it with image/build-iso.sh'
    Bad 'and put the ISO next to this script, then run this again.'
    exit 1
  }
  return Save-ReleaseIso $rel
}

$IsoPath = Find-Iso $Iso
$IsoSize = [long](Get-Item $IsoPath).Length
Good ("Installer image: {0} ({1:N0} MB)" -f $IsoPath, ($IsoSize / 1MB))
Write-Host ''

# ── 2. pick the USB stick ────────────────────────────────────────────────────
# Only USB-bus disks are ever offered, and never a disk Windows runs from.
$usb = @(Get-Disk | Where-Object { $_.BusType -eq 'USB' -and -not $_.IsBoot -and -not $_.IsSystem })
if ($usb.Count -eq 0) {
  Bad 'No USB stick found. Plug one in (8 GB or larger) and run this again.'
  Read-Host 'Press ENTER to close'
  exit 1
}

Say 'USB sticks on this computer (internal drives are never listed):'
Write-Host ''
for ($i = 0; $i -lt $usb.Count; $i++) {
  $d = $usb[$i]
  Write-Host ("  {0}) {1}  -  {2:N1} GB" -f ($i + 1), $d.FriendlyName.Trim(), ($d.Size / 1GB))
}
Write-Host ''

$target = $null
while (-not $target) {
  $pick = Read-Host ('> write to stick # (1-{0}, or q to quit)' -f $usb.Count)
  if ($pick -eq 'q') { Say 'Aborted - nothing was touched.'; Read-Host 'Press ENTER to close'; exit 0 }
  $n = 0
  if ([int]::TryParse($pick, [ref]$n) -and $n -ge 1 -and $n -le $usb.Count) { $target = $usb[$n - 1] }
}

if ($target.Size -lt $IsoSize) {
  Bad ("That stick is too small: it holds {0:N1} GB, the installer needs {1:N1} GB." -f
       ($target.Size / 1GB), ($IsoSize / 1GB))
  Read-Host 'Press ENTER to close'
  exit 1
}

# ── Raw disk helpers (used by probe + all write modes) ───────────────────────
if (-not ([System.Management.Automation.PSTypeName]'RawDisk').Type) {
  Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

public static class RawDisk {
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  static extern SafeFileHandle CreateFile(string name, uint access, uint share,
    IntPtr sec, uint disposition, uint flags, IntPtr template);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern bool DeviceIoControl(SafeFileHandle h, uint code,
    IntPtr inBuf, uint inSize, IntPtr outBuf, uint outSize,
    out uint returned, IntPtr overlapped);

  const uint GENERIC_READ  = 0x80000000;
  const uint GENERIC_WRITE = 0x40000000;
  const uint SHARE_RW      = 0x3;          // FILE_SHARE_READ | FILE_SHARE_WRITE
  const uint OPEN_EXISTING = 3;
  public const uint FSCTL_LOCK_VOLUME     = 0x00090018;
  public const uint FSCTL_DISMOUNT_VOLUME = 0x00090020;

  public static SafeFileHandle Open(string path, bool write) {
    uint access = write ? (GENERIC_READ | GENERIC_WRITE) : GENERIC_READ;
    var h = CreateFile(path, access, SHARE_RW, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero);
    if (h.IsInvalid)
      throw new IOException(string.Format("CreateFile('{0}') failed (win32 error {1})",
        path, Marshal.GetLastWin32Error()));
    return h;
  }

  public static void Fsctl(SafeFileHandle h, uint code) {
    uint ret;
    if (!DeviceIoControl(h, code, IntPtr.Zero, 0, IntPtr.Zero, 0, out ret, IntPtr.Zero))
      throw new IOException(string.Format("DeviceIoControl(0x{0:X}) failed (win32 error {1})",
        code, Marshal.GetLastWin32Error()));
  }
}
'@
}

function Test-GzipFile([string]$path) {
  if (-not (Test-Path $path)) { return $false }
  $fs = [IO.File]::OpenRead($path)
  try {
    $b = New-Object byte[] 2
    if ($fs.Read($b, 0, 2) -lt 2) { return $false }
    return ($b[0] -eq 0x1f -and $b[1] -eq 0x8b)
  } finally { $fs.Close() }
}

function Test-BytesEqual([byte[]]$a, [byte[]]$b, [int]$len) {
  if ($null -eq $a -or $null -eq $b) { return $false }
  if ($a.Length -lt $len -or $b.Length -lt $len) { return $false }
  for ($i = 0; $i -lt $len; $i++) {
    if ($a[$i] -ne $b[$i]) { return $false }
  }
  return $true
}

function Read-DiskRange([string]$phys, [long]$offset, [int]$count) {
  $buf = New-Object byte[] $count
  $fs = New-Object IO.FileStream($phys, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
  try {
    $null = $fs.Seek($offset, [IO.SeekOrigin]::Begin)
    $got = $fs.Read($buf, 0, $count)
    if ($got -lt $count) {
      $trim = New-Object byte[] $got
      [Array]::Copy($buf, $trim, $got)
      return $trim
    }
    return $buf
  } finally { $fs.Close() }
}

function Get-StickProbe {
  param(
    [int]$DiskNumber,
    [string]$IsoPath,
    [long]$IsoSize,
    [long]$StageOffset,
    [string]$ModelPath,
    [string]$ServerPath,
    [bool]$WantAi
  )
  $phys = "\\.\PHYSICALDRIVE$DiskNumber"
  $isoMatch = $false
  $aiPresent = $false
  $aiMatch = $false
  $isoNote = 'unreadable or empty'
  $aiNote = 'not checked'

  try {
    $chunk = 1MB
    if ($IsoSize -lt (2 * $chunk)) { $chunk = [int]([math]::Max(512, [math]::Floor($IsoSize / 2))) }
    $src = [IO.File]::OpenRead($IsoPath)
    try {
      $headIso = New-Object byte[] $chunk
      $tailIso = New-Object byte[] $chunk
      [void]$src.Read($headIso, 0, $chunk)
      $null = $src.Seek($IsoSize - $chunk, [IO.SeekOrigin]::Begin)
      [void]$src.Read($tailIso, 0, $chunk)
    } finally { $src.Close() }

    $headDisk = Read-DiskRange $phys 0 $chunk
    $tailDisk = Read-DiskRange $phys ($IsoSize - $chunk) $chunk
    $headOk = Test-BytesEqual $headIso $headDisk $chunk
    $tailOk = Test-BytesEqual $tailIso $tailDisk $chunk
    if ($headOk -and $tailOk) {
      $isoMatch = $true
      $isoNote = 'matches local ISO (head+tail 1 MB)'
    } elseif ($headOk) {
      $isoNote = 'partial match (head only) — will rewrite ISO'
    } else {
      # Hybrid ISO9660 marker at 32 KiB + 1 ("CD001") is a weak "looks like an ISO" signal
      $looksIso = $false
      if ($headDisk.Length -gt 32773) {
        $sig = [Text.Encoding]::ASCII.GetString($headDisk, 32769, 5)
        $looksIso = ($sig -eq 'CD001')
      }
      if ($looksIso) { $isoNote = 'different ISO present — will rewrite' }
      else { $isoNote = 'not a matching Foundation ISO (blank or other)' }
    }
  } catch {
    $isoNote = "probe failed: $($_.Exception.Message)"
  }

  try {
    $hdrBuf = Read-DiskRange $phys $StageOffset 4096
    if ($hdrBuf.Length -ge 64) {
      $hdrEnd = [Array]::IndexOf($hdrBuf, [byte]0)
      if ($hdrEnd -lt 0) { $hdrEnd = $hdrBuf.Length }
      $hdrText = [Text.Encoding]::ASCII.GetString($hdrBuf, 0, $hdrEnd)
      if ($hdrText.StartsWith('FOUNDATIONAI2')) {
        $aiPresent = $true
        $mo = 0L; $ms = 0L; $so = 0L; $ss = 0L
        foreach ($ln in ($hdrText -split "`n")) {
          $t = $ln.Trim()
          if ($t.StartsWith('model_offset=')) { [void][long]::TryParse($t.Substring(13), [ref]$mo) }
          elseif ($t.StartsWith('model_size=')) { [void][long]::TryParse($t.Substring(11), [ref]$ms) }
          elseif ($t.StartsWith('server_offset=')) { [void][long]::TryParse($t.Substring(14), [ref]$so) }
          elseif ($t.StartsWith('server_size=')) { [void][long]::TryParse($t.Substring(12), [ref]$ss) }
        }
        $gguf = Read-DiskRange $phys $mo 4
        $gz = Read-DiskRange $phys $so 2
        $ggufOk = ($gguf.Length -ge 4 -and [Text.Encoding]::ASCII.GetString($gguf) -eq 'GGUF')
        $gzOk = ($gz.Length -ge 2 -and $gz[0] -eq 0x1f -and $gz[1] -eq 0x8b)
        if (-not $WantAi) {
          $aiMatch = $true
          $aiNote = 'present (NoModel — not restaging)'
        } elseif ($ggufOk -and $gzOk -and (Test-Path $ModelPath) -and (Test-Path $ServerPath)) {
          $localMs = [long](Get-Item $ModelPath).Length
          $localSs = [long](Get-Item $ServerPath).Length
          if ($ms -eq $localMs -and $ss -eq $localSs) {
            $aiMatch = $true
            $aiNote = ("matches local AI (model {0:N0} MB + runtime {1:N0} KB)" -f ($ms / 1MB), ($ss / 1KB))
          } else {
            $aiNote = ("present but size mismatch (stick model={0} local={1})" -f $ms, $localMs)
          }
        } elseif ($ggufOk -and $gzOk) {
          $aiNote = 'present and readable (local AI files not ready to compare)'
          $aiMatch = $false
        } else {
          $aiNote = 'header present but payload magic failed'
        }
      } else {
        $aiNote = 'no FOUNDATIONAI2 header at 2 GiB'
      }
    } else {
      $aiNote = 'could not read AI header region'
    }
  } catch {
    $aiNote = "AI probe failed: $($_.Exception.Message)"
  }

  [pscustomobject]@{
    IsoMatch  = $isoMatch
    AiPresent = $aiPresent
    AiMatch   = $aiMatch
    IsoNote   = $isoNote
    AiNote    = $aiNote
  }
}

# Paths for AI prep / probe (next to this script)
$modelPath   = Join-Path (Split-Path -Parent $PSCommandPath) 'model.gguf'
$runtimePath = Join-Path (Split-Path -Parent $PSCommandPath) 'ai-runtime.tar.gz'
$serverPath  = Join-Path (Split-Path -Parent $PSCommandPath) 'llama-server'  # legacy bare ELF
$requireAI   = -not ($NoModel -or $env:FOUNDATION_NO_MODEL -eq '1')
$stageAI     = $false
$stageServerPath = $null

function FailAi([string]$m) {
  Bad $m
  if ($requireAI) {
    Bad 'Local AI is required for a full offline install (Hub ASSISTANT + Frank).'
    Bad 'Fix the problem above, or pass -NoModel only if the target already has AI.'
    Read-Host 'Press ENTER to close'
    exit 1
  }
}

# Light local AI discovery for probe (no downloads yet — downloads happen if mode needs AI)
if ($requireAI) {
  if (Test-GzipFile $runtimePath) { $stageServerPath = $runtimePath }
  elseif (Test-Path $serverPath) { $stageServerPath = $serverPath }
}

Say 'Probing the stick (what is already there)...'
$probe = Get-StickProbe -DiskNumber $target.Number -IsoPath $IsoPath -IsoSize $IsoSize `
  -StageOffset $STAGE_OFFSET -ModelPath $modelPath -ServerPath $(if ($stageServerPath) { $stageServerPath } else { $runtimePath }) `
  -WantAi $requireAI
Write-Host ("  ISO: {0}" -f $probe.IsoNote)
Write-Host ("  AI:  {0}" -f $probe.AiNote)
Write-Host ''

# ── decide write mode ────────────────────────────────────────────────────────
# full | iso_only | ai_only | skip
$mode = 'full'
if ($ForceFull) {
  $mode = 'full'
  Say 'ForceFull: full wipe + rewrite requested.'
} elseif (-not $requireAI) {
  if ($probe.IsoMatch) { $mode = 'skip' } else { $mode = 'iso_only' }
} else {
  if ($probe.IsoMatch -and $probe.AiMatch) { $mode = 'skip' }
  elseif ($probe.IsoMatch -and -not $probe.AiMatch) { $mode = 'ai_only' }
  elseif (-not $probe.IsoMatch -and $probe.AiMatch) { $mode = 'iso_only' }
  else { $mode = 'full' }
}

# Prefer if/elseif over switch when format strings with braces appear nearby
# (switch case parsing can confuse closing braces with format tokens).
if ($mode -eq 'skip') {
  Good 'Stick already has this ISO'
  if ($requireAI) { Good 'and a matching AI sidecar - nothing to write.' }
  else { Good '(NoModel) - nothing to write.' }
  Write-Host ''
  Good 'Your Foundation TerminalOS install USB is ready (unchanged).'
  Write-Host 'Boot the mini PC from this stick -> UPDATE or INSTALL as needed.'
  Write-Host ''
  Write-Host 'Force a full rewrite anytime with -ForceFull.'
  Read-Host 'Press ENTER to close'
  exit 0
} elseif ($mode -eq 'iso_only') {
  Say 'Mode: ISO-ONLY - rewrite installer, keep AI sidecar past 2 GiB.'
  $stickName = $target.FriendlyName.Trim()
  Bad "Stick '$stickName' ISO will be rewritten; free-space AI (if any) is preserved."
  $confirm = Read-Host '> type UPDATE (all caps) to continue, anything else aborts'
  if ($confirm -cne 'UPDATE') {
    Say 'Aborted - nothing was touched.'
    Read-Host 'Press ENTER to close'
    exit 0
  }
  $stageAI = $false
} elseif ($mode -eq 'ai_only') {
  Say 'Mode: AI-ONLY - keep existing ISO, stage/refresh AI sidecar only.'
  $stickName = $target.FriendlyName.Trim()
  Bad "AI sidecar (~1.2 GB+) will be written at 2 GiB on '$stickName'."
  Bad 'The installer ISO already on the stick is NOT wiped.'
  $confirm = Read-Host '> type STAGE (all caps) to continue, anything else aborts'
  if ($confirm -cne 'STAGE') {
    Say 'Aborted - nothing was touched.'
    Read-Host 'Press ENTER to close'
    exit 0
  }
} else {
  $mode = 'full'
  Say 'Mode: FULL - clean stick, write ISO, stage AI (if required).'
  $stickName = $target.FriendlyName.Trim()
  $stickGb = [string]::Format('{0:N1}', ($target.Size / 1GB))
  Bad "EVERYTHING on '$stickName' ($stickGb GB) will be destroyed."
  $confirm = Read-Host '> type ERASE (all caps) to continue, anything else aborts'
  if ($confirm -cne 'ERASE') {
    Say 'Aborted - nothing was touched.'
    Read-Host 'Press ENTER to close'
    exit 0
  }
}

# ── prepare AI when the chosen mode needs it ─────────────────────────────────
if ($mode -eq 'full' -or $mode -eq 'ai_only') {
  if ($requireAI) {
    try {
      $ModelUrl = if ($env:FOUNDATION_MODEL_URL) { $env:FOUNDATION_MODEL_URL }
                  else { 'https://huggingface.co/microsoft/bitnet-b1.58-2B-4T-gguf/resolve/main/ggml-model-i2_s.gguf' }
      if (-not (Test-Path $modelPath)) {
        Say 'Downloading the AI model to stage (~1.2 GB; skip with -NoModel)...'
        try { Start-BitsTransfer -Source $ModelUrl -Destination $modelPath -DisplayName 'Frank local AI model' }
        catch {
          $old = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
          try { Invoke-WebRequest -UseBasicParsing $ModelUrl -OutFile $modelPath } finally { $ProgressPreference = $old }
        }
      }
      if (-not (Test-GzipFile $runtimePath)) {
        $srvUrl = $env:FOUNDATION_AI_SERVER_URL
        if (-not $srvUrl) {
          try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $rels = @(Invoke-RestMethod -UseBasicParsing "https://api.github.com/repos/$GitHubRepo/releases")
            $assets = @($rels | ForEach-Object { $_.assets })
            $pick = $assets |
              Where-Object {
                $_.name -like 'foundation-ai-runtime*.tar.gz' -or
                $_.name -like 'foundation-ai-llama-server*.tar.gz'
              } |
              Where-Object { $_.name -notlike '*.sha256' } |
              Select-Object -First 1
            if (-not $pick) {
              $pick = $assets |
                Where-Object { $_.name -like 'foundation-ai-llama-server*' -and $_.name -notlike '*.sha256' -and $_.name -notlike '*.tar.gz' } |
                Select-Object -First 1
            }
            $srvUrl = $pick.browser_download_url
          } catch { $srvUrl = $null }
        }
        if ($srvUrl) {
          $dest = if ($srvUrl -match '\.tar\.gz') { $runtimePath } else { $serverPath }
          Say "Downloading the AI runtime ($([IO.Path]::GetFileName(($srvUrl -split '\?')[0])))..."
          try { Invoke-WebRequest -UseBasicParsing $srvUrl -OutFile $dest } catch {}
        }
      }
      if ((Test-Path $serverPath) -and -not (Test-GzipFile $runtimePath)) {
        Bad 'Found legacy bare llama-server ELF next to this script.'
        Bad 'Delete it and re-run so the creator downloads ai-runtime.tar.gz instead.'
      }
      $stageServerPath = $null
      if (Test-GzipFile $runtimePath) { $stageServerPath = $runtimePath }

      if (-not (Test-Path $modelPath)) {
        FailAi 'AI model download failed.'
      } elseif (-not $stageServerPath) {
        FailAi 'AI runtime tarball missing (foundation-ai-runtime-*.tar.gz from the release).'
      } elseif ($IsoSize -ge $STAGE_OFFSET) {
        FailAi 'ISO is larger than the 2 GiB staging offset — cannot stage AI past it.'
      } else {
        $fs = [IO.File]::OpenRead($modelPath)
        try {
          $mag = New-Object byte[] 4
          [void]$fs.Read($mag, 0, 4)
        } finally { $fs.Close() }
        $magStr = [Text.Encoding]::ASCII.GetString($mag)
        if ($magStr -ne 'GGUF') {
          Remove-Item -Force $modelPath -ErrorAction SilentlyContinue
          FailAi "Downloaded model is not a GGUF file (magic='$magStr')."
        } else {
          $need = [long]$STAGE_OFFSET + 4096 + (Get-Item $modelPath).Length + 512
          $need += (Get-Item $stageServerPath).Length + 512
          if ($target.Size -lt $need) {
            FailAi ("Stick too small to stage the AI (need ~{0:N1} GB)." -f ($need / 1GB))
          } else {
            $serverPath = $stageServerPath
            $stageAI = $true
            Good ("AI ready - model {0:N0} MB + runtime will stage." -f ((Get-Item $modelPath).Length / 1MB))
          }
        }
      }
    } catch {
      FailAi "Could not prepare the AI to stage: $($_.Exception.Message)"
    }
    if (-not $stageAI) {
      FailAi 'AI staging was not prepared (unexpected).'
    }
  } else {
    Say 'NoModel: skipping AI sidecar (target must already have local AI for Assistant).'
  }
} elseif ($mode -eq 'iso_only') {
  if ($requireAI -and $probe.AiMatch) {
    Good 'Keeping existing AI sidecar on the stick (sizes match local files).'
  } elseif ($requireAI -and $probe.AiPresent) {
    Say 'AI sidecar present; ISO-only mode leaves it as-is.'
  } elseif ($requireAI) {
    Bad 'No usable AI sidecar on this stick and mode is ISO-only.'
    Bad 'Re-run without special flags for a full write, or use Stage-FoundationAI.ps1 after.'
  } else {
    Say 'NoModel: ISO-only write (no AI staging).'
  }
}

function Write-RawFileSectorPadded($dst, $path) {
  $f = [IO.File]::OpenRead($path)
  try {
    $buf = New-Object byte[] (4MB)
    while (($r = $f.Read($buf, 0, $buf.Length)) -gt 0) {
      if ($r % 512 -ne 0) {
        $pad = 512 * [math]::Ceiling($r / 512.0)
        [Array]::Clear($buf, $r, $pad - $r); $r = $pad
      }
      $dst.Write($buf, 0, $r)
    }
  } finally { $f.Close() }
}

function Lock-StickVolumes([int]$DiskNumber) {
  $handles = @()
  $volPaths = @(Get-Partition -DiskNumber $DiskNumber -ErrorAction SilentlyContinue |
                ForEach-Object { $_.AccessPaths } |
                Where-Object { $_ -like '\\?\Volume*' } |
                ForEach-Object { $_.TrimEnd('\') } | Sort-Object -Unique)
  foreach ($vp in $volPaths) {
    try {
      $vh = [RawDisk]::Open($vp, $true)
      [RawDisk]::Fsctl($vh, [RawDisk]::FSCTL_LOCK_VOLUME)
      [RawDisk]::Fsctl($vh, [RawDisk]::FSCTL_DISMOUNT_VOLUME)
      $handles += $vh
    } catch {
      # Best-effort on in-place modes; full mode fails hard if lock needed later
      Say "Could not lock volume $vp : $($_.Exception.Message)"
    }
  }
  return $handles
}

function Write-AiSidecarToDisk($dst) {
  # Raw-offset sidecar: [4 KB header][model][server] at STAGE_OFFSET
  Say "Staging Frank's local AI into the stick's free space..."
  $modelOff  = [long]$STAGE_OFFSET + 4096
  $modelSize = (Get-Item $modelPath).Length
  $srvSize   = if (Test-Path $serverPath) { (Get-Item $serverPath).Length } else { 0 }
  $srvOff    = $modelOff + [long]([math]::Ceiling($modelSize / 512.0) * 512)
  $hdrText   = "FOUNDATIONAI2`nmodel_offset=$modelOff`nmodel_size=$modelSize`nserver_offset=$srvOff`nserver_size=$srvSize`n"
  $hdr = New-Object byte[] 4096
  [Array]::Copy([Text.Encoding]::ASCII.GetBytes($hdrText), $hdr, [Text.Encoding]::ASCII.GetByteCount($hdrText))
  $null = $dst.Seek([long]$STAGE_OFFSET, [IO.SeekOrigin]::Begin)
  $dst.Write($hdr, 0, 4096)
  Write-RawFileSectorPadded $dst $modelPath
  if ($srvSize -gt 0) {
    $null = $dst.Seek($srvOff, [IO.SeekOrigin]::Begin)
    Write-RawFileSectorPadded $dst $serverPath
  }
  Good 'AI model + runtime staged onto the stick.'
}

function Write-IsoStream($dst, [string]$IsoPath, [long]$IsoSize, [string]$activity) {
  $src = [IO.File]::OpenRead($IsoPath)
  try {
    # First chunk (MBR) last — avoids Windows automount mid-stream.
    $buf = New-Object byte[] (4MB)
    $firstChunk = $null
    $firstLen = 0
    $done = [long]0
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while (($read = $src.Read($buf, 0, $buf.Length)) -gt 0) {
      if ($read % 512 -ne 0) {
        $padded = 512 * [math]::Ceiling($read / 512.0)
        [Array]::Clear($buf, $read, $padded - $read)
        $read = $padded
      }
      if ($null -eq $firstChunk) {
        $firstChunk = $buf.Clone()
        $firstLen = $read
        $null = $dst.Seek($read, [IO.SeekOrigin]::Begin)
      } else {
        $dst.Write($buf, 0, $read)
      }
      $done += $read
      $pct = [int](100 * $done / $IsoSize)
      $mbs = if ($sw.Elapsed.TotalSeconds -gt 0) { $done / 1MB / $sw.Elapsed.TotalSeconds } else { 0 }
      Write-Progress -Activity $activity `
        -Status ("{0:N0} / {1:N0} MB  ({2:N1} MB/s)" -f ($done / 1MB), ($IsoSize / 1MB), $mbs) `
        -PercentComplete ([math]::Min($pct, 100))
    }
    return @{ FirstChunk = $firstChunk; FirstLen = $firstLen }
  } finally { $src.Close() }
}

function Test-IsoHead([int]$DiskNumber, [string]$IsoPath) {
  $check = New-Object IO.FileStream("\\.\PHYSICALDRIVE$DiskNumber",
            [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
  $srcCheck = [IO.File]::OpenRead($IsoPath)
  try {
    $a = New-Object byte[] (1MB); $b = New-Object byte[] (1MB)
    [void]$check.Read($a, 0, $a.Length)
    [void]$srcCheck.Read($b, 0, $b.Length)
    return [Linq.Enumerable]::SequenceEqual($a, $b)
  } finally {
    $check.Close()
    $srcCheck.Close()
  }
}

function Test-AiSidecarOnDisk([int]$DiskNumber) {
  $check = New-Object IO.FileStream("\\.\PHYSICALDRIVE$DiskNumber",
            [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
  try {
    $null = $check.Seek([long]$STAGE_OFFSET, [IO.SeekOrigin]::Begin)
    $hdrBuf = New-Object byte[] 4096
    $got = $check.Read($hdrBuf, 0, 4096)
    if ($got -lt 64) { return $false }
    $hdrEnd = [Array]::IndexOf($hdrBuf, [byte]0)
    if ($hdrEnd -lt 0) { $hdrEnd = $hdrBuf.Length }
    $hdrTextRb = [Text.Encoding]::ASCII.GetString($hdrBuf, 0, $hdrEnd)
    if (-not $hdrTextRb.StartsWith('FOUNDATIONAI2')) { return $false }
    $moRb = 0L; $msRb = 0L; $soRb = 0L; $ssRb = 0L
    foreach ($ln in ($hdrTextRb -split "`n")) {
      $t = $ln.Trim()
      if ($t.StartsWith('model_offset=')) { [void][long]::TryParse($t.Substring(13), [ref]$moRb) }
      elseif ($t.StartsWith('model_size=')) { [void][long]::TryParse($t.Substring(11), [ref]$msRb) }
      elseif ($t.StartsWith('server_offset=')) { [void][long]::TryParse($t.Substring(14), [ref]$soRb) }
      elseif ($t.StartsWith('server_size=')) { [void][long]::TryParse($t.Substring(12), [ref]$ssRb) }
    }
    if ($moRb -lt ([long]$STAGE_OFFSET + 4096) -or $msRb -le 0 -or $ssRb -le 0) { return $false }
    $null = $check.Seek($moRb, [IO.SeekOrigin]::Begin)
    $gguf = New-Object byte[] 4
    if ($check.Read($gguf, 0, 4) -lt 4 -or [Text.Encoding]::ASCII.GetString($gguf) -ne 'GGUF') { return $false }
    $null = $check.Seek($soRb, [IO.SeekOrigin]::Begin)
    $srvMag = New-Object byte[] 2
    if ($check.Read($srvMag, 0, 2) -lt 2 -or $srvMag[0] -ne 0x1f -or $srvMag[1] -ne 0x8b) { return $false }
    Good ("AI sidecar verified (model {0:N0} MB + runtime {1:N0} KB)." -f ($msRb / 1MB), ($ssRb / 1KB))
    return $true
  } finally { $check.Close() }
}

$n = $target.Number
$phys = "\\.\PHYSICALDRIVE$n"

try {
  if ($mode -eq 'ai_only') {
    Say 'Writing AI sidecar only (ISO untouched)...'
    try { Set-Disk -Number $n -IsReadOnly $false -ErrorAction SilentlyContinue } catch {}
    $volHandles = Lock-StickVolumes $n
    $dst = New-Object IO.FileStream($phys, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
    try {
      Write-AiSidecarToDisk $dst
      Say 'Flushing AI to the stick (do NOT unplug)...'
      $dst.Flush($true)
    } finally {
      $dst.Close()
      foreach ($h in $volHandles) { $h.Close() }
    }
    Say 'Verifying AI sidecar...'
    if (-not (Test-AiSidecarOnDisk $n)) {
      Bad 'AI sidecar verification FAILED.'
      Read-Host 'Press ENTER to close'
      exit 1
    }
  } else {
    # full or iso_only — write ISO; full also cleans + stages AI
    try { Set-Disk -Number $n -IsReadOnly $false -ErrorAction SilentlyContinue } catch {}
    if ($mode -eq 'full') {
      Say 'Preparing the stick (removing its old partitions)...'
      $null = @"
select disk $n
clean
rescan
exit
"@ | diskpart
      if ($LASTEXITCODE -ne 0) {
        Bad "Windows (diskpart) could not clean the stick (exit code $LASTEXITCODE)."
        Bad 'Unplug it, plug it back in, and run this again.'
        Read-Host 'Press ENTER to close'
        exit 1
      }
      Start-Sleep -Seconds 2
    } else {
      Say 'In-place ISO rewrite (no diskpart clean — AI region preserved)...'
    }

    $volHandles = Lock-StickVolumes $n
    Say 'Writing the installer (this takes a few minutes - do not unplug)...'
    $dst = New-Object IO.FileStream(([RawDisk]::Open($phys, $true)), [IO.FileAccess]::Write)
    try {
      $parts = Write-IsoStream $dst $IsoPath $IsoSize 'Writing installer to USB'
      Write-Progress -Activity 'Writing installer to USB' `
        -Status 'Finalizing - do NOT unplug the stick!' -PercentComplete 100
      Say 'Data written. Finalizing the stick - do NOT unplug it yet...'
      # Stage AI BEFORE MBR on full mode so automount cannot block STAGE_OFFSET writes.
      if ($stageAI) {
        Write-AiSidecarToDisk $dst
      }
      $null = $dst.Seek(0, [IO.SeekOrigin]::Begin)
      $dst.Write($parts.FirstChunk, 0, $parts.FirstLen)
      Say 'Flushing everything to the stick (can take a minute, still do NOT unplug)...'
      $dst.Flush($true)
    } catch [System.UnauthorizedAccessException] {
      Bad 'Windows refused the raw write even with the stick''s volumes locked.'
      Bad 'Usual causes: antivirus / Windows "Controlled folder access" blocking'
      Bad 'disk writes, or something reopened the stick mid-write. Try excluding'
      Bad 'PowerShell in your AV for a moment, or write the same ISO with Rufus'
      Bad 'or balenaEtcher instead - the ISO itself is fine.'
      Bad 'NOTE: Rufus/Etcher/Ventoy write the ISO ONLY — they do NOT stage the'
      Bad 'local AI sidecar. Sticks made that way leave Hub ASSISTANT as:'
      Bad '  idle: missing: runtime model'
      Bad 'Re-run THIS creator (without -NoModel) for offline AI on the target.'
      Read-Host 'Press ENTER to close'
      exit 1
    } finally {
      $dst.Close()
      foreach ($h in $volHandles) { $h.Close() }
      Write-Progress -Activity 'Writing installer to USB' -Completed
    }

    Say 'Verifying (almost done - keep the stick plugged in)...'
    if (Test-IsoHead $n $IsoPath) {
      Good 'Verified - the stick reads back correctly.'
    } else {
      Bad 'Verification FAILED - the stick did not read back what was written.'
      Bad 'Try a different USB stick or port and run this again.'
      Read-Host 'Press ENTER to close'
      exit 1
    }
    if ($stageAI) {
      if (-not (Test-AiSidecarOnDisk $n)) {
        Bad 'AI sidecar verification FAILED - FOUNDATIONAI2 / GGUF / runtime check failed.'
        Bad 'The ISO is fine, but the local AI was not staged. Re-run this creator.'
        Read-Host 'Press ENTER to close'
        exit 1
      }
    } elseif ($mode -eq 'iso_only' -and $probe.AiPresent) {
      if (Test-AiSidecarOnDisk $n) {
        Good 'Existing AI sidecar still intact after ISO-only rewrite.'
      } else {
        Bad 'WARNING: AI sidecar no longer verifies after ISO rewrite.'
        Bad 'Re-run with default options (full) or Stage-FoundationAI.ps1.'
      }
    }
  }
} catch {
  Bad "Write failed: $($_.Exception.Message)"
  Read-Host 'Press ENTER to close'
  exit 1
}

# ── done ─────────────────────────────────────────────────────────────────────
Write-Host ''
Good 'All done - it is now safe to unplug the stick.'
Write-Host ''
if ($mode -eq 'ai_only') { Good 'Mode used: AI-ONLY (ISO kept).' }
elseif ($mode -eq 'iso_only') { Good 'Mode used: ISO-ONLY (AI sidecar preserved when present).' }
else { Good 'Mode used: FULL wipe + write.' }
Good 'Your Foundation TerminalOS install USB is ready. Next steps:'
Write-Host ''
Write-Host '  1. Unplug the stick. (If Windows offers to "format" it, say no -'
Write-Host '     Windows just cannot read it, which is expected.)'
Write-Host '  2. Plug it into the computer you want to turn into Foundation'
Write-Host '     TerminalOS, and turn that computer on while tapping its boot-menu'
Write-Host '     key (usually F12, F11, Esc, F2, or Del - it flashes on screen).'
Write-Host '  3. Pick the USB stick from the boot menu.'
Write-Host '  4. Follow the on-screen installer. UPDATE refreshes an existing'
Write-Host '     install; INSTALL / ERASE wipes a disk for a fresh machine.'
Write-Host ''
Write-Host '  WARNING: the installer turns that computer into a locked-down,'
Write-Host '  no-shell kiosk with an always-on overseer. Not for a machine you'
Write-Host '  still need as a normal PC.'
Write-Host ''
Write-Host 'This window stays open so you can read the steps - close it whenever'
Write-Host 'you are ready.'
