<#
    Leave ONE obvious thing to click in the project folder, and put everything else out of
    sight without moving it.

        powershell -ExecutionPolicy Bypass -File packaging\tidy_folder.ps1
        powershell -ExecutionPolicy Bypass -File packaging\tidy_folder.ps1 -Revert

    WHY HIDE INSTEAD OF MOVE. Batman opened the folder, counted thirty entries and could not
    tell which one starts the app. Moving the clutter into a subfolder would break more than
    it tidies: the launchers resolve their own directory with %~dp0, config.py derives every
    path from the repo root, sync_public.py finds the public snapshot as a sibling, and this
    project has already been broken twice by folders moving. The hidden attribute changes
    what Explorer DRAWS, not where anything lives, and -Revert undoes it in one command.

    ONE COST, MEASURED, SO NOBODY REDISCOVERS IT THE HARD WAY. Windows refuses to
    re-create an existing HIDDEN file, so anything that writes by truncating fails on one:
    Python's Path.write_text raises PermissionError. Appending (>>) and sed -i work, and
    sed -i quietly drops the attribute because it writes a new file. Git is fine. The fix
    when editing a hidden root file is one line - attrib -H <file> - and the hooks below
    put it back at the next commit, so the folder heals itself.

    WHY IT HAS TO BE RE-RUNNABLE. Measured 2026-08-29: git handles hidden files fine, but
    when it rewrites one (checkout, merge, pull) the file comes back VISIBLE. So the tidy is
    not a one-time act, and a hook re-runs this after commits, checkouts and merges.
#>
param([switch]$Revert)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

# The only things that stay visible. Everything else in the root is hidden.
$keepVisible = @('Abrir Froth.lnk', 'Mis cosas')

function Set-Hidden([string]$path, [bool]$hidden) {
    $item = Get-Item -LiteralPath $path -Force
    if ($hidden) { $item.Attributes = $item.Attributes -bor [IO.FileAttributes]::Hidden }
    else { $item.Attributes = $item.Attributes -band (-bnot [IO.FileAttributes]::Hidden) }
}

function New-Link([string]$link, [string]$target, [string]$icon) {
    if (-not (Test-Path -LiteralPath $target)) {
        Write-Host "  skipped (target missing): $target"
        return
    }
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($link)
    $sc.TargetPath = $target
    if (Test-Path -LiteralPath $target -PathType Container) {
        $sc.WorkingDirectory = $target
    } else {
        $sc.WorkingDirectory = Split-Path -Parent $target
    }
    if ($icon) { $sc.IconLocation = $icon }
    $sc.Save()
}

if ($Revert) {
    Get-ChildItem -LiteralPath $root -Force | ForEach-Object { Set-Hidden $_.FullName $false }
    Write-Host "Everything in the project root is visible again."
    Write-Host "  The two shortcuts were left in place; delete them by hand if you want them gone."
    exit 0
}

# --- 1. The one thing to click -------------------------------------------------------
# Targets "Froth App.bat" (own window, no browser), which is what he chose in phase 7.
# A .lnk can carry an icon; a .bat always draws as a console script. That is the whole
# reason this shortcut exists instead of just leaving the .bat visible.
$launcher = Join-Path $root 'Froth App.bat'
$icon = Join-Path $root 'assets\froth.ico'
if (-not (Test-Path -LiteralPath $launcher)) { throw "Launcher not found: $launcher" }
if (-not (Test-Path -LiteralPath $icon)) { throw "Icon not found: $icon. Run packaging\make_icons.py first." }

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut((Join-Path $root 'Abrir Froth.lnk'))
$sc.TargetPath = $launcher
$sc.WorkingDirectory = $root
$sc.IconLocation = "$icon,0"
$sc.Description = 'Abrir Froth'
$sc.WindowStyle = 7                      # minimised: the .bat console is plumbing
$sc.Save()
Write-Host "Created: Abrir Froth.lnk"

# --- 2. His own material, one click away ---------------------------------------------
# Shortcuts, never copies: a copy silently goes stale, and these PDFs get rebuilt.
# Pointing into a hidden folder is fine - hiding a folder removes it from the parent
# listing, it does not hide what is inside once you are there.
$mine = Join-Path $root 'Mis cosas'
if (-not (Test-Path -LiteralPath $mine)) { New-Item -ItemType Directory -Path $mine | Out-Null }

New-Link (Join-Path $mine 'Apuntes (español).lnk') (Join-Path $root '1_Apuntes\Froth_Apuntes_completos_ES.pdf') ''
New-Link (Join-Path $mine 'Study notes (English).lnk') (Join-Path $root '1_Apuntes\Froth_Study_Notes_EN.pdf') ''
New-Link (Join-Path $mine 'Todos los apuntes sueltos.lnk') (Join-Path $root '1_Apuntes\1. Apuntes acumulados') ''
New-Link (Join-Path $mine 'Resultados.lnk') (Join-Path $root '3_Resultados') ''
New-Link (Join-Path $mine 'Datos.lnk') (Join-Path $root '2_Datos') ''
New-Link (Join-Path $mine 'Notebooks.lnk') (Join-Path $root '4_Notebooks') ''
Write-Host "Created: Mis cosas\ with $((Get-ChildItem $mine).Count) shortcut(s)"

# --- 3. Everything else out of sight -------------------------------------------------
# Computed as "the root minus the keep list" rather than a fixed list of names, so a file
# added next month is hidden too instead of quietly reappearing in the middle of it.
$hidden = 0
Get-ChildItem -LiteralPath $root -Force | ForEach-Object {
    if ($keepVisible -notcontains $_.Name) {
        Set-Hidden $_.FullName $true
        $hidden++
    }
}
Write-Host "Hidden: $hidden entr(ies). Nothing moved, nothing deleted."
Write-Host "  Undo: powershell -ExecutionPolicy Bypass -File packaging\tidy_folder.ps1 -Revert"
