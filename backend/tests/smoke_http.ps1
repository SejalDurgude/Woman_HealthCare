param([string]$BaseUrl = 'http://127.0.0.1:8000')
$ErrorActionPreference = 'Stop'
$pdfPath = Join-Path $PSScriptRoot 'http-smoke-summary.pdf'
$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$emailA = "smoke-a-$stamp@example.com"
$emailB = "smoke-b-$stamp@example.com"
$password = 'synthetic-only-test-passphrase'
$accountA = $null
$accountB = $null
$headersA = $null
$headersB = $null
try {
    $health = Invoke-RestMethod "$BaseUrl/api/health"
    if ($health.status -ne 'ok') { throw 'Backend health check failed.' }
    $frontend = Invoke-WebRequest "$BaseUrl/"
    if ($frontend.StatusCode -ne 200) { throw 'Frontend is unavailable. Run npm run build before this smoke check.' }

    $bodyA = @{name='Synthetic Smoke A';email=$emailA;password=$password} | ConvertTo-Json -Compress
    $bodyB = @{name='Synthetic Smoke B';email=$emailB;password=$password} | ConvertTo-Json -Compress
    $accountA = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/auth/register" -ContentType 'application/json' -Body $bodyA
    $headersA = @{Authorization="Bearer $($accountA.access_token)"}
    $accountB = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/auth/register" -ContentType 'application/json' -Body $bodyB
    $headersB = @{Authorization="Bearer $($accountB.access_token)"}
    $login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/auth/login" -ContentType 'application/json' -Body (@{email=$emailA;password=$password}|ConvertTo-Json -Compress)

    $today = (Get-Date).ToString('yyyy-MM-dd')
    $symptom = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/symptoms" -Headers $headersA -ContentType 'application/json' -Body (@{symptom='Headache';recorded_on=$today;severity=5;description='synthetic smoke record'}|ConvertTo-Json -Compress)
    $symptom = Invoke-RestMethod -Method Put -Uri "$BaseUrl/api/symptoms/$($symptom.id)" -Headers $headersA -ContentType 'application/json' -Body (@{symptom='Headache';recorded_on=$today;severity=7;description='synthetic updated record'}|ConvertTo-Json -Compress)
    $otherResponse = Invoke-RestMethod -Uri "$BaseUrl/api/symptoms" -Headers $headersB
    $otherRecordCount = if ($null -eq $otherResponse) { 0 } else { @($otherResponse).Count }
    $denied = Invoke-WebRequest -Method Put -Uri "$BaseUrl/api/symptoms/$($symptom.id)" -Headers $headersB -ContentType 'application/json' -Body (@{symptom='Headache';recorded_on=$today;severity=2}|ConvertTo-Json -Compress) -SkipHttpErrorCheck
    if ($otherRecordCount -ne 0 -or $denied.StatusCode -ne 404) { throw 'User record ownership check failed.' }
    $insights = Invoke-RestMethod -Uri "$BaseUrl/api/insights" -Headers $headersA
    $deletedSymptom = Invoke-WebRequest -Method Delete -Uri "$BaseUrl/api/symptoms/$($symptom.id)" -Headers $headersA -SkipHttpErrorCheck
    if ($deletedSymptom.StatusCode -ne 204) { throw 'Symptom deletion failed.' }

    $null = Invoke-RestMethod -Method Put -Uri "$BaseUrl/api/cycle/profile" -Headers $headersA -ContentType 'application/json' -Body '{"age":29,"life_stage":"postpartum","acne":0}'
    $cycleDates = @((Get-Date).AddDays(-70),(Get-Date).AddDays(-68),(Get-Date).AddDays(-42),(Get-Date).AddDays(-40))
    foreach ($cycleDate in $cycleDates) {
        $cycleBody = @{recorded_on=$cycleDate.ToString('yyyy-MM-dd');flow=3;pain=2;tags=@('cramps')} | ConvertTo-Json -Compress
        $null = Invoke-RestMethod -Method Put -Uri "$BaseUrl/api/cycle/days" -Headers $headersA -ContentType 'application/json' -Body $cycleBody
    }
    $cycleLogs = @(Invoke-RestMethod -Uri "$BaseUrl/api/cycle/days" -Headers $headersA)
    $firstCycle = $cycleLogs[0]
    if ($firstCycle -is [array]) { $firstCycle = $firstCycle[0] }
    $cycleId = [int]$firstCycle.id
    $deletedCycle = Invoke-WebRequest -Method Delete -Uri "$BaseUrl/api/cycle/days/$cycleId" -Headers $headersA -SkipHttpErrorCheck
    if ($deletedCycle.StatusCode -ne 204) { throw "Cycle log deletion failed for id $cycleId`: HTTP $($deletedCycle.StatusCode)" }
    $null = Invoke-RestMethod -Method Put -Uri "$BaseUrl/api/cycle/days" -Headers $headersA -ContentType 'application/json' -Body (@{recorded_on=$cycleDates[0].ToString('yyyy-MM-dd');flow=3;pain=2;tags=@('cramps')}|ConvertTo-Json -Compress)
    $analysis = Invoke-RestMethod -Uri "$BaseUrl/api/cycle/analyze" -Headers $headersA
    $quick = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/cycle/quick" -Headers $headersA -ContentType 'application/json' -Body '{"age":29,"life_stage":"postpartum","phq_interest":2,"phq_down":2}'
    $phq = @($quick.conditions | ForEach-Object { $_.evidence } | Where-Object { $_.text -match 'PHQ-2' })
    if ($analysis.conditions.Count -lt 1 -or $phq.Count -eq 0) { throw 'Screening response did not contain expected results.' }

    $pdfResponse = Invoke-WebRequest -Method Post -Uri "$BaseUrl/api/reports/pdf" -Headers $headersA -ContentType 'application/json' -Body '{"sections":["entries","cycles","observations","questions"]}' -OutFile $pdfPath -PassThru
    $pdfSignature = [System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes($pdfPath)[0..3])
    if ($pdfResponse.StatusCode -ne 200 -or $pdfSignature -ne '%PDF') { throw 'PDF report generation failed.' }
    $export = Invoke-RestMethod -Uri "$BaseUrl/api/export" -Headers $headersA
    if ($export.cycle_days.Count -ne 4 -or 'cycle_profile' -notin $export.PSObject.Properties.Name) { throw 'Health data export omitted cycle data.' }
    $assistant = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/assistant/chat" -ContentType 'application/json' -Body '{"question":"How can I track my period?"}'

    $null = Invoke-RestMethod -Method Delete -Uri "$BaseUrl/api/account/data" -Headers $headersA
    $remainingRows = Invoke-RestMethod -Uri "$BaseUrl/api/cycle/days" -Headers $headersA
    $remaining = if ($null -eq $remainingRows) { 0 } else { @($remainingRows).Count }
    if ($remaining -ne 0) { throw 'Delete all data did not remove cycle records.' }
    $null = Invoke-RestMethod -Method Delete -Uri "$BaseUrl/api/account" -Headers $headersA
    $null = Invoke-RestMethod -Method Delete -Uri "$BaseUrl/api/account" -Headers $headersB

    [pscustomobject]@{
        Health = $health.status
        FrontendHttp = $frontend.StatusCode
        RegistrationAndLogin = 'passed'
        CrossUserListCount = $otherRecordCount
        CrossUserUpdateStatus = $denied.StatusCode
        SymptomCreateUpdateDelete = 'passed'
        SymptomInsightDays = $insights.distinct_logged_days
        CycleCrudAndAnalyze = 'passed'
        ScreeningConditions = $analysis.conditions.Count
        QuickQuestionnaire = 'passed'
        PdfStatus = $pdfResponse.StatusCode
        PdfSignature = $pdfSignature
        ExportCycleRecords = $export.cycle_days.Count
        AssistantFallbackMode = $assistant.mode
        DeleteAllAndAccountDelete = 'passed'
    } | Format-List
}
finally {
    if ($headersA) { try { Invoke-RestMethod -Method Delete -Uri "$BaseUrl/api/account" -Headers $headersA | Out-Null } catch {} }
    if ($headersB) { try { Invoke-RestMethod -Method Delete -Uri "$BaseUrl/api/account" -Headers $headersB | Out-Null } catch {} }
    Remove-Item -LiteralPath $pdfPath -Force -ErrorAction SilentlyContinue
}
