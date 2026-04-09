#!/bin/bash
set -e
cd /home/cosmo/icm-production
echo "Updating icm-production..."
git add -A
git commit -m "Update: Add time extraction for appointments and mark past dates as done" || echo "Nothing to commit"
git push origin main || echo "Push failed or no remote"
echo "✅ icm-production updated"
