<#
.SYNOPSIS
    Construye el paquete de Windows con PyInstaller: dist\OSINEITOR\ y el ZIP portable.
.EXAMPLE
    .\packaging\windows\build.ps1 -Version 0.5.0
#>
param(
    [Parameter(Mandatory = $true)][string]$Version
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $root

python -m PyInstaller --noconfirm --clean packaging\windows\osineitor.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller terminó con código $LASTEXITCODE" }

$folder = Join-Path $root 'dist\OSINEITOR'
foreach ($name in 'osineitor.exe', 'osineitor-gui.exe') {
    if (-not (Test-Path (Join-Path $folder $name))) { throw "Falta $name en $folder" }
}

$zip = Join-Path $root "dist\OSINEITOR-$Version-portable.zip"
# El antivirus puede tener bloqueado un fichero recién generado: se reintenta unas veces.
for ($try = 1; $try -le 5; $try++) {
    try {
        if (Test-Path $zip) { Remove-Item $zip }
        Compress-Archive -Path $folder -DestinationPath $zip -ErrorAction Stop
        break
    } catch {
        if ($try -eq 5) { throw }
        Write-Host "ZIP bloqueado (intento $try de 5), reintento en 3 s: $($_.Exception.Message)"
        Start-Sleep -Seconds 3
    }
}
Write-Host "Paquete: $folder"
Write-Host "ZIP:     $zip"
