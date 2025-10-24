// ==========================================
// CRUMP AI - GOOGLE SEARCH API
// Google Custom Search JSON API Integration
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
        const { query, context } = req.body;
        
        if (!query) {
            return res.status(400).json({ error: 'Query is required' });
        }
        
        // Check for API key and Search Engine ID
        const apiKey = process.env.GOOGLE_SEARCH_API_KEY;
        const searchEngineId = process.env.GOOGLE_SEARCH_ENGINE_ID;
        
        if (!apiKey || !searchEngineId) {
            console.warn('⚠️ Google Search API not configured');
            return res.status(503).json({ 
                error: 'Google Search API not configured',
                fallback: true,
                message: 'Please add GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID to environment variables'
            });
        }
        
        console.log(`🔍 Google Search query: ${query}`);
        
        // Detect intent
        const intent = detectSearchIntent(query);
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        switch (intent.type) {
            case 'web_search':
                result = await webSearch(intent.searchQuery, intent.options, apiKey, searchEngineId);
                break;
            
            case 'image_search':
                result = await imageSearch(intent.searchQuery, apiKey, searchEngineId);
                break;
            
            case 'site_search':
                result = await siteSearch(intent.searchQuery, intent.site, apiKey, searchEngineId);
                break;
            
            case 'news_search':
                result = await newsSearch(intent.searchQuery, apiKey, searchEngineId);
                break;
            
            case 'recent_search':
                result = await recentSearch(intent.searchQuery, intent.timeframe, apiKey, searchEngineId);
                break;
            
            default:
                result = await webSearch(query, {}, apiKey, searchEngineId);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'googleSearch',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Google Search API error:', error);
        return res.status(500).json({ 
            error: 'Search failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT SEARCH INTENT
// ==========================================
function detectSearchIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: Image search
    if (text.match(/images?|pictures?|photos?/i)) {
        const searchQuery = text
            .replace(/search|find|show|images?|pictures?|photos?|of|for/gi, '')
            .trim();
        
        return {
            type: 'image_search',
            searchQuery: searchQuery
        };
    }
    
    // Pattern 2: Site-specific search
    const siteMatch = text.match(/on\s+(\w+\.(?:com|org|net|edu|gov))|site:(\S+)/i);
    if (siteMatch) {
        const site = siteMatch[1] || siteMatch[2];
        const searchQuery = text
            .replace(/search|find|on\s+\w+\.\w+|site:\S+/gi, '')
            .trim();
        
        return {
            type: 'site_search',
            searchQuery: searchQuery,
            site: site
        };
    }
    
    // Pattern 3: News search
    if (text.match(/news|latest|breaking|current events/i)) {
        const searchQuery = text
            .replace(/search|find|news|latest|breaking|current events|about|on/gi, '')
            .trim();
        
        return {
            type: 'news_search',
            searchQuery: searchQuery
        };
    }
    
    // Pattern 4: Recent/time-based search
    const timeMatch = text.match(/(?:past|last)\s+(day|week|month|year)|recent|today|yesterday/i);
    if (timeMatch) {
        const timeframe = timeMatch[1] || 'week';
        const searchQuery = text
            .replace(/search|find|(?:past|last)\s+(?:day|week|month|year)|recent|today|yesterday/gi, '')
            .trim();
        
        return {
            type: 'recent_search',
            searchQuery: searchQuery,
            timeframe: timeframe
        };
    }
    
    // Pattern 5: Standard web search
    const searchQuery = text
        .replace(/^(?:search|google|find|look up|look for)\s+/i, '')
        .trim();
    
    const options = {
        safeSearch: extractSafeSearch(text),
        numResults: extractNumResults(text)
    };
    
    return {
        type: 'web_search',
        searchQuery: searchQuery,
        options: options
    };
}

// ==========================================
// EXTRACT SAFE SEARCH
// ==========================================
function extractSafeSearch(text) {
    if (text.includes('safe search') || text.includes('family friendly')) {
        return 'active';
    }
    return 'off';
}

// ==========================================
// EXTRACT NUM RESULTS
// ==========================================
function extractNumResults(text) {
    const match = text.match(/(?:top|first)\s+(\d+)/i);
    if (match) {
        return Math.min(parseInt(match[1]), 10); // Max 10 results per query
    }
    return 10; // Default
}

// ==========================================
// WEB SEARCH
// ==========================================
async function webSearch(searchQuery, options = {}, apiKey, searchEngineId) {
    try {
        const safeSearch = options.safeSearch || 'off';
        const numResults = options.numResults || 10;
        
        let url = `https://www.googleapis.com/customsearch/v1?key=${apiKey}&cx=${searchEngineId}&q=${encodeURIComponent(searchQuery)}&num=${numResults}`;
        
        if (safeSearch === 'active') {
            url += '&safe=active';
        }
        
        const response = await fetch(url);
        
        if (!response.ok) {
            if (response.status === 429) {
                return {
                    success: false,
                    error: 'Google Search API quota exceeded',
                    hint: 'Free tier: 100 queries per day. Upgrade for more queries.'
                };
            }
            
            const errorData = await response.json().catch(() => ({}));
            
            if (response.status === 403) {
                return {
                    success: false,
                    error: 'Google Search API not authorized',
                    hint: 'Check that your API key and Search Engine ID are correct'
                };
            }
            
            throw new Error(`Google Search API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: `No results found for "${searchQuery}"`,
                hint: 'Try different search terms'
            };
        }
        
        // Format response
        const formatted = formatSearchResults(data.items, searchQuery, data.searchInformation);
        
        return {
            success: true,
            data: data.items,
            formatted: formatted,
            searchInfo: data.searchInformation
        };
        
    } catch (error) {
        console.error('Error performing web search:', error);
        return {
            success: false,
            error: 'Failed to perform web search'
        };
    }
}

// ==========================================
// IMAGE SEARCH
// ==========================================
async function imageSearch(searchQuery, apiKey, searchEngineId) {
    try {
        const url = `https://www.googleapis.com/customsearch/v1?key=${apiKey}&cx=${searchEngineId}&q=${encodeURIComponent(searchQuery)}&searchType=image&num=10`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            if (response.status === 429) {
                return {
                    success: false,
                    error: 'Google Search API quota exceeded'
                };
            }
            throw new Error(`Google Search API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: `No images found for "${searchQuery}"`
            };
        }
        
        // Format response
        const formatted = formatImageResults(data.items, searchQuery);
        
        return {
            success: true,
            data: data.items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error performing image search:', error);
        return {
            success: false,
            error: 'Failed to perform image search'
        };
    }
}

// ==========================================
// SITE SEARCH
// ==========================================
async function siteSearch(searchQuery, site, apiKey, searchEngineId) {
    try {
        const siteQuery = `${searchQuery} site:${site}`;
        const url = `https://www.googleapis.com/customsearch/v1?key=${apiKey}&cx=${searchEngineId}&q=${encodeURIComponent(siteQuery)}&num=10`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`Google Search API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: `No results found on ${site} for "${searchQuery}"`
            };
        }
        
        // Format response
        const formatted = formatSiteSearchResults(data.items, searchQuery, site);
        
        return {
            success: true,
            data: data.items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error performing site search:', error);
        return {
            success: false,
            error: 'Failed to perform site search'
        };
    }
}

// ==========================================
// NEWS SEARCH
// ==========================================
async function newsSearch(searchQuery, apiKey, searchEngineId) {
    try {
        // Add date restriction for recent news
        const url = `https://www.googleapis.com/customsearch/v1?key=${apiKey}&cx=${searchEngineId}&q=${encodeURIComponent(searchQuery)}&num=10&sort=date`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`Google Search API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: `No news found for "${searchQuery}"`
            };
        }
        
        // Format response
        const formatted = formatNewsResults(data.items, searchQuery);
        
        return {
            success: true,
            data: data.items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error performing news search:', error);
        return {
            success: false,
            error: 'Failed to perform news search'
        };
    }
}

// ==========================================
// RECENT SEARCH
// ==========================================
async function recentSearch(searchQuery, timeframe, apiKey, searchEngineId) {
    try {
        // Calculate date range
        const dateRestrict = getDateRestrict(timeframe);
        
        let url = `https://www.googleapis.com/customsearch/v1?key=${apiKey}&cx=${searchEngineId}&q=${encodeURIComponent(searchQuery)}&num=10&sort=date`;
        
        if (dateRestrict) {
            url += `&dateRestrict=${dateRestrict}`;
        }
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`Google Search API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: `No recent results found for "${searchQuery}"`
            };
        }
        
        // Format response
        const formatted = formatRecentResults(data.items, searchQuery, timeframe);
        
        return {
            success: true,
            data: data.items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error performing recent search:', error);
        return {
            success: false,
            error: 'Failed to perform recent search'
        };
    }
}

// ==========================================
// GET DATE RESTRICT
// ==========================================
function getDateRestrict(timeframe) {
    const timeMap = {
        'day': 'd1',
        'week': 'w1',
        'month': 'm1',
        'year': 'y1'
    };
    
    return timeMap[timeframe] || 'w1';
}

// ==========================================
// FORMAT SEARCH RESULTS
// ==========================================
function formatSearchResults(results, query, searchInfo) {
    const totalResults = searchInfo?.totalResults || 'Unknown';
    const searchTime = searchInfo?.searchTime || 'N/A';
    
    let formatted = `🔍 **Google Search: "${query}"**\n\n`;
    formatted += `Found ${totalResults} results in ${searchTime} seconds\n\n`;
    
    results.forEach((result, index) => {
        const title = result.title;
        const snippet = result.snippet || 'No description available';
        const link = result.link;
        const displayLink = result.displayLink;
        
        formatted += `**${index + 1}. ${title}**\n`;
        formatted += `   ${snippet}\n`;
        formatted += `   🌐 ${displayLink}\n`;
        formatted += `   🔗 [View Page](${link})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT IMAGE RESULTS
// ==========================================
function formatImageResults(results, query) {
    let formatted = `🖼️ **Image Search: "${query}"**\n\n`;
    formatted += `Found ${results.length} images:\n\n`;
    
    results.forEach((result, index) => {
        const title = result.title;
        const link = result.link;
        const contextLink = result.image?.contextLink;
        const width = result.image?.width;
        const height = result.image?.height;
        
        formatted += `**${index + 1}. ${title}**\n`;
        
        if (width && height) {
            formatted += `   📐 ${width} × ${height}\n`;
        }
        
        formatted += `   🔗 [View Image](${link})\n`;
        
        if (contextLink) {
            formatted += `   🌐 [Source Page](${contextLink})\n`;
        }
        
        formatted += '\n';
    });
    
    return formatted;
}

// ==========================================
// FORMAT SITE SEARCH RESULTS
// ==========================================
function formatSiteSearchResults(results, query, site) {
    let formatted = `🔍 **Search on ${site}: "${query}"**\n\n`;
    formatted += `Found ${results.length} results:\n\n`;
    
    results.forEach((result, index) => {
        const title = result.title;
        const snippet = result.snippet || 'No description available';
        const link = result.link;
        
        formatted += `**${index + 1}. ${title}**\n`;
        formatted += `   ${snippet}\n`;
        formatted += `   🔗 [View Page](${link})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT NEWS RESULTS
// ==========================================
function formatNewsResults(results, query) {
    let formatted = `📰 **News: "${query}"**\n\n`;
    formatted += `Found ${results.length} news articles:\n\n`;
    
    results.forEach((result, index) => {
        const title = result.title;
        const snippet = result.snippet || 'No description available';
        const link = result.link;
        const source = result.displayLink;
        
        formatted += `**${index + 1}. ${title}**\n`;
        formatted += `   ${snippet}\n`;
        formatted += `   📰 Source: ${source}\n`;
        formatted += `   🔗 [Read Article](${link})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT RECENT RESULTS
// ==========================================
function formatRecentResults(results, query, timeframe) {
    const timeLabel = timeframe === 'day' ? 'today' : 
                     timeframe === 'week' ? 'this week' : 
                     timeframe === 'month' ? 'this month' : 
                     timeframe === 'year' ? 'this year' : 'recently';
    
    let formatted = `🕐 **Recent Search (${timeLabel}): "${query}"**\n\n`;
    formatted += `Found ${results.length} recent results:\n\n`;
    
    results.forEach((result, index) => {
        const title = result.title;
        const snippet = result.snippet || 'No description available';
        const link = result.link;
        const displayLink = result.displayLink;
        
        formatted += `**${index + 1}. ${title}**\n`;
        formatted += `   ${snippet}\n`;
        formatted += `   🌐 ${displayLink}\n`;
        formatted += `   🔗 [View Page](${link})\n\n`;
    });
    
    return formatted;
}
