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

Safety: it only ever offers USB-bus disks (never your internal drive), and
the write is gated behind typing ERASE in full — same gate as the OS
installer itself.
#>
[CmdletBinding()]
param(
  # Path to the installer ISO. If omitted, the script looks next to itself,
  # then in the repo's image/out/, then offers to download the latest release.
  [string]$Iso,
  # Skip staging Frank's local AI (model + llama-server) onto the stick.
  # Use only for faster stick refreshes when the target ALREADY has working
  # local AI. Fresh installs need full staging (default) for offline Assistant.
  [switch]$NoModel
)

$ErrorActionPreference = 'Stop'
$GitHubRepo = 'HankTheMan2828/Foundation-Terminal-OS'

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
  Write-Host '  This writes the Foundation TerminalOS installer onto a USB stick.'
  Write-Host '  Everything currently on that stick will be erased.'
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
$IsoSize = (Get-Item $IsoPath).Length
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

Write-Host ''
Bad ("EVERYTHING on '{0}' ({1:N1} GB) will be destroyed." -f $target.FriendlyName.Trim(), ($target.Size / 1GB))
$confirm = Read-Host '> type ERASE (all caps) to continue, anything else aborts'
if ($confirm -cne 'ERASE') {
  Say 'Aborted - nothing was touched.'
  Read-Host 'Press ENTER to close'
  exit 0
}

# ── 2b. prepare Frank's local AI to stage (downloaded on THIS online PC) ──────
# The installed mini PCs have no network, so the model + server binary must ride
# on the stick. We fetch them here (this PC is online) and stage them into the
# stick's free space during the write below.
#
# Default: AI staging is REQUIRED so fresh offline installs get a working Hub
# Assistant + Frank sensor. Fail before writing if prep fails. Skip only with
# -NoModel (faster refreshes when the target already has local AI).
$stageAI = $false
$requireAI = -not ($NoModel -or $env:FOUNDATION_NO_MODEL -eq '1')
# Raw-offset where the AI sidecar header is written (and where foundation-install
# reads it back). MUST be defined before the size checks below — a use-before-def
# left it $null, and `$IsoSize -ge $null` coerces to `-ge 0` (always true), so the
# creator silently skipped AI staging on every run (2026-07-07). 2 GiB, not 3:
# it sits just past a sub-2 GB ISO (our size target) and leaves room for the
# ~1.2 GB AI on a 3.8 GB stick. Keep in sync with create-foundation-usb.sh and
# foundation-install (off=…). Contract: the ISO must stay under 2 GiB.
$STAGE_OFFSET = 2147483648   # 2 GiB
$modelPath   = Join-Path (Split-Path -Parent $PSCommandPath) 'model.gguf'
# Runtime tarball (llama-server + libllama/libggml). Bare ELF alone cannot start.
$runtimePath = Join-Path (Split-Path -Parent $PSCommandPath) 'ai-runtime.tar.gz'
$serverPath  = Join-Path (Split-Path -Parent $PSCommandPath) 'llama-server'  # legacy bare ELF
function FailAi([string]$m) {
  Bad $m
  if ($requireAI) {
    Bad 'Local AI is required for a full offline install (Hub ASSISTANT + Frank).'
    Bad 'Fix the problem above, or pass -NoModel only if the target already has AI.'
    Read-Host 'Press ENTER to close'
    exit 1
  }
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
    # Prefer the runtime tarball (binary + shared libs). Bare ELF is not enough.
    if (-not (Test-GzipFile $runtimePath)) {
      $srvUrl = $env:FOUNDATION_AI_SERVER_URL
      if (-not $srvUrl) {
        try {
          [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
          $rels = @(Invoke-RestMethod -UseBasicParsing "https://api.github.com/repos/$GitHubRepo/releases")
          $assets = @($rels | ForEach-Object { $_.assets })
          # Prefer runtime tarball names over the bare ELF asset.
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
    # Require the gzip runtime tarball (binary + libllama + libggml). A bare
    # ELF alone cannot start on the target — refuse it even if present from an
    # older download.
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
      # Quick GGUF magic check so we don't stage a truncated HTML error page.
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
          $serverPath = $stageServerPath   # used in the write section below
          $stageAI = $true
          $kind = if (Test-GzipFile $serverPath) { 'runtime tarball' } else { 'bare ELF (may lack libs)' }
          Good ("AI ready - model {0:N0} MB + {1} will stage with the OS." -f ((Get-Item $modelPath).Length / 1MB), $kind)
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

# ── 3. write the image ───────────────────────────────────────────────────────
# Windows refuses raw writes to a disk while any volume on it counts as
# mounted. The reliable sequence (same as Rufus/Win32DiskImager) is: lock and
# dismount every volume on the stick, HOLD those locks, and only then stream
# to \\.\PHYSICALDRIVEn.
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

# ── Frank local-AI staging (raw-offset sidecar) ──────────────────────────────
# Windows won't surface a volume for a 2nd partition on a REMOVABLE stick that
# was raw-written with a hybrid ISO (both the Storage cmdlets and diskpart fail),
# so we do NOT partition. Instead we write [4 KB header][model][server] as raw
# bytes at a fixed offset in the stick's free space PAST the ISO, and the Linux
# installer reads them straight off the raw device. Contract shared with
# create-foundation-usb.sh and foundation-install (docs/FRANK-LOCAL-AI.md).
# ($STAGE_OFFSET is defined up in section 2b — it has to exist before the size
# checks there. 2 GiB; see the note at its definition.)

# Stream a file to the raw disk handle, zero-padding the final chunk up to a
# 512-byte sector (raw disk writes must be whole sectors). The header records
# exact byte sizes, so the padding is invisible to the reader.
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

$n = $target.Number
Say 'Preparing the stick (removing its old partitions)...'
try { Set-Disk -Number $n -IsReadOnly $false -ErrorAction SilentlyContinue } catch {}
# diskpart clean wipes the partition table, so no partition on the stick can
# have a volume object Windows would protect against raw writes.
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
$volHandles = @()
$volPaths = @(Get-Partition -DiskNumber $n -ErrorAction SilentlyContinue |
              ForEach-Object { $_.AccessPaths } |
              Where-Object { $_ -like '\\?\Volume*' } |
              ForEach-Object { $_.TrimEnd('\') } | Sort-Object -Unique)
foreach ($vp in $volPaths) {
  try {
    $vh = [RawDisk]::Open($vp, $true)
    [RawDisk]::Fsctl($vh, [RawDisk]::FSCTL_LOCK_VOLUME)
    [RawDisk]::Fsctl($vh, [RawDisk]::FSCTL_DISMOUNT_VOLUME)
    $volHandles += $vh
  } catch {
    Bad "Could not lock a volume on the stick ($vp): $($_.Exception.Message)"
    Bad 'Close any Explorer window or program using the stick and run this again.'
    foreach ($h in $volHandles) { $h.Close() }
    Read-Host 'Press ENTER to close'
    exit 1
  }
}

Say 'Writing the installer (this takes a few minutes - do not unplug)...'
$src = [IO.File]::OpenRead($IsoPath)
$dst = New-Object IO.FileStream(([RawDisk]::Open("\\.\PHYSICALDRIVE$n", $true)),
        [IO.FileAccess]::Write)
try {
  # The image's first chunk holds the MBR/partition table. If it goes in
  # first, Windows spots the new partitions while we're still streaming,
  # mounts volumes over them, and denies every later write. So: skip the
  # first chunk, write the rest, then drop the first chunk in LAST — the
  # disk has no partition table (nothing to automount) until we're done.
  $buf = New-Object byte[] (4MB)
  $firstChunk = $null
  $firstLen = 0
  $done = [long]0
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while (($read = $src.Read($buf, 0, $buf.Length)) -gt 0) {
    if ($read % 512 -ne 0) {
      # raw disk writes must be whole sectors; zero-pad the final chunk
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
    Write-Progress -Activity 'Writing installer to USB' `
      -Status ("{0:N0} / {1:N0} MB  ({2:N1} MB/s)" -f ($done / 1MB), ($IsoSize / 1MB), $mbs) `
      -PercentComplete ([math]::Min($pct, 100))
  }
  # Data is streamed, but the job is NOT done: the boot record still has to
  # go in, and Windows' write cache has to be flushed all the way to the
  # stick — that flush alone can take a minute or more on a slow stick.
  Write-Progress -Activity 'Writing installer to USB' `
    -Status 'Finalizing - do NOT unplug the stick!' -PercentComplete 100
  Say 'Data written. Finalizing the stick - do NOT unplug it yet...'
  # Stage AI BEFORE writing the MBR/first chunk. Once the boot record lands,
  # Windows remounts ISO partitions and often blocks further raw seeks/writes
  # at STAGE_OFFSET — which silently left sticks without a usable AI payload.
  if ($stageAI) {
    # Raw-offset sidecar: [4 KB header][model][server] at STAGE_OFFSET, past the
    # ISO. The header records exact byte offsets/sizes; the Linux installer reads
    # them off the raw device. No partition, so Windows has nothing to refuse.
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
  # Boot record last — after AI sidecar — so Windows automount cannot block AI.
  $null = $dst.Seek(0, [IO.SeekOrigin]::Begin)
  $dst.Write($firstChunk, 0, $firstLen)
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
  $src.Close()
  foreach ($h in $volHandles) { $h.Close() }
  Write-Progress -Activity 'Writing installer to USB' -Completed
}

# quick read-back sanity check of the first megabyte
Say 'Verifying (almost done - keep the stick plugged in)...'
$check = New-Object IO.FileStream("\\.\PHYSICALDRIVE$n",
          [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
$srcCheck = [IO.File]::OpenRead($IsoPath)
try {
  $a = New-Object byte[] (1MB); $b = New-Object byte[] (1MB)
  [void]$check.Read($a, 0, $a.Length)
  [void]$srcCheck.Read($b, 0, $b.Length)
  if ([Linq.Enumerable]::SequenceEqual($a, $b)) {
    Good 'Verified - the stick reads back correctly.'
  } else {
    Bad 'Verification FAILED - the stick did not read back what was written.'
    Bad 'Try a different USB stick or port and run this again.'
    Read-Host 'Press ENTER to close'
    exit 1
  }
  # AI sidecar: confirm FOUNDATIONAI2 header + GGUF magic at model_offset.
  # Without this, a silent seek/write failure shipped sticks that left every
  # offline install as "idle: missing: runtime model".
  if ($stageAI) {
    $null = $check.Seek([long]$STAGE_OFFSET, [IO.SeekOrigin]::Begin)
    $hdrBuf = New-Object byte[] 4096
    $got = $check.Read($hdrBuf, 0, 4096)
    if ($got -lt 64) {
      Bad 'AI sidecar verification FAILED - could not read header at 2 GiB offset.'
      Read-Host 'Press ENTER to close'
      exit 1
    }
    $hdrEnd = [Array]::IndexOf($hdrBuf, [byte]0)
    if ($hdrEnd -lt 0) { $hdrEnd = $hdrBuf.Length }
    $hdrTextRb = [Text.Encoding]::ASCII.GetString($hdrBuf, 0, $hdrEnd)
    if (-not $hdrTextRb.StartsWith('FOUNDATIONAI2')) {
      Bad 'AI sidecar verification FAILED - FOUNDATIONAI2 header missing after write.'
      Bad 'The ISO is fine, but the local AI was not staged. Re-run this creator.'
      Read-Host 'Press ENTER to close'
      exit 1
    }
    $moRb = 0L; $msRb = 0L; $soRb = 0L; $ssRb = 0L
    foreach ($ln in ($hdrTextRb -split "`n")) {
      $t = $ln.Trim()
      if ($t.StartsWith('model_offset=')) { [void][long]::TryParse($t.Substring(13), [ref]$moRb) }
      elseif ($t.StartsWith('model_size=')) { [void][long]::TryParse($t.Substring(11), [ref]$msRb) }
      elseif ($t.StartsWith('server_offset=')) { [void][long]::TryParse($t.Substring(14), [ref]$soRb) }
      elseif ($t.StartsWith('server_size=')) { [void][long]::TryParse($t.Substring(12), [ref]$ssRb) }
    }
    if ($moRb -lt ([long]$STAGE_OFFSET + 4096) -or $msRb -le 0 -or $ssRb -le 0) {
      Bad ("AI sidecar verification FAILED - bad header fields (mo={0} ms={1} ss={2})." -f $moRb, $msRb, $ssRb)
      Read-Host 'Press ENTER to close'
      exit 1
    }
    $null = $check.Seek($moRb, [IO.SeekOrigin]::Begin)
    $gguf = New-Object byte[] 4
    if ($check.Read($gguf, 0, 4) -lt 4 -or [Text.Encoding]::ASCII.GetString($gguf) -ne 'GGUF') {
      Bad 'AI sidecar verification FAILED - model GGUF magic not at model_offset.'
      Read-Host 'Press ENTER to close'
      exit 1
    }
    $null = $check.Seek($soRb, [IO.SeekOrigin]::Begin)
    $srvMag = New-Object byte[] 2
    if ($check.Read($srvMag, 0, 2) -lt 2 -or $srvMag[0] -ne 0x1f -or $srvMag[1] -ne 0x8b) {
      Bad 'AI sidecar verification FAILED - runtime is not a gzip tarball at server_offset.'
      Read-Host 'Press ENTER to close'
      exit 1
    }
    Good ("AI sidecar verified (model {0:N0} MB + runtime {1:N0} KB)." -f ($msRb / 1MB), ($ssRb / 1KB))
  }
} finally {
  $check.Close()
  $srcCheck.Close()
}

# (Frank's local AI was staged during the write above, as a raw-offset sidecar in
#  the stick's free space — see the STAGE_OFFSET section. No post-write step.)

# ── done ─────────────────────────────────────────────────────────────────────
Write-Host ''
Good 'All done - it is now safe to unplug the stick.'
Write-Host ''
Good 'Your Foundation TerminalOS install USB is ready. Next steps:'
Write-Host ''
Write-Host '  1. Unplug the stick. (If Windows offers to "format" it, say no -'
Write-Host '     Windows just cannot read it, which is expected.)'
Write-Host '  2. Plug it into the computer you want to turn into Foundation'
Write-Host '     TerminalOS, and turn that computer on while tapping its boot-menu'
Write-Host '     key (usually F12, F11, Esc, F2, or Del - it flashes on screen).'
Write-Host '  3. Pick the USB stick from the boot menu.'
Write-Host '  4. Follow the on-screen installer. The one destructive step - wiping'
Write-Host '     that computer''s disk - is gated behind typing ERASE, same as here.'
Write-Host ''
Write-Host '  WARNING: the installer turns that computer into a locked-down,'
Write-Host '  no-shell kiosk with an always-on overseer. Not for a machine you'
Write-Host '  still need as a normal PC.'
Write-Host ''
Write-Host 'This window stays open so you can read the steps - close it whenever'
Write-Host 'you are ready.'
