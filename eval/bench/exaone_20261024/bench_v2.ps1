# EXAONE 규칙 기반 비교 테스트 v2 (받은 날짜 기준 / 기한 임의 생성 금지 / 공지·참조 분류)
# A: 기본 프롬프트 / B: 규칙 프롬프트 + JSON 스키마 강제 / C: B 결과에 코드 후처리 규칙 적용
$ErrorActionPreference = 'Continue'
$base  = Split-Path -Parent $MyInvocation.MyCommand.Path
$utf8  = New-Object Text.UTF8Encoding($true)
$mails = [IO.File]::ReadAllText("$base\mails_v2.json", [Text.Encoding]::UTF8) | ConvertFrom-Json
$exe   = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
$models = @('hf.co/LGAI-EXAONE/EXAONE-4.0-1.2B-GGUF:Q8_0','hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M')
$tag = 'v2'

$sysBase = '너는 업무 메일 분류기다. 메일을 읽고 아래 키만 가진 JSON 하나만 출력한다: category(요청/공지/참조/뉴스레터), needs_action(true/false), action(해야 할 일 한 문장), deadline(YYYY-MM-DD HH:MM 또는 null), priority(high/medium/low), summary(20자 이내 요약).'

$sysRules = @'
너는 업무 메일 분류기다. 아래 규칙을 반드시 지켜 JSON 하나만 출력한다.
규칙1 날짜 기준: 모든 날짜는 메일의 "받은날짜"를 기준으로 계산한다. 연도가 없으면 받은날짜의 연도를 쓰되, 받은날짜보다 앞선 날짜가 되면 다음 해로 한다. 오늘·내일·다음 주·다음 달도 받은날짜 기준이다.
규칙2 category: 요청/공지/참조/뉴스레터 중 하나. 받는사람이 내가 아니고 참조로만 받았으면 참조.
규칙3 needs_action: 나에게 직접 요청한 일이 있을 때만 true. 공지·참조·뉴스레터는 업무를 따로 만들지 않는다. 단, 공지가 이수·확인·제출을 요구하면 true.
규칙4 deadline: 메일에 적힌 기한만 쓴다. 시간이 있으면 "YYYY-MM-DD HH:MM", 날짜만 있으면 "YYYY-MM-DD". 기한이 없으면 "없음". 휴무일·행사일 같은 일정은 기한이 아니다. 기한을 추측해 만들지 않는다.
규칙5 priority: needs_action이 false면 low. 기한이 있으면 high. 기한이 없으면 medium(확인 후 회신).
규칙6 action: 할 일을 30자 이내로. needs_action이 false면 "없음". summary: 20자 이내 요약.
예시) 받은날짜: 2026-03-02(월) / 받는사람: 나 / 본문: "이번 달 20일까지 교육 수강 신청 부탁드립니다."
→ {"category":"요청","needs_action":true,"action":"교육 수강 신청","deadline":"2026-03-20","priority":"high","summary":"교육 수강 신청 요청"}
'@

$schema = @{
  type = 'object'
  properties = @{
    category     = @{ type = 'string'; enum = @('요청','공지','참조','뉴스레터') }
    needs_action = @{ type = 'boolean' }
    action       = @{ type = 'string' }
    deadline     = @{ type = 'string' }
    priority     = @{ type = 'string'; enum = @('high','medium','low') }
    summary      = @{ type = 'string' }
  }
  required = @('category','needs_action','action','deadline','priority','summary')
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

# 날짜 형식 정리: 시간 있으면 'yyyy-MM-dd HH:mm', 날짜만 있으면 'yyyy-MM-dd'. 시간을 새로 만들지 않는다.
function Norm-Deadline($v) {
  if ($null -eq $v) { return $null }
  $s = "$v".Trim()
  if ($s -eq '' -or $s -match '^(없음|null|none|n/a)$') { return $null }
  $d = [datetime]::MinValue
  foreach ($f in 'yyyy-MM-dd HH:mm','yyyy-MM-ddTHH:mm:ss','yyyy-MM-ddTHH:mm:ssZ','yyyy-MM-ddTHH:mm') {
    if ([datetime]::TryParseExact($s, $f, $null, 'None', [ref]$d)) { return $d.ToString('yyyy-MM-dd HH:mm') }
  }
  if ([datetime]::TryParseExact($s, 'yyyy-MM-dd', $null, 'None', [ref]$d)) { return $d.ToString('yyyy-MM-dd') }
  return "INVALID:$s"
}

function Cut-Summary($s, $n) {
  if ($s.Length -le $n) { return $s }
  $c = $s.Substring(0, $n)
  $i = $c.LastIndexOf(' ')
  if ($i -ge 8) { $c = $c.Substring(0, $i) }
  return $c.TrimEnd(' ', '(', ',', ':')
}

# 코드 후처리 규칙 (모델 호출 없이 적용)
function Post-Process($o, $x) {
  $recv = [datetime]$x.received
  $mailText = $x.mail
  $p = [pscustomobject]@{ category="$($o.category)"; needs_action=[bool]$o.needs_action; action="$($o.action)"; deadline=(Norm-Deadline $o.deadline); priority="$($o.priority)"; summary="$($o.summary)" }
  if ($p.deadline -like 'INVALID:*') { $p.deadline = $null }
  # P1 메일 머리글 규칙: 받는사람에 내가 없고 참조에만 있으면 참조, 업무 만들지 않음
  $to = [regex]::Match($mailText, '받는사람:\s*(.+)').Groups[1].Value
  $cc = [regex]::Match($mailText, '참조:\s*(.+)').Groups[1].Value
  if ($cc -match '나' -and $to -notmatch '(^|\s)나($|\s)') { $p.category = '참조'; $p.needs_action = $false }
  # P2 받은 날짜 기준 연도 교정: 메일에 연도가 없으면 받은 연도로, 받은 날짜보다 앞서면 다음 해
  if ($p.deadline -and $mailText -notmatch '\d{4}년') {
    $parts = $p.deadline -split ' ', 2
    $md = $parts[0].Substring(5)
    $cand = [datetime]::ParseExact("$($recv.Year)-$md", 'yyyy-MM-dd', $null)
    if ($cand -lt $recv.Date) { $cand = $cand.AddYears(1) }
    $p.deadline = $cand.ToString('yyyy-MM-dd') + $(if ($parts.Count -gt 1) { ' ' + $parts[1] } else { '' })
  }
  # P3 할 일이 없으면 기한·할 일 비움
  if (-not $p.needs_action) { $p.deadline = $null; $p.action = '없음' }
  # P4 우선순위: 할 일 없음 low / 기한 있음 high / 기한 없음 medium
  if (-not $p.needs_action) { $p.priority = 'low' } elseif ($p.deadline) { $p.priority = 'high' } else { $p.priority = 'medium' }
  # P5 요약 20자: 단어 경계에서 자르기
  $p.summary = Cut-Summary $p.summary 20
  return $p
}

function Score($o, $gt) {
  if ($null -eq $o) { return [pscustomobject]@{ json=0; category=0; needs=0; deadline=0; priority=0; summary=0; action=0; got_deadline='' } }
  $dl = Norm-Deadline $o.deadline
  $catOk = [int]("$($o.category)" -eq "$($gt.category)")
  $needsOk = [int]([bool]$o.needs_action -eq [bool]$gt.needs_action)
  $dlOk = [int](("$dl") -eq ("$($gt.deadline)"))
  $prOk = [int]("$($o.priority)" -eq "$($gt.priority)")
  $sm = "$($o.summary)"
  $smOk = [int]($sm.Length -gt 0 -and $sm.Length -le 20)
  if ($gt.needs_action) { $acOk = [int](("$($o.action)") -match [regex]::Escape($gt.keyword)) } else { $acOk = [int](("$($o.action)") -match '없음' -or ("$($o.action)").Trim() -eq '') }
  return [pscustomobject]@{ json=1; category=$catOk; needs=$needsOk; deadline=$dlOk; priority=$prOk; summary=$smOk; action=$acOk; got_deadline="$dl" }
}

function Row($short, $cond, $id, $s, $r, $raw) {
  return [pscustomobject]@{ model=$short; cond=$cond; id=$id; json=$s.json; category=$s.category; needs=$s.needs; deadline=$s.deadline; priority=$s.priority; summary=$s.summary; action=$s.action; got_deadline=$s.got_deadline; total_s=$r.total_s; load_s=$r.load_s; eval_s=$r.eval_s; tokens=$r.tokens; raw=$raw }
}

$rows = @()
$prog = "$base\progress_$tag.txt"
foreach ($m in $models) {
  $short = if ($m -match '1.2B') { '1.2B' } else { '7.8B' }
  "[$(Get-Date -f HH:mm:ss)] $short warmup" | Out-File $prog -Append -Encoding utf8
  $w = Call-Model $m '짧게 답해.' '안녕' $null
  $empty = [pscustomobject]@{ json=''; category=''; needs=''; deadline=''; priority=''; summary=''; action=''; got_deadline='' }
  $rows += Row $short 'warmup' 0 $empty $w ''
  foreach ($x in $mails) {
    foreach ($cond in 'A','B') {
      if ($cond -eq 'A') { $r = Call-Model $m $sysBase $x.mail 'json' } else { $r = Call-Model $m $sysRules $x.mail $schema }
      $o = Parse-Json $r.content
      $rows += Row $short $cond $x.id (Score $o $x.gt) $r ($r.content -replace "`r|`n",' ')
      if ($cond -eq 'B') {
        if ($null -ne $o) { $pp = Post-Process $o $x; $rows += Row $short 'C' $x.id (Score $pp $x.gt) $r ($pp | ConvertTo-Json -Compress) }
        else { $rows += Row $short 'C' $x.id (Score $null $x.gt) $r 'parse fail' }
      }
      "[$(Get-Date -f HH:mm:ss)] $short mail$($x.id) $cond $($r.total_s)s" | Out-File $prog -Append -Encoding utf8
    }
  }
  & $exe stop $m | Out-Null
}

$csv = ($rows | ConvertTo-Csv -NoTypeInformation) -join "`r`n"
[IO.File]::WriteAllText("$base\results_$tag.csv", $csv, $utf8)

$sum = @()
foreach ($g in ($rows | Where-Object { $_.cond -ne 'warmup' } | Group-Object model, cond)) {
  $n = $g.Group.Count
  $f = { param($k) [math]::Round((($g.Group | Measure-Object -Property $k -Sum).Sum / $n) * 100) }
  $sum += [pscustomobject]@{ group=$g.Name; n=$n; json=(& $f 'json'); category=(& $f 'category'); needs=(& $f 'needs'); deadline=(& $f 'deadline'); priority=(& $f 'priority'); summary=(& $f 'summary'); action=(& $f 'action'); avg_total_s=[math]::Round(($g.Group | Measure-Object total_s -Average).Average,1); avg_eval_s=[math]::Round(($g.Group | Measure-Object eval_s -Average).Average,1) }
}
$warm = $rows | Where-Object { $_.cond -eq 'warmup' } | ForEach-Object { "$($_.model) load=$($_.load_s)s total=$($_.total_s)s" }
$txt = (($sum | Format-Table -AutoSize | Out-String) + "`r`nwarmup:`r`n" + ($warm -join "`r`n"))
[IO.File]::WriteAllText("$base\summary_$tag.txt", $txt, $utf8)
'DONE' | Out-File "$base\done_$tag.txt" -Encoding utf8
