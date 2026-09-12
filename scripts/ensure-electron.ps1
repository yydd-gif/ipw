# Recover Electron binary using the npmmirror pin. Run from repo root in PowerShell.
$ErrorActionPreference = 'Stop'
$env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'
if (Test-Path .\node_modules\electron) {
  Remove-Item -Recurse -Force .\node_modules\electron
}
npm install electron --save-dev --force
Get-ChildItem .\node_modules\electron\dist\electron.exe
