#!/usr/bin/env python3
"""
Bug intake automation for Intercom to Linear syncing.
Fetches Intercom bug reports and posts them to Linear ISSUE-281.
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IntercomClient:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.intercom.io"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
        }

    def search_conversations(self, query: str) -> List[Dict]:
        """Search conversations using Intercom Search API."""
        url = f"{self.base_url}/conversations/search"
        payload = {"query": {"field": "tag", "operator": "eq", "value": query}}
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json().get("conversations", [])
        except requests.RequestException as e:
            logger.error(f"Failed to search conversations: {e}")
            return []

    def get_conversation(self, conversation_id: str) -> Optional[Dict]:
        """Get full conversation details."""
        url = f"{self.base_url}/conversations/{conversation_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get conversation {conversation_id}: {e}")
            return None

    def get_contact(self, contact_id: str) -> Optional[Dict]:
        """Get contact details."""
        url = f"{self.base_url}/contacts/{contact_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get contact {contact_id}: {e}")
            return None

    def add_tag_to_conversation(self, conversation_id: str, tag_name: str) -> bool:
        """Add a tag to a conversation."""
        url = f"{self.base_url}/conversations/{conversation_id}/tags"
        payload = {"tag": {"name": tag_name}}
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            logger.info(f"Added tag '{tag_name}' to conversation {conversation_id}")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to add tag to conversation {conversation_id}: {e}")
            return False

    def add_internal_note(self, conversation_id: str, body: str) -> bool:
        """Add an internal note to a conversation."""
        url = f"{self.base_url}/conversations/{conversation_id}/parts"
        payload = {
            "part_type": "internal_note",
            "body": body,
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            logger.info(f"Added internal note to conversation {conversation_id}")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to add internal note to conversation {conversation_id}: {e}")
            return False

    def has_tag(self, conversation: Dict, tag_name: str) -> bool:
        """Check if conversation has a specific tag."""
        tags = conversation.get("tags", {}).get("tags", [])
        return any(tag.get("name") == tag_name for tag in tags)


class LinearClient:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.linear.app/graphql"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    def create_comment(self, issue_id: str, body: str) -> Optional[Dict]:
        """Create a comment on a Linear issue."""
        query = """
        mutation CreateComment($issueId: String!, $body: String!) {
            commentCreate(input: {issueId: $issueId, body: $body}) {
                comment {
                    id
                    url
                    body
                }
            }
        }
        """
        
        variables = {
            "issueId": issue_id,
            "body": body,
        }
        
        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json={"query": query, "variables": variables}
            )
            response.raise_for_status()
            result = response.json()
            
            if "errors" in result:
                logger.error(f"GraphQL error: {result['errors']}")
                return None
                
            return result.get("data", {}).get("commentCreate", {}).get("comment")
        except requests.RequestException as e:
            logger.error(f"Failed to create comment on Linear: {e}")
            return None


def extract_summary(conversation: Dict) -> str:
    """Extract a one-line summary from conversation."""
    # Get the initial message body
    source = conversation.get("source", {})
    body = source.get("body", "")
    
    # Clean HTML tags for readability
    import re
    body = re.sub(r"<[^>]+>", "", body)
    body = body.strip()
    
    # Get custom AI title if available
    custom_attrs = conversation.get("custom_attributes", {})
    ai_title = custom_attrs.get("AI Title", "")
    
    if ai_title:
        return ai_title
    
    # Otherwise use first 100 chars of body
    if body:
        return body[:100].rstrip() + ("..." if len(body) > 100 else "")
    
    return "Bug Report"


def extract_repro_steps(conversation: Dict) -> Optional[str]:
    """Extract repro steps from conversation parts."""
    parts = conversation.get("conversation_parts", {}).get("conversation_parts", [])
    
    # Look for user messages that might contain repro steps
    user_messages = []
    for part in parts:
        if part.get("part_type") == "comment":
            author = part.get("author", {})
            if author.get("type") == "user":
                body = part.get("body", "")
                import re
                body = re.sub(r"<[^>]+>", "", body).strip()
                if body and len(body) > 20:  # Meaningful content
                    user_messages.append(body)
    
    if user_messages:
        return " ".join(user_messages[:2])  # First couple of user messages
    
    return None


def extract_attachments(conversation: Dict) -> List[str]:
    """Extract attachment URLs from conversation."""
    attachments = []
    parts = conversation.get("conversation_parts", {}).get("conversation_parts", [])
    
    for part in parts:
        part_attachments = part.get("attachments", [])
        for attachment in part_attachments:
            url = attachment.get("url")
            if url:
                attachments.append(url)
    
    return attachments


def format_linear_comment(
    summary: str,
    user_name: str,
    email: str,
    intercom_url: str,
    repro_steps: Optional[str] = None,
    attachments: List[str] = None,
) -> str:
    """Format the comment for Linear."""
    attachments = attachments or []
    
    comment = f"**{summary}** — [{user_name}]({intercom_url}) ({email})\n\n"
    
    if repro_steps:
        comment += f"{repro_steps}\n\n"
    
    if attachments:
        comment += "Attachments:\n"
        for url in attachments[:3]:  # Limit to 3 attachments
            comment += f"- [{url.split('/')[-1]}]({url})\n"
        comment += "\n"
    
    comment += "@adel"
    
    # Ensure under 150 words (roughly)
    word_count = len(comment.split())
    if word_count > 150:
        logger.warning(f"Comment exceeds 150 words ({word_count} words), truncating repro section")
        if repro_steps:
            comment = f"**{summary}** — [{user_name}]({intercom_url}) ({email})\n\n"
            if attachments:
                comment += "Attachments:\n"
                for url in attachments[:2]:
                    comment += f"- [{url.split('/')[-1]}]({url})\n"
            comment += "\n@adel"
    
    return comment


def process_bug_conversation(
    intercom_client: IntercomClient,
    linear_client: LinearClient,
    conversation_id: str,
) -> bool:
    """Process a single bug conversation."""
    logger.info(f"Processing conversation {conversation_id}...")
    
    # Get conversation
    conversation = intercom_client.get_conversation(conversation_id)
    if not conversation:
        return False
    
    # Check if already synced
    if intercom_client.has_tag(conversation, "linear-synced"):
        logger.info(f"Conversation {conversation_id} already synced, skipping")
        return True
    
    # Get user info
    contacts = conversation.get("contacts", {}).get("contacts", [])
    if not contacts:
        logger.warning(f"No contacts found for conversation {conversation_id}")
        return False
    
    contact_id = contacts[0].get("id")
    contact = intercom_client.get_contact(contact_id)
    if not contact:
        return False
    
    user_name = contact.get("name", "Unknown")
    email = contact.get("email", "unknown@example.com")
    
    # Extract content
    summary = extract_summary(conversation)
    repro_steps = extract_repro_steps(conversation)
    attachments = extract_attachments(conversation)
    intercom_url = f"https://app.intercom.com/a/inbox/_/inbox/conversation/{conversation_id}"
    
    # Format and post to Linear
    comment_body = format_linear_comment(
        summary, user_name, email, intercom_url, repro_steps, attachments
    )
    
    logger.info(f"Posting comment to Linear for {user_name}...")
    comment = linear_client.create_comment("ISSUE-281", comment_body)
    if not comment:
        logger.error(f"Failed to create Linear comment for conversation {conversation_id}")
        return False
    
    linear_comment_url = comment.get("url")
    logger.info(f"Created Linear comment: {linear_comment_url}")
    
    # Tag as synced
    if not intercom_client.add_tag_to_conversation(conversation_id, "linear-synced"):
        logger.error(f"Failed to add linear-synced tag to conversation {conversation_id}")
        # Don't fail completely, note was posted
    
    # Add internal note
    internal_note = f"Logged on Linear ISSUE-281. Link: {linear_comment_url}"
    if not intercom_client.add_internal_note(conversation_id, internal_note):
        logger.error(f"Failed to add internal note to conversation {conversation_id}")
        # Don't fail completely, comment was posted
    
    logger.info(f"Successfully processed conversation {conversation_id}")
    return True


def main():
    """Main automation function."""
    # Get API tokens from environment
    intercom_token = os.environ.get("INTERCOM_API_TOKEN")
    linear_token = os.environ.get("LINEAR_API_TOKEN")
    
    if not intercom_token or not linear_token:
        logger.error("Missing INTERCOM_API_TOKEN or LINEAR_API_TOKEN environment variables")
        sys.exit(1)
    
    # Initialize clients
    intercom = IntercomClient(intercom_token)
    linear = LinearClient(linear_token)
    
    # Search for Bug Report conversations updated in last 60 minutes
    logger.info("Searching for Bug Report conversations from last 60 minutes...")
    
    # Note: Intercom Search API may have limited filtering by time
    # We'll need to search and filter client-side
    try:
        # Get conversations with Bug Report tag
        url = "https://api.intercom.io/conversations/search"
        payload = {
            "query": {
                "operator": "and",
                "value": [
                    {"field": "tag", "operator": "eq", "value": "Bug Report"},
                    {
                        "field": "updated_at",
                        "operator": "gte",
                        "value": int((datetime.utcnow() - timedelta(hours=1)).timestamp()),
                    },
                ],
            }
        }
        
        response = requests.post(
            url,
            headers=intercom.headers,
            json=payload,
        )
        response.raise_for_status()
        conversations = response.json().get("conversations", [])
        
        if not conversations:
            logger.info("No new bug conversations found")
            return
        
        logger.info(f"Found {len(conversations)} bug conversation(s)")
        
        # Process each conversation
        for conv in conversations:
            conversation_id = conv.get("id")
            process_bug_conversation(intercom, linear, conversation_id)
        
    except requests.RequestException as e:
        logger.error(f"Failed to search conversations: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
