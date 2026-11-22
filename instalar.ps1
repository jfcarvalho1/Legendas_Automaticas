# Media Organizer — instalação automática para Windows.
# É chamado pelo instalar.bat (duplo clique).
$ErrorActionPreference = "Continue"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Dir
Write-Host ""
Write-Host "== Media Organizer: instalação ==" -ForegroundColor Cyan
Write-Host ""

# Ficheiros vindos de um ZIP da internet ficam "bloqueados" pelo Windows
Get-ChildItem -Path $Dir -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

function Test-Python($exe) {
    if (-not $exe -or -not (Test-Path $exe)) { return $false }
    & $exe -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Get-Python {
    $cands = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $exe = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { $cands += $exe.Trim() }
    }
    $cands += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
              Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
    $cands += Get-ChildItem "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue |
              Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
    foreach ($c in $cands) { if (Test-Python $c) { return $c } }
    return $null
}

$HasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)

# 1. Python
Write-Host "-> A verificar o Python..."
$Python = Get-Python
if (-not $Python -and $HasWinget) {
    Write-Host "   Python não encontrado. A instalar o Python 3.12 (winget)..." -ForegroundColor Yellow
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    $Python = Get-Python
}
if (-not $Python) {
    Write-Host ""
    Write-Host "Não foi possível instalar o Python automaticamente." -ForegroundColor Red
    Write-Host "Instale-o em https://www.python.org/downloads/ (marque 'Add python.exe to PATH')"
    Write-Host "e volte a fazer duplo clique em instalar.bat."
    exit 1
}
Write-Host "   OK: $Python" -ForegroundColor Green

# 2. FFmpeg / FFprobe (análise técnica dos ficheiros)
Write-Host "-> A verificar o FFmpeg..."
$ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
if (-not $ffprobe -and -not (Test-Path "$env:LOCALAPPDATA\Microsoft\WinGet\Links\ffprobe.exe")) {
    if ($HasWinget) {
        Write-Host "   FFmpeg não encontrado. A instalar (winget)..." -ForegroundColor Yellow
        winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    } else {
        Write-Host "   FFmpeg em falta: a aplicação funciona, mas sem análise técnica." -ForegroundColor Yellow
    }
} else {
    Write-Host "   OK" -ForegroundColor Green
}

# 3. Ambiente Python próprio da aplicação
Write-Host "-> A preparar o ambiente da aplicação (pode demorar alguns minutos)..."
if (-not (Test-Path "$Dir\.venv\Scripts\python.exe")) {
    & $Python -m venv "$Dir\.venv"
}
$VPy = "$Dir\.venv\Scripts\python.exe"
& $VPy -m pip install --quiet --upgrade pip
& $VPy -m pip install --quiet -r "$Dir\requirements.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Falhou a instalação dos componentes Python (PySide6, Mutagen)." -ForegroundColor Red
    Write-Host "Verifique a ligação à internet e volte a correr instalar.bat."
    exit 1
}
Write-Host "   OK" -ForegroundColor Green

# 4. Atalhos no Ambiente de Trabalho e no Menu Iniciar
Write-Host "-> A criar os atalhos..."
$ws = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath("Desktop"),
            (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))
foreach ($p in $places) {
    if (-not (Test-Path $p)) { continue }
    $lnk = $ws.CreateShortcut((Join-Path $p "Media Organizer.lnk"))
    $lnk.TargetPath = "$Dir\.venv\Scripts\pythonw.exe"
    $lnk.Arguments = "`"$Dir\app.py`""
    $lnk.WorkingDirectory = $Dir
    $lnk.IconLocation = "$Dir\assets\icon.ico"
    $lnk.Description = "Organizar filmes e música"
    $lnk.Save()
}

Write-Host ""
Write-Host "== Instalação concluída ==" -ForegroundColor Cyan
Write-Host "Abra o 'Media Organizer' pelo atalho no Ambiente de Trabalho ou no Menu Iniciar."
Write-Host ""
