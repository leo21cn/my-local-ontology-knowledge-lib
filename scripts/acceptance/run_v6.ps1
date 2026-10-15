$ErrorActionPreference = "Stop"
$env:KB_AUTH_TOKEN = ((Get-Content .env | Where-Object { $_ -match '^KB_AUTH_TOKEN=' }) -split '=',2)[1]
$h = @{ Authorization = "Bearer $env:KB_AUTH_TOKEN" }
$enc = [System.Text.Encoding]::UTF8
$base = "http://127.0.0.1:8101/api/v1"
$corpus = "c01bc5ea859a"
$dir = "D:\szp\work\my-center-knowledge-lib\scripts\acceptance"

function Post-Json($uri, $file) {
  $body = [System.IO.File]::ReadAllText("$dir\$file", $enc)
  return Invoke-RestMethod -Method Post -Uri $uri -Headers $h -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
}

# create entities
$p1 = Post-Json "$base/entities?corpus_id=$corpus" "v6-person.json"
$p2 = Post-Json "$base/entities?corpus_id=$corpus" "v6-project.json"
"person eid=$($p1.data.eid)"
"project eid=$($p2.data.eid)"

# create valid relation person -> project
$relBody = '{"from_eid":"' + $p1.data.eid + '","to_eid":"' + $p2.data.eid + '","type_iri":"http://kb.local/o/acc#belongsTo"}'
$rel = Invoke-RestMethod -Method Post -Uri "$base/relations" -Headers $h -ContentType "application/json" -Body $relBody
"relation created=$($rel.data.created)"

# patch belongsTo range -> Person (violates the existing relation)
$patchBody = [System.IO.File]::ReadAllText("$dir\patch-belongs-range-person.json", $enc)
$patch = Invoke-RestMethod -Method Patch -Uri "$base/ontology/object-properties/http%3A%2F%2Fkb.local%2Fo%2Facc%23belongsTo?corpus_id=$corpus" -Headers $h -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($patchBody))
"V6 violations=$($patch.data.violations.Count) queued=$($patch.data.queued)"

# verify pending contains the violation
$pending = Invoke-RestMethod -Method Get -Uri "$base/pending?corpus_id=$corpus" -Headers $h
"pending violations:"
$pending.data | Where-Object { $_.kind -eq 'violation' } | ForEach-Object { "  pid=$($_.pid) reason=$($_.payload.reason) from=$($_.payload.from)" }

# restore range back to Project
$restoreBody = [System.IO.File]::ReadAllText("$dir\patch-belongs-range-project.json", $enc)
$restore = Invoke-RestMethod -Method Patch -Uri "$base/ontology/object-properties/http%3A%2F%2Fkb.local%2Fo%2Facc%23belongsTo?corpus_id=$corpus" -Headers $h -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($restoreBody))
"restored violations=$($restore.data.violations.Count)"

# resolve all open pending items (reject) to clear the queue
$pending2 = Invoke-RestMethod -Method Get -Uri "$base/pending?corpus_id=$corpus" -Headers $h
foreach ($item in $pending2.data) {
  $r = Invoke-RestMethod -Method Post -Uri "$base/pending/$($item.pid)/resolve" -Headers $h -ContentType "application/json" -Body '{"action":"reject"}'
  "resolved $($item.pid) -> $($r.data.status)"
}
$pending3 = Invoke-RestMethod -Method Get -Uri "$base/pending?corpus_id=$corpus" -Headers $h
"V6 queue after resolve: $($pending3.data.Count) open items"

# save state for V7
Set-Content -Path "$env:TEMP\v6-person-eid.txt" -Value $p1.data.eid
Set-Content -Path "$env:TEMP\v6-project-eid.txt" -Value $p2.data.eid
