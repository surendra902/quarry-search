@echo off
title Quarry Claude Referral Pass Collector
echo ========================================================
echo  Quarry Claude Referral Pass Harvester (24/7 Runner)
echo ========================================================
echo Active Sources: Exa, GitHub, Qiita, DEV.to, URLScan, Web Watchlist
echo Check interval: 10 minutes (600 seconds)
echo Telegram alerts: Configured to @suri8bot
echo ========================================================
python run_harvester.py --interval 600
pause
