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
  [string]$Iso
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
  Start-Process powershell -Verb RunAs -ArgumentList $argList
  exit 0
}

Show-Banner

# ── 1. find the ISO ──────────────────────────────────────────────────────────
function Find-Iso {
  param([string]$Given)
  if ($Given) {
    if (Test-Path $Given) { return (Resolve-Path $Given).Path }
    Bad "ISO not found at: $Given"
    exit 1
  }
  # next to this script (the "downloaded both files into one folder" case)
  $here = Split-Path -Parent $PSCommandPath
  $near = Get-ChildItem -Path $here -Filter 'foundation-terminalos-*.iso' -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($near) { return $near.FullName }
  # a repo checkout two levels up (tools/usb-creator/ -> repo root)
  $repoOut = Join-Path $here '..\..\image\out'
  if (Test-Path $repoOut) {
    $built = Get-ChildItem -Path $repoOut -Filter 'foundation-terminalos-*.iso' -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($built) { return $built.FullName }
  }
  # Downloads folder
  $dl = Join-Path $env:USERPROFILE 'Downloads'
  if (Test-Path $dl) {
    $down = Get-ChildItem -Path $dl -Filter 'foundation-terminalos-*.iso' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($down) { return $down.FullName }
  }
  # offer to download the latest release
  Say 'No installer ISO found on this computer.'
  $ans = Read-Host '> download the latest release now? [Y/n]'
  if ($ans -and $ans.Trim().ToLower().StartsWith('n')) {
    Bad 'Nothing to write. Put the ISO next to this script, or pass -Iso <path>.'
    exit 1
  }
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    # the release list (not /latest, which 404s on a repo with no releases yet)
    $rels = @(Invoke-RestMethod -UseBasicParsing "https://api.github.com/repos/$GitHubRepo/releases")
  } catch {
    Bad "Could not reach GitHub ($($_.Exception.Message))."
    Bad 'Check your internet connection and try again, or download the ISO'
    Bad 'manually from the Releases page and put it next to this script.'
    exit 1
  }
  $asset = $rels | ForEach-Object { $_.assets } |
           Where-Object { $_.name -like '*.iso' } | Select-Object -First 1
  if (-not $asset) {
    if ($rels.Count -eq 0) {
      Bad "The project hasn't published a release yet, so there is no ISO to download."
    } else {
      Bad "No release of $GitHubRepo has an ISO attached."
    }
    Bad 'A maintainer publishes one by pushing a TerminalOS-v* tag (CI builds and attaches'
    Bad 'the ISO automatically). Until then: build it with image/build-iso.sh'
    Bad 'and put the ISO next to this script, then run this again.'
    exit 1
  }
  $dest = Join-Path (Join-Path $env:USERPROFILE 'Downloads') $asset.name
  Say ("Downloading {0} ({1:N0} MB) to your Downloads folder..." -f $asset.name, ($asset.size / 1MB))
  try {
    Start-BitsTransfer -Source $asset.browser_download_url -Destination $dest `
      -DisplayName 'Foundation TerminalOS installer ISO'
  } catch {
    # BITS can be disabled; plain download works everywhere (just no progress bar)
    $old = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
    try { Invoke-WebRequest -UseBasicParsing $asset.browser_download_url -OutFile $dest }
    finally { $ProgressPreference = $old }
  }
  Good "Downloaded: $dest"
  return $dest
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

# ── 3. write the image ───────────────────────────────────────────────────────
$n = $target.Number
Say 'Preparing the stick...'
try { Set-Disk -Number $n -IsReadOnly $false -ErrorAction SilentlyContinue } catch {}
try { Clear-Disk -Number $n -RemoveData -RemoveOEM -Confirm:$false } catch {
  # a factory-blank / uninitialized stick has nothing to clear
}
# Offline keeps Windows from grabbing the new partitions mid-write.
try { Set-Disk -Number $n -IsOffline $true } catch {}

Say 'Writing the installer (this takes a few minutes - do not unplug)...'
$src = [IO.File]::OpenRead($IsoPath)
$dst = New-Object IO.FileStream("\\.\PHYSICALDRIVE$n",
        [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
  $buf = New-Object byte[] (4MB)
  $done = [long]0
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while (($read = $src.Read($buf, 0, $buf.Length)) -gt 0) {
    if ($read % 512 -ne 0) {
      # raw disk writes must be whole sectors; zero-pad the final chunk
      $padded = 512 * [math]::Ceiling($read / 512.0)
      [Array]::Clear($buf, $read, $padded - $read)
      $read = $padded
    }
    $dst.Write($buf, 0, $read)
    $done += $read
    $pct = [int](100 * $done / $IsoSize)
    $mbs = if ($sw.Elapsed.TotalSeconds -gt 0) { $done / 1MB / $sw.Elapsed.TotalSeconds } else { 0 }
    Write-Progress -Activity 'Writing installer to USB' `
      -Status ("{0:N0} / {1:N0} MB  ({2:N1} MB/s)" -f ($done / 1MB), ($IsoSize / 1MB), $mbs) `
      -PercentComplete ([math]::Min($pct, 100))
  }
  $dst.Flush($true)
} finally {
  $dst.Close()
  $src.Close()
  Write-Progress -Activity 'Writing installer to USB' -Completed
}

# quick read-back sanity check of the first megabyte
Say 'Verifying...'
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
} finally {
  $check.Close()
  $srcCheck.Close()
}

# ── done ─────────────────────────────────────────────────────────────────────
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
Read-Host 'Press ENTER to close'
