// ==========================================
// CRUMP AI - WEATHER API
// OpenWeatherMap Integration (Improved Parsing)
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
        const { query, context } = req.body || {};
        
        if (!query || typeof query !== 'string') {
            return res.status(400).json({ error: 'Query is required' });
        }
        
        // Check for API key
        const apiKey = process.env.OPENWEATHER_API_KEY;
        if (!apiKey) {
            console.warn('⚠️ OpenWeatherMap API key not configured');
            return res.status(503).json({ 
                error: 'Weather API key not configured',
                fallback: true,
                message: 'Please add OPENWEATHER_API_KEY to environment variables'
            });
        }
        
        // Extract location from natural language
        const location = extractLocation(query);
        if (!location) {
            console.warn('⚠️ Could not extract location from query:', query);
            return res.status(400).json({ 
                error: 'Could not determine location from query',
                hint: 'Try: "weather in Atlanta" or "temperature in NYC"'
            });
        }
        
        console.log(`🌤️ Fetching weather for: ${location}`);
        
        // Call OpenWeatherMap API
        const weatherUrl = `https://api.openweathermap.org/data/2.5/weather?q=${encodeURIComponent(location)}&appid=${apiKey}&units=imperial`;
        const weatherResponse = await fetch(weatherUrl);
        
        if (!weatherResponse.ok) {
            const text = await weatherResponse.text().catch(() => null);
            console.warn('⚠️ OpenWeatherMap non-OK response:', weatherResponse.status, text);
            
            if (weatherResponse.status === 404) {
                return res.status(404).json({ 
                    error: `Location "${location}" not found`,
                    hint: 'Try a different city name or be more specific'
                });
            }
            
            return res.status(502).json({
                error: `Weather provider error (status ${weatherResponse.status})`
            });
        }
        
        const weatherData = await weatherResponse.json();
        const formatted = formatWeatherResponse(weatherData);
        
        return res.status(200).json({
            success: true,
            api: 'weather',
            location,
            data: weatherData,
            formatted
        });
        
    } catch (error) {
        console.error('❌ Weather API error:', error);
        return res.status(500).json({ 
            error: 'Weather lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// EXTRACT LOCATION FROM QUERY (IMPROVED)
// ==========================================
function extractLocation(query) {
    if (!query || typeof query !== 'string') return null;
    
    // Keep original case for nicer city names, but trim
    let text = query.trim();
    
    // Strip greetings / assistant name at the start
    text = text.replace(/^(hey|hi|hello|yo)\s+crump[,\s]*/i, '');
    text = text.replace(/^(hey|hi|hello|yo)[,\s]*/i, '');
    
    // Normalize spaces
    text = text.replace(/\s+/g, ' ').trim();
    
    // 1) "what's the weather like in georgia tomorrow?"
    let match = text.match(/weather\s+like\s+(?:in|at|for)\s+(.+)/i);
    if (match) return cleanLocation(match[1]);
    
    // 2) "weather in atlanta"
    match = text.match(/weather\s+(?:in|for|at)\s+(.+)/i);
    if (match) return cleanLocation(match[1]);
    
    // 3) "what's the weather in atlanta"
    match = text.match(/what'?s?\s+(?:the\s+)?weather\s+(?:in|for|at)\s+(.+)/i);
    if (match) return cleanLocation(match[1]);
    
    // 4) "temperature in atlanta"
    match = text.match(/temperature\s+(?:in|for|at)\s+(.+)/i);
    if (match) return cleanLocation(match[1]);
    
    // 5) "forecast for atlanta"
    match = text.match(/forecast\s+(?:for|in|at)\s+(.+)/i);
    if (match) return cleanLocation(match[1]);
    
    // 6) "how hot is atlanta", "how cold is it in atlanta"
    match = text.match(/how\s+(?:hot|cold|warm)\s+(?:is\s+)?(?:it\s+)?(?:in\s+)?(.+)/i);
    if (match) return cleanLocation(match[1]);
    
    // 7) "[location] weather"
    match = text.match(/^(.+?)\s+weather/i);
    if (match) return cleanLocation(match[1]);
    
    // Fallback: treat the whole thing as the location and clean it
    return cleanLocation(text);
}

// Clean up extra words / punctuation around the location
function cleanLocation(str) {
    if (!str) return null;
    
    let cleaned = str
        // Drop trailing punctuation
        .replace(/[?!.]+$/, '')
        // Remove time words
        .replace(/\b(today|tomorrow|tonight|this (?:morning|afternoon|evening|weekend)|right now|outside)\b/gi, '')
        // Remove helper words
        .replace(/\b(please|now|like|currently)\b/gi, '')
        // Remove assistant references
        .replace(/\b(crump|ask crump|assistant)\b/gi, '')
        // Trim stray commas / spaces at ends
        .replace(/^[,\s]+/, '')
        .replace(/[,\s]+$/, '')
        .trim();
    
    return cleaned.length > 0 ? cleaned : null;
}

// ==========================================
// FORMAT WEATHER RESPONSE
// ==========================================
function formatWeatherResponse(data) {
    const temp = Math.round(data.main.temp);
    const feelsLike = Math.round(data.main.feels_like);
    const description = data.weather[0].description;
    const icon = getWeatherEmoji(data.weather[0].main);
    const humidity = data.main.humidity;
    const windSpeed = Math.round(data.wind.speed);
    const location = data.name;
    const country = data.sys.country;
    
    // Build formatted response
    let formatted = `${icon} **Weather in ${location}, ${country}**\n\n`;
    formatted += `🌡️ **Temperature:** ${temp}°F (feels like ${feelsLike}°F)\n`;
    formatted += `☁️ **Conditions:** ${capitalizeFirst(description)}\n`;
    formatted += `💧 **Humidity:** ${humidity}%\n`;
    formatted += `💨 **Wind Speed:** ${windSpeed} mph\n`;
    
    // Add weather advice
    if (temp > 85) {
        formatted += `\n🔥 It's hot! Stay hydrated and seek shade.`;
    } else if (temp < 32) {
        formatted += `\n🥶 It's freezing! Bundle up and stay warm.`;
    } else if (description.toLowerCase().includes('rain')) {
        formatted += `\n☔ Don't forget your umbrella!`;
    } else if (description.toLowerCase().includes('clear')) {
        formatted += `\n☀️ Perfect weather to be outside!`;
    }
    
    return formatted;
}

// ==========================================
// GET WEATHER EMOJI
// ==========================================
function getWeatherEmoji(condition) {
    const emojiMap = {
        'Clear': '☀️',
        'Clouds': '☁️',
        'Rain': '🌧️',
        'Drizzle': '🌦️',
        'Thunderstorm': '⛈️',
        'Snow': '🌨️',
        'Mist': '🌫️',
        'Fog': '🌫️',
        'Haze': '🌫️'
    };
    
    return emojiMap[condition] || '🌤️';
}

// ==========================================
// UTILITY
// ==========================================
function capitalizeFirst(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}
