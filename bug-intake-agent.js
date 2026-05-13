#!/usr/bin/env node

/**
 * Bug Intake Agent - Hourly automation
 * Fetches Intercom bug reports and forwards them to Linear ISSUE-281
 */

const https = require('https');

// Configuration
const INTERCOM_TOKEN = process.env.INTERCOM_TOKEN;
const LINEAR_TOKEN = process.env.LINEAR_TOKEN;
const LINEAR_ISSUE_ID = 'ISSUE-281';
const BUG_REPORT_TAG = 'Bug Report';
const LINEAR_SYNCED_TAG = 'linear-synced';

if (!INTERCOM_TOKEN || !LINEAR_TOKEN) {
  console.error('Missing required environment variables: INTERCOM_TOKEN and LINEAR_TOKEN');
  process.exit(1);
}

/**
 * Make HTTPS request helper
 */
function makeRequest(options, body = null) {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => {
        data += chunk;
      });
      res.on('end', () => {
        try {
          const parsed = data ? JSON.parse(data) : {};
          resolve({ status: res.statusCode, headers: res.headers, body: parsed });
        } catch (e) {
          resolve({ status: res.statusCode, headers: res.headers, body: data });
        }
      });
    });

    req.on('error', reject);
    if (body) {
      req.write(JSON.stringify(body));
    }
    req.end();
  });
}

/**
 * Search Intercom conversations with "Bug Report" tag updated in last 60 minutes
 */
async function fetchBugReportConversations() {
  const sixtyMinutesAgo = Math.floor((Date.now() - 60 * 60 * 1000) / 1000);

  const options = {
    hostname: 'api.intercom.io',
    path: '/conversations/search',
    method: 'POST',
    headers: {
      Authorization: `Bearer ${INTERCOM_TOKEN}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
  };

  // Use Intercom's conversation search with DSL
  const body = {
    query: {
      operator: 'AND',
      value: [
        {
          field: 'tag_names',
          operator: '=',
          value: BUG_REPORT_TAG,
        },
        {
          field: 'updated_at',
          operator: '>',
          value: sixtyMinutesAgo,
        },
      ],
    },
  };

  try {
    const response = await makeRequest(options, body);
    if (response.status !== 200) {
      console.error('Intercom search failed:', response.status, response.body);
      return [];
    }
    return response.body.conversations || [];
  } catch (error) {
    console.error('Error fetching bug report conversations:', error);
    return [];
  }
}

/**
 * Get full conversation details including all messages
 */
async function getConversationDetails(conversationId) {
  const options = {
    hostname: 'api.intercom.io',
    path: `/conversations/${conversationId}`,
    method: 'GET',
    headers: {
      Authorization: `Bearer ${INTERCOM_TOKEN}`,
      Accept: 'application/json',
    },
  };

  try {
    const response = await makeRequest(options);
    if (response.status !== 200) {
      console.error(`Failed to fetch conversation ${conversationId}:`, response.status);
      return null;
    }
    return response.body;
  } catch (error) {
    console.error(`Error fetching conversation details:`, error);
    return null;
  }
}

/**
 * Get contact details (user info)
 */
async function getContact(contactId) {
  const options = {
    hostname: 'api.intercom.io',
    path: `/contacts/${contactId}`,
    method: 'GET',
    headers: {
      Authorization: `Bearer ${INTERCOM_TOKEN}`,
      Accept: 'application/json',
    },
  };

  try {
    const response = await makeRequest(options);
    if (response.status !== 200) {
      console.error(`Failed to fetch contact ${contactId}:`, response.status);
      return null;
    }
    return response.body;
  } catch (error) {
    console.error(`Error fetching contact:`, error);
    return null;
  }
}

/**
 * Check if conversation already has "linear-synced" tag
 */
function isAlreadySynced(conversation) {
  const tags = conversation.tags?.data || [];
  return tags.some((tag) => tag.name === LINEAR_SYNCED_TAG);
}

/**
 * Extract thread content (initial message + replies)
 */
function extractThreadContent(conversation) {
  let content = {
    summary: null,
    repoSteps: null,
    attachmentUrls: [],
  };

  // Extract from conversation source (initial message)
  if (conversation.source && conversation.source.body) {
    content.summary = conversation.source.body.substring(0, 150);
  }

  // Extract from conversation parts (messages and attachments)
  const parts = conversation.conversation_parts?.conversation_parts || [];

  let textContent = [];
  let attachments = [];

  for (const part of parts) {
    if (part.part_type === 'comment' && part.body) {
      textContent.push(part.body);
    }

    // Extract attachment URLs
    if (part.attachments) {
      for (const attachment of part.attachments) {
        if (attachment.url) {
          attachments.push({
            name: attachment.name || 'Attachment',
            url: attachment.url,
          });
        }
      }
    }
  }

  // Look for "repro" or "steps" keywords in the text
  const fullText = textContent.join('\n');
  const repoMatch = fullText.match(/(?:repro|steps|reproduce)[\s:]+([^\n]+(?:\n[^\n]+)*)/i);
  if (repoMatch) {
    content.repoSteps = repoMatch[1].substring(0, 150);
  }

  content.attachmentUrls = attachments;
  return content;
}

/**
 * Post comment to Linear issue
 */
async function postLinearComment(issueId, commentBody) {
  const options = {
    hostname: 'api.linear.app',
    path: '/graphql',
    method: 'POST',
    headers: {
      Authorization: `Bearer ${LINEAR_TOKEN}`,
      'Content-Type': 'application/json',
    },
  };

  const query = `
    mutation CreateComment($issueId: String!, $body: String!) {
      commentCreate(input: {
        issueId: $issueId
        body: $body
      }) {
        comment {
          id
          url
        }
      }
    }
  `;

  const body = {
    query,
    variables: {
      issueId,
      body: commentBody,
    },
  };

  try {
    const response = await makeRequest(options, body);
    if (response.status !== 200 || response.body.errors) {
      console.error('Linear API error:', response.body.errors || response.body);
      return null;
    }
    return response.body.data?.commentCreate?.comment?.url || null;
  } catch (error) {
    console.error('Error posting to Linear:', error);
    return null;
  }
}

/**
 * Apply tag to Intercom conversation
 */
async function applyTag(conversationId, tagName) {
  const options = {
    hostname: 'api.intercom.io',
    path: `/conversations/${conversationId}/tags`,
    method: 'POST',
    headers: {
      Authorization: `Bearer ${INTERCOM_TOKEN}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
  };

  const body = {
    tag: {
      name: tagName,
    },
  };

  try {
    const response = await makeRequest(options, body);
    if (response.status !== 200) {
      console.error(`Failed to apply tag to conversation ${conversationId}:`, response.status);
      return false;
    }
    return true;
  } catch (error) {
    console.error(`Error applying tag:`, error);
    return false;
  }
}

/**
 * Add internal note to Intercom conversation
 */
async function addInternalNote(conversationId, noteBody) {
  const options = {
    hostname: 'api.intercom.io',
    path: `/conversations/${conversationId}/parts`,
    method: 'POST',
    headers: {
      Authorization: `Bearer ${INTERCOM_TOKEN}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
  };

  const body = {
    message_type: 'note',
    body: noteBody,
  };

  try {
    const response = await makeRequest(options, body);
    if (response.status !== 201) {
      console.error(`Failed to add note to conversation ${conversationId}:`, response.status);
      return false;
    }
    return true;
  } catch (error) {
    console.error(`Error adding internal note:`, error);
    return false;
  }
}

/**
 * Format comment for Linear
 */
function formatLinearComment(summary, contact, repoSteps, attachmentUrls, intercomUrl, email) {
  const lines = [];

  // Summary with user link
  const userName = contact.name || 'Unknown';
  lines.push(`**${summary}** — [${userName}](${intercomUrl}) (${email})`);
  lines.push('');

  // Repro steps or quoted text
  if (repoSteps) {
    lines.push(repoSteps);
    lines.push('');
  }

  // Attachment links
  if (attachmentUrls.length > 0) {
    for (const attachment of attachmentUrls) {
      lines.push(`[${attachment.name}](${attachment.url})`);
    }
    lines.push('');
  }

  // Mention
  lines.push('@adel');

  return lines.join('\n');
}

/**
 * Main agent function
 */
async function runAgent() {
  console.log('Starting bug intake agent...');

  // Step 1: Fetch bug report conversations from last 60 minutes
  console.log('Fetching bug report conversations from the last 60 minutes...');
  const conversations = await fetchBugReportConversations();

  if (conversations.length === 0) {
    console.log('No new bug report conversations found. Exiting silently.');
    return;
  }

  console.log(`Found ${conversations.length} bug report conversation(s)`);

  // Step 2-6: Process each conversation
  for (const conversation of conversations) {
    const conversationId = conversation.id;
    const conversationUrl = `https://app.intercom.com/a/inbox/${conversationId}`;

    console.log(`\nProcessing conversation ${conversationId}...`);

    // Check if already synced
    if (isAlreadySynced(conversation)) {
      console.log(`Conversation ${conversationId} already synced. Skipping.`);
      continue;
    }

    // Get full conversation details
    const fullConversation = await getConversationDetails(conversationId);
    if (!fullConversation) {
      console.error(`Failed to get details for conversation ${conversationId}`);
      continue;
    }

    // Get contact details (user info)
    const contactId = conversation.participants?.[0]?.id;
    if (!contactId) {
      console.error(`No contact found for conversation ${conversationId}`);
      continue;
    }

    const contact = await getContact(contactId);
    if (!contact) {
      console.error(`Failed to get contact details for ${contactId}`);
      continue;
    }

    // Extract thread content
    const threadContent = extractThreadContent(fullConversation);
    const summary = threadContent.summary || 'Bug report';
    const email = contact.email || 'unknown@email.com';
    const userName = contact.name || 'Unknown';
    const userId = contact.external_id || contact.id;

    console.log(`User: ${userName} (${userId}, ${email})`);
    console.log(`Summary: ${summary}`);

    // Format and post to Linear
    const commentBody = formatLinearComment(
      summary,
      contact,
      threadContent.repoSteps,
      threadContent.attachmentUrls,
      conversationUrl,
      email
    );

    console.log('Posting to Linear...');
    const linearCommentUrl = await postLinearComment(LINEAR_ISSUE_ID, commentBody);

    if (!linearCommentUrl) {
      console.error(`Failed to post comment to Linear for conversation ${conversationId}`);
      continue;
    }

    console.log(`Comment posted: ${linearCommentUrl}`);

    // Apply linear-synced tag
    console.log('Applying linear-synced tag...');
    const tagApplied = await applyTag(conversationId, LINEAR_SYNCED_TAG);
    if (!tagApplied) {
      console.error(`Failed to apply tag to conversation ${conversationId}`);
      continue;
    }

    // Add internal note
    const internalNote = `Logged on Linear ${LINEAR_ISSUE_ID}. Link: ${linearCommentUrl}`;
    console.log('Adding internal note...');
    const noteAdded = await addInternalNote(conversationId, internalNote);
    if (!noteAdded) {
      console.error(`Failed to add internal note to conversation ${conversationId}`);
      continue;
    }

    console.log(`Successfully processed conversation ${conversationId}`);
  }

  console.log('\nBug intake agent completed.');
}

// Run the agent
runAgent().catch((error) => {
  console.error('Fatal error in bug intake agent:', error);
  process.exit(1);
});
