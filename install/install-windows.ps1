param(
  [Parameter(Mandatory=$true)][string]$Name,
  [Parameter(Mandatory=$true)][int]$HumanPort,
  [Parameter(Mandatory=$true)][int]$AiPort,
  [Parameter(Mandatory=$true)][string]$ContactsFile,
  [switch]$Hub,
  [string]$HubHost = "",
  [int]$HubPort = 0
)
$ErrorActionPreference = "Stop"
$Root = Join-Path $env:ProgramData "NoobiaCouncil"
$Source = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
New-Item -ItemType Directory -Force -Path $Root | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "files") | Out-Null
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
  throw "Run from a Visual Studio Developer PowerShell with the C compiler installed."
}
$CoreNames = @("authentication","arbitration","contact_book","conversation_activity","conversation_memory","file_commands","file_storage","network","presence","protocol","service_config","sha256","transcript")
$Core = $CoreNames | ForEach-Object { Join-Path $Source "src/$_.c" }
& cl.exe /nologo /O2 /I (Join-Path $Source "include") $Core (Join-Path $Source "src/council_service.c") /Fe:(Join-Path $Root "noobia-council.exe") ws2_32.lib bcrypt.lib
if ($LASTEXITCODE -ne 0) { throw "daemon compilation failed" }
$ClientCoreNames = @("authentication","contact_book","network","protocol","sha256")
$ClientCore = $ClientCoreNames | ForEach-Object { Join-Path $Source "src/$_.c" }
& cl.exe /nologo /O2 /I (Join-Path $Source "include") $ClientCore (Join-Path $Source "src/council_live.c") /Fe:(Join-Path $Root "council-live.exe") ws2_32.lib bcrypt.lib
if ($LASTEXITCODE -ne 0) { throw "live client compilation failed" }
Copy-Item $ContactsFile (Join-Path $Root "contacts.json") -Force
@"
name=$Name
role=ai
bind_address=0.0.0.0
human_port=$HumanPort
ai_port=$AiPort
is_hub=$($Hub.IsPresent.ToString().ToLower())
hub_host=$HubHost
hub_port=$HubPort
contacts_file=$Root\contacts.json
transcript_file=$Root\transcript.tsv
inbox_file=$Root\inbox.tsv
summary_file=$Root\summary.txt
activity_file=$Root\last-activity
files_directory=$Root\files
max_file_bytes=10485760
presence_seconds=15
"@ | Set-Content -Encoding ASCII (Join-Path $Root "service.conf")
$Action = New-ScheduledTaskAction -Execute (Join-Path $Root "noobia-council.exe") -Argument "--config `"$Root\service.conf`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName "NoobiaCouncil" -Action $Action -Trigger $Trigger -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName "NoobiaCouncil"
Write-Host "Noobia Council installed as startup task NoobiaCouncil."
