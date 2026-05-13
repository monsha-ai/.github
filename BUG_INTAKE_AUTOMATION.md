# Bug Intake Automation

This document describes the Intercom-to-Linear bug intake automation system.

## Overview

The `bug_intake_automation.py` script runs on a scheduled basis (via cron or similar) to:

1. Search Intercom for conversations tagged with "Bug Report" updated in the last 60 minutes
2. Filter out conversations already synced (those tagged with "linear-synced")
3. For each new bug conversation:
   - Extract user details (name, email, user ID)
   - Summarize the issue
   - Identify repro steps and attachments
   - Post a formatted comment to Linear issue ISSUE-281
   - Tag the Intercom conversation with "linear-synced"
   - Add an internal note with the Linear comment URL

## Setup

### Prerequisites

- Python 3.7+
- Intercom API token (with read/write access to conversations)
- Linear API token (with comment creation access)

### Installation

1. Install required dependencies:
```bash
pip install requests
```

2. Set environment variables:
```bash
export INTERCOM_API_TOKEN="your_intercom_api_token"
export LINEAR_API_TOKEN="your_linear_api_token"
```

3. Run the script:
```bash
python bug_intake_automation.py
```

## Environment Variables

- `INTERCOM_API_TOKEN`: Your Intercom API token (required)
- `LINEAR_API_TOKEN`: Your Linear API token (required)

## Linear Comment Format

Comments posted to ISSUE-281 follow this format:

```
**{one-line summary}** — [{user_name}]({intercom_url}) ({email})

{repro steps or relevant quoted text from the user}

{attachment links if any}

@adel
```

Comments are kept under approximately 150 words per specification.

## Automation Schedule

This script is designed to run on an hourly cron schedule:

```
0 * * * * cd /path/to/workspace && python bug_intake_automation.py
```

## How It Works

### Step 1: Search for Bug Reports

The script searches Intercom for conversations tagged "Bug Report" updated in the last 60 minutes using the Intercom Search API.

### Step 2: Filter Already-Synced Conversations

For each bug conversation found, the script checks if it already has the "linear-synced" tag. If so, it skips that conversation to prevent duplicate entries.

### Step 3: Extract Conversation Details

For each new bug conversation:
- Fetches full conversation thread including all messages and attachments
- Extracts user/contact information (name, email, ID)
- Identifies a one-line summary (from AI Title custom attribute or initial message)
- Collects repro steps from user messages
- Gathers attachment URLs

### Step 4: Post to Linear

Formats a comment combining all extracted information and posts it to ISSUE-281 with an @adel mention.

### Step 5: Update Intercom

- Adds "linear-synced" tag to prevent re-processing
- Adds an internal note with the Linear comment URL for reference

## Error Handling

The script includes comprehensive error handling:
- Failed API calls are logged with details
- If an API call fails, the process continues to the next step where possible
- If comment creation fails, the conversation is not tagged (to allow retry)
- All errors are logged with timestamps

## Logging

The script outputs logs to stdout with timestamps and log levels:
- `INFO`: Normal operation progress
- `WARNING`: Non-fatal issues (e.g., comment exceeds word limit)
- `ERROR`: Failed operations (API calls, tag additions, etc.)

## API Endpoints Used

### Intercom
- `POST /conversations/search` - Search for conversations
- `GET /conversations/{id}` - Get conversation details
- `GET /contacts/{id}` - Get contact information
- `POST /conversations/{id}/tags` - Add tag to conversation
- `POST /conversations/{id}/parts` - Add internal note

### Linear
- `POST /graphql` - GraphQL endpoint for comment creation

## Notes

- The script avoids duplicate processing by checking for the "linear-synced" tag
- Only summaries from the past 60 minutes are processed each run
- Comments are mentioned to @adel for visibility
- Screenshots and attachment URLs are preserved in the Linear comment
- Repro steps are extracted from user messages in the conversation thread

## Troubleshooting

### No conversations found
- Check that there are conversations with "Bug Report" tag in Intercom
- Verify the tag name exactly matches "Bug Report"
- Ensure the API token has read access to conversations

### Comments not posting
- Verify the LINEAR_API_TOKEN is valid and has permission to comment
- Check that ISSUE-281 exists in the Linear workspace
- Review error logs for GraphQL errors

### Tags not being added
- Verify the INTERCOM_API_TOKEN has write access to conversations
- Check that "linear-synced" tag exists in Intercom (create if necessary)
- Review error logs for API errors

## Future Enhancements

Potential improvements to consider:
- Support for multiple Linear issues (configurable)
- Custom tag names via environment variables
- Batch processing for high-volume bug reports
- Retry logic with exponential backoff
- Metrics/reporting on processed conversations
- Support for additional bug classification/prioritization
