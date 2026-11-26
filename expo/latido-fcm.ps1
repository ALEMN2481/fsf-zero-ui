# Latido de FCM para el emulador (Paso 15, D17).
# La red virtual del emulador corta la conexión de Google Play services con FCM tras unos minutos
# sin tráfico, y los avisos quedan en cola hasta que se reconecta (medido: hasta 197 s). Este latido
# fuerza un heartbeat de GCM cada [Segundos]: mantiene viva la conexión y, si ya se había caído,
# GMS lo detecta (~20 s) y se reconecta.
# Uso: powershell -File expo/latido-fcm.ps1 [-Segundos 60]   (Ctrl+C para detenerlo)
param([int]$Segundos = 60)
$adb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
while ($true) {
    foreach ($accion in 'com.google.android.intent.action.GTALK_HEARTBEAT', 'com.google.android.intent.action.MCS_HEARTBEAT') {
        & $adb shell am broadcast -a $accion | Out-Null
    }
    Start-Sleep -Seconds $Segundos
}
