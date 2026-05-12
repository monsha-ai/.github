#!/usr/bin/env python3
"""
Bug Intake Automation Workflow
Syncs Intercom bug reports to Linear ISSUE-281
"""

import json
from datetime import datetime, timedelta

# Current timestamp
current_time = datetime.utcnow()
sixty_minutes_ago = current_time - timedelta(minutes=60)

# Bug conversations found and processed
processed_bugs = []

# Bug #1: Linda M. - Worksheet download issue
bug_1 = {
    "intercom_id": "215474198427643",
    "contact_name": "Linda M.",
    "contact_email": "ilyyymariee7@gmail.com",
    "contact_id": "69fb5a8673bd6c93a2e6d930",
    "summary": "Worksheet download fails on mobile",
    "intercom_url": "https://app.intercom.com/a/inbox/_/inbox/conversation/215474198427643",
    "linear_comment_id": "c4eb8799-d8d3-47be-af44-7fd6a5a84461",
    "linear_comment_url": "https://linear.app/monsha/issue/ISSUE-281#comment-c4eb8799-d8d3-47be-af44-7fd6a5a84461",
    "status": "comment_posted",
    "next_steps": [
        "Apply 'linear-synced' tag to conversation 215474198427643",
        "Add internal note: 'Logged on Linear ISSUE-281. Link: https://linear.app/monsha/issue/ISSUE-281#comment-c4eb8799-d8d3-47be-af44-7fd6a5a84461'"
    ]
}

processed_bugs.append(bug_1)

# Summary
print("=" * 70)
print("BUG INTAKE AUTOMATION - EXECUTION LOG")
print("=" * 70)
print(f"Run time: {current_time.isoformat()}Z")
print(f"Time window: Last 60 minutes (since {sixty_minutes_ago.isoformat()}Z)")
print()

print(f"Bugs processed: {len(processed_bugs)}")
print()

for i, bug in enumerate(processed_bugs, 1):
    print(f"BUG #{i}: {bug['summary']}")
    print(f"  From: {bug['contact_name']} <{bug['contact_email']}>")
    print(f"  Intercom: {bug['intercom_url']}")
    print(f"  Linear Comment ID: {bug['linear_comment_id']}")
    print(f"  Status: {bug['status']}")
    print(f"  Linear Comment URL: {bug['linear_comment_url']}")
    print()
    print("  MANUAL ACTIONS NEEDED (MCP limitation):")
    for step in bug['next_steps']:
        print(f"    - {step}")
    print()

print("=" * 70)
print("NOTE: The following require manual execution via Intercom UI:")
print("  1. Apply 'linear-synced' tag to each conversation")
print("  2. Add internal note with Linear comment URL")
print("=" * 70)

# Save summary as JSON for reference
summary = {
    "run_timestamp": current_time.isoformat() + "Z",
    "bugs_processed": len(processed_bugs),
    "bugs": processed_bugs
}

with open("/workspace/bug_sync_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print("\nSummary saved to /workspace/bug_sync_summary.json")
