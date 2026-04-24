Set-Location -Path $PSScriptRoot
$env:TUNNEL_LOGFILE = Join-Path $PSScriptRoot 'tunnel.log'
& (Join-Path $PSScriptRoot 'cloudflared.exe') tunnel --url http://127.0.0.1:8000 --no-autoupdate --logfile $env:TUNNEL_LOGFILE
