// ==========================================
// CRUMP AI - MOVIES API
// The Movie Database (TMDB) API Integration
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
        const apiKey = process.env.TMDB_API_KEY;
        
        if (!apiKey) {
            console.warn('⚠️ TMDB API key not configured');
            return res.status(503).json({ 
                error: 'Movies API key not configured',
                fallback: true,
                message: 'Please add TMDB_API_KEY to environment variables'
            });
        }
        
        console.log(`🎬 Movies query: ${query}`);
        
        // Detect intent
        const intent = detectMovieIntent(query);
        
        if (!intent) {
            return res.status(400).json({ 
                error: 'Could not understand movie query',
                hint: 'Try: "Search for Inception" or "Popular movies right now"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        switch (intent.type) {
            case 'search_movie':
                result = await searchMovie(intent.movieName, apiKey);
                break;
            
            case 'search_tv':
                result = await searchTVShow(intent.showName, apiKey);
                break;
            
            case 'movie_details':
                result = await getMovieDetails(intent.movieName, apiKey);
                break;
            
            case 'popular':
                result = await getPopular(intent.mediaType, apiKey);
                break;
            
            case 'trending':
                result = await getTrending(intent.mediaType, intent.timeWindow, apiKey);
                break;
            
            case 'now_playing':
                result = await getNowPlaying(apiKey);
                break;
            
            case 'upcoming':
                result = await getUpcoming(apiKey);
                break;
            
            case 'top_rated':
                result = await getTopRated(intent.mediaType, apiKey);
                break;
            
            case 'recommendations':
                result = await getRecommendations(intent.movieName, apiKey);
                break;
            
            case 'actor_search':
                result = await searchActor(intent.actorName, apiKey);
                break;
            
            default:
                result = await searchMovie(query, apiKey);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'movies',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Movies API error:', error);
        return res.status(500).json({ 
            error: 'Movie lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT MOVIE INTENT
// ==========================================
function detectMovieIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: Search for specific movie
    if (text.match(/(?:search|find|look up|tell me about|info on|details about)\s+(?:the\s+)?(?:movie|film)/i)) {
        const match = text.match(/(?:search|find|look up|tell me about|info on|details about)\s+(?:the\s+)?(?:movie|film)\s+(.+)/i);
        if (match) {
            return {
                type: 'movie_details',
                movieName: match[1].trim()
            };
        }
    }
    
    // Pattern 2: Search for TV show
    if (text.match(/(?:search|find|look up|tell me about)\s+(?:the\s+)?(?:tv show|series|show)/i)) {
        const match = text.match(/(?:search|find|look up|tell me about)\s+(?:the\s+)?(?:tv show|series|show)\s+(.+)/i);
        if (match) {
            return {
                type: 'search_tv',
                showName: match[1].trim()
            };
        }
    }
    
    // Pattern 3: Popular movies/shows
    if (text.match(/popular|most watched|trending/i)) {
        const mediaType = text.includes('tv') || text.includes('show') || text.includes('series') ? 'tv' : 'movie';
        
        if (text.includes('trending')) {
            const timeWindow = text.includes('today') ? 'day' : 'week';
            return {
                type: 'trending',
                mediaType: mediaType,
                timeWindow: timeWindow
            };
        }
        
        return {
            type: 'popular',
            mediaType: mediaType
        };
    }
    
    // Pattern 4: Now playing
    if (text.match(/now playing|in theaters|in cinemas|currently showing/i)) {
        return {
            type: 'now_playing'
        };
    }
    
    // Pattern 5: Upcoming
    if (text.match(/upcoming|coming soon|future releases|new releases/i)) {
        return {
            type: 'upcoming'
        };
    }
    
    // Pattern 6: Top rated
    if (text.match(/top rated|best|highest rated/i)) {
        const mediaType = text.includes('tv') || text.includes('show') || text.includes('series') ? 'tv' : 'movie';
        return {
            type: 'top_rated',
            mediaType: mediaType
        };
    }
    
    // Pattern 7: Recommendations
    if (text.match(/similar to|like|recommendations|if i liked/i)) {
        const match = text.match(/(?:similar to|like|recommendations|if i liked)\s+(.+)/i);
        if (match) {
            return {
                type: 'recommendations',
                movieName: match[1].trim()
            };
        }
    }
    
    // Pattern 8: Actor/actress search
    if (text.match(/movies (?:with|by|starring)|actor|actress/i)) {
        const match = text.match(/(?:movies (?:with|by|starring)|actor|actress)\s+(.+)/i);
        if (match) {
            return {
                type: 'actor_search',
                actorName: match[1].trim()
            };
        }
    }
    
    // Default: Search movie
    const movieName = text
        .replace(/movie|film|search|find/gi, '')
        .trim();
    
    return {
        type: 'search_movie',
        movieName: movieName
    };
}

// ==========================================
// SEARCH MOVIE
// ==========================================
async function searchMovie(movieName, apiKey) {
    try {
        const url = `https://api.themoviedb.org/3/search/movie?api_key=${apiKey}&query=${encodeURIComponent(movieName)}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            if (response.status === 401) {
                return {
                    success: false,
                    error: 'Invalid TMDB API key',
                    hint: 'Check your TMDB_API_KEY environment variable'
                };
            }
            throw new Error(`TMDB API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.results || data.results.length === 0) {
            return {
                success: false,
                error: `No movies found for "${movieName}"`,
                hint: 'Try a different movie title'
            };
        }
        
        // Get top 10 results
        const movies = data.results.slice(0, 10);
        
        // Format response
        const formatted = formatMovieSearchResults(movies, movieName);
        
        return {
            success: true,
            data: movies,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching movie:', error);
        return {
            success: false,
            error: 'Failed to search movie'
        };
    }
}

// ==========================================
// SEARCH TV SHOW
// ==========================================
async function searchTVShow(showName, apiKey) {
    try {
        const url = `https://api.themoviedb.org/3/search/tv?api_key=${apiKey}&query=${encodeURIComponent(showName)}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`TMDB API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.results || data.results.length === 0) {
            return {
                success: false,
                error: `No TV shows found for "${showName}"`
            };
        }
        
        const shows = data.results.slice(0, 10);
        
        // Format response
        const formatted = formatTVSearchResults(shows, showName);
        
        return {
            success: true,
            data: shows,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching TV show:', error);
        return {
            success: false,
            error: 'Failed to search TV show'
        };
    }
}

// ==========================================
// GET MOVIE DETAILS
// ==========================================
async function getMovieDetails(movieName, apiKey) {
    try {
        // First search for the movie
        const searchUrl = `https://api.themoviedb.org/3/search/movie?api_key=${apiKey}&query=${encodeURIComponent(movieName)}`;
        
        const searchResponse = await fetch(searchUrl);
        const searchData = await searchResponse.json();
        
        if (!searchData.results || searchData.results.length === 0) {
            return {
                success: false,
                error: `Movie not found: "${movieName}"`
            };
        }
        
        const movieId = searchData.results[0].id;
        
        // Get detailed info including credits and videos
        const detailsUrl = `https://api.themoviedb.org/3/movie/${movieId}?api_key=${apiKey}&append_to_response=credits,videos,reviews`;
        
        const detailsResponse = await fetch(detailsUrl);
        const details = await detailsResponse.json();
        
        // Format response
        const formatted = formatMovieDetails(details);
        
        return {
            success: true,
            data: details,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting movie details:', error);
        return {
            success: false,
            error: 'Failed to get movie details'
        };
    }
}

// ==========================================
// GET POPULAR
// ==========================================
async function getPopular(mediaType, apiKey) {
    try {
        const endpoint = mediaType === 'tv' ? 'tv/popular' : 'movie/popular';
        const url = `https://api.themoviedb.org/3/${endpoint}?api_key=${apiKey}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`TMDB API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        const items = data.results.slice(0, 10);
        
        // Format response
        const formatted = mediaType === 'tv' 
            ? formatTVList(items, 'Popular TV Shows')
            : formatMovieList(items, 'Popular Movies');
        
        return {
            success: true,
            data: items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting popular:', error);
        return {
            success: false,
            error: 'Failed to get popular content'
        };
    }
}

// ==========================================
// GET TRENDING
// ==========================================
async function getTrending(mediaType, timeWindow, apiKey) {
    try {
        const media = mediaType === 'tv' ? 'tv' : 'movie';
        const url = `https://api.themoviedb.org/3/trending/${media}/${timeWindow}?api_key=${apiKey}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`TMDB API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        const items = data.results.slice(0, 10);
        
        const timeLabel = timeWindow === 'day' ? 'Today' : 'This Week';
        const title = `Trending ${mediaType === 'tv' ? 'TV Shows' : 'Movies'} ${timeLabel}`;
        
        // Format response
        const formatted = mediaType === 'tv' 
            ? formatTVList(items, title)
            : formatMovieList(items, title);
        
        return {
            success: true,
            data: items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting trending:', error);
        return {
            success: false,
            error: 'Failed to get trending content'
        };
    }
}

// ==========================================
// GET NOW PLAYING
// ==========================================
async function getNowPlaying(apiKey) {
    try {
        const url = `https://api.themoviedb.org/3/movie/now_playing?api_key=${apiKey}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`TMDB API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        const movies = data.results.slice(0, 10);
        
        // Format response
        const formatted = formatMovieList(movies, 'Now Playing in Theaters');
        
        return {
            success: true,
            data: movies,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting now playing:', error);
        return {
            success: false,
            error: 'Failed to get now playing movies'
        };
    }
}

// ==========================================
// GET UPCOMING
// ==========================================
async function getUpcoming(apiKey) {
    try {
        const url = `https://api.themoviedb.org/3/movie/upcoming?api_key=${apiKey}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`TMDB API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        const movies = data.results.slice(0, 10);
        
        // Format response
        const formatted = formatMovieList(movies, 'Upcoming Movies');
        
        return {
            success: true,
            data: movies,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting upcoming:', error);
        return {
            success: false,
            error: 'Failed to get upcoming movies'
        };
    }
}

// ==========================================
// GET TOP RATED
// ==========================================
async function getTopRated(mediaType, apiKey) {
    try {
        const endpoint = mediaType === 'tv' ? 'tv/top_rated' : 'movie/top_rated';
        const url = `https://api.themoviedb.org/3/${endpoint}?api_key=${apiKey}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`TMDB API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        const items = data.results.slice(0, 10);
        
        // Format response
        const formatted = mediaType === 'tv' 
            ? formatTVList(items, 'Top Rated TV Shows')
            : formatMovieList(items, 'Top Rated Movies');
        
        return {
            success: true,
            data: items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting top rated:', error);
        return {
            success: false,
            error: 'Failed to get top rated content'
        };
    }
}

// ==========================================
// GET RECOMMENDATIONS
// ==========================================
async function getRecommendations(movieName, apiKey) {
    try {
        // First search for the movie
        const searchUrl = `https://api.themoviedb.org/3/search/movie?api_key=${apiKey}&query=${encodeURIComponent(movieName)}`;
        
        const searchResponse = await fetch(searchUrl);
        const searchData = await searchResponse.json();
        
        if (!searchData.results || searchData.results.length === 0) {
            return {
                success: false,
                error: `Movie not found: "${movieName}"`
            };
        }
        
        const movieId = searchData.results[0].id;
        
        // Get recommendations
        const recUrl = `https://api.themoviedb.org/3/movie/${movieId}/recommendations?api_key=${apiKey}`;
        
        const recResponse = await fetch(recUrl);
        const recData = await recResponse.json();
        
        if (!recData.results || recData.results.length === 0) {
            return {
                success: false,
                error: `No recommendations found for "${movieName}"`
            };
        }
        
        const recommendations = recData.results.slice(0, 10);
        
        // Format response
        const formatted = formatMovieList(recommendations, `Movies Similar to ${searchData.results[0].title}`);
        
        return {
            success: true,
            data: recommendations,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting recommendations:', error);
        return {
            success: false,
            error: 'Failed to get recommendations'
        };
    }
}

// ==========================================
// SEARCH ACTOR
// ==========================================
async function searchActor(actorName, apiKey) {
    try {
        // Search for person
        const personUrl = `https://api.themoviedb.org/3/search/person?api_key=${apiKey}&query=${encodeURIComponent(actorName)}`;
        
        const personResponse = await fetch(personUrl);
        const personData = await personResponse.json();
        
        if (!personData.results || personData.results.length === 0) {
            return {
                success: false,
                error: `Actor not found: "${actorName}"`
            };
        }
        
        const person = personData.results[0];
        const personId = person.id;
        
        // Get their movie credits
        const creditsUrl = `https://api.themoviedb.org/3/person/${personId}/movie_credits?api_key=${apiKey}`;
        
        const creditsResponse = await fetch(creditsUrl);
        const creditsData = await creditsResponse.json();
        
        // Sort by popularity and get top movies
        const movies = creditsData.cast
            .sort((a, b) => b.popularity - a.popularity)
            .slice(0, 10);
        
        // Format response
        const formatted = formatActorMovies(movies, person.name);
        
        return {
            success: true,
            data: { person, movies },
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching actor:', error);
        return {
            success: false,
            error: 'Failed to search actor'
        };
    }
}

// ==========================================
// FORMAT MOVIE SEARCH RESULTS
// ==========================================
function formatMovieSearchResults(movies, query) {
    let formatted = `🎬 **Movie Search: "${query}"**\n\n`;
    formatted += `Found ${movies.length} movies:\n\n`;
    
    movies.forEach((movie, index) => {
        const title = movie.title;
        const year = movie.release_date ? new Date(movie.release_date).getFullYear() : 'N/A';
        const rating = movie.vote_average ? movie.vote_average.toFixed(1) : 'N/A';
        const overview = movie.overview 
            ? (movie.overview.length > 120 ? movie.overview.substring(0, 120) + '...' : movie.overview)
            : 'No description available';
        
        formatted += `**${index + 1}. ${title} (${year})**\n`;
        formatted += `   ⭐ ${rating}/10\n`;
        formatted += `   ${overview}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT TV SEARCH RESULTS
// ==========================================
function formatTVSearchResults(shows, query) {
    let formatted = `📺 **TV Show Search: "${query}"**\n\n`;
    formatted += `Found ${shows.length} shows:\n\n`;
    
    shows.forEach((show, index) => {
        const name = show.name;
        const year = show.first_air_date ? new Date(show.first_air_date).getFullYear() : 'N/A';
        const rating = show.vote_average ? show.vote_average.toFixed(1) : 'N/A';
        const overview = show.overview 
            ? (show.overview.length > 120 ? show.overview.substring(0, 120) + '...' : show.overview)
            : 'No description available';
        
        formatted += `**${index + 1}. ${name} (${year})**\n`;
        formatted += `   ⭐ ${rating}/10\n`;
        formatted += `   ${overview}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT MOVIE DETAILS
// ==========================================
function formatMovieDetails(movie) {
    const title = movie.title;
    const year = movie.release_date ? new Date(movie.release_date).getFullYear() : 'N/A';
    const rating = movie.vote_average ? movie.vote_average.toFixed(1) : 'N/A';
    const runtime = movie.runtime ? `${movie.runtime} min` : 'N/A';
    const genres = movie.genres ? movie.genres.map(g => g.name).join(', ') : 'N/A';
    const overview = movie.overview || 'No description available';
    const budget = movie.budget ? `$${(movie.budget / 1000000).toFixed(0)}M` : 'N/A';
    const revenue = movie.revenue ? `$${(movie.revenue / 1000000).toFixed(0)}M` : 'N/A';
    
    let formatted = `🎬 **${title} (${year})**\n\n`;
    formatted += `⭐ **Rating:** ${rating}/10 (${movie.vote_count} votes)\n`;
    formatted += `⏱️ **Runtime:** ${runtime}\n`;
    formatted += `🎭 **Genres:** ${genres}\n`;
    formatted += `💰 **Budget:** ${budget} • **Revenue:** ${revenue}\n\n`;
    formatted += `**Overview:**\n${overview}\n\n`;
    
    // Cast
    if (movie.credits && movie.credits.cast && movie.credits.cast.length > 0) {
        const cast = movie.credits.cast
            .slice(0, 5)
            .map(c => c.name)
            .join(', ');
        formatted += `**Cast:** ${cast}\n\n`;
    }
    
    // Director
    if (movie.credits && movie.credits.crew) {
        const director = movie.credits.crew.find(c => c.job === 'Director');
        if (director) {
            formatted += `**Director:** ${director.name}\n\n`;
        }
    }
    
    // Trailer
    if (movie.videos && movie.videos.results && movie.videos.results.length > 0) {
        const trailer = movie.videos.results.find(v => v.type === 'Trailer' && v.site === 'YouTube');
        if (trailer) {
            formatted += `🎥 [Watch Trailer](https://www.youtube.com/watch?v=${trailer.key})\n`;
        }
    }
    
    // TMDB link
    formatted += `🔗 [View on TMDB](https://www.themoviedb.org/movie/${movie.id})`;
    
    return formatted;
}

// ==========================================
// FORMAT MOVIE LIST
// ==========================================
function formatMovieList(movies, title) {
    let formatted = `🎬 **${title}**\n\n`;
    
    movies.forEach((movie, index) => {
        const movieTitle = movie.title;
        const year = movie.release_date ? new Date(movie.release_date).getFullYear() : 'N/A';
        const rating = movie.vote_average ? movie.vote_average.toFixed(1) : 'N/A';
        
        formatted += `**${index + 1}. ${movieTitle} (${year})**\n`;
        formatted += `   ⭐ ${rating}/10\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT TV LIST
// ==========================================
function formatTVList(shows, title) {
    let formatted = `📺 **${title}**\n\n`;
    
    shows.forEach((show, index) => {
        const showName = show.name;
        const year = show.first_air_date ? new Date(show.first_air_date).getFullYear() : 'N/A';
        const rating = show.vote_average ? show.vote_average.toFixed(1) : 'N/A';
        
        formatted += `**${index + 1}. ${showName} (${year})**\n`;
        formatted += `   ⭐ ${rating}/10\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT ACTOR MOVIES
// ==========================================
function formatActorMovies(movies, actorName) {
    let formatted = `🎬 **Movies Starring ${actorName}**\n\n`;
    
    movies.forEach((movie, index) => {
        const title = movie.title;
        const year = movie.release_date ? new Date(movie.release_date).getFullYear() : 'N/A';
        const character = movie.character || 'Unknown role';
        const rating = movie.vote_average ? movie.vote_average.toFixed(1) : 'N/A';
        
        formatted += `**${index + 1}. ${title} (${year})**\n`;
        formatted += `   🎭 as ${character}\n`;
        formatted += `   ⭐ ${rating}/10\n\n`;
    });
    
    return formatted;
}
