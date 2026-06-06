param(
  [int]$Port = 3020,
  [string]$HostName = "127.0.0.1",
  [string]$Token = ""
)

$ErrorActionPreference = "Stop"

$env:WHATSAPP_GATEWAY_PORT = [string]$Port
$env:WHATSAPP_GATEWAY_HOST = $HostName
if ($Token) {
  $env:WHATSAPP_GATEWAY_TOKEN = $Token
}

Write-Host "Starting QIB ATM Manager WhatsApp gateway on http://$HostName`:$Port"
npm start
