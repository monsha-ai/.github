# Bug Intake Agent

Automated agent that runs hourly to forward Intercom bug reports to Linear ISSUE-281.

## Overview

This agent:
1. Fetches Intercom conversations with the "Bug Report" tag updated in the last 60 minutes
2. Skips conversations already synced (with "linear-synced" tag)
3. For each new bug report:
   - Extracts user details (name, ID, email)
   - Extracts a one-line summary and repro steps
   - Collects attachment/screenshot URLs
   - Posts a formatted comment to Linear ISSUE-281
   - Tags the conversation with "linear-synced"
   - Adds an internal note with the Linear comment link
4. Exits silently if no new bug reports are found

## Setup

### Environment Variables

The agent requires two environment variables to be set:

- `INTERCOM_TOKEN`: Your Intercom API authentication token
- `LINEAR_TOKEN`: Your Linear API authentication token

These should be configured as secrets in the Cursor Dashboard:
- Go to Cloud Agents > Secrets
- Add `INTERCOM_TOKEN` and `LINEAR_TOKEN` with their respective values

### Running the Agent

The agent is triggered automatically via a cron job that runs hourly (`0 * * * *`).

To run manually:
```bash
node bug-intake-agent.js
```

## Implementation Details

### Intercom API Integration

- **Search Conversations**: Uses the `/conversations/search` endpoint with a query DSL to find conversations with the "Bug Report" tag updated in the last 60 minutes.
- **Get Conversation Details**: Fetches full conversation thread including messages and attachments.
- **Get Contact Info**: Retrieves user details from the contact record.
- **Apply Tags**: Tags conversations with "linear-synced" to prevent re-processing.
- **Add Internal Notes**: Adds private notes with the Linear comment link for tracking.

### Linear API Integration

- **Post Comments**: Uses GraphQL mutation to post comments on ISSUE-281.
- **Capture Comment URL**: The response includes the comment URL for linking back to Intercom.

### Comment Format

Comments posted to Linear follow this format:
```
**{one-line summary}** — [{name}]({intercom_url}) ({email})

{repro steps or relevant quoted text}

{attachment links}

@adel
```

All comments are kept under ~150 words and mention `@adel` for visibility.

## Error Handling

The agent:
- Logs all errors to the console
- Continues processing other conversations if one fails
- Skips conversations that fail to fetch or process
- Exits silently if no new bug reports exist (as per requirements)

## Tag Management

- **Bug Report**: The tag that marks conversations as bug reports
- **linear-synced**: Applied after a conversation is successfully synced to Linear, preventing duplicates

## Notes

- Duplicate comments are prevented by the "linear-synced" tag
- Summaries are action-oriented and specific (not generic like "User reports problem")
- Non-English bug reports keep quoted text as-is but summaries are in English
- Only comments on ISSUE-281; never creates new Linear issues
