# EXAONE 규칙 기반 비교 테스트
# A: 기존 프롬프트 / B: 규칙 프롬프트 + JSON 스키마 강제 / C: B 결과에 코드 후처리 규칙 적용
$ErrorActionPreference = 'Continue'
$base  = Split-Path -Parent $MyInvocation.MyCommand.Path
$utf8  = New-Object Text.UTF8Encoding($true)
$mails = [IO.File]::ReadAllText("$base\mails.json", [Text.Encoding]::UTF8) | ConvertFrom-Json
$today = [datetime]'2026-10-24'
$exe   = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
$models = @('hf.co/LGAI-EXAONE/EXAONE-4.0-1.2B-GGUF:Q8_0','hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M')

$sysBase = '너는 업무 메일 분류기다. 메일을 읽고 아래 키만 가진 JSON 하나만 출력한다: needs_action(true/false), action(해야 할 일 한 문장), deadline(YYYY-MM-DD HH:MM 또는 null), priority(high/medium/low), summary(20자 이내 요약).'

$sysRules = @'
너는 업무 메일 분류기다. 아래 규칙을 반드시 지켜 JSON 하나만 출력한다.
[기준] 오늘은 2026-10-24(토)이다.
규칙1 needs_action: 회신·작업·결재·참석 여부처럼 받는 사람이 할 일이 있으면 true. 공지·뉴스레터·참고용 공유·"회신 불필요"면 false.
규칙2 action: 할 일을 30자 이내로. needs_action이 false면 "없음".
규칙3 deadline: "YYYY-MM-DD HH:MM" 형식. 연도가 없으면 2026년. 오늘/내일/모레는 2026-10-24 기준으로 바꾼다. 시간이 없으면 18:00. 마감이 없거나 needs_action이 false면 "없음".
규칙4 priority: needs_action이 false면 low. "긴급"이라는 말이 있거나 마감이 3일 이내면 high. 나머지는 medium.
규칙5 summary: 20자 이내 요약.
예시) 메일: "11월 20일까지 교육 수강 신청 부탁드립니다." → {"needs_action":true,"action":"교육 수강 신청","deadline":"2026-11-20 18:00","priority":"medium","summary":"교육 수강 신청 요청"}
'@

$schema = @{
  type = 'object'
  properties = @{
    needs_action = @{ type = 'boolean' }
    action       = @{ type = 'string' }
    deadline     = @{ type = 'string' }
    priority     = @{ type = 'string'; enum = @('high','medium','low') }
    summary      = @{ type = 'string' }
  }
  required = @('needs_action','action','deadline','priority','summary')
}

function Call-Model($model, $sys, $mail, $fmt) {
  $h = @{ model=$model; stream=$false; think=$false; options=@{temperature=0}
          messages=@(@{role='system';content=$sys}, @{role='user';content=$mail}) }
  if ($null -ne $fmt) { $h.format = $fmt }
  $body = $h | ConvertTo-Json -Depth 10
  $sw = [Diagnostics.Stopwatch]::StartNew()
  try {
    $r = Invoke-RestMethod -Uri http://localhost:11434/api/chat -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 600
    $sw.Stop()
    return [pscustomobject]@{ content=$r.message.content; total_s=[math]::Round($sw.Elapsed.TotalSeconds,1); load_s=[math]::Round($r.load_duration/1e9,1); eval_s=[math]::Round($r.eval_duration/1e9,1); tokens=$r.eval_count }
  } catch {
    $sw.Stop()
    return [pscustomobject]@{ content="ERROR: $($_.Exception.Message)"; total_s=[math]::Round($sw.Elapsed.TotalSeconds,1); load_s=0; eval_s=0; tokens=0 }
  }
}

function Parse-Json($s) {
  try { return ($s | ConvertFrom-Json) } catch {}
  $m = [regex]::Match($s, '\{[\s\S]*\}')
  if ($m.Success) { try { return ($m.Value | ConvertFrom-Json) } catch {} }
  return $null
}

function Norm-Deadline($v) {
  if ($null -eq $v) { return $null }
  $s = "$v".Trim()
  if ($s -eq '' -or $s -match '^(없음|null|none|n/a)$') { return $null }
  $d = [datetime]::MinValue
  if ([datetime]::TryParseExact($s, 'yyyy-MM-dd HH:mm', $null, 'None', [ref]$d)) { return $d.ToString('yyyy-MM-dd HH:mm') }
  if ([datetime]::TryParseExact($s, 'yyyy-MM-dd', $null, 'None', [ref]$d)) { return $d.ToString('yyyy-MM-dd') }
  return "INVALID:$s"
}

# 코드 후처리 규칙 (모델 호출 없이 적용)
function Post-Process($o, $mailText) {
  $p = [pscustomobject]@{ needs_action=[bool]$o.needs_action; action="$($o.action)"; deadline=(Norm-Deadline $o.deadline); priority="$($o.priority)"; summary="$($o.summary)" }
  # P1 날짜만 있으면 18:00
  if ($p.deadline -match '^\d{4}-\d{2}-\d{2}$') { $p.deadline = "$($p.deadline) 18:00" }
  # P2 메일에 연도가 없는데 연도가 올해가 아니면 올해로 교정
  if ($p.deadline -match '^(\d{4})-' -and $mailText -notmatch '\d{4}년' -and $Matches[1] -ne "$($today.Year)") { $p.deadline = "$($today.Year)" + $p.deadline.Substring(4) }
  # P3 할 일이 없으면 마감 없음, action 없음
  if (-not $p.needs_action) { $p.deadline = $null; $p.action = '없음' }
  # P4 우선순위 재계산
  $dl = [datetime]::MinValue
  $hasDl = $p.deadline -and [datetime]::TryParseExact($p.deadline, 'yyyy-MM-dd HH:mm', $null, 'None', [ref]$dl)
  if (-not $p.needs_action) { $p.priority = 'low' }
  elseif ($mailText -match '긴급' -or ($hasDl -and ($dl - $today).TotalDays -le 3)) { $p.priority = 'high' }
  else { $p.priority = 'medium' }
  # P5 요약 20자 자르기
  if ($p.summary.Length -gt 20) { $p.summary = $p.summary.Substring(0,20) }
  return $p
}

function Score($o, $gt, $raw) {
  if ($null -eq $o) { return [pscustomobject]@{ json=0; needs=0; deadline=0; priority=0; summary=0; action=0; got_deadline='' } }
  $dl = Norm-Deadline $o.deadline
  $needsOk = [int]([bool]$o.needs_action -eq [bool]$gt.needs_action)
  $dlOk = [int](("$dl") -eq ("$($gt.deadline)"))
  $prOk = [int]("$($o.priority)" -eq "$($gt.priority)")
  $smOk = [int](("$($o.summary)").Length -gt 0 -and ("$($o.summary)").Length -le 20)
  if ($gt.needs_action) { $acOk = [int](("$($o.action)") -match [regex]::Escape($gt.keyword)) } else { $acOk = [int](("$($o.action)") -match '없음' -or ("$($o.action)").Trim() -eq '') }
  return [pscustomobject]@{ json=1; needs=$needsOk; deadline=$dlOk; priority=$prOk; summary=$smOk; action=$acOk; got_deadline="$dl" }
}

$rows = @()
$prog = "$base\progress.txt"
foreach ($m in $models) {
  $short = if ($m -match '1.2B') { '1.2B' } else { '7.8B' }
  "[$(Get-Date -f HH:mm:ss)] $short warmup" | Out-File $prog -Append -Encoding utf8
  $w = Call-Model $m '짧게 답해.' '안녕' $null
  $rows += [pscustomobject]@{ model=$short; cond='warmup'; id=0; json=''; needs=''; deadline=''; priority=''; summary=''; action=''; got_deadline=''; total_s=$w.total_s; load_s=$w.load_s; eval_s=$w.eval_s; tokens=$w.tokens; raw='' }
  foreach ($x in $mails) {
    foreach ($cond in 'A','B') {
      if ($cond -eq 'A') { $r = Call-Model $m $sysBase $x.mail 'json' } else { $r = Call-Model $m $sysRules $x.mail $schema }
      $o = Parse-Json $r.content
      $s = Score $o $x.gt $r.content
      $rows += [pscustomobject]@{ model=$short; cond=$cond; id=$x.id; json=$s.json; needs=$s.needs; deadline=$s.deadline; priority=$s.priority; summary=$s.summary; action=$s.action; got_deadline=$s.got_deadline; total_s=$r.total_s; load_s=$r.load_s; eval_s=$r.eval_s; tokens=$r.tokens; raw=($r.content -replace "`r|`n",' ') }
      if ($cond -eq 'B' -and $null -ne $o) {
        $pp = Post-Process $o $x.mail
        $s2 = Score $pp $x.gt ''
        $rows += [pscustomobject]@{ model=$short; cond='C'; id=$x.id; json=$s2.json; needs=$s2.needs; deadline=$s2.deadline; priority=$s2.priority; summary=$s2.summary; action=$s2.action; got_deadline=$s2.got_deadline; total_s=$r.total_s; load_s=0; eval_s=$r.eval_s; tokens=$r.tokens; raw=($pp | ConvertTo-Json -Compress) }
      } elseif ($cond -eq 'B') {
        $rows += [pscustomobject]@{ model=$short; cond='C'; id=$x.id; json=0; needs=0; deadline=0; priority=0; summary=0; action=0; got_deadline=''; total_s=$r.total_s; load_s=0; eval_s=$r.eval_s; tokens=$r.tokens; raw='parse fail' }
      }
      "[$(Get-Date -f HH:mm:ss)] $short mail$($x.id) $cond $($r.total_s)s" | Out-File $prog -Append -Encoding utf8
    }
  }
  & $exe stop $m | Out-Null
}

$csv = ($rows | ConvertTo-Csv -NoTypeInformation) -join "`r`n"
[IO.File]::WriteAllText("$base\results.csv", $csv, $utf8)

$sum = @()
foreach ($g in ($rows | Where-Object { $_.cond -ne 'warmup' } | Group-Object model, cond)) {
  $n = $g.Group.Count
  $f = { param($k) [math]::Round((($g.Group | Measure-Object -Property $k -Sum).Sum / $n) * 100) }
  $sum += [pscustomobject]@{ group=$g.Name; n=$n; json=(& $f 'json'); needs=(& $f 'needs'); deadline=(& $f 'deadline'); priority=(& $f 'priority'); summary=(& $f 'summary'); action=(& $f 'action'); avg_total_s=[math]::Round(($g.Group | Measure-Object total_s -Average).Average,1); avg_eval_s=[math]::Round(($g.Group | Measure-Object eval_s -Average).Average,1) }
}
$warm = $rows | Where-Object { $_.cond -eq 'warmup' } | ForEach-Object { "$($_.model) load=$($_.load_s)s total=$($_.total_s)s" }
$txt = (($sum | Format-Table -AutoSize | Out-String) + "`r`nwarmup:`r`n" + ($warm -join "`r`n"))
[IO.File]::WriteAllText("$base\summary.txt", $txt, $utf8)
'DONE' | Out-File "$base\done.txt" -Encoding utf8
