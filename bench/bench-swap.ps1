param([string]$base='http://127.0.0.1:8080/upstream/qwen3.6-35b-a3b', [int]$iters = 3, [int]$npred = 128, [string]$name='qwen-swap')
$ErrorActionPreference = 'Stop'

# Health check
try { $h = Invoke-RestMethod -Uri "$base/health" -TimeoutSec 10 } catch { Write-Output "SERVER NOT REACHABLE on $base"; return }
$vram = (nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits)
Write-Output "=== BENCH name=$name base=$base iters=$iters npred=$npred ==="
Write-Output "VRAM used/total (MiB): $vram"

# Same 3 distinct prompts (~6K tokens each) as bench-live.ps1
$c1 = 'The quick brown fox jumps over the lazy dog and then keeps running through the quiet forest. '
$c2 = 'In distributed systems a write-ahead log records each mutation before it is applied to the primary store, so that after a crash the node can replay uncommitted entries and reach a consistent state again. '
$c3 = 'She walked along the shoreline at dawn, counting the gulls that circled the fishing boats, while the tide slowly pulled the wet sand from beneath her bare feet and the town behind her began to wake. '
$prompts = @(
  @{ tag='fox';  text = ($c1 * 350) },
  @{ tag='tech'; text = ($c2 * 150) },
  @{ tag='prose';text = ($c3 * 160) }
)

# Warmup (discarded) — 2 full-size passes so measured iters are warm (allocator/graph)
$wbody = @{ prompt = ($c1 * 350); n_predict = 32; temperature = 0; cache_prompt = $false; ignore_eos = $true } | ConvertTo-Json
foreach($w in 1..2){ try { Invoke-RestMethod -Uri "$base/completion" -Method Post -ContentType 'application/json' -Body $wbody -TimeoutSec 300 | Out-Null } catch { Write-Output "warmup $w failed: $($_.Exception.Message)" } }
Write-Output "warmup done (2 full passes)"

$allpp = @(); $alltg = @()
foreach ($pr in $prompts) {
  $ppv = @(); $tgv = @()
  for ($k=1; $k -le $iters; $k++) {
    $body = @{ prompt = $pr.text; n_predict = $npred; temperature = 0; cache_prompt = $false; ignore_eos = $true } | ConvertTo-Json
    $resp = Invoke-RestMethod -Uri "$base/completion" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 300
    $t = $resp.timings
    $ppv += $t.prompt_per_second; $tgv += $t.predicted_per_second
    Write-Output ("  [$($pr.tag)] iter $k : prompt_n=$($t.prompt_n) predicted_n=$($t.predicted_n)  pp=$([math]::Round($t.prompt_per_second,1))  tg=$([math]::Round($t.predicted_per_second,1))")
  }
  $ppAvg = ($ppv | Measure-Object -Average).Average
  $tgAvg = ($tgv | Measure-Object -Average).Average
  Write-Output ("  [$($pr.tag)] AVG  pp=$([math]::Round($ppAvg,1)) tok/s  tg=$([math]::Round($tgAvg,1)) tok/s")
  $allpp += $ppv; $alltg += $tgv
}
$ppO = ($allpp | Measure-Object -Average).Average
$tgO = ($alltg | Measure-Object -Average).Average
Write-Output ("=== OVERALL AVG ($name) : pp=$([math]::Round($ppO,1)) tok/s  tg=$([math]::Round($tgO,1)) tok/s  (n=$($allpp.Count) runs) ===")
