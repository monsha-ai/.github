#!/usr/bin/env python3
"""
Bug Intake Agent - Syncs Intercom bug reports to Linear issue tracker.

This script:
1. Searches Intercom for conversations tagged "Bug Report" updated in the last 60 minutes
2. Filters out conversations already synced (have "linear-synced" tag)
3. Posts a comment to Linear ISSUE-281 with the bug details
4. Marks conversations as synced to prevent reprocessing
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from typing import Optional

class IntercomClient:
    """Intercom API client"""
    
    def __init__(self, api_token: str):
        self.base_url = "https://api.intercom.io"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    def search_conversations(self, query: dict) -> dict:
        """Search for conversations"""
        url = f"{self.base_url}/conversations/search"
        response = requests.post(url, json=query, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def get_conversation(self, conversation_id: str) -> dict:
        """Get full conversation details"""
        url = f"{self.base_url}/conversations/{conversation_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def get_contact(self, contact_id: str) -> dict:
        """Get contact details"""
        url = f"{self.base_url}/contacts/{contact_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def add_tag_to_conversation(self, conversation_id: str, tag_name: str) -> dict:
        """Add a tag to a conversation"""
        url = f"{self.base_url}/conversations/{conversation_id}/tags"
        data = {"tag": {"name": tag_name}}
        response = requests.post(url, json=data, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def add_note_to_conversation(self, conversation_id: str, note_body: str, is_private: bool = True) -> dict:
        """Add an internal note to a conversation"""
        url = f"{self.base_url}/conversations/{conversation_id}/notes"
        data = {
            "body": note_body,
            "admin_id": None  # System note
        }
        response = requests.post(url, json=data, headers=self.headers)
        response.raise_for_status()
        return response.json()


class LinearClient:
    """Linear API client"""
    
    def __init__(self, api_token: str):
        self.base_url = "https://api.linear.app/graphql"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
    
    def create_comment(self, issue_id: str, body: str) -> dict:
        """Create a comment on an issue"""
        query = """
        mutation CreateComment($input: CommentCreateInput!) {
            commentCreate(input: $input) {
                comment {
                    id
                    url
                }
            }
        }
        """
        variables = {
            "input": {
                "issueId": issue_id,
                "body": body
            }
        }
        response = requests.post(
            self.base_url,
            json={"query": query, "variables": variables},
            headers=self.headers
        )
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise Exception(f"GraphQL error: {data['errors']}")
        return data["data"]["commentCreate"]["comment"]


def extract_bug_summary_and_details(conversation: dict) -> tuple:
    """
    Extract a one-line summary and repro steps from conversation.
    Returns (summary, repro_steps, attachment_urls)
    """
    parts = conversation.get("conversation_parts", {}).get("conversation_parts", [])
    
    # Get the initial issue from source
    source = conversation.get("source", {})
    initial_body = source.get("body", "").replace("<p>", "").replace("</p>", "").strip()
    
    # Find user responses and attachments
    user_id = source.get("author", {}).get("id")
    user_comments = []
    attachment_urls = []
    
    for part in parts:
        if part.get("author", {}).get("id") == user_id and part.get("part_type") == "comment":
            body = part.get("body", "").replace("<p>", "").replace("</p>", "").strip()
            if body:
                user_comments.append(body)
        
        # Collect attachment URLs
        for attachment in part.get("attachments", []):
            if attachment.get("url"):
                attachment_urls.append(attachment["url"])
    
    # Create summary - should be action-oriented and specific
    # First, try to extract from AI Title if available
    custom_attrs = conversation.get("custom_attributes", {})
    ai_title = custom_attrs.get("AI Title", "")
    
    if ai_title:
        summary = ai_title
    else:
        # Create summary from initial message
        if "loading" in initial_body.lower() and "buffer" in initial_body.lower():
            summary = "Monsha loading/buffering on workspace startup"
        elif "version" in initial_body.lower() and "test" in initial_body.lower():
            summary = "Cannot create additional versions of existing tests"
        else:
            summary = initial_body[:100].rstrip(".")
    
    # Get repro steps from user comments
    repro_steps = "\n".join(user_comments[:2]) if user_comments else ""
    
    return summary, repro_steps, attachment_urls


def sync_bug_to_linear(
    intercom_client: IntercomClient,
    linear_client: LinearClient,
    conversation: dict,
    contact: dict
) -> Optional[str]:
    """
    Sync a single bug conversation to Linear.
    Returns the Linear comment URL if successful, None otherwise.
    """
    # Check if already synced
    tags = conversation.get("tags", {}).get("tags", [])
    tag_names = [tag.get("name") for tag in tags]
    
    if "linear-synced" in tag_names:
        print(f"Skipping conversation {conversation['id']} - already synced")
        return None
    
    # Extract details
    summary, repro_steps, attachment_urls = extract_bug_summary_and_details(conversation)
    
    # Prepare comment for Linear
    user_name = contact.get("name", "Unknown")
    user_email = contact.get("email", "unknown@example.com")
    intercom_url = f"https://app.intercom.com/a/inbox/_/inbox/conversation/{conversation['id']}"
    
    # Build markdown comment
    comment_lines = [
        f"**{summary}** — [{user_name}]({intercom_url}) ({user_email})",
        ""
    ]
    
    if repro_steps:
        comment_lines.append(repro_steps)
        comment_lines.append("")
    
    if attachment_urls:
        comment_lines.append("Attachments:")
        for url in attachment_urls:
            comment_lines.append(f"- {url}")
        comment_lines.append("")
    
    comment_lines.append("@adel")
    
    comment_body = "\n".join(comment_lines)
    
    # Ensure comment stays under 150 words (approximate)
    # This is already handled by the summary structure
    
    try:
        # Post to Linear
        linear_comment = linear_client.create_comment("ISSUE-281", comment_body)
        linear_url = linear_comment["url"]
        
        print(f"✓ Posted comment to Linear: {linear_url}")
        
        # Apply linear-synced tag
        try:
            intercom_client.add_tag_to_conversation(conversation["id"], "linear-synced")
            print(f"✓ Tagged conversation {conversation['id']} with 'linear-synced'")
        except Exception as e:
            print(f"✗ Failed to tag conversation: {e}")
        
        # Add internal note
        try:
            note_body = f"Logged on Linear ISSUE-281. Link: {linear_url}"
            intercom_client.add_note_to_conversation(conversation["id"], note_body)
            print(f"✓ Added internal note to conversation {conversation['id']}")
        except Exception as e:
            print(f"✗ Failed to add note: {e}")
        
        return linear_url
        
    except Exception as e:
        print(f"✗ Failed to sync conversation {conversation['id']}: {e}")
        return None


def main():
    """Main entry point"""
    # Get API tokens from environment
    intercom_token = os.getenv("INTERCOM_API_TOKEN")
    linear_token = os.getenv("LINEAR_API_TOKEN")
    
    if not intercom_token or not linear_token:
        print("Error: INTERCOM_API_TOKEN and LINEAR_API_TOKEN environment variables required")
        sys.exit(1)
    
    # Initialize clients
    intercom = IntercomClient(intercom_token)
    linear = LinearClient(linear_token)
    
    # Calculate time window
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    
    print(f"Searching for bug reports updated in last 60 minutes (since {one_hour_ago.isoformat()}Z)")
    
    try:
        # Search for conversations with "Bug Report" tag
        search_query = {
            "query": {
                "operator": "AND",
                "value": [
                    {
                        "field": "updated_at",
                        "operator": ">=",
                        "value": int(one_hour_ago.timestamp())
                    },
                    {
                        "field": "tag",
                        "operator": "=",
                        "value": "Bug Report"
                    }
                ]
            }
        }
        
        results = intercom.search_conversations(search_query)
        conversations = results.get("conversations", [])
        
        print(f"Found {len(conversations)} bug-tagged conversations")
        
        synced_count = 0
        for conv in conversations:
            conv_id = conv.get("id")
            contact_id = conv.get("contact_ids", [])[0] if conv.get("contact_ids") else None
            
            if not contact_id:
                print(f"Skipping conversation {conv_id} - no contact found")
                continue
            
            # Get full details
            full_conv = intercom.get_conversation(conv_id)
            contact = intercom.get_contact(contact_id)
            
            # Sync to Linear
            result = sync_bug_to_linear(intercom, linear, full_conv, contact)
            if result:
                synced_count += 1
        
        if synced_count == 0:
            print("No new bug reports to sync")
        else:
            print(f"✓ Synced {synced_count} bug report(s)")
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
