@echo off
cd /d "c:\Users\Errachandhanam\Videos\1\search_task"
if not exist "logs" mkdir "logs"
echo ======================================================== >> logs\harvester_20min.log
echo [%DATE% %TIME%] Starting 20-minute Quarry Harvest Cycle >> logs\harvester_20min.log
echo ======================================================== >> logs\harvester_20min.log

python run_harvester.py --oneshot --interval 1200 --export-snapshot data/snapshot.json --auto-push >> logs\harvester_20min.log 2>&1

echo [%DATE% %TIME%] 20-minute Harvest Cycle Completed >> logs\harvester_20min.log
