// ==========================================
// CRUMP AI - NEWS API
// NewsAPI.org Integration (FREE)
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
        
        // Check for API key
        const apiKey = process.env.NEWS_API_KEY;
        
        if (!apiKey) {
            console.warn('⚠️ NewsAPI key not configured');
            return res.status(503).json({ 
                error: 'News API key not configured',
                fallback: true,
                message: 'Please add NEWS_API_KEY to environment variables'
            });
        }
        
        console.log(`📰 News query: ${query}`);
        
        // Detect news intent
        const intent = detectNewsIntent(query);
        
        let result;
        
        switch (intent.type) {
            case 'topic':
                result = await getNewsByTopic(intent.topic, apiKey);
                break;
            
            case 'headlines':
                result = await getTopHeadlines(intent.category, intent.country, apiKey);
                break;
            
            case 'source':
                result = await getNewsBySource(intent.source, apiKey);
                break;
            
            default:
                // Default to top headlines
                result = await getTopHeadlines('general', 'us', apiKey);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'news',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ News API error:', error);
        return res.status(500).json({ 
            error: 'News lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT NEWS INTENT
// ==========================================
function detectNewsIntent(query) {
    const text = query.toLowerCase().trim();

    // ------------------------------------------
    // Pattern 0: Death / assassination / "what happened" / reactions
    // e.g.:
    //  - "how did some people react to charlie kirk's death"
    //  - "reactions to charlie kirk's assassination"
    //  - "what happened to charlie kirk"
    //  - "news about the death of charlie kirk"
    // ------------------------------------------
    const deathOrEventTerms = /\b(death|died|was killed|killed|assassination|was shot|was murdered|passed away|shooting)\b/;
    const reactionTerms = /\b(reaction|reactions|responded|responses|how did people react|how are people reacting|how did some people react|how did people respond)\b/;

    if (deathOrEventTerms.test(text)) {
        // Try to strip reaction framing and death/event words, keep the subject
        let topic = text;

        topic = topic
            // remove reaction phrases
            .replace(/how did some people react to/gi, '')
            .replace(/how did people react to/gi, '')
            .replace(/how are people reacting to/gi, '')
            .replace(/how did people respond to/gi, '')
            .replace(/reactions?\s+to/gi, '')
            .replace(/reaction\s+to/gi, '')
            // remove generic "to"
            .replace(/\bto\b/gi, '')
            // remove death/event terms
            .replace(/\b(death|died|was killed|killed|assassination|was shot|was murdered|passed away|shooting)\b/gi, '')
            // remove filler like "about", "news", "the"
            .replace(/\b(about|news|the)\b/gi, '')
            // trim punctuation and spaces
            .replace(/\?+$/g, '')
            .trim();

        if (!topic) {
            topic = query.trim();
        }

        return {
            type: 'topic',
            topic
        };
    }

    // ------------------------------------------
    // Pattern 1: "latest / recent / breaking news about X"
    //           "what's going on with X"
    //           "what's happening with X"
    //           "current situation with X"
    // ------------------------------------------

    // e.g. "latest news about charlie kirk"
    let match = text.match(/(?:latest|recent|breaking)\s+news\s+(?:about|on|regarding)\s+(.+)/i);
    if (match) {
        return {
            type: 'topic',
            topic: match[1].trim()
        };
    }

    // e.g. "what's going on with charlie kirk", "what's happening with tesla"
    match = text.match(/what(?:'s| is)?\s+(?:going on|happening)\s+(?:with|in|around)\s+(.+)/i);
    if (match) {
        return {
            type: 'topic',
            topic: match[1].trim()
        };
    }

    // e.g. "current situation with gaza", "current status of boeing"
    match = text.match(/current\s+(?:situation|status)\s+(?:with|in|of)\s+(.+)/i);
    if (match) {
        return {
            type: 'topic',
            topic: match[1].trim()
        };
    }

    // ------------------------------------------
    // Pattern 2: "news about [topic]"
    // ------------------------------------------
    match = text.match(/news\s+(?:about|on|regarding)\s+(.+)/i);
    if (match) {
        return {
            type: 'topic',
            topic: match[1].trim()
        };
    }

    // ------------------------------------------
    // Pattern 3: "[topic] news"
    // ------------------------------------------
    match = text.match(/^(.+?)\s+news/i);
    if (match) {
        const topic = match[1].trim();
        // Check if it's a category
        const category = detectCategory(topic);
        if (category) {
            return {
                type: 'headlines',
                category: category,
                country: 'us'
            };
        }
        return {
            type: 'topic',
            topic: topic
        };
    }

    // ------------------------------------------
    // Pattern 4: "latest/breaking/headlines" (no explicit topic)
    // ------------------------------------------
    if (text.includes('latest') || text.includes('breaking') || text.includes('top') || text.includes('headlines')) {
        const category = detectCategory(text);
        return {
            type: 'headlines',
            category: category || 'general',
            country: 'us'
        };
    }

    // ------------------------------------------
    // Pattern 5: "what's happening" / "what's going on" (no specific topic)
    // ------------------------------------------
    if (text.includes('what') && (text.includes('happen') || text.includes('going on'))) {
        return {
            type: 'headlines',
            category: 'general',
            country: 'us'
        };
    }

    // ------------------------------------------
    // Pattern 6: News from specific source
    // ------------------------------------------
    const source = detectSource(text);
    if (source) {
        return {
            type: 'source',
            source: source
        };
    }

    // ------------------------------------------
    // Default: treat remaining text as topic
    // ------------------------------------------
    return {
        type: 'topic',
        topic: text.replace(/news|latest|breaking|headlines/gi, '').trim()
    };
}



// ==========================================
// DETECT CATEGORY
// ==========================================
function detectCategory(text) {
    const categories = {
        'business': ['business', 'economy', 'finance', 'market', 'stock'],
        'entertainment': ['entertainment', 'celebrity', 'movies', 'music', 'hollywood'],
        'health': ['health', 'medical', 'covid', 'virus', 'disease'],
        'science': ['science', 'research', 'study', 'discovery'],
        'sports': ['sports', 'game', 'championship', 'tournament'],
        'technology': ['tech', 'technology', 'ai', 'artificial intelligence', 'software', 'hardware', 'silicon valley'],
        'politics': ['politics', 'political', 'election', 'government', 'congress', 'senate']
    };
    
    for (const [category, keywords] of Object.entries(categories)) {
        if (keywords.some(keyword => text.includes(keyword))) {
            return category;
        }
    }
    
    return null;
}

// ==========================================
// DETECT SOURCE
// ==========================================
function detectSource(text) {
    const sources = {
        'cnn': 'cnn',
        'bbc': 'bbc-news',
        'fox': 'fox-news',
        'nbc': 'nbc-news',
        'abc': 'abc-news',
        'reuters': 'reuters',
        'associated press': 'associated-press',
        'ap': 'associated-press',
        'bloomberg': 'bloomberg',
        'wall street journal': 'the-wall-street-journal',
        'wsj': 'the-wall-street-journal',
        'new york times': 'the-new-york-times',
        'nyt': 'the-new-york-times',
        'washington post': 'the-washington-post',
        'techcrunch': 'techcrunch',
        'wired': 'wired',
        'ars technica': 'ars-technica',
        'verge': 'the-verge',
        'espn': 'espn'
    };
    
    for (const [name, id] of Object.entries(sources)) {
        if (text.includes(name)) {
            return id;
        }
    }
    
    return null;
}

// ==========================================
// GET NEWS BY TOPIC
// ==========================================
async function getNewsByTopic(topic, apiKey) {
    try {
        // Use everything endpoint for topic search
        const url = `https://newsapi.org/v2/everything?q=${encodeURIComponent(topic)}&sortBy=publishedAt&language=en&pageSize=10&apiKey=${apiKey}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.status === 'error') {
            if (data.code === 'rateLimited') {
                return {
                    success: false,
                    error: 'News API rate limit reached',
                    hint: 'Free tier: 100 requests per day. Please try again later.'
                };
            }
            return {
                success: false,
                error: data.message || 'Failed to fetch news'
            };
        }
        
        if (!data.articles || data.articles.length === 0) {
            return {
                success: false,
                error: `No news found about "${topic}"`,
                hint: 'Try a different topic or broader search term'
            };
        }
        
        // Format response
        const formatted = formatNewsArticles(data.articles, topic);
        
        return {
            success: true,
            data: data.articles,
            formatted: formatted,
            totalResults: data.totalResults
        };
        
    } catch (error) {
        console.error('Error fetching news by topic:', error);
        return {
            success: false,
            error: 'Failed to fetch news'
        };
    }
}

// ==========================================
// GET TOP HEADLINES
// ==========================================
async function getTopHeadlines(category, country, apiKey) {
    try {
        // Use top-headlines endpoint
        let url = `https://newsapi.org/v2/top-headlines?country=${country}&pageSize=10&apiKey=${apiKey}`;
        
        if (category && category !== 'general') {
            url += `&category=${category}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.status === 'error') {
            if (data.code === 'rateLimited') {
                return {
                    success: false,
                    error: 'News API rate limit reached',
                    hint: 'Free tier: 100 requests per day. Please try again later.'
                };
            }
            return {
                success: false,
                error: data.message || 'Failed to fetch headlines'
            };
        }
        
        if (!data.articles || data.articles.length === 0) {
            return {
                success: false,
                error: `No headlines found for category "${category}"`,
                hint: 'Try a different category'
            };
        }
        
        // Format response
        const formatted = formatTopHeadlines(data.articles, category);
        
        return {
            success: true,
            data: data.articles,
            formatted: formatted,
            totalResults: data.totalResults
        };
        
    } catch (error) {
        console.error('Error fetching top headlines:', error);
        return {
            success: false,
            error: 'Failed to fetch headlines'
        };
    }
}

// ==========================================
// GET NEWS BY SOURCE
// ==========================================
async function getNewsBySource(source, apiKey) {
    try {
        const url = `https://newsapi.org/v2/top-headlines?sources=${source}&pageSize=10&apiKey=${apiKey}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.status === 'error') {
            if (data.code === 'rateLimited') {
                return {
                    success: false,
                    error: 'News API rate limit reached'
                };
            }
            return {
                success: false,
                error: data.message || 'Failed to fetch news from source'
            };
        }
        
        if (!data.articles || data.articles.length === 0) {
            return {
                success: false,
                error: `No articles found from source "${source}"`
            };
        }
        
        // Format response
        const formatted = formatNewsArticles(data.articles, `from ${source}`);
        
        return {
            success: true,
            data: data.articles,
            formatted: formatted,
            totalResults: data.totalResults
        };
        
    } catch (error) {
        console.error('Error fetching news by source:', error);
        return {
            success: false,
            error: 'Failed to fetch news from source'
        };
    }
}

// ==========================================
// FORMAT NEWS ARTICLES
// ==========================================
function formatNewsArticles(articles, topic) {
    const categoryEmoji = '📰';
    
    let formatted = `${categoryEmoji} **News about: ${topic}**\n\n`;
    formatted += `Found ${articles.length} recent articles:\n\n`;
    
    articles.slice(0, 8).forEach((article, index) => {
        const title = article.title || 'No title';
        const source = article.source.name || 'Unknown source';
        const publishedAt = formatDate(article.publishedAt);
        const url = article.url;
        
        formatted += `**${index + 1}. ${title}**\n`;
        formatted += `   📍 ${source} • ${publishedAt}\n`;
        
        if (article.description) {
            const description = article.description.length > 120 
                ? article.description.substring(0, 120) + '...' 
                : article.description;
            formatted += `   ${description}\n`;
        }
        
        formatted += `   🔗 [Read more](${url})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT TOP HEADLINES
// ==========================================
function formatTopHeadlines(articles, category) {
    const categoryEmojis = {
        'general': '🌍',
        'business': '💼',
        'entertainment': '🎬',
        'health': '🏥',
        'science': '🔬',
        'sports': '⚽',
        'technology': '💻',
        'politics': '🏛️'
    };
    
    const emoji = categoryEmojis[category] || '📰';
    const categoryName = category.charAt(0).toUpperCase() + category.slice(1);
    
    let formatted = `${emoji} **Top ${categoryName} Headlines**\n\n`;
    
    articles.slice(0, 10).forEach((article, index) => {
        const title = article.title || 'No title';
        const source = article.source.name || 'Unknown source';
        const publishedAt = formatDate(article.publishedAt);
        const url = article.url;
        
        formatted += `**${index + 1}. ${title}**\n`;
        formatted += `   📍 ${source} • ${publishedAt}\n`;
        
        if (article.description) {
            const description = article.description.length > 100 
                ? article.description.substring(0, 100) + '...' 
                : article.description;
            formatted += `   ${description}\n`;
        }
        
        formatted += `   🔗 [Read more](${url})\n\n`;
    });
    
    // Add breaking news indicator
    const recentArticles = articles.filter(a => {
        const publishedDate = new Date(a.publishedAt);
        const now = new Date();
        const hoursDiff = (now - publishedDate) / (1000 * 60 * 60);
        return hoursDiff < 2;
    });
    
    if (recentArticles.length > 0) {
        formatted += `\n🔴 **${recentArticles.length} breaking stories in the last 2 hours**`;
    }
    
    return formatted;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function formatDate(dateString) {
    if (!dateString) return 'Unknown date';
    
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    // Format relative time
    if (diffMins < 1) {
        return 'Just now';
    } else if (diffMins < 60) {
        return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`;
    } else if (diffHours < 24) {
        return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
    } else if (diffDays < 7) {
        return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
    } else {
        // Format as date
        const options = { month: 'short', day: 'numeric' };
        return date.toLocaleDateString('en-US', options);
    }
}
```

---

## **🔑 API KEY SETUP:**

1. Go to: https://newsapi.org/register
2. Get your **FREE** API key
3. Free tier: **100 requests per day**
4. Add to Vercel:
```
   NEWS_API_KEY=your_key_here
