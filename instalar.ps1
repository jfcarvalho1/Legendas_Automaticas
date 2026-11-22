# Media Organizer — instalação completa para Windows (de início ao fim).
# É chamado pelo instalar.bat (duplo clique). Pode ser repetido sem problema.
$ErrorActionPreference = "Continue"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Dir
New-Item -ItemType Directory -Force -Path "$Dir\logs" | Out-Null
try { Start-Transcript -Path "$Dir\logs\instalacao.log" -Force | Out-Null } catch {}

function Titulo($t) { Write-Host ""; Write-Host "== $t ==" -ForegroundColor Cyan }
function Ok($t)     { Write-Host "   OK: $t" -ForegroundColor Green }
function Aviso($t)  { Write-Host "   $t" -ForegroundColor Yellow }

Titulo "Media Organizer: instalação"

# Ficheiros vindos de um ZIP da internet ficam "bloqueados" pelo Windows
Get-ChildItem -Path $Dir -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

# Fechar o Media Organizer se estiver aberto (para poder actualizar os componentes)
Get-Process python, pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "$Dir\.venv\*" } |
    Stop-Process -Force -ErrorAction SilentlyContinue

$HasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)

# ---------------------------------------------------------------- 1. Python
# Usa o Python 3.12 (compatível com todos os componentes, incluindo o motor de
# tradução). Se não existir, instala-o. Versões muito recentes (3.14, 3.15…)
# ainda não têm todos os componentes disponíveis.
function Get-PyVersion($exe) {
    if (-not $exe -or -not (Test-Path $exe)) { return $null }
    $v = & $exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0 -and $v) { return $v.Trim() }
    return $null
}

function Find-Python($versions) {
    foreach ($ver in $versions) {
        $nodot = $ver -replace '\.', ''
        $cands = @()
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $exe = & py "-$ver" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { $cands += $exe.Trim() }
        }
        $cands += "$env:LOCALAPPDATA\Programs\Python\Python$nodot\python.exe"
        $cands += "$env:LOCALAPPDATA\Python\pythoncore-$ver-64\python.exe"
        $cands += "$env:ProgramFiles\Python$nodot\python.exe"
        foreach ($c in $cands) { if ((Get-PyVersion $c) -eq $ver) { return $c } }
    }
    return $null
}

Titulo "1/6 Python"
$Good = @("3.12", "3.11", "3.13")
$Python = Find-Python $Good
if (-not $Python -and $HasWinget) {
    Aviso "A instalar o Python 3.12 (gratuito; pode demorar)..."
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    $Python = Find-Python $Good
}
if (-not $Python) {
    $Python = Find-Python @("3.14", "3.15", "3.10")
    if ($Python) { Aviso "A usar $(Get-PyVersion $Python): o motor de tradução pode não instalar nesta versão." }
}
if (-not $Python) {
    Write-Host "Não foi possível instalar o Python automaticamente." -ForegroundColor Red
    Write-Host "Instale o Python 3.12 em https://www.python.org/downloads/ e volte a correr instalar.bat."
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}
$PyVer = Get-PyVersion $Python
Ok "Python $PyVer ($Python)"

# ---------------------------------------------------------------- 2. FFmpeg
Titulo "2/6 FFmpeg (análise de vídeo e áudio)"
$ff = (Get-Command ffprobe -ErrorAction SilentlyContinue) -or (Test-Path "$env:LOCALAPPDATA\Microsoft\WinGet\Links\ffprobe.exe") -or `
      (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\*FFmpeg*\*\bin\ffprobe.exe" -ErrorAction SilentlyContinue)
if (-not $ff -and $HasWinget) {
    Aviso "A instalar o FFmpeg..."
    winget install -e --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
}
if ($ff -or (Test-Path "$env:LOCALAPPDATA\Microsoft\WinGet\Links\ffprobe.exe") -or
    (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\*FFmpeg*\*\bin\ffprobe.exe" -ErrorAction SilentlyContinue)) {
    Ok "FFmpeg"
} else {
    Aviso "FFmpeg em falta: a aplicação funciona, mas sem análise técnica."
}

# ---------------------------------------------------------------- 3. Ambiente
Titulo "3/6 Componentes da aplicação"
$VPy = "$Dir\.venv\Scripts\python.exe"
$cur = Get-PyVersion $VPy
if ($cur -and $cur -ne $PyVer) {
    Aviso "Ambiente antigo com Python ${cur}: a refazer com Python ${PyVer}..."
    Remove-Item -Recurse -Force "$Dir\.venv" -ErrorAction SilentlyContinue
}
if (-not (Test-Path $VPy)) { & $Python -m venv "$Dir\.venv" }
& $VPy -m pip install --quiet --upgrade pip
& $VPy -m pip install --quiet -r "$Dir\requirements.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Falhou a instalação dos componentes (PySide6, Mutagen). Verifique a internet e repita." -ForegroundColor Red
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}
Ok "PySide6 e Mutagen"

# ---------------------------------------------------------------- 4. Tradução
Titulo "4/6 Motor de tradução local (Argos Translate, ~1 GB, só da primeira vez)"
& $VPy -c "import argostranslate.translate as t; import sys; sys.exit(0 if any(l.code=='pt' for l in t.get_installed_languages()) else 1)" 2>$null
if ($LASTEXITCODE -eq 0) {
    Ok "já instalado"
} else {
    Aviso "A descarregar o motor e os modelos inglês/espanhol/francês -> português (pode demorar bastante)..."
    & $VPy -c "import sys; sys.path.insert(0, r'$Dir'); from movies.translation import install_argos; install_argos(print)"
    if ($LASTEXITCODE -eq 0) { Ok "motor de tradução instalado" }
    else { Aviso "O motor de tradução não instalou agora. O resto funciona; pode tentar depois na página Legendas." }
}

# ---------------------------------------------------------------- 5. Atalhos
Titulo "5/6 Atalhos"
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
Ok "Ambiente de Trabalho e Menu Iniciar (apontam para $Dir)"

# ---------------------------------------------------------------- 6. Verificação
Titulo "6/6 Verificação final"
& $VPy "$Dir\app.py" --check
$check = $LASTEXITCODE

Write-Host ""
if ($check -eq 0) {
    Write-Host "== Instalação concluída: TUDO OK ==" -ForegroundColor Green
    Write-Host "A abrir o Media Organizer..."
    Start-Process -FilePath "$Dir\.venv\Scripts\pythonw.exe" -ArgumentList "`"$Dir\app.py`"" -WorkingDirectory $Dir
} else {
    Write-Host "== A verificação encontrou problemas (ver acima). Registo em logs\instalacao.log ==" -ForegroundColor Red
}
try { Stop-Transcript | Out-Null } catch {}
