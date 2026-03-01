#!/bin/bash
pkill -9 "Google Chrome"
sleep 1
CHROME_BOT_PROFILE=$HOME/chrome-bot-profile
mkdir -p $CHROME_BOT_PROFILE
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=$CHROME_BOT_PROFILE --no-first-run%