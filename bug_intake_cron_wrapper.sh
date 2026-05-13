#!/bin/bash
# Bug Intake Automation - Cron Wrapper
# This script is designed to be run hourly via cron
# Cron entry: 0 * * * * /path/to/bug_intake_cron_wrapper.sh

# Set the working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Source environment variables if they exist
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(cat "$SCRIPT_DIR/.env" | grep -v '^#' | xargs)
fi

# Ensure required environment variables are set
if [ -z "$INTERCOM_API_TOKEN" ] || [ -z "$LINEAR_API_TOKEN" ]; then
    echo "$(date): ERROR - Missing INTERCOM_API_TOKEN or LINEAR_API_TOKEN" >&2
    exit 1
fi

# Run the automation script
python3 "$SCRIPT_DIR/bug_intake_automation.py" 2>&1 | while read line; do
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $line"
done

exit_code=${PIPESTATUS[0]}

if [ $exit_code -ne 0 ]; then
    echo "$(date): ERROR - Script exited with code $exit_code" >&2
fi

exit $exit_code
