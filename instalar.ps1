# =====================================================================
#  SIG-TEC - Instalacion con un solo comando (Windows)
#
#  Uso (en PowerShell):
#     irm https://raw.githubusercontent.com/Danny7w7-coder/proyecto3Bases2/main/instalar.ps1 | iex
#
#  O, si ya descargo este archivo:
#     powershell -ExecutionPolicy Bypass -File instalar.ps1
#
#  Que hace:
#     1. Revisa que Docker Desktop y Python esten instalados (y enciende Docker si hace falta).
#     2. Descarga el proyecto en la carpeta  %USERPROFILE%\SIG-TEC  (si no existe ya).
#     3. Instala la libreria de Python necesaria (psycopg2).
#     4. Levanta los 6 servidores y deja todo listo (python scripts/init_all.py --reset).
#     5. Muestra el estado y los siguientes pasos.
#
#  El texto va sin tildes a proposito: asi se ve bien en cualquier consola de Windows.
# =====================================================================

function Install-SigTec {
    # "Continue": los avisos normales de docker y python (que salen por stderr) no deben cortar el script.
    # Cada paso revisa su propio resultado.
    $ErrorActionPreference = "Continue"
    $repo     = "Danny7w7-coder/proyecto3Bases2"
    # Carpeta de instalacion (se puede cambiar con la variable de entorno SIGTEC_DESTINO)
    $destino  = if ($env:SIGTEC_DESTINO) { $env:SIGTEC_DESTINO } else { Join-Path $HOME "SIG-TEC" }
    $docker_desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"

    function Write-Paso($numero, $texto) { Write-Host ""; Write-Host "[$numero/5] $texto" -ForegroundColor Cyan }
    function Write-Bien($texto)  { Write-Host "      OK  $texto" -ForegroundColor Green }
    function Write-Aviso($texto) { Write-Host "      !   $texto" -ForegroundColor Yellow }
    function Stop-ConError($texto) {
        Write-Host ""
        Write-Host "  NO SE PUDO TERMINAR LA INSTALACION" -ForegroundColor Red
        Write-Host "  $texto" -ForegroundColor Red
        Write-Host "  Cuando lo resuelva, vuelva a ejecutar el mismo comando." -ForegroundColor Red
        Write-Host ""
        throw "SIGTEC_DETENIDO"
    }

    Write-Host ""
    Write-Host "  SIG-TEC - Sistema Distribuido de Informacion Geografica de los Campus del TEC" -ForegroundColor White
    Write-Host "  Tercer Proyecto - Bases de Datos II" -ForegroundColor Gray

    # -----------------------------------------------------------------
    Write-Paso 1 "Revisando los programas necesarios"

    # Python (se acepta 'python' o el lanzador 'py'). Se descarta el acceso directo de la Microsoft Store.
    $python = $null
    foreach ($candidato in @("python", "py")) {
        try {
            $version = & $candidato -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version) { $python = $candidato; break }
        } catch { }
    }
    if (-not $python) {
        Stop-ConError "No se encontro Python. Instalelo desde https://www.python.org/downloads/ y marque 'Add python.exe to PATH'."
    }
    $partes = $version.Trim().Split(".")
    if ([int]$partes[0] -lt 3 -or ([int]$partes[0] -eq 3 -and [int]$partes[1] -lt 10)) {
        Stop-ConError "Se necesita Python 3.10 o superior. Tiene Python $version."
    }
    Write-Bien "Python $version"

    # Docker
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Stop-ConError "No se encontro Docker. Instale Docker Desktop desde https://www.docker.com/products/docker-desktop/"
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path $docker_desktop) {
            Write-Aviso "Docker Desktop esta apagado. Encendiendolo (puede tardar hasta 2 minutos)..."
            Start-Process $docker_desktop
            $limite = (Get-Date).AddMinutes(3)
            do { Start-Sleep -Seconds 5; docker info *> $null } until ($LASTEXITCODE -eq 0 -or (Get-Date) -gt $limite)
        }
        if ($LASTEXITCODE -ne 0) {
            Stop-ConError "Docker Desktop no esta encendido. Abralo, espere a que diga 'Engine running' y vuelva a intentar."
        }
    }
    Write-Bien "Docker Desktop encendido"

    # Puertos que usa el sistema
    $ocupados = @()
    foreach ($puerto in 5440..5445) {
        $uso = Get-NetTCPConnection -State Listen -LocalPort $puerto -ErrorAction SilentlyContinue |
               Where-Object { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName -notmatch "docker|com.docker|wslrelay|vpnkit" }
        if ($uso) { $ocupados += $puerto }
    }
    if ($ocupados.Count -gt 0) {
        Stop-ConError "Otro programa usa los puertos $($ocupados -join ', '). Cierre ese programa o cambie los puertos en el archivo .env del proyecto."
    }
    Write-Bien "Puertos 5440 a 5445 disponibles"

    # -----------------------------------------------------------------
    Write-Paso 2 "Descargando el proyecto"
    if (Test-Path (Join-Path $destino "scripts\init_all.py")) {
        Write-Aviso "Ya existe $destino. Se usa esa copia (no se descarga de nuevo)."
    } else {
        $zip      = Join-Path $env:TEMP "sigtec_descarga.zip"
        $temporal = Join-Path $env:TEMP "sigtec_descarga"
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $ProgressPreference = "SilentlyContinue"   # la barra de progreso hace muy lenta la descarga
            Invoke-WebRequest -Uri "https://github.com/$repo/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing -ErrorAction Stop
            if (Test-Path $temporal) { Remove-Item $temporal -Recurse -Force }
            Expand-Archive -Path $zip -DestinationPath $temporal -Force -ErrorAction Stop
            $carpeta = Get-ChildItem $temporal -Directory | Select-Object -First 1
            New-Item -ItemType Directory -Force (Split-Path $destino) | Out-Null
            Move-Item $carpeta.FullName $destino -ErrorAction Stop
        } catch {
            Stop-ConError "No se pudo descargar el proyecto ($($_.Exception.Message)). Revise la conexion a internet."
        } finally {
            Remove-Item $zip, $temporal -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Bien "Proyecto descargado en $destino"
    }
    Set-Location $destino

    # -----------------------------------------------------------------
    Write-Paso 3 "Instalando la libreria de Python (psycopg2)"
    & $python -m pip install --quiet --disable-pip-version-check -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Stop-ConError "No se pudo instalar psycopg2. Pruebe a mano: $python -m pip install -r requirements.txt" }
    Write-Bien "psycopg2 instalado"

    # -----------------------------------------------------------------
    Write-Paso 4 "Levantando los 6 servidores (unos 2 minutos; la primera vez descarga la imagen)"

    # Si ya hay una instalacion de SIG-TEC desde otra carpeta, init_all.py la reemplaza
    # (solo puede haber una por computadora) y lo explica en pantalla.
    $env:PYTHONIOENCODING = "utf-8"
    & $python scripts/init_all.py --reset
    if ($LASTEXITCODE -ne 0) { Stop-ConError "Fallo la puesta en marcha. Revise el mensaje de arriba y la seccion 'Solucion de problemas' del README." }

    # -----------------------------------------------------------------
    Write-Paso 5 "Comprobando el estado"
    & $python scripts/estado_nodos.py

    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Green
    Write-Host "   SIG-TEC esta listo" -ForegroundColor Green
    Write-Host "  ============================================================" -ForegroundColor Green
    Write-Host "   Carpeta del proyecto:  $destino"
    Write-Host "   (esta ventana ya quedo dentro de esa carpeta)"
    Write-Host ""
    Write-Host "   Siguientes pasos:"
    Write-Host "     python scripts/correr_pruebas.py           54 pruebas automaticas (unos 4 minutos)"
    Write-Host "     python scripts/verificar_consistencia.py   compara los datos de los 6 servidores"
    Write-Host "     python scripts/demo_2pc.py                 commit en dos fases"
    Write-Host "     python scripts/escenarios.py a             borrado por error y recuperacion (PITR)"
    Write-Host ""
    Write-Host "   Plugin de QGIS: descargue sigtec.zip de"
    Write-Host "     https://github.com/$repo/releases/latest"
    Write-Host "   Usuario: sancarlos1   Clave: tec2026"
    Write-Host ""
    Write-Host "   Guia completa: https://github.com/$repo#readme"
    Write-Host ""
}

try {
    Install-SigTec
} catch {
    if ($_.Exception.Message -ne "SIGTEC_DETENIDO") {
        Write-Host ""
        Write-Host "  Error inesperado: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  Puede seguir los pasos manuales del README: https://github.com/Danny7w7-coder/proyecto3Bases2#readme" -ForegroundColor Red
    }
}
