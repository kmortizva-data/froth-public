<#
    Put a Froth shortcut on the Desktop, pointing at the desktop-window launcher.

        powershell -ExecutionPolicy Bypass -File packaging\make_shortcut.ps1

    Re-run it after moving the project folder: a .lnk stores an absolute path, so moving
    the project silently breaks any shortcut made before the move. That is not
    hypothetical here - the whole project tree moved into Documents\04_Proyectos and
    stale paths were part of what broke.

    It targets "Froth App.bat" (own window, no browser, own taskbar icon) rather than
    "Froth.bat" (browser plus a console window), and gives it assets\froth.ico.
#>

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$target = Join-Path $root 'Froth App.bat'
$icon = Join-Path $root 'assets\froth.ico'

if (-not (Test-Path $target)) { throw "Launcher not found: $target" }
if (-not (Test-Path $icon)) { throw "Icon not found: $icon. Run packaging\make_icons.py first." }

# [Environment]::GetFolderPath resolves the REAL Desktop, which is not always
# $HOME\Desktop: OneDrive backup relocates it, and a Spanish Windows may show it as
# "Escritorio". Asking the system avoids guessing wrong and writing to a dead folder.
$desktop = [Environment]::GetFolderPath('Desktop')
$link = Join-Path $desktop 'Froth.lnk'

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($link)
$sc.TargetPath = $target
$sc.WorkingDirectory = $root
$sc.IconLocation = "$icon,0"
$sc.Description = 'Froth: map the literature of a scientific topic'
$sc.WindowStyle = 7                      # start minimised: the .bat window is plumbing
$sc.Save()

Write-Host "Shortcut created: $link"
Write-Host "  -> $target"
Write-Host "  icon: $icon"
