// ==========================================
// CRUMP AI - WEATHER API
// OpenWeatherMap Integration
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
        const apiKey = process.env.OPENWEATHER_API_KEY;
        
        if (!apiKey) {
            console.warn('⚠️ OpenWeatherMap API key not configured');
            return res.status(503).json({ 
                error: 'Weather API key not configured',
                fallback: true,
                message: 'Please add OPENWEATHER_API_KEY to environment variables'
            });
        }
        
        // Extract location from query
        const location = extractLocation(query);
        
        if (!location) {
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
            if (weatherResponse.status === 404) {
                return res.status(404).json({ 
                    error: `Location "${location}" not found`,
                    hint: 'Try a different city name or be more specific'
                });
            }
            throw new Error(`Weather API returned ${weatherResponse.status}`);
        }
        
        const weatherData = await weatherResponse.json();
        
        // Format response
        const formatted = formatWeatherResponse(weatherData);
        
        return res.status(200).json({
            success: true,
            api: 'weather',
            location: location,
            data: weatherData,
            formatted: formatted
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
// EXTRACT LOCATION FROM QUERY
// ==========================================
function extractLocation(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: "weather in [location]"
    let match = text.match(/weather\s+(?:in|for|at)\s+(.+)/i);
    if (match) return match[1].trim();
    
    // Pattern 2: "what's the weather in [location]"
    match = text.match(/what'?s?\s+(?:the\s+)?weather\s+(?:in|for|at)\s+(.+)/i);
    if (match) return match[1].trim();
    
    // Pattern 3: "temperature in [location]"
    match = text.match(/temperature\s+(?:in|for|at)\s+(.+)/i);
    if (match) return match[1].trim();
    
    // Pattern 4: "forecast for [location]"
    match = text.match(/forecast\s+(?:for|in|at)\s+(.+)/i);
    if (match) return match[1].trim();
    
    // Pattern 5: "how hot is [location]"
    match = text.match(/how\s+(?:hot|cold|warm)\s+(?:is\s+)?(?:it\s+)?(?:in\s+)?(.+)/i);
    if (match) return match[1].trim();
    
    // Pattern 6: "[location] weather"
    match = text.match(/^(.+?)\s+weather/i);
    if (match) return match[1].trim();
    
    // Default: try to extract city name (remove common words)
    const cleaned = text
        .replace(/weather|temperature|forecast|what'?s?|the|in|for|at|today|tomorrow/gi, '')
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
    } else if (description.includes('rain')) {
        formatted += `\n☔ Don't forget your umbrella!`;
    } else if (description.includes('clear')) {
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
