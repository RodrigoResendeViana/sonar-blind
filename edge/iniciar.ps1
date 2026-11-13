# Sobe o serviço da câmera no notebook do ponto (Windows, PowerShell).
#
#   .\iniciar.ps1                         # webcam + janela, parada demo, linhas DEMO-10 e DEMO-20
#   .\iniciar.ps1 -Braco                  # também publica a posição do letreiro sem espera (demo do braço)
#   .\iniciar.ps1 -Modo teclado -Braco    # sem câmera: digite DEMO-10@0.2, DEMO-10@0.8...
#   .\iniciar.ps1 -Camera "http://192.168.0.50:81/stream?t=SEU_TOKEN"   # ESP32-CAM na cabeça do braço
#
# Na primeira vez, cria o ambiente (.venv) e instala tudo (alguns minutos: EasyOCR traz o PyTorch).
# A senha do MQTT (camera-<parada>) é pedida na hora e não fica gravada em lugar nenhum.
# Pegue no CloudShell: aws ssm get-parameter --name /sonar/mqtt/usuarios/camera-demo --with-decryption --query Parameter.Value --output text
# Se o Windows bloquear o script: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
param(
    [ValidateSet("webcam", "teclado")] [string]$Modo = "webcam",
    [string]$Parada = "demo",
    [string]$Linhas = "DEMO-10,DEMO-20",
    [string]$Servidor = "sonar.rodrigoviana.app.br",
    [string]$Camera = "0",
    [ValidateSet("auto", "yolo", "ocr")] [string]$Detector = "auto",
    [switch]$Braco,
    [switch]$SemJanela
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Criando o ambiente e instalando as dependências (só na primeira vez)..."
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3 -m venv .venv } else { python -m venv .venv }
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements-visao.txt
    # o EasyOCR instala o OpenCV sem janela (headless); troca pelo com janela, para o --janela funcionar
    & $python -m pip uninstall -y opencv-python-headless
    & $python -m pip install --force-reinstall --no-deps opencv-python
}

if (-not $env:SONAR_MQTT_SENHA) {
    $segura = Read-Host "Senha do MQTT do usuario camera-$Parada" -AsSecureString
    $env:SONAR_MQTT_SENHA = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura))
}
$env:SONAR_MQTT_HOST = $Servidor
$env:SONAR_MQTT_PORTA = "8883"
$env:SONAR_MQTT_USUARIO = "camera-$Parada"
$env:SONAR_MQTT_TLS = "1"

$argumentos = @("-m", "sonar_camera", "--parada", $Parada, "--linhas", $Linhas, "--modo", $Modo,
    "--camera", $Camera, "--detector", $Detector)
if ($Modo -eq "webcam" -and -not $SemJanela) { $argumentos += "--janela" }
if ($Braco) { $argumentos += "--mirar-sempre" }
Write-Host "Sonar camera: parada $Parada, linhas $Linhas, modo $Modo. Ctrl+C para sair."
& $python @argumentos
