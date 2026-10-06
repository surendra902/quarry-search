@echo off
title Quarry Claude Referral Pass Harvester (20-Min Continuous Runner)
echo ========================================================
echo  Quarry Claude Referral Pass Harvester (20-Min Continuous)
echo ========================================================
echo Active Sources: Exa, GitHub, Qiita, DEV.to, URLScan, Web Watchlist
echo Check interval: 20 minutes (1200 seconds)
echo Telegram alerts: Enabled to @suri8bot
echo Auto-Sync: Commits and pushes to GitHub/Vercel on discovery
echo ========================================================
python run_harvester.py --interval 1200 --auto-push
pause
