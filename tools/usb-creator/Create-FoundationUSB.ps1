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
} finally {
  $check.Close()
  $srcCheck.Close()
}

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
