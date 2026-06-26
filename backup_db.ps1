$timestamp = Get-Date -Format "yyyyMMdd_HHmm"
$backupDir = "C:\Users\buffa\NLP_Task_AI_Report\backup\$timestamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

Write-Host "DB 백업 시작: $backupDir"
mongodump --uri="mongodb://127.0.0.1:27017/nlp_lecture" --out="$backupDir"
Write-Host "백업 완료!"
