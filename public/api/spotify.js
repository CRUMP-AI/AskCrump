// ==========================================
// CRUMP AI - SPOTIFY API
// Spotify Web API Integration
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
        
        // Check for API credentials
        const clientId = process.env.SPOTIFY_CLIENT_ID;
        const clientSecret = process.env.SPOTIFY_CLIENT_SECRET;
        
        if (!clientId || !clientSecret) {
            console.warn('⚠️ Spotify API credentials not configured');
            return res.status(503).json({ 
                error: 'Spotify API credentials not configured',
                fallback: true,
                message: 'Please add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to environment variables'
            });
        }
        
        console.log(`🎵 Spotify query: ${query}`);
        
        // Get access token
        const accessToken = await getAccessToken(clientId, clientSecret);
        
        if (!accessToken) {
            return res.status(500).json({ 
                error: 'Failed to authenticate with Spotify'
            });
        }
        
        // Detect intent and extract search query
        const intent = detectSpotifyIntent(query);
        const searchQuery = extractSearchQuery(query);
        
        if (!searchQuery) {
            return res.status(400).json({ 
                error: 'Could not determine search query',
                hint: 'Try: "Find songs by Drake" or "Search Spotify for jazz music"'
            });
        }
        
        console.log(`🎯 Searching ${intent.type}: ${searchQuery}`);
        
        let result;
        
        switch (intent.type) {
            case 'track':
                result = await searchTracks(searchQuery, accessToken);
                break;
            
            case 'artist':
                result = await searchArtists(searchQuery, accessToken);
                break;
            
            case 'album':
                result = await searchAlbums(searchQuery, accessToken);
                break;
            
            case 'playlist':
                result = await searchPlaylists(searchQuery, accessToken);
                break;
            
            default:
                // Default to track search
                result = await searchTracks(searchQuery, accessToken);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'spotify',
            query: searchQuery,
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Spotify API error:', error);
        return res.status(500).json({ 
            error: 'Spotify search failed',
            details: error.message 
        });
    }
}

// ==========================================
// GET ACCESS TOKEN (Client Credentials Flow)
// ==========================================
async function getAccessToken(clientId, clientSecret) {
    try {
        const authString = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');
        
        const response = await fetch('https://accounts.spotify.com/api/token', {
            method: 'POST',
            headers: {
                'Authorization': `Basic ${authString}`,
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: 'grant_type=client_credentials'
        });
        
        if (!response.ok) {
            console.error('Failed to get Spotify access token:', response.status);
            return null;
        }
        
        const data = await response.json();
        return data.access_token;
        
    } catch (error) {
        console.error('Error getting Spotify access token:', error);
        return null;
    }
}

// ==========================================
// DETECT SPOTIFY INTENT
// ==========================================
function detectSpotifyIntent(query) {
    const text = query.toLowerCase();
    
    // Artist search
    if (text.includes('artist') || text.includes('musician') || text.match(/music by|songs by/i)) {
        return { type: 'artist' };
    }
    
    // Album search
    if (text.includes('album')) {
        return { type: 'album' };
    }
    
    // Playlist search
    if (text.includes('playlist')) {
        return { type: 'playlist' };
    }
    
    // Default to track search
    return { type: 'track' };
}

// ==========================================
// EXTRACT SEARCH QUERY
// ==========================================
function extractSearchQuery(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: "find [query] on spotify"
    let match = text.match(/find\s+(.+?)\s+(?:on|in)\s+spotify/i);
    if (match) return match[1].trim();
    
    // Pattern 2: "search spotify for [query]"
    match = text.match(/search\s+spotify\s+for\s+(.+)/i);
    if (match) return match[1].trim();
    
    // Pattern 3: "spotify [query]"
    match = text.match(/spotify\s+(.+)/i);
    if (match) return match[1].trim();
    
    // Pattern 4: "songs by [artist]" or "music by [artist]"
    match = text.match(/(?:songs?|music|tracks?)\s+by\s+(.+)/i);
    if (match) return match[1].trim();
    
    // Pattern 5: "play [query]"
    match = text.match(/play\s+(.+)/i);
    if (match) return match[1].trim();
    
    // Pattern 6: "[artist] songs"
    match = text.match(/(.+?)\s+(?:songs?|music|tracks?)/i);
    if (match) return match[1].trim();
    
    // Pattern 7: "who sang [query]"
    match = text.match(/who\s+(?:sang|sings)\s+(.+)/i);
    if (match) return match[1].trim();
    
    // Default: return cleaned query
    return text.replace(/spotify|find|search|play|music|song|track/gi, '').trim();
}

// ==========================================
// SEARCH TRACKS
// ==========================================
async function searchTracks(query, accessToken) {
    try {
        const url = `https://api.spotify.com/v1/search?q=${encodeURIComponent(query)}&type=track&limit=15`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        
        if (!response.ok) {
            throw new Error(`Spotify API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.tracks || !data.tracks.items || data.tracks.items.length === 0) {
            return {
                success: false,
                error: `No tracks found for "${query}"`,
                hint: 'Try a different song name or artist'
            };
        }
        
        const tracks = data.tracks.items;
        
        // Format response
        const formatted = formatTracks(tracks, query);
        
        return {
            success: true,
            data: tracks,
            formatted: formatted,
            totalResults: data.tracks.total
        };
        
    } catch (error) {
        console.error('Error searching Spotify tracks:', error);
        return {
            success: false,
            error: 'Failed to search Spotify tracks'
        };
    }
}

// ==========================================
// SEARCH ARTISTS
// ==========================================
async function searchArtists(query, accessToken) {
    try {
        const url = `https://api.spotify.com/v1/search?q=${encodeURIComponent(query)}&type=artist&limit=10`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        
        if (!response.ok) {
            throw new Error(`Spotify API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.artists || !data.artists.items || data.artists.items.length === 0) {
            return {
                success: false,
                error: `No artists found for "${query}"`,
                hint: 'Try a different artist name'
            };
        }
        
        const artists = data.artists.items;
        
        // Get top tracks for the first artist
        let topTracks = null;
        if (artists.length > 0) {
            const artistId = artists[0].id;
            const topTracksUrl = `https://api.spotify.com/v1/artists/${artistId}/top-tracks?market=US`;
            
            const topTracksResponse = await fetch(topTracksUrl, {
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                }
            });
            
            if (topTracksResponse.ok) {
                const topTracksData = await topTracksResponse.json();
                topTracks = topTracksData.tracks;
            }
        }
        
        // Format response
        const formatted = formatArtists(artists, topTracks, query);
        
        return {
            success: true,
            data: { artists, topTracks },
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching Spotify artists:', error);
        return {
            success: false,
            error: 'Failed to search Spotify artists'
        };
    }
}

// ==========================================
// SEARCH ALBUMS
// ==========================================
async function searchAlbums(query, accessToken) {
    try {
        const url = `https://api.spotify.com/v1/search?q=${encodeURIComponent(query)}&type=album&limit=10`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        
        if (!response.ok) {
            throw new Error(`Spotify API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.albums || !data.albums.items || data.albums.items.length === 0) {
            return {
                success: false,
                error: `No albums found for "${query}"`,
                hint: 'Try a different album name'
            };
        }
        
        const albums = data.albums.items;
        
        // Format response
        const formatted = formatAlbums(albums, query);
        
        return {
            success: true,
            data: albums,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching Spotify albums:', error);
        return {
            success: false,
            error: 'Failed to search Spotify albums'
        };
    }
}

// ==========================================
// SEARCH PLAYLISTS
// ==========================================
async function searchPlaylists(query, accessToken) {
    try {
        const url = `https://api.spotify.com/v1/search?q=${encodeURIComponent(query)}&type=playlist&limit=10`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        
        if (!response.ok) {
            throw new Error(`Spotify API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.playlists || !data.playlists.items || data.playlists.items.length === 0) {
            return {
                success: false,
                error: `No playlists found for "${query}"`,
                hint: 'Try a different playlist name'
            };
        }
        
        const playlists = data.playlists.items;
        
        // Format response
        const formatted = formatPlaylists(playlists, query);
        
        return {
            success: true,
            data: playlists,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching Spotify playlists:', error);
        return {
            success: false,
            error: 'Failed to search Spotify playlists'
        };
    }
}

// ==========================================
// FORMAT TRACKS
// ==========================================
function formatTracks(tracks, query) {
    let formatted = `🎵 **Spotify Tracks: ${query}**\n\n`;
    formatted += `Found ${tracks.length} tracks:\n\n`;
    
    tracks.slice(0, 10).forEach((track, index) => {
        const name = track.name;
        const artists = track.artists.map(a => a.name).join(', ');
        const album = track.album.name;
        const duration = formatDuration(track.duration_ms);
        const url = track.external_urls.spotify;
        const popularity = track.popularity;
        
        formatted += `**${index + 1}. ${name}**\n`;
        formatted += `   🎤 ${artists}\n`;
        formatted += `   💿 ${album} • ⏱️ ${duration}`;
        
        if (popularity) {
            formatted += ` • 🔥 ${popularity}% popular`;
        }
        
        formatted += `\n   🔗 [Listen on Spotify](${url})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT ARTISTS
// ==========================================
function formatArtists(artists, topTracks, query) {
    let formatted = `🎤 **Spotify Artists: ${query}**\n\n`;
    
    // Show main artist
    const mainArtist = artists[0];
    formatted += `**${mainArtist.name}**\n`;
    
    if (mainArtist.genres && mainArtist.genres.length > 0) {
        formatted += `🎸 Genres: ${mainArtist.genres.slice(0, 3).join(', ')}\n`;
    }
    
    formatted += `👥 ${formatNumber(mainArtist.followers.total)} followers`;
    
    if (mainArtist.popularity) {
        formatted += ` • 🔥 ${mainArtist.popularity}% popularity`;
    }
    
    formatted += `\n🔗 [View on Spotify](${mainArtist.external_urls.spotify})\n\n`;
    
    // Show top tracks if available
    if (topTracks && topTracks.length > 0) {
        formatted += `**🎵 Top Tracks:**\n`;
        topTracks.slice(0, 5).forEach((track, index) => {
            formatted += `${index + 1}. ${track.name} (${track.album.name})\n`;
        });
        formatted += '\n';
    }
    
    // Show other matching artists
    if (artists.length > 1) {
        formatted += `**Other Artists:**\n`;
        artists.slice(1, 5).forEach((artist, index) => {
            formatted += `${index + 2}. ${artist.name} (${formatNumber(artist.followers.total)} followers)\n`;
        });
    }
    
    return formatted;
}

// ==========================================
// FORMAT ALBUMS
// ==========================================
function formatAlbums(albums, query) {
    let formatted = `💿 **Spotify Albums: ${query}**\n\n`;
    
    albums.forEach((album, index) => {
        const name = album.name;
        const artists = album.artists.map(a => a.name).join(', ');
        const releaseDate = album.release_date;
        const totalTracks = album.total_tracks;
        const url = album.external_urls.spotify;
        
        formatted += `**${index + 1}. ${name}**\n`;
        formatted += `   🎤 ${artists}\n`;
        formatted += `   📅 ${releaseDate} • 🎵 ${totalTracks} tracks\n`;
        formatted += `   🔗 [Listen on Spotify](${url})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT PLAYLISTS
// ==========================================
function formatPlaylists(playlists, query) {
    let formatted = `📻 **Spotify Playlists: ${query}**\n\n`;
    
    playlists.forEach((playlist, index) => {
        const name = playlist.name;
        const owner = playlist.owner.display_name;
        const totalTracks = playlist.tracks.total;
        const url = playlist.external_urls.spotify;
        const description = playlist.description;
        
        formatted += `**${index + 1}. ${name}**\n`;
        formatted += `   👤 By ${owner} • 🎵 ${totalTracks} tracks\n`;
        
        if (description) {
            const shortDesc = description.length > 80 
                ? description.substring(0, 80) + '...' 
                : description;
            // Remove HTML tags
            const cleanDesc = shortDesc.replace(/<[^>]*>/g, '');
            formatted += `   ${cleanDesc}\n`;
        }
        
        formatted += `   🔗 [Open Playlist](${url})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function formatDuration(ms) {
    const minutes = Math.floor(ms / 60000);
    const seconds = Math.floor((ms % 60000) / 1000);
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}
```

---

## **🔑 API KEY SETUP:**

1. Go to: https://developer.spotify.com/dashboard
2. Create an app (Login → Create an App)
3. Get your **Client ID** and **Client Secret**
4. Free tier: **Unlimited searches** (rate limited)
5. Add to Vercel:
```
   SPOTIFY_CLIENT_ID=your_client_id_here
   SPOTIFY_CLIENT_SECRET=your_client_secret_here
