// ==========================================
// CRUMP AI - YOUTUBE API
// YouTube Data API v3 Integration
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
        const apiKey = process.env.YOUTUBE_API_KEY;
        
        if (!apiKey) {
            console.warn('⚠️ YouTube API key not configured');
            return res.status(503).json({ 
                error: 'YouTube API key not configured',
                fallback: true,
                message: 'Please add YOUTUBE_API_KEY to environment variables'
            });
        }
        
        console.log(`📺 YouTube query: ${query}`);
        
        // Detect intent
        const intent = detectYouTubeIntent(query);
        
        if (!intent) {
            return res.status(400).json({ 
                error: 'Could not understand YouTube query',
                hint: 'Try: "Search YouTube for cooking tutorials" or "Find videos about Python"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        switch (intent.type) {
            case 'search':
                result = await searchVideos(intent.searchQuery, intent.maxResults, apiKey);
                break;
            
            case 'channel':
                result = await getChannelInfo(intent.channelName, apiKey);
                break;
            
            case 'trending':
                result = await getTrendingVideos(intent.category, apiKey);
                break;
            
            case 'video_details':
                result = await getVideoDetails(intent.videoId, apiKey);
                break;
            
            default:
                result = await searchVideos(query, 10, apiKey);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'youtube',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ YouTube API error:', error);
        return res.status(500).json({ 
            error: 'YouTube lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT YOUTUBE INTENT
// ==========================================
function detectYouTubeIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: Search for videos
    if (text.match(/search|find|look for|show me|videos? about/i)) {
        const match = text.match(/(?:search|find|look for|show me|videos? about)\s+(.+?)(?:\s+on\s+youtube)?$/i);
        if (match) {
            const maxResults = extractMaxResults(text);
            return {
                type: 'search',
                searchQuery: match[1].trim(),
                maxResults: maxResults
            };
        }
    }
    
    // Pattern 2: Channel information
    if (text.match(/channel|youtuber|creator/i)) {
        const match = text.match(/(?:channel|youtuber|creator)\s+(.+)/i);
        if (match) {
            return {
                type: 'channel',
                channelName: match[1].trim()
            };
        }
    }
    
    // Pattern 3: Trending videos
    if (text.match(/trending|popular|viral|hot videos/i)) {
        const category = extractCategory(text);
        return {
            type: 'trending',
            category: category
        };
    }
    
    // Pattern 4: Specific video details
    const videoIdMatch = text.match(/(?:v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
    if (videoIdMatch) {
        return {
            type: 'video_details',
            videoId: videoIdMatch[1]
        };
    }
    
    // Default: Search for videos
    const searchQuery = text
        .replace(/youtube|video|videos|search|find/gi, '')
        .trim();
    
    return {
        type: 'search',
        searchQuery: searchQuery,
        maxResults: 10
    };
}

// ==========================================
// EXTRACT MAX RESULTS
// ==========================================
function extractMaxResults(text) {
    const match = text.match(/(?:top|first|show me)\s+(\d+)/i);
    if (match) {
        return Math.min(parseInt(match[1]), 50); // YouTube API max is 50
    }
    return 10; // Default
}

// ==========================================
// EXTRACT CATEGORY
// ==========================================
function extractCategory(text) {
    const categories = {
        'music': '10',
        'gaming': '20',
        'sports': '17',
        'entertainment': '24',
        'news': '25',
        'education': '27',
        'tech': '28',
        'technology': '28',
        'science': '28'
    };
    
    for (const [key, value] of Object.entries(categories)) {
        if (text.includes(key)) {
            return value;
        }
    }
    
    return null; // All categories
}

// ==========================================
// SEARCH VIDEOS
// ==========================================
async function searchVideos(searchQuery, maxResults, apiKey) {
    try {
        const url = `https://www.googleapis.com/youtube/v3/search?part=snippet&q=${encodeURIComponent(searchQuery)}&type=video&maxResults=${maxResults}&key=${apiKey}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            if (response.status === 403) {
                const errorData = await response.json();
                if (errorData.error.errors[0].reason === 'quotaExceeded') {
                    return {
                        success: false,
                        error: 'YouTube API quota exceeded',
                        hint: 'Free tier: 10,000 units per day. Each search uses ~100 units.'
                    };
                }
                return {
                    success: false,
                    error: 'YouTube API access denied',
                    hint: 'Check your YOUTUBE_API_KEY is valid and has YouTube Data API v3 enabled'
                };
            }
            throw new Error(`YouTube API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: `No videos found for "${searchQuery}"`,
                hint: 'Try different search terms'
            };
        }
        
        // Get video IDs for detailed stats
        const videoIds = data.items.map(item => item.id.videoId).join(',');
        
        // Get video statistics
        const statsUrl = `https://www.googleapis.com/youtube/v3/videos?part=statistics,contentDetails&id=${videoIds}&key=${apiKey}`;
        
        const statsResponse = await fetch(statsUrl);
        const statsData = await statsResponse.json();
        
        // Merge statistics with video data
        const videos = data.items.map(item => {
            const stats = statsData.items.find(s => s.id === item.id.videoId);
            return {
                ...item,
                statistics: stats?.statistics || {},
                contentDetails: stats?.contentDetails || {}
            };
        });
        
        // Format response
        const formatted = formatVideoResults(videos, searchQuery);
        
        return {
            success: true,
            data: videos,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching videos:', error);
        return {
            success: false,
            error: 'Failed to search videos'
        };
    }
}

// ==========================================
// GET CHANNEL INFO
// ==========================================
async function getChannelInfo(channelName, apiKey) {
    try {
        // First search for the channel
        const searchUrl = `https://www.googleapis.com/youtube/v3/search?part=snippet&q=${encodeURIComponent(channelName)}&type=channel&maxResults=1&key=${apiKey}`;
        
        const searchResponse = await fetch(searchUrl);
        const searchData = await searchResponse.json();
        
        if (!searchData.items || searchData.items.length === 0) {
            return {
                success: false,
                error: `Channel not found: "${channelName}"`,
                hint: 'Try the exact channel name or username'
            };
        }
        
        const channelId = searchData.items[0].id.channelId;
        
        // Get detailed channel information
        const channelUrl = `https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics,contentDetails&id=${channelId}&key=${apiKey}`;
        
        const channelResponse = await fetch(channelUrl);
        const channelData = await channelResponse.json();
        
        if (!channelData.items || channelData.items.length === 0) {
            return {
                success: false,
                error: 'Failed to get channel details'
            };
        }
        
        const channel = channelData.items[0];
        
        // Get recent videos from channel
        const uploadsPlaylistId = channel.contentDetails.relatedPlaylists.uploads;
        const videosUrl = `https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId=${uploadsPlaylistId}&maxResults=5&key=${apiKey}`;
        
        const videosResponse = await fetch(videosUrl);
        const videosData = await videosResponse.json();
        
        // Format response
        const formatted = formatChannelInfo(channel, videosData.items);
        
        return {
            success: true,
            data: { channel, recentVideos: videosData.items },
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting channel info:', error);
        return {
            success: false,
            error: 'Failed to get channel information'
        };
    }
}

// ==========================================
// GET TRENDING VIDEOS
// ==========================================
async function getTrendingVideos(categoryId, apiKey) {
    try {
        let url = `https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&chart=mostPopular&maxResults=10&regionCode=US&key=${apiKey}`;
        
        if (categoryId) {
            url += `&videoCategoryId=${categoryId}`;
        }
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`YouTube API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: 'No trending videos found'
            };
        }
        
        // Format response
        const formatted = formatTrendingVideos(data.items);
        
        return {
            success: true,
            data: data.items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting trending videos:', error);
        return {
            success: false,
            error: 'Failed to get trending videos'
        };
    }
}

// ==========================================
// GET VIDEO DETAILS
// ==========================================
async function getVideoDetails(videoId, apiKey) {
    try {
        const url = `https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics,contentDetails&id=${videoId}&key=${apiKey}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`YouTube API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: 'Video not found'
            };
        }
        
        const video = data.items[0];
        
        // Format response
        const formatted = formatVideoDetails(video);
        
        return {
            success: true,
            data: video,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting video details:', error);
        return {
            success: false,
            error: 'Failed to get video details'
        };
    }
}

// ==========================================
// FORMAT VIDEO RESULTS
// ==========================================
function formatVideoResults(videos, query) {
    let formatted = `📺 **YouTube Search: "${query}"**\n\n`;
    formatted += `Found ${videos.length} videos:\n\n`;
    
    videos.forEach((video, index) => {
        const title = video.snippet.title;
        const channel = video.snippet.channelTitle;
        const publishedAt = new Date(video.snippet.publishedAt);
        const videoId = video.id.videoId;
        const views = video.statistics?.viewCount ? formatNumber(video.statistics.viewCount) : 'N/A';
        const likes = video.statistics?.likeCount ? formatNumber(video.statistics.likeCount) : 'N/A';
        
        formatted += `**${index + 1}. ${title}**\n`;
        formatted += `   👤 ${channel}\n`;
        formatted += `   👁️ ${views} views • 👍 ${likes} likes\n`;
        formatted += `   📅 ${formatDate(publishedAt)}\n`;
        formatted += `   🔗 [Watch Video](https://www.youtube.com/watch?v=${videoId})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT CHANNEL INFO
// ==========================================
function formatChannelInfo(channel, recentVideos) {
    const name = channel.snippet.title;
    const description = channel.snippet.description;
    const subscribers = formatNumber(channel.statistics.subscriberCount);
    const totalViews = formatNumber(channel.statistics.viewCount);
    const videoCount = channel.statistics.videoCount;
    const channelUrl = `https://www.youtube.com/channel/${channel.id}`;
    
    let formatted = `📺 **${name}**\n\n`;
    formatted += `${description.substring(0, 200)}${description.length > 200 ? '...' : ''}\n\n`;
    formatted += `👥 **${subscribers} subscribers**\n`;
    formatted += `👁️ **${totalViews} total views**\n`;
    formatted += `🎥 **${videoCount} videos**\n\n`;
    
    if (recentVideos && recentVideos.length > 0) {
        formatted += `**Recent Videos:**\n`;
        recentVideos.slice(0, 5).forEach((video, index) => {
            const title = video.snippet.title;
            const videoId = video.snippet.resourceId.videoId;
            formatted += `${index + 1}. [${title}](https://www.youtube.com/watch?v=${videoId})\n`;
        });
        formatted += '\n';
    }
    
    formatted += `🔗 [Visit Channel](${channelUrl})`;
    
    return formatted;
}

// ==========================================
// FORMAT TRENDING VIDEOS
// ==========================================
function formatTrendingVideos(videos) {
    let formatted = `🔥 **Trending Videos on YouTube**\n\n`;
    
    videos.forEach((video, index) => {
        const title = video.snippet.title;
        const channel = video.snippet.channelTitle;
        const views = formatNumber(video.statistics.viewCount);
        const likes = formatNumber(video.statistics.likeCount);
        const videoId = video.id;
        
        formatted += `**${index + 1}. ${title}**\n`;
        formatted += `   👤 ${channel}\n`;
        formatted += `   👁️ ${views} views • 👍 ${likes} likes\n`;
        formatted += `   🔗 [Watch Video](https://www.youtube.com/watch?v=${videoId})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT VIDEO DETAILS
// ==========================================
function formatVideoDetails(video) {
    const title = video.snippet.title;
    const channel = video.snippet.channelTitle;
    const description = video.snippet.description;
    const publishedAt = new Date(video.snippet.publishedAt);
    const views = formatNumber(video.statistics.viewCount);
    const likes = formatNumber(video.statistics.likeCount);
    const comments = formatNumber(video.statistics.commentCount);
    const duration = parseDuration(video.contentDetails.duration);
    const videoUrl = `https://www.youtube.com/watch?v=${video.id}`;
    
    let formatted = `📺 **${title}**\n\n`;
    formatted += `👤 **Channel:** ${channel}\n`;
    formatted += `⏱️ **Duration:** ${duration}\n`;
    formatted += `📅 **Published:** ${formatDate(publishedAt)}\n`;
    formatted += `👁️ **Views:** ${views}\n`;
    formatted += `👍 **Likes:** ${likes}\n`;
    formatted += `💬 **Comments:** ${comments}\n\n`;
    formatted += `**Description:**\n${description.substring(0, 300)}${description.length > 300 ? '...' : ''}\n\n`;
    formatted += `🔗 [Watch Video](${videoUrl})`;
    
    return formatted;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function formatNumber(num) {
    if (!num) return '0';
    
    const number = parseInt(num);
    
    if (number >= 1000000000) {
        return (number / 1000000000).toFixed(1) + 'B';
    } else if (number >= 1000000) {
        return (number / 1000000).toFixed(1) + 'M';
    } else if (number >= 1000) {
        return (number / 1000).toFixed(1) + 'K';
    }
    
    return number.toString();
}

function formatDate(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffDays < 1) {
        return 'Today';
    } else if (diffDays < 7) {
        return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
    } else if (diffDays < 30) {
        const weeks = Math.floor(diffDays / 7);
        return `${weeks} week${weeks === 1 ? '' : 's'} ago`;
    } else if (diffDays < 365) {
        const months = Math.floor(diffDays / 30);
        return `${months} month${months === 1 ? '' : 's'} ago`;
    } else {
        const years = Math.floor(diffDays / 365);
        return `${years} year${years === 1 ? '' : 's'} ago`;
    }
}

function parseDuration(duration) {
    // Parse ISO 8601 duration format (PT#H#M#S)
    const match = duration.match(/PT(\d+H)?(\d+M)?(\d+S)?/);
    
    const hours = (match[1] || '').replace('H', '');
    const minutes = (match[2] || '').replace('M', '');
    const seconds = (match[3] || '').replace('S', '');
    
    let result = '';
    
    if (hours) result += `${hours}:`;
    if (minutes) result += `${minutes.padStart(2, '0')}:`;
    else if (hours) result += '00:';
    
    result += (seconds || '0').padStart(2, '0');
    
    return result;
}
