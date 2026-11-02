# PC(Windows)의 ollama 엑사원을 서버 ai 서비스에 연결하는 역방향 SSH 터널. 서버 쪽은 scripts/exaone-pc.sh.
# 실행: powershell -ExecutionPolicy Bypass -File scripts\pc\exaone-tunnel.ps1 [-SshHost cheonan]
# 이 창을 닫으면 터널이 끊기고, 서버 ai 서비스는 규칙 결과만 낸다.
#
# 보안
# - ollama는 PC의 127.0.0.1에만 열려 있어야 한다(OLLAMA_HOST가 0.0.0.0 같은 값이면 멈춘다).
# - 서버 쪽 출구는 TCP 포트가 아니라 내 홈의 0700 폴더 안 Unix 소켓이다. 같은 서버의 다른 계정은 붙을 수 없다.
# - 모델 digest · ollama 버전이 scripts/exaone-pc.env의 고정값과 다르면 연결하지 않는다.
param(
  [string]$SshHost = 'cheonan',                                  # ~/.ssh/config의 서버 이름(VS Code Remote와 같은 것)
  [string]$RemoteSock = '/home/user41/run/exaone/ollama.sock',   # exaone-pc.env의 OLLAMA_UDS와 같아야 한다
  [int]$LocalPort = 11434
)
$ErrorActionPreference = 'Stop'

function Stop-With($msg) { Write-Host "exaone-tunnel: $msg" -ForegroundColor Red; exit 1 }

# 1. 고정값 읽기
$envFile = Join-Path $PSScriptRoot '..\exaone-pc.env'
$pin = @{}
foreach ($line in [IO.File]::ReadAllLines($envFile, [Text.Encoding]::UTF8)) {
  if ($line -match '^\s*([A-Z_]+)=(.*)$') { $pin[$Matches[1]] = $Matches[2].Trim() }
}
$model = $pin['EXAONE_MODEL']

# 2. ollama가 이 PC 안에서만 열려 있는지
foreach ($scope in 'Process', 'User', 'Machine') {
  $h = [Environment]::GetEnvironmentVariable('OLLAMA_HOST', $scope)
  if ($h -and $h -notmatch '^(https?://)?(127\.0\.0\.1|localhost)(:\d+)?/?$') {
    Stop-With "OLLAMA_HOST($scope)=$h. 외부에 열려 있다. 값을 지우고 ollama를 다시 시작한다"
  }
}

# 3. 모델 · 버전 확인
$base = "http://127.0.0.1:$LocalPort"
try {
  $version = (Invoke-RestMethod "$base/api/version" -TimeoutSec 5).version
  $tags = (Invoke-RestMethod "$base/api/tags" -TimeoutSec 5).models
} catch { Stop-With "ollama가 $base 에서 응답하지 않는다. ollama 앱을 켠다" }
$m = $tags | Where-Object { $_.name -eq $model -or $_.model -eq $model } | Select-Object -First 1
if (-not $m) { Stop-With "모델 없음. 먼저: ollama pull $model" }
if ($pin['OLLAMA_VERSION'] -and $pin['OLLAMA_VERSION'] -ne $version) { Stop-With "ollama 버전 $version 이 고정값 $($pin['OLLAMA_VERSION']) 과 다르다" }
if ($pin['EXAONE_MODEL_DIGEST'] -and $pin['EXAONE_MODEL_DIGEST'] -ne $m.digest) { Stop-With "모델 digest $($m.digest) 가 고정값과 다르다" }
Write-Host "ollama $version · $model · digest $($m.digest.Substring(0,12))"
if (-not $pin['EXAONE_MODEL_DIGEST']) { Write-Host '고정값이 비어 있다. 터널이 붙으면 서버에서 scripts/exaone-pc.sh pin 을 한 번 실행한다' -ForegroundColor Yellow }

# 4. 터널 (끊기면 5초 뒤 다시 연결)
$dir = $RemoteSock.Substring(0, $RemoteSock.LastIndexOf('/'))
while ($true) {
  # 지난 연결이 남긴 소켓 파일을 지운다(sshd는 남은 파일이 있으면 새로 열지 못한다)
  ssh $SshHost "umask 077 && mkdir -p '$dir' && chmod 700 '$dir' && rm -f '$RemoteSock'"
  if ($LASTEXITCODE -ne 0) { Stop-With "서버 접속 실패($SshHost)" }
  Write-Host "[$(Get-Date -f HH:mm:ss)] 연결: 127.0.0.1:$LocalPort → ${SshHost}:$RemoteSock (Ctrl+C로 끝)"
  ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 `
      -R "${RemoteSock}:127.0.0.1:$LocalPort" $SshHost
  Write-Host "[$(Get-Date -f HH:mm:ss)] 끊김. 5초 뒤 다시 연결" -ForegroundColor Yellow
  Start-Sleep 5
}
