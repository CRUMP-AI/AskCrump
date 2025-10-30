// ==========================================
// CRUMP AI - GMAIL API
// Gmail API Integration (OAuth Required)
// ==========================================

export default async function handler(req, res) {
    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }
    
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }
    
    try {
        const { query, context, accessToken } = req.body;
        
        if (!query) {
            return res.status(400).json({ error: 'Query is required' });
        }
        
        // Check for access token (user must authorize)
        if (!accessToken) {
            return res.status(401).json({ 
                error: 'Gmail access not authorized',
                authRequired: true,
                message: 'User must authorize Gmail access via OAuth 2.0'
            });
        }
        
        console.log(`📧 Gmail query: ${query}`);
        
        // Detect intent
        const intent = detectGmailIntent(query);
        
        if (!intent) {
            return res.status(400).json({ 
                error: 'Could not understand Gmail query',
                hint: 'Try: "Check my email" or "Search emails from boss"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        switch (intent.type) {
            case 'list_recent':
                result = await listRecentEmails(accessToken, intent.maxResults);
                break;
            
            case 'search':
                result = await searchEmails(accessToken, intent.searchQuery, intent.maxResults);
                break;
            
            case 'unread_count':
                result = await getUnreadCount(accessToken);
                break;
            
            case 'from_sender':
                result = await getEmailsFromSender(accessToken, intent.sender);
                break;
            
            case 'labels':
                result = await getLabels(accessToken);
                break;
            
            case 'send':
                result = await sendEmail(accessToken, intent.to, intent.subject, intent.body);
                break;
            
            default:
                result = await listRecentEmails(accessToken, 10);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'gmail',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Gmail API error:', error);
        
        // Handle OAuth errors
        if (error.message.includes('401')) {
            return res.status(401).json({
                error: 'Gmail authorization expired',
                authRequired: true,
                message: 'Please re-authorize Gmail access'
            });
        }
        
        return res.status(500).json({ 
            error: 'Gmail lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT GMAIL INTENT
// ==========================================
function detectGmailIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: List recent emails
    if (text.match(/check|show|list|get|view|my\s+(?:recent\s+)?(?:email|inbox|mail)/i)) {
        const match = text.match(/(?:last|recent)\s+(\d+)/i);
        const maxResults = match ? parseInt(match[1]) : 10;
        
        return {
            type: 'list_recent',
            maxResults: Math.min(maxResults, 50)
        };
    }
    
    // Pattern 2: Unread count
    if (text.match(/how\s+many|count|number\s+of.*unread/i)) {
        return {
            type: 'unread_count'
        };
    }
    
    // Pattern 3: Search emails
    if (text.match(/search|find|look for/i)) {
        const searchQuery = text
            .replace(/search|find|look for|emails?|messages?|in\s+(?:my\s+)?(?:gmail|inbox|mail)/gi, '')
            .trim();
        
        return {
            type: 'search',
            searchQuery: searchQuery,
            maxResults: 10
        };
    }
    
    // Pattern 4: From specific sender
    if (text.match(/from|emails?\s+(?:by|from)/i)) {
        const match = text.match(/(?:from|by)\s+(.+?)(?:\s|$)/i);
        if (match) {
            return {
                type: 'from_sender',
                sender: match[1].trim()
            };
        }
    }
    
    // Pattern 5: Get labels
    if (text.match(/labels?|folders?|categories/i)) {
        return {
            type: 'labels'
        };
    }
    
    // Pattern 6: Send email
    if (text.match(/send|compose|write/i)) {
        // Extract recipient, subject, body
        const toMatch = text.match(/to\s+(.+?)(?:\s+(?:subject|about|with subject)|$)/i);
        const subjectMatch = text.match(/(?:subject|about|with subject)\s+(.+?)(?:\s+(?:body|message|saying)|$)/i);
        const bodyMatch = text.match(/(?:body|message|saying)\s+(.+)/i);
        
        if (toMatch) {
            return {
                type: 'send',
                to: toMatch[1].trim(),
                subject: subjectMatch ? subjectMatch[1].trim() : 'No subject',
                body: bodyMatch ? bodyMatch[1].trim() : ''
            };
        }
    }
    
    // Default: list recent
    return {
        type: 'list_recent',
        maxResults: 10
    };
}

// ==========================================
// LIST RECENT EMAILS
// ==========================================
async function listRecentEmails(accessToken, maxResults = 10) {
    try {
        // Get list of message IDs
        const listUrl = `https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=${maxResults}`;
        
        const listResponse = await fetch(listUrl, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!listResponse.ok) {
            throw new Error(`Gmail API returned ${listResponse.status}`);
        }
        
        const listData = await listResponse.json();
        
        if (!listData.messages || listData.messages.length === 0) {
            return {
                success: false,
                error: 'No emails found in inbox'
            };
        }
        
        // Get full message details for each
        const messages = await Promise.all(
            listData.messages.slice(0, maxResults).map(async (msg) => {
                const msgUrl = `https://gmail.googleapis.com/gmail/v1/users/me/messages/${msg.id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date`;
                
                const msgResponse = await fetch(msgUrl, {
                    headers: {
                        'Authorization': `Bearer ${accessToken}`,
                        'Accept': 'application/json'
                    }
                });
                
                if (msgResponse.ok) {
                    return await msgResponse.json();
                }
                return null;
            })
        );
        
        const validMessages = messages.filter(m => m !== null);
        
        // Format response
        const formatted = formatEmailList(validMessages);
        
        return {
            success: true,
            data: validMessages,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error listing emails:', error);
        return {
            success: false,
            error: 'Failed to list emails'
        };
    }
}

// ==========================================
// SEARCH EMAILS
// ==========================================
async function searchEmails(accessToken, searchQuery, maxResults = 10) {
    try {
        const q = encodeURIComponent(searchQuery);
        const url = `https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${q}&maxResults=${maxResults}`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Gmail API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.messages || data.messages.length === 0) {
            return {
                success: false,
                error: `No emails found matching "${searchQuery}"`
            };
        }
        
        // Get full message details
        const messages = await Promise.all(
            data.messages.slice(0, maxResults).map(async (msg) => {
                const msgUrl = `https://gmail.googleapis.com/gmail/v1/users/me/messages/${msg.id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date`;
                
                const msgResponse = await fetch(msgUrl, {
                    headers: {
                        'Authorization': `Bearer ${accessToken}`,
                        'Accept': 'application/json'
                    }
                });
                
                if (msgResponse.ok) {
                    return await msgResponse.json();
                }
                return null;
            })
        );
        
        const validMessages = messages.filter(m => m !== null);
        
        // Format response
        const formatted = formatSearchResults(validMessages, searchQuery);
        
        return {
            success: true,
            data: validMessages,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching emails:', error);
        return {
            success: false,
            error: 'Failed to search emails'
        };
    }
}

// ==========================================
// GET UNREAD COUNT
// ==========================================
async function getUnreadCount(accessToken) {
    try {
        const url = 'https://gmail.googleapis.com/gmail/v1/users/me/labels/INBOX';
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Gmail API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        const unreadCount = data.messagesUnread || 0;
        const totalCount = data.messagesTotal || 0;
        
        // Format response
        const formatted = formatUnreadCount(unreadCount, totalCount);
        
        return {
            success: true,
            data: { unread: unreadCount, total: totalCount },
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting unread count:', error);
        return {
            success: false,
            error: 'Failed to get unread count'
        };
    }
}

// ==========================================
// GET EMAILS FROM SENDER
// ==========================================
async function getEmailsFromSender(accessToken, sender) {
    try {
        const q = encodeURIComponent(`from:${sender}`);
        const url = `https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${q}&maxResults=10`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Gmail API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.messages || data.messages.length === 0) {
            return {
                success: false,
                error: `No emails found from "${sender}"`
            };
        }
        
        // Get full message details
        const messages = await Promise.all(
            data.messages.slice(0, 10).map(async (msg) => {
                const msgUrl = `https://gmail.googleapis.com/gmail/v1/users/me/messages/${msg.id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date`;
                
                const msgResponse = await fetch(msgUrl, {
                    headers: {
                        'Authorization': `Bearer ${accessToken}`,
                        'Accept': 'application/json'
                    }
                });
                
                if (msgResponse.ok) {
                    return await msgResponse.json();
                }
                return null;
            })
        );
        
        const validMessages = messages.filter(m => m !== null);
        
        // Format response
        const formatted = formatSenderEmails(validMessages, sender);
        
        return {
            success: true,
            data: validMessages,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting emails from sender:', error);
        return {
            success: false,
            error: 'Failed to get emails from sender'
        };
    }
}

// ==========================================
// GET LABELS
// ==========================================
async function getLabels(accessToken) {
    try {
        const url = 'https://gmail.googleapis.com/gmail/v1/users/me/labels';
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Gmail API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatLabels(data.labels);
        
        return {
            success: true,
            data: data.labels,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting labels:', error);
        return {
            success: false,
            error: 'Failed to get labels'
        };
    }
}

// ==========================================
// SEND EMAIL
// ==========================================
async function sendEmail(accessToken, to, subject, body) {
    try {
        // Create email in RFC 2822 format
        const email = [
            `To: ${to}`,
            `Subject: ${subject}`,
            '',
            body
        ].join('\r\n');
        
        // Encode to base64url
        const encodedEmail = Buffer.from(email)
            .toString('base64')
            .replace(/\+/g, '-')
            .replace(/\//g, '_')
            .replace(/=+$/, '');
        
        const url = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send';
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                raw: encodedEmail
            })
        });
        
        if (!response.ok) {
            throw new Error(`Gmail API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatSentEmail(to, subject);
        
        return {
            success: true,
            data: data,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error sending email:', error);
        return {
            success: false,
            error: 'Failed to send email'
        };
    }
}

// ==========================================
// FORMAT EMAIL LIST
// ==========================================
function formatEmailList(messages) {
    let formatted = `📧 **Recent Emails**\n\n`;
    formatted += `Found ${messages.length} emails:\n\n`;
    
    messages.forEach((msg, index) => {
        const headers = msg.payload.headers;
        const from = headers.find(h => h.name === 'From')?.value || 'Unknown';
        const subject = headers.find(h => h.name === 'Subject')?.value || 'No subject';
        const date = headers.find(h => h.name === 'Date')?.value || '';
        
        // Extract just name and email
        const fromMatch = from.match(/(.+?)\s*<(.+?)>/) || [null, from, ''];
        const senderName = fromMatch[1].trim();
        const senderEmail = fromMatch[2];
        
        // Format date
        const formattedDate = date ? formatDate(new Date(date)) : 'Unknown date';
        
        formatted += `**${index + 1}. ${subject}**\n`;
        formatted += `   👤 From: ${senderName}${senderEmail ? ` (${senderEmail})` : ''}\n`;
        formatted += `   📅 ${formattedDate}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT SEARCH RESULTS
// ==========================================
function formatSearchResults(messages, query) {
    let formatted = `🔍 **Email Search: "${query}"**\n\n`;
    formatted += `Found ${messages.length} emails:\n\n`;
    
    messages.forEach((msg, index) => {
        const headers = msg.payload.headers;
        const from = headers.find(h => h.name === 'From')?.value || 'Unknown';
        const subject = headers.find(h => h.name === 'Subject')?.value || 'No subject';
        const date = headers.find(h => h.name === 'Date')?.value || '';
        
        const fromMatch = from.match(/(.+?)\s*<(.+?)>/) || [null, from, ''];
        const senderName = fromMatch[1].trim();
        
        formatted += `**${index + 1}. ${subject}**\n`;
        formatted += `   👤 ${senderName}\n`;
        formatted += `   📅 ${formatDate(new Date(date))}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT UNREAD COUNT
// ==========================================
function formatUnreadCount(unread, total) {
    let formatted = `📧 **Gmail Inbox Status**\n\n`;
    formatted += `📬 **Unread:** ${unread} emails\n`;
    formatted += `📨 **Total:** ${total} emails\n\n`;
    
    if (unread === 0) {
        formatted += `✅ **Inbox Zero!** All caught up!`;
    } else if (unread < 10) {
        formatted += `👍 **Looking good!** Just a few to go.`;
    } else if (unread < 50) {
        formatted += `⚠️ **Getting busy** - might want to clear some out.`;
    } else {
        formatted += `🚨 **Inbox overload!** Time for some cleanup.`;
    }
    
    return formatted;
}

// ==========================================
// FORMAT SENDER EMAILS
// ==========================================
function formatSenderEmails(messages, sender) {
    let formatted = `📧 **Emails from: ${sender}**\n\n`;
    
    messages.forEach((msg, index) => {
        const headers = msg.payload.headers;
        const subject = headers.find(h => h.name === 'Subject')?.value || 'No subject';
        const date = headers.find(h => h.name === 'Date')?.value || '';
        
        formatted += `**${index + 1}. ${subject}**\n`;
        formatted += `   📅 ${formatDate(new Date(date))}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT LABELS
// ==========================================
function formatLabels(labels) {
    let formatted = `🏷️ **Gmail Labels**\n\n`;
    
    // Separate system and user labels
    const systemLabels = labels.filter(l => l.type === 'system');
    const userLabels = labels.filter(l => l.type === 'user');
    
    if (systemLabels.length > 0) {
        formatted += `**System Labels:**\n`;
        systemLabels.forEach(label => {
            formatted += `• ${label.name}\n`;
        });
        formatted += '\n';
    }
    
    if (userLabels.length > 0) {
        formatted += `**Custom Labels:**\n`;
        userLabels.forEach(label => {
            formatted += `• ${label.name}\n`;
        });
    }
    
    return formatted;
}

// ==========================================
// FORMAT SENT EMAIL
// ==========================================
function formatSentEmail(to, subject) {
    let formatted = `✅ **Email Sent Successfully!**\n\n`;
    formatted += `📧 **To:** ${to}\n`;
    formatted += `📝 **Subject:** ${subject}\n`;
    
    return formatted;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function formatDate(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) {
        return 'Just now';
    } else if (diffMins < 60) {
        return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`;
    } else if (diffHours < 24) {
        return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
    } else if (diffDays < 7) {
        return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
    } else {
        const options = { month: 'short', day: 'numeric', year: 'numeric' };
        return date.toLocaleDateString('en-US', options);
    }
}
