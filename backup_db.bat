@echo off
set BACKUP_DIR=C:\Users\buffa\NLP_Task_AI_Report\backup\%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%
set BACKUP_DIR=%BACKUP_DIR: =0%
mkdir "%BACKUP_DIR%"

echo DB 백업 시작: %BACKUP_DIR%
mongodump --uri="mongodb://127.0.0.1:27017/nlp_lecture" --out="%BACKUP_DIR%"

echo 완료!
pause
