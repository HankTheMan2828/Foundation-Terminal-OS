<#
Stage-FoundationAI.ps1 — write ONLY Frank's local AI sidecar onto a stick
that already has the Foundation TerminalOS ISO (no full re-image).

Use this when UPDATE says "offline install and no staged AI runtime/model"
but the OS ISO on the stick is fine. Admin required.

  powershell -ExecutionPolicy Bypass -File .\Stage-FoundationAI.ps1

Needs model.gguf + ai-runtime.tar.gz next to this script (same as the full
USB creator). Verifies FOUNDATIONAI2 + GGUF + gzip after write.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$STAGE_OFFSET = [long]2147483648  # 2 GiB

function Say([string]$m)  { Write-Host "[*] $m" -ForegroundColor Yellow }
function Good([string]$m) { Write-Host "[+] $m" -ForegroundColor Green }
function Bad([string]$m)  { Write-Host "[!] $m" -ForegroundColor Red }

$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Say 'Administrator rights required — re-launching elevated...'
  Start-Process powershell -Verb RunAs -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit',
    '-File', ('"{0}"' -f $PSCommandPath))
  exit 0
}

$here = Split-Path -Parent $PSCommandPath
$modelPath = Join-Path $here 'model.gguf'
$runtimePath = Join-Path $here 'ai-runtime.tar.gz'

function Test-GzipFile([string]$path) {
  if (-not (Test-Path $path)) { return $false }
  $fs = [IO.File]::OpenRead($path)
  try {
    $b = New-Object byte[] 2
    if ($fs.Read($b, 0, 2) -lt 2) { return $false }
    return ($b[0] -eq 0x1f -and $b[1] -eq 0x8b)
  } finally { $fs.Close() }
}

if (-not (Test-Path $modelPath)) {
  Bad "Missing model.gguf next to this script: $modelPath"
  Bad 'Run Create-FoundationUSB.ps1 once (it downloads), or copy model.gguf here.'
  Read-Host 'Press ENTER to close'; exit 1
}
if (-not (Test-GzipFile $runtimePath)) {
  Bad "Missing ai-runtime.tar.gz (gzip) next to this script: $runtimePath"
  Bad 'Download foundation-ai-runtime-x86_64.tar.gz from the release and rename it.'
  Read-Host 'Press ENTER to close'; exit 1
}
$fs = [IO.File]::OpenRead($modelPath)
try {
  $mag = New-Object byte[] 4
  [void]$fs.Read($mag, 0, 4)
} finally { $fs.Close() }
if ([Text.Encoding]::ASCII.GetString($mag) -ne 'GGUF') {
  Bad 'model.gguf does not start with GGUF magic — re-download the model.'
  Read-Host 'Press ENTER to close'; exit 1
}

$modelSize = [long](Get-Item $modelPath).Length
$srvSize   = [long](Get-Item $runtimePath).Length
$needEnd   = $STAGE_OFFSET + 4096 + $modelSize + 512 + $srvSize + 512

$usb = @(Get-Disk | Where-Object { $_.BusType -eq 'USB' -and -not $_.IsBoot -and -not $_.IsSystem })
if ($usb.Count -eq 0) {
  Bad 'No USB stick found.'
  Read-Host 'Press ENTER to close'; exit 1
}

Say 'USB sticks (internal drives are never listed):'
for ($i = 0; $i -lt $usb.Count; $i++) {
  $d = $usb[$i]
  Write-Host ("  {0}) {1}  -  {2:N1} GB" -f ($i + 1), $d.FriendlyName.Trim(), ($d.Size / 1GB))
}
$target = $null
while (-not $target) {
  $pick = Read-Host ('> write AI sidecar to stick # (1-{0}, or q to quit)' -f $usb.Count)
  if ($pick -eq 'q') { exit 0 }
  $n = 0
  if ([int]::TryParse($pick, [ref]$n) -and $n -ge 1 -and $n -le $usb.Count) {
    $target = $usb[$n - 1]
  }
}
if ($target.Size -lt $needEnd) {
  Bad ("Stick too small for AI at 2 GiB offset (need ~{0:N1} GB)." -f ($needEnd / 1GB))
  Read-Host 'Press ENTER to close'; exit 1
}

Write-Host ''
Bad ("This will write ~{0:N0} MB of AI data at the 2 GiB mark on '{1}'." -f `
     (($modelSize + $srvSize) / 1MB), $target.FriendlyName.Trim())
Bad 'It does NOT wipe the ISO — only the AI sidecar region past 2 GiB.'
$confirm = Read-Host '> type STAGE (all caps) to continue'
if ($confirm -cne 'STAGE') {
  Say 'Aborted.'
  Read-Host 'Press ENTER to close'; exit 0
}

if (-not ([System.Management.Automation.PSTypeName]'RawDiskAI').Type) {
  Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

public static class RawDiskAI {
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  static extern SafeFileHandle CreateFile(string name, uint access, uint share,
    IntPtr sec, uint disposition, uint flags, IntPtr template);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern bool DeviceIoControl(SafeFileHandle h, uint code,
    IntPtr inBuf, uint inSize, IntPtr outBuf, uint outSize,
    out uint returned, IntPtr overlapped);

  const uint GENERIC_READ  = 0x80000000;
  const uint GENERIC_WRITE = 0x40000000;
  const uint SHARE_RW      = 0x3;
  const uint OPEN_EXISTING = 3;
  public const uint FSCTL_LOCK_VOLUME     = 0x00090018;
  public const uint FSCTL_DISMOUNT_VOLUME = 0x00090020;

  public static SafeFileHandle Open(string path, bool write) {
    uint access = write ? (GENERIC_READ | GENERIC_WRITE) : GENERIC_READ;
    var h = CreateFile(path, access, SHARE_RW, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero);
    if (h.IsInvalid)
      throw new IOException(string.Format("CreateFile('{0}') failed ({1})",
        path, Marshal.GetLastWin32Error()));
    return h;
  }
  public static void Fsctl(SafeFileHandle h, uint code) {
    uint ret;
    if (!DeviceIoControl(h, code, IntPtr.Zero, 0, IntPtr.Zero, 0, out ret, IntPtr.Zero))
      throw new IOException(string.Format("DeviceIoControl(0x{0:X}) failed ({1})",
        code, Marshal.GetLastWin32Error()));
  }
}
'@
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

$n = $target.Number
# Lock volumes so raw writes are not blocked
$volHandles = @()
$volPaths = @(Get-Partition -DiskNumber $n -ErrorAction SilentlyContinue |
              ForEach-Object { $_.AccessPaths } |
              Where-Object { $_ -like '\\?\Volume*' } |
              ForEach-Object { $_.TrimEnd('\') } | Sort-Object -Unique)
foreach ($vp in $volPaths) {
  try {
    $vh = [RawDiskAI]::Open($vp, $true)
    [RawDiskAI]::Fsctl($vh, [RawDiskAI]::FSCTL_LOCK_VOLUME)
    [RawDiskAI]::Fsctl($vh, [RawDiskAI]::FSCTL_DISMOUNT_VOLUME)
    $volHandles += $vh
  } catch {
    Say "Could not lock $vp (continuing): $($_.Exception.Message)"
  }
}

$modelOff = $STAGE_OFFSET + 4096
$srvOff   = $modelOff + [long]([math]::Ceiling($modelSize / 512.0) * 512)
$hdrText  = "FOUNDATIONAI2`nmodel_offset=$modelOff`nmodel_size=$modelSize`nserver_offset=$srvOff`nserver_size=$srvSize`n"
$hdr = New-Object byte[] 4096
[Array]::Copy([Text.Encoding]::ASCII.GetBytes($hdrText), $hdr, [Text.Encoding]::ASCII.GetByteCount($hdrText))

$phys = "\\.\PHYSICALDRIVE$n"
Say "Writing AI sidecar to $phys at offset $STAGE_OFFSET..."
$dst = New-Object IO.FileStream($phys, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
try {
  $null = $dst.Seek($STAGE_OFFSET, [IO.SeekOrigin]::Begin)
  $dst.Write($hdr, 0, 4096)
  Write-RawFileSectorPadded $dst $modelPath
  $null = $dst.Seek($srvOff, [IO.SeekOrigin]::Begin)
  Write-RawFileSectorPadded $dst $runtimePath
  $dst.Flush($true)
} finally {
  $dst.Close()
  foreach ($h in $volHandles) { $h.Close() }
}

# Verify
Say 'Verifying AI sidecar...'
$check = New-Object IO.FileStream($phys, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
try {
  $null = $check.Seek($STAGE_OFFSET, [IO.SeekOrigin]::Begin)
  $hdrBuf = New-Object byte[] 4096
  [void]$check.Read($hdrBuf, 0, 4096)
  $hdrEnd = [Array]::IndexOf($hdrBuf, [byte]0)
  if ($hdrEnd -lt 0) { $hdrEnd = $hdrBuf.Length }
  $hdrTextRb = [Text.Encoding]::ASCII.GetString($hdrBuf, 0, $hdrEnd)
  if (-not $hdrTextRb.StartsWith('FOUNDATIONAI2')) {
    Bad 'VERIFY FAILED: FOUNDATIONAI2 header missing.'
    Read-Host 'Press ENTER to close'; exit 1
  }
  $null = $check.Seek($modelOff, [IO.SeekOrigin]::Begin)
  $gguf = New-Object byte[] 4
  [void]$check.Read($gguf, 0, 4)
  if ([Text.Encoding]::ASCII.GetString($gguf) -ne 'GGUF') {
    Bad 'VERIFY FAILED: GGUF magic missing at model_offset.'
    Read-Host 'Press ENTER to close'; exit 1
  }
  $null = $check.Seek($srvOff, [IO.SeekOrigin]::Begin)
  $gz = New-Object byte[] 2
  [void]$check.Read($gz, 0, 2)
  if ($gz[0] -ne 0x1f -or $gz[1] -ne 0x8b) {
    Bad 'VERIFY FAILED: runtime is not gzip at server_offset.'
    Read-Host 'Press ENTER to close'; exit 1
  }
} finally { $check.Close() }

Good 'AI sidecar verified on the stick (FOUNDATIONAI2 + GGUF + gzip runtime).'
Good 'Next: boot the mini PC from this stick → UPDATE → type UPDATE.'
Good 'You want the line: Local AI READY'
Read-Host 'Press ENTER to close'
