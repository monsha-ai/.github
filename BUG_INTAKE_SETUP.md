# Bug Intake Agent Setup

## Overview

The Bug Intake Agent automatically syncs bug reports from Intercom to Linear. It:

1. Fetches Intercom conversations tagged "Bug Report" updated in the last 60 minutes
2. Filters out conversations already synced (have "linear-synced" tag)
3. Posts a comment to Linear ISSUE-281 with bug details
4. Marks conversations as synced to prevent reprocessing
5. Adds internal notes to Intercom conversations with the Linear link

## Prerequisites

- Python 3.7+
- `requests` library: `pip install requests`

## Configuration

Set the following environment variables:

```bash
export INTERCOM_API_TOKEN="your_intercom_token_here"
export LINEAR_API_TOKEN="your_linear_token_here"
```

## Obtaining API Tokens

### Intercom API Token

1. Go to https://app.intercom.com/a/apps/_/settings/api-keys
2. Create a new Access Token with these permissions:
   - `conversations:read`
   - `conversations:write` (for tagging and notes)
   - `contacts:read`
3. Copy the token

### Linear API Token

1. Go to https://linear.app/settings/api
2. Create a new API key
3. Copy the token

## Running the Agent

### One-time run:
```bash
python3 bug-intake-agent.py
```

### Scheduled run (cron):
```bash
0 * * * * cd /workspace && python3 bug-intake-agent.py >> /var/log/bug-intake.log 2>&1
```

This runs the agent every hour at the top of the hour.

## How It Works

### Conversation Discovery

The agent searches Intercom for conversations that:
- Have the "Bug Report" tag
- Were updated in the last 60 minutes
- Don't already have the "linear-synced" tag

### Bug Summary Generation

For each bug, the agent extracts:
- **Summary**: A one-line, action-oriented description (e.g., "Geometry tool crashes when inserting circle on Safari")
- **Repro Steps**: Relevant quoted text from the user describing how to reproduce
- **Attachments**: Links to screenshots or other files
- **Contact Info**: User name, ID, and email

### Linear Comment Format

Comments posted to ISSUE-281 follow this format:

```
**{summary}** — [{name}]({intercom_url}) ({email})

{repro steps or relevant quoted text}

{attachment links if any}

@adel
```

Keep comments under ~150 words. Quote users directly only when exact wording matters.

## Deduplication

The agent prevents duplicate processing by:

1. **Checking for "linear-synced" tag**: Before processing a conversation, it checks if it already has this tag
2. **Adding tag after sync**: Once successfully synced, it adds the "linear-synced" tag to the conversation
3. **Internal note**: An internal note is added with the Linear comment URL for reference

## Manual Sync

If you need to manually sync a specific conversation:

1. Find the conversation ID in Intercom's URL
2. Ensure it has the "Bug Report" tag
3. Run the agent - it will pick it up if it doesn't have "linear-synced" tag
4. Or modify the agent to target specific conversation IDs

## Troubleshooting

### API Token Errors

If you see "Unauthorized" errors:
- Verify the token is correct and hasn't expired
- Check that the token has the required permissions
- Regenerate the token if needed

### Rate Limiting

Intercom and Linear have rate limits:
- Intercom: 500 requests per minute
- Linear: Rate limits vary by plan

The agent is designed to process incrementally, so it shouldn't hit rate limits in normal usage.

### Failed Conversations

If a conversation fails to sync:
- The agent will log the error
- The "linear-synced" tag won't be applied
- The conversation will be retried in the next hour's run

## Testing

To test with MCP clients (Cursor's MCP servers):

The agent can also be run through Cursor's MCP servers if you configure Intercom and Linear MCPs. However, note that the current Intercom MCP is read-only for conversation tagging/notes, so the full workflow requires the REST API directly.

## Current Limitations

### MCP-Based Implementation

When using Cursor's MCP servers:
- ✓ Searching for bug conversations works
- ✓ Getting conversation details works
- ✓ Posting comments to Linear works
- ✗ Tagging conversations in Intercom requires direct API
- ✗ Adding internal notes requires direct API

The Python script above uses the REST API directly to support the full workflow.

## Next Steps

1. Obtain API tokens from both Intercom and Linear
2. Set environment variables
3. Run `python3 bug-intake-agent.py`
4. Verify comments appear on https://linear.app/monsha/issue/ISSUE-281
5. Set up cron job for hourly execution

## Example Output

```
Searching for bug reports updated in last 60 minutes (since 2026-05-12T08:03:51Z)
Found 1 bug-tagged conversations
✓ Posted comment to Linear: https://linear.app/monsha/issue/ISSUE-281#comment-34aba3a8-529f-4fa2-9003-23136f9fefc4
✓ Tagged conversation 215474154263922 with 'linear-synced'
✓ Added internal note to conversation 215474154263922
✓ Synced 1 bug report(s)
```
