// ==========================================
// CRUMP AI - GOOGLE CALENDAR API
// Google Calendar API Integration (OAuth Required)
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
                error: 'Calendar access not authorized',
                authRequired: true,
                message: 'User must authorize Google Calendar access via OAuth 2.0'
            });
        }
        
        console.log(`📅 Calendar query: ${query}`);
        
        // Detect intent
        const intent = detectCalendarIntent(query);
        
        if (!intent) {
            return res.status(400).json({ 
                error: 'Could not understand calendar query',
                hint: 'Try: "What\'s on my calendar today?" or "Schedule meeting for tomorrow at 2pm"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        switch (intent.type) {
            case 'list_events':
                result = await listEvents(accessToken, intent.timeMin, intent.timeMax, intent.maxResults);
                break;
            
            case 'today':
                result = await getTodaysEvents(accessToken);
                break;
            
            case 'this_week':
                result = await getThisWeeksEvents(accessToken);
                break;
            
            case 'next_event':
                result = await getNextEvent(accessToken);
                break;
            
            case 'create_event':
                result = await createEvent(accessToken, intent.eventDetails);
                break;
            
            case 'search':
                result = await searchEvents(accessToken, intent.searchQuery);
                break;
            
            case 'free_busy':
                result = await getFreeBusy(accessToken, intent.timeMin, intent.timeMax);
                break;
            
            case 'list_calendars':
                result = await listCalendars(accessToken);
                break;
            
            default:
                result = await getTodaysEvents(accessToken);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'googleCalendar',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Calendar API error:', error);
        
        // Handle OAuth errors
        if (error.message.includes('401')) {
            return res.status(401).json({
                error: 'Calendar authorization expired',
                authRequired: true,
                message: 'Please re-authorize Google Calendar access'
            });
        }
        
        return res.status(500).json({ 
            error: 'Calendar lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT CALENDAR INTENT
// ==========================================
function detectCalendarIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: Today's events
    if (text.match(/today|what'?s?\s+(?:on\s+)?(?:my\s+)?(?:schedule|calendar|agenda)\s+today/i)) {
        return {
            type: 'today'
        };
    }
    
    // Pattern 2: This week's events
    if (text.match(/this\s+week|week|weekly|what'?s?\s+(?:on\s+)?(?:my\s+)?(?:schedule|calendar|agenda)\s+this\s+week/i)) {
        return {
            type: 'this_week'
        };
    }
    
    // Pattern 3: Next event
    if (text.match(/next\s+(?:event|meeting|appointment)|what'?s?\s+next/i)) {
        return {
            type: 'next_event'
        };
    }
    
    // Pattern 4: Create event
    if (text.match(/schedule|create|add|book|set up/i) && text.match(/meeting|event|appointment|call/i)) {
        const eventDetails = extractEventDetails(text);
        if (eventDetails) {
            return {
                type: 'create_event',
                eventDetails: eventDetails
            };
        }
    }
    
    // Pattern 5: Search events
    if (text.match(/search|find|look for/i) && text.match(/event|meeting|appointment/i)) {
        const searchQuery = text
            .replace(/search|find|look for|events?|meetings?|appointments?|in\s+(?:my\s+)?calendar/gi, '')
            .trim();
        
        return {
            type: 'search',
            searchQuery: searchQuery
        };
    }
    
    // Pattern 6: Free/busy
    if (text.match(/free|busy|available|availability/i)) {
        const { timeMin, timeMax } = extractTimeRange(text);
        
        return {
            type: 'free_busy',
            timeMin: timeMin,
            timeMax: timeMax
        };
    }
    
    // Pattern 7: List calendars
    if (text.match(/list|show\s+(?:my\s+)?calendars?/i)) {
        return {
            type: 'list_calendars'
        };
    }
    
    // Pattern 8: Generic "what's on my calendar"
    if (text.match(/what'?s?\s+on\s+(?:my\s+)?calendar|show\s+(?:my\s+)?(?:schedule|calendar|events)/i)) {
        const { timeMin, timeMax } = extractTimeRange(text);
        
        return {
            type: 'list_events',
            timeMin: timeMin,
            timeMax: timeMax,
            maxResults: 10
        };
    }
    
    // Default: today's events
    return {
        type: 'today'
    };
}

// ==========================================
// EXTRACT EVENT DETAILS
// ==========================================
function extractEventDetails(text) {
    const details = {
        summary: '',
        startTime: null,
        endTime: null,
        description: '',
        location: ''
    };
    
    // Extract summary/title
    const summaryMatch = text.match(/(?:schedule|create|add|book)\s+(?:a\s+)?(?:meeting|event|appointment|call)\s+(?:for|with|about)\s+(.+?)(?:\s+(?:at|on|for|tomorrow|today)|$)/i);
    if (summaryMatch) {
        details.summary = summaryMatch[1].trim();
    } else {
        details.summary = 'New Event';
    }
    
    // Extract date/time
    const now = new Date();
    
    // Tomorrow
    if (text.includes('tomorrow')) {
        const tomorrow = new Date(now);
        tomorrow.setDate(tomorrow.getDate() + 1);
        
        const timeMatch = text.match(/at\s+(\d+)(?::(\d+))?\s*(am|pm)?/i);
        if (timeMatch) {
            let hours = parseInt(timeMatch[1]);
            const minutes = timeMatch[2] ? parseInt(timeMatch[2]) : 0;
            const meridiem = timeMatch[3];
            
            if (meridiem && meridiem.toLowerCase() === 'pm' && hours < 12) {
                hours += 12;
            } else if (meridiem && meridiem.toLowerCase() === 'am' && hours === 12) {
                hours = 0;
            }
            
            tomorrow.setHours(hours, minutes, 0, 0);
            details.startTime = tomorrow.toISOString();
            
            const endTime = new Date(tomorrow);
            endTime.setHours(endTime.getHours() + 1);
            details.endTime = endTime.toISOString();
        } else {
            tomorrow.setHours(9, 0, 0, 0);
            details.startTime = tomorrow.toISOString();
            
            const endTime = new Date(tomorrow);
            endTime.setHours(10, 0, 0, 0);
            details.endTime = endTime.toISOString();
        }
    }
    // Today
    else if (text.includes('today')) {
        const timeMatch = text.match(/at\s+(\d+)(?::(\d+))?\s*(am|pm)?/i);
        if (timeMatch) {
            let hours = parseInt(timeMatch[1]);
            const minutes = timeMatch[2] ? parseInt(timeMatch[2]) : 0;
            const meridiem = timeMatch[3];
            
            if (meridiem && meridiem.toLowerCase() === 'pm' && hours < 12) {
                hours += 12;
            } else if (meridiem && meridiem.toLowerCase() === 'am' && hours === 12) {
                hours = 0;
            }
            
            const today = new Date(now);
            today.setHours(hours, minutes, 0, 0);
            details.startTime = today.toISOString();
            
            const endTime = new Date(today);
            endTime.setHours(endTime.getHours() + 1);
            details.endTime = endTime.toISOString();
        }
    }
    // Next week
    else if (text.match(/next\s+week/i)) {
        const nextWeek = new Date(now);
        nextWeek.setDate(nextWeek.getDate() + 7);
        nextWeek.setHours(9, 0, 0, 0);
        details.startTime = nextWeek.toISOString();
        
        const endTime = new Date(nextWeek);
        endTime.setHours(10, 0, 0, 0);
        details.endTime = endTime.toISOString();
    }
    // Specific time today
    else {
        const timeMatch = text.match(/at\s+(\d+)(?::(\d+))?\s*(am|pm)?/i);
        if (timeMatch) {
            let hours = parseInt(timeMatch[1]);
            const minutes = timeMatch[2] ? parseInt(timeMatch[2]) : 0;
            const meridiem = timeMatch[3];
            
            if (meridiem && meridiem.toLowerCase() === 'pm' && hours < 12) {
                hours += 12;
            } else if (meridiem && meridiem.toLowerCase() === 'am' && hours === 12) {
                hours = 0;
            }
            
            const eventTime = new Date(now);
            eventTime.setHours(hours, minutes, 0, 0);
            
            // If time is in the past today, assume tomorrow
            if (eventTime < now) {
                eventTime.setDate(eventTime.getDate() + 1);
            }
            
            details.startTime = eventTime.toISOString();
            
            const endTime = new Date(eventTime);
            endTime.setHours(endTime.getHours() + 1);
            details.endTime = endTime.toISOString();
        }
    }
    
    return details.startTime ? details : null;
}

// ==========================================
// EXTRACT TIME RANGE
// ==========================================
function extractTimeRange(text) {
    const now = new Date();
    let timeMin = now.toISOString();
    let timeMax = null;
    
    if (text.includes('today')) {
        const endOfDay = new Date(now);
        endOfDay.setHours(23, 59, 59, 999);
        timeMax = endOfDay.toISOString();
    } else if (text.includes('tomorrow')) {
        const tomorrow = new Date(now);
        tomorrow.setDate(tomorrow.getDate() + 1);
        tomorrow.setHours(0, 0, 0, 0);
        timeMin = tomorrow.toISOString();
        
        const endOfTomorrow = new Date(tomorrow);
        endOfTomorrow.setHours(23, 59, 59, 999);
        timeMax = endOfTomorrow.toISOString();
    } else if (text.includes('this week')) {
        const endOfWeek = new Date(now);
        endOfWeek.setDate(endOfWeek.getDate() + (7 - endOfWeek.getDay()));
        endOfWeek.setHours(23, 59, 59, 999);
        timeMax = endOfWeek.toISOString();
    } else {
        // Default: next 7 days
        const weekFromNow = new Date(now);
        weekFromNow.setDate(weekFromNow.getDate() + 7);
        timeMax = weekFromNow.toISOString();
    }
    
    return { timeMin, timeMax };
}

// ==========================================
// LIST EVENTS
// ==========================================
async function listEvents(accessToken, timeMin, timeMax, maxResults = 10) {
    try {
        let url = `https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${encodeURIComponent(timeMin)}&orderBy=startTime&singleEvents=true&maxResults=${maxResults}`;
        
        if (timeMax) {
            url += `&timeMax=${encodeURIComponent(timeMax)}`;
        }
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Calendar API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: 'No events found for the specified time range'
            };
        }
        
        // Format response
        const formatted = formatEventList(data.items, 'Upcoming Events');
        
        return {
            success: true,
            data: data.items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error listing events:', error);
        return {
            success: false,
            error: 'Failed to list events'
        };
    }
}

// ==========================================
// GET TODAY'S EVENTS
// ==========================================
async function getTodaysEvents(accessToken) {
    const now = new Date();
    const startOfDay = new Date(now);
    startOfDay.setHours(0, 0, 0, 0);
    
    const endOfDay = new Date(now);
    endOfDay.setHours(23, 59, 59, 999);
    
    try {
        const url = `https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${encodeURIComponent(startOfDay.toISOString())}&timeMax=${encodeURIComponent(endOfDay.toISOString())}&orderBy=startTime&singleEvents=true`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Calendar API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: true,
                data: [],
                formatted: '📅 **Today\'s Schedule**\n\n✅ No events scheduled for today!'
            };
        }
        
        // Format response
        const formatted = formatEventList(data.items, 'Today\'s Schedule');
        
        return {
            success: true,
            data: data.items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting today\'s events:', error);
        return {
            success: false,
            error: 'Failed to get today\'s events'
        };
    }
}

// ==========================================
// GET THIS WEEK'S EVENTS
// ==========================================
async function getThisWeeksEvents(accessToken) {
    const now = new Date();
    const startOfWeek = new Date(now);
    startOfWeek.setDate(startOfWeek.getDate() - startOfWeek.getDay());
    startOfWeek.setHours(0, 0, 0, 0);
    
    const endOfWeek = new Date(startOfWeek);
    endOfWeek.setDate(endOfWeek.getDate() + 7);
    endOfWeek.setHours(23, 59, 59, 999);
    
    try {
        const url = `https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${encodeURIComponent(startOfWeek.toISOString())}&timeMax=${encodeURIComponent(endOfWeek.toISOString())}&orderBy=startTime&singleEvents=true&maxResults=50`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Calendar API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: true,
                data: [],
                formatted: '📅 **This Week\'s Schedule**\n\n✅ No events scheduled for this week!'
            };
        }
        
        // Format response
        const formatted = formatEventList(data.items, 'This Week\'s Schedule');
        
        return {
            success: true,
            data: data.items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting this week\'s events:', error);
        return {
            success: false,
            error: 'Failed to get this week\'s events'
        };
    }
}

// ==========================================
// GET NEXT EVENT
// ==========================================
async function getNextEvent(accessToken) {
    const now = new Date();
    
    try {
        const url = `https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${encodeURIComponent(now.toISOString())}&orderBy=startTime&singleEvents=true&maxResults=1`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Calendar API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: true,
                data: null,
                formatted: '📅 **Next Event**\n\n✅ No upcoming events scheduled!'
            };
        }
        
        const event = data.items[0];
        
        // Format response
        const formatted = formatNextEvent(event);
        
        return {
            success: true,
            data: event,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting next event:', error);
        return {
            success: false,
            error: 'Failed to get next event'
        };
    }
}

// ==========================================
// CREATE EVENT
// ==========================================
async function createEvent(accessToken, eventDetails) {
    try {
        const event = {
            summary: eventDetails.summary,
            start: {
                dateTime: eventDetails.startTime,
                timeZone: 'America/New_York' // TODO: Get from user
            },
            end: {
                dateTime: eventDetails.endTime,
                timeZone: 'America/New_York'
            }
        };
        
        if (eventDetails.description) {
            event.description = eventDetails.description;
        }
        
        if (eventDetails.location) {
            event.location = eventDetails.location;
        }
        
        const url = 'https://www.googleapis.com/calendar/v3/calendars/primary/events';
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(event)
        });
        
        if (!response.ok) {
            throw new Error(`Calendar API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatCreatedEvent(data);
        
        return {
            success: true,
            data: data,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error creating event:', error);
        return {
            success: false,
            error: 'Failed to create event'
        };
    }
}

// ==========================================
// SEARCH EVENTS
// ==========================================
async function searchEvents(accessToken, searchQuery) {
    try {
        const now = new Date();
        const url = `https://www.googleapis.com/calendar/v3/calendars/primary/events?q=${encodeURIComponent(searchQuery)}&timeMin=${encodeURIComponent(now.toISOString())}&orderBy=startTime&singleEvents=true&maxResults=10`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Calendar API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: `No events found matching "${searchQuery}"`
            };
        }
        
        // Format response
        const formatted = formatSearchResults(data.items, searchQuery);
        
        return {
            success: true,
            data: data.items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching events:', error);
        return {
            success: false,
            error: 'Failed to search events'
        };
    }
}

// ==========================================
// GET FREE/BUSY
// ==========================================
async function getFreeBusy(accessToken, timeMin, timeMax) {
    try {
        const url = 'https://www.googleapis.com/calendar/v3/freeBusy';
        
        const requestBody = {
            timeMin: timeMin,
            timeMax: timeMax,
            items: [{ id: 'primary' }]
        };
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            throw new Error(`Calendar API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatFreeBusy(data.calendars.primary.busy, timeMin, timeMax);
        
        return {
            success: true,
            data: data.calendars.primary.busy,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting free/busy:', error);
        return {
            success: false,
            error: 'Failed to get availability'
        };
    }
}

// ==========================================
// LIST CALENDARS
// ==========================================
async function listCalendars(accessToken) {
    try {
        const url = 'https://www.googleapis.com/calendar/v3/users/me/calendarList';
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Calendar API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatCalendarList(data.items);
        
        return {
            success: true,
            data: data.items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error listing calendars:', error);
        return {
            success: false,
            error: 'Failed to list calendars'
        };
    }
}

// ==========================================
// FORMAT EVENT LIST
// ==========================================
function formatEventList(events, title) {
    let formatted = `📅 **${title}**\n\n`;
    
    if (events.length === 0) {
        formatted += '✅ No events scheduled!';
        return formatted;
    }
    
    formatted += `Found ${events.length} event${events.length === 1 ? '' : 's'}:\n\n`;
    
    events.forEach((event, index) => {
        const summary = event.summary || 'Untitled Event';
        const start = event.start.dateTime || event.start.date;
        const end = event.end.dateTime || event.end.date;
        const location = event.location || '';
        
        const startDate = new Date(start);
        const endDate = new Date(end);
        
        formatted += `**${index + 1}. ${summary}**\n`;
        formatted += `   🕐 ${formatEventTime(startDate, endDate)}\n`;
        
        if (location) {
            formatted += `   📍 ${location}\n`;
        }
        
        if (event.attendees && event.attendees.length > 0) {
            formatted += `   👥 ${event.attendees.length} attendee${event.attendees.length === 1 ? '' : 's'}\n`;
        }
        
        formatted += '\n';
    });
    
    return formatted;
}

// ==========================================
// FORMAT NEXT EVENT
// ==========================================
function formatNextEvent(event) {
    const summary = event.summary || 'Untitled Event';
    const start = event.start.dateTime || event.start.date;
    const end = event.end.dateTime || event.end.date;
    const location = event.location || '';
    const description = event.description || '';
    
    const startDate = new Date(start);
    const endDate = new Date(end);
    
    let formatted = `📅 **Next Event: ${summary}**\n\n`;
    formatted += `🕐 **Time:** ${formatEventTime(startDate, endDate)}\n`;
    
    if (location) {
        formatted += `📍 **Location:** ${location}\n`;
    }
    
    if (event.attendees && event.attendees.length > 0) {
        formatted += `👥 **Attendees:** ${event.attendees.length}\n`;
    }
    
    if (description) {
        const shortDesc = description.length > 150 
            ? description.substring(0, 150) + '...' 
            : description;
        formatted += `\n${shortDesc}`;
    }
    
    // Time until event
    const now = new Date();
    const timeUntil = startDate - now;
    const minutesUntil = Math.floor(timeUntil / 60000);
    const hoursUntil = Math.floor(minutesUntil / 60);
    
    if (minutesUntil < 0) {
        formatted += `\n\n⚠️ **In progress!**`;
    } else if (minutesUntil < 15) {
        formatted += `\n\n🔔 **Starting in ${minutesUntil} minutes!**`;
    } else if (hoursUntil < 2) {
        formatted += `\n\n⏰ Starting in ${hoursUntil} hour${hoursUntil === 1 ? '' : 's'}`;
    }
    
    return formatted;
}

// ==========================================
// FORMAT CREATED EVENT
// ==========================================
function formatCreatedEvent(event) {
    const summary = event.summary;
    const start = event.start.dateTime || event.start.date;
    const startDate = new Date(start);
    
    let formatted = `✅ **Event Created!**\n\n`;
    formatted += `📅 **${summary}**\n`;
    formatted += `🕐 ${formatDateTime(startDate)}\n`;
    
    if (event.htmlLink) {
        formatted += `\n🔗 [View in Google Calendar](${event.htmlLink})`;
    }
    
    return formatted;
}

// ==========================================
// FORMAT SEARCH RESULTS
// ==========================================
function formatSearchResults(events, query) {
    let formatted = `🔍 **Calendar Search: "${query}"**\n\n`;
    
    events.forEach((event, index) => {
        const summary = event.summary || 'Untitled Event';
        const start = event.start.dateTime || event.start.date;
        const startDate = new Date(start);
        
        formatted += `**${index + 1}. ${summary}**\n`;
        formatted += `   🕐 ${formatDateTime(startDate)}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT FREE/BUSY
// ==========================================
function formatFreeBusy(busyTimes, timeMin, timeMax) {
    let formatted = `📊 **Availability**\n\n`;
    formatted += `**Period:** ${formatDateTime(new Date(timeMin))} to ${formatDateTime(new Date(timeMax))}\n\n`;
    
    if (busyTimes.length === 0) {
        formatted += `✅ **Completely free!** No events scheduled.`;
    } else {
        formatted += `**Busy Times:**\n`;
        busyTimes.forEach((busy, index) => {
            const start = new Date(busy.start);
            const end = new Date(busy.end);
            formatted += `${index + 1}. ${formatEventTime(start, end)}\n`;
        });
    }
    
    return formatted;
}

// ==========================================
// FORMAT CALENDAR LIST
// ==========================================
function formatCalendarList(calendars) {
    let formatted = `📅 **Your Calendars**\n\n`;
    
    calendars.forEach((calendar, index) => {
        const name = calendar.summary;
        const isPrimary = calendar.primary ? ' (Primary)' : '';
        
        formatted += `${index + 1}. ${name}${isPrimary}\n`;
    });
    
    return formatted;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function formatEventTime(start, end) {
    const startStr = formatDateTime(start);
    const endStr = formatTime(end);
    
    return `${startStr} - ${endStr}`;
}

function formatDateTime(date) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    
    const dateOnly = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    
    let dateStr = '';
    if (dateOnly.getTime() === today.getTime()) {
        dateStr = 'Today';
    } else if (dateOnly.getTime() === tomorrow.getTime()) {
        dateStr = 'Tomorrow';
    } else {
        const options = { weekday: 'short', month: 'short', day: 'numeric' };
        dateStr = date.toLocaleDateString('en-US', options);
    }
    
    const timeStr = formatTime(date);
    
    return `${dateStr} at ${timeStr}`;
}

function formatTime(date) {
    const hours = date.getHours();
    const minutes = date.getMinutes();
    const ampm = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    const displayMinutes = minutes < 10 ? `0${minutes}` : minutes;
    
    return `${displayHours}:${displayMinutes} ${ampm}`;
}
