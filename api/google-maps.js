// ==========================================
// CRUMP AI - GOOGLE MAPS API
// Google Maps Platform Integration
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
        const apiKey = process.env.GOOGLE_MAPS_API_KEY;
        
        if (!apiKey) {
            console.warn('⚠️ Google Maps API key not configured');
            return res.status(503).json({ 
                error: 'Google Maps API key not configured',
                fallback: true,
                message: 'Please add GOOGLE_MAPS_API_KEY to environment variables'
            });
        }
        
        console.log(`🗺️ Google Maps query: ${query}`);
        
        // Detect intent
        const intent = detectMapsIntent(query);
        
        if (!intent) {
            return res.status(400).json({ 
                error: 'Could not understand Maps query',
                hint: 'Try: "Directions to Starbucks" or "Find Italian restaurants nearby"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        switch (intent.type) {
            case 'directions':
                result = await getDirections(intent.origin, intent.destination, apiKey);
                break;
            
            case 'nearby':
                result = await findNearby(intent.location, intent.placeType, apiKey);
                break;
            
            case 'place_search':
                result = await searchPlaces(intent.query, intent.location, apiKey);
                break;
            
            case 'geocode':
                result = await geocodeAddress(intent.address, apiKey);
                break;
            
            case 'place_details':
                result = await getPlaceDetails(intent.placeName, apiKey);
                break;
            
            default:
                return res.status(400).json({ 
                    error: 'Unsupported Maps query type',
                    detected: intent.type
                });
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'googleMaps',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Google Maps API error:', error);
        return res.status(500).json({ 
            error: 'Maps lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT MAPS INTENT
// ==========================================
function detectMapsIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: Directions
    if (text.match(/directions?\s+(?:to|from)|navigate\s+to|how\s+(?:do i|to)\s+get\s+to|route\s+to/i)) {
        const match = text.match(/(?:directions?|navigate|route|get)\s+(?:to|from)\s+(.+?)(?:\s+from\s+(.+))?$/i);
        if (match) {
            return {
                type: 'directions',
                destination: match[1].trim(),
                origin: match[2] ? match[2].trim() : 'current location'
            };
        }
    }
    
    // Pattern 2: Nearby searches
    if (text.match(/nearby|near me|closest|nearest/i)) {
        const placeType = extractPlaceType(text);
        return {
            type: 'nearby',
            location: 'current location',
            placeType: placeType || 'restaurant'
        };
    }
    
    // Pattern 3: Find/Search places
    if (text.match(/find|search|locate|show me/i)) {
        const placeType = extractPlaceType(text);
        if (placeType) {
            return {
                type: 'nearby',
                location: 'current location',
                placeType: placeType
            };
        }
        
        // General place search
        const match = text.match(/(?:find|search|locate|show me)\s+(.+?)(?:\s+(?:in|at|near)\s+(.+))?$/i);
        if (match) {
            return {
                type: 'place_search',
                query: match[1].trim(),
                location: match[2] ? match[2].trim() : null
            };
        }
    }
    
    // Pattern 4: Where is [place]
    if (text.match(/where\s+(?:is|are|can i find)/i)) {
        const match = text.match(/where\s+(?:is|are|can i find)\s+(.+)/i);
        if (match) {
            return {
                type: 'place_details',
                placeName: match[1].trim()
            };
        }
    }
    
    // Pattern 5: Address lookup
    if (text.match(/address\s+(?:of|for)|what'?s?\s+the\s+address/i)) {
        const match = text.match(/(?:address\s+(?:of|for)|what'?s?\s+the\s+address\s+of)\s+(.+)/i);
        if (match) {
            return {
                type: 'geocode',
                address: match[1].trim()
            };
        }
    }
    
    return null;
}

// ==========================================
// EXTRACT PLACE TYPE
// ==========================================
function extractPlaceType(text) {
    const placeTypes = {
        'restaurant': ['restaurant', 'food', 'eat', 'dine', 'dining'],
        'cafe': ['cafe', 'coffee', 'starbucks', 'coffee shop'],
        'bar': ['bar', 'pub', 'brewery', 'drink'],
        'gas_station': ['gas', 'gas station', 'fuel', 'petrol'],
        'parking': ['parking', 'park', 'garage'],
        'hospital': ['hospital', 'emergency', 'medical'],
        'pharmacy': ['pharmacy', 'drugstore', 'cvs', 'walgreens'],
        'bank': ['bank', 'atm'],
        'hotel': ['hotel', 'motel', 'lodging'],
        'gym': ['gym', 'fitness', 'workout'],
        'store': ['store', 'shop', 'shopping'],
        'supermarket': ['grocery', 'supermarket', 'walmart', 'target'],
        'airport': ['airport'],
        'train_station': ['train', 'subway', 'metro'],
        'movie_theater': ['movie', 'cinema', 'theater'],
        'library': ['library'],
        'school': ['school'],
        'church': ['church'],
        'police': ['police'],
        'post_office': ['post office']
    };
    
    for (const [type, keywords] of Object.entries(placeTypes)) {
        if (keywords.some(keyword => text.includes(keyword))) {
            return type;
        }
    }
    
    return null;
}

// ==========================================
// GET DIRECTIONS
// ==========================================
async function getDirections(origin, destination, apiKey) {
    try {
        // Default origin to user's location hint
        const originParam = origin === 'current location' 
            ? 'Port Wentworth, GA' // Default location from context
            : origin;
        
        const url = `https://maps.googleapis.com/maps/api/directions/json?origin=${encodeURIComponent(originParam)}&destination=${encodeURIComponent(destination)}&key=${apiKey}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.status === 'ZERO_RESULTS') {
            return {
                success: false,
                error: `No route found from "${originParam}" to "${destination}"`,
                hint: 'Try being more specific with the locations'
            };
        }
        
        if (data.status !== 'OK') {
            return {
                success: false,
                error: `Directions lookup failed: ${data.status}`,
                hint: 'Check that both locations are valid'
            };
        }
        
        const route = data.routes[0];
        
        // Format response
        const formatted = formatDirections(route, originParam, destination);
        
        return {
            success: true,
            data: route,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting directions:', error);
        return {
            success: false,
            error: 'Failed to get directions'
        };
    }
}

// ==========================================
// FIND NEARBY PLACES
// ==========================================
async function findNearby(location, placeType, apiKey) {
    try {
        // Default location (Port Wentworth, GA)
        const defaultLat = 32.1771;
        const defaultLng = -81.1621;
        
        const url = `https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=${defaultLat},${defaultLng}&radius=5000&type=${placeType}&key=${apiKey}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.status === 'ZERO_RESULTS') {
            return {
                success: false,
                error: `No ${placeType}s found nearby`,
                hint: 'Try expanding your search radius'
            };
        }
        
        if (data.status !== 'OK') {
            return {
                success: false,
                error: `Place search failed: ${data.status}`
            };
        }
        
        const places = data.results;
        
        // Format response
        const formatted = formatNearbyPlaces(places, placeType);
        
        return {
            success: true,
            data: places,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error finding nearby places:', error);
        return {
            success: false,
            error: 'Failed to find nearby places'
        };
    }
}

// ==========================================
// SEARCH PLACES
// ==========================================
async function searchPlaces(query, location, apiKey) {
    try {
        let url = `https://maps.googleapis.com/maps/api/place/textsearch/json?query=${encodeURIComponent(query)}&key=${apiKey}`;
        
        if (location) {
            url += `&location=${encodeURIComponent(location)}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.status === 'ZERO_RESULTS') {
            return {
                success: false,
                error: `No places found for "${query}"`,
                hint: 'Try a different search term'
            };
        }
        
        if (data.status !== 'OK') {
            return {
                success: false,
                error: `Place search failed: ${data.status}`
            };
        }
        
        const places = data.results;
        
        // Format response
        const formatted = formatPlaceSearch(places, query);
        
        return {
            success: true,
            data: places,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching places:', error);
        return {
            success: false,
            error: 'Failed to search places'
        };
    }
}

// ==========================================
// GEOCODE ADDRESS
// ==========================================
async function geocodeAddress(address, apiKey) {
    try {
        const url = `https://maps.googleapis.com/maps/api/geocode/json?address=${encodeURIComponent(address)}&key=${apiKey}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.status === 'ZERO_RESULTS') {
            return {
                success: false,
                error: `Address not found: "${address}"`,
                hint: 'Try being more specific'
            };
        }
        
        if (data.status !== 'OK') {
            return {
                success: false,
                error: `Geocoding failed: ${data.status}`
            };
        }
        
        const result = data.results[0];
        
        // Format response
        const formatted = formatGeocodeResult(result);
        
        return {
            success: true,
            data: result,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error geocoding address:', error);
        return {
            success: false,
            error: 'Failed to geocode address'
        };
    }
}

// ==========================================
// GET PLACE DETAILS
// ==========================================
async function getPlaceDetails(placeName, apiKey) {
    try {
        // First, search for the place
        const searchUrl = `https://maps.googleapis.com/maps/api/place/findplacefromtext/json?input=${encodeURIComponent(placeName)}&inputtype=textquery&fields=place_id,name,formatted_address&key=${apiKey}`;
        
        const searchResponse = await fetch(searchUrl);
        const searchData = await searchResponse.json();
        
        if (searchData.status === 'ZERO_RESULTS' || !searchData.candidates || searchData.candidates.length === 0) {
            return {
                success: false,
                error: `Place not found: "${placeName}"`,
                hint: 'Try being more specific'
            };
        }
        
        const placeId = searchData.candidates[0].place_id;
        
        // Get detailed information
        const detailsUrl = `https://maps.googleapis.com/maps/api/place/details/json?place_id=${placeId}&fields=name,formatted_address,formatted_phone_number,website,rating,user_ratings_total,opening_hours,price_level,types&key=${apiKey}`;
        
        const detailsResponse = await fetch(detailsUrl);
        const detailsData = await detailsResponse.json();
        
        if (detailsData.status !== 'OK') {
            return {
                success: false,
                error: `Failed to get place details: ${detailsData.status}`
            };
        }
        
        const place = detailsData.result;
        
        // Format response
        const formatted = formatPlaceDetails(place);
        
        return {
            success: true,
            data: place,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting place details:', error);
        return {
            success: false,
            error: 'Failed to get place details'
        };
    }
}

// ==========================================
// FORMAT DIRECTIONS
// ==========================================
function formatDirections(route, origin, destination) {
    const leg = route.legs[0];
    const distance = leg.distance.text;
    const duration = leg.duration.text;
    
    let formatted = `🗺️ **Directions: ${origin} → ${destination}**\n\n`;
    formatted += `📏 **Distance:** ${distance}\n`;
    formatted += `⏱️ **Duration:** ${duration}\n\n`;
    formatted += `**Turn-by-turn:**\n`;
    
    leg.steps.slice(0, 10).forEach((step, index) => {
        const instruction = step.html_instructions
            .replace(/<[^>]*>/g, '') // Remove HTML tags
            .replace(/&nbsp;/g, ' ');
        const stepDistance = step.distance.text;
        
        formatted += `${index + 1}. ${instruction} (${stepDistance})\n`;
    });
    
    if (leg.steps.length > 10) {
        formatted += `\n...and ${leg.steps.length - 10} more steps\n`;
    }
    
    formatted += `\n🔗 [View on Google Maps](https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)})`;
    
    return formatted;
}

// ==========================================
// FORMAT NEARBY PLACES
// ==========================================
function formatNearbyPlaces(places, placeType) {
    const typeLabel = placeType.replace(/_/g, ' ');
    
    let formatted = `📍 **Nearby ${typeLabel}s**\n\n`;
    formatted += `Found ${places.length} locations:\n\n`;
    
    places.slice(0, 10).forEach((place, index) => {
        const name = place.name;
        const address = place.vicinity;
        const rating = place.rating || 'No rating';
        const isOpen = place.opening_hours?.open_now;
        const openStatus = isOpen === true ? '🟢 Open' : isOpen === false ? '🔴 Closed' : '❓ Unknown';
        
        formatted += `**${index + 1}. ${name}**\n`;
        formatted += `   📍 ${address}\n`;
        formatted += `   ⭐ ${rating}/5`;
        
        if (place.user_ratings_total) {
            formatted += ` (${place.user_ratings_total} reviews)`;
        }
        
        formatted += `\n   ${openStatus}\n`;
        
        // Add Google Maps link
        const lat = place.geometry.location.lat;
        const lng = place.geometry.location.lng;
        formatted += `   🔗 [View on Maps](https://www.google.com/maps/search/?api=1&query=${lat},${lng})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT PLACE SEARCH
// ==========================================
function formatPlaceSearch(places, query) {
    let formatted = `🔍 **Places: ${query}**\n\n`;
    
    places.slice(0, 8).forEach((place, index) => {
        const name = place.name;
        const address = place.formatted_address;
        const rating = place.rating || 'No rating';
        
        formatted += `**${index + 1}. ${name}**\n`;
        formatted += `   📍 ${address}\n`;
        formatted += `   ⭐ ${rating}/5`;
        
        if (place.user_ratings_total) {
            formatted += ` (${place.user_ratings_total} reviews)`;
        }
        
        formatted += '\n\n';
    });
    
    return formatted;
}

// ==========================================
// FORMAT GEOCODE RESULT
// ==========================================
function formatGeocodeResult(result) {
    const address = result.formatted_address;
    const lat = result.geometry.location.lat;
    const lng = result.geometry.location.lng;
    
    let formatted = `📍 **Address Found**\n\n`;
    formatted += `${address}\n\n`;
    formatted += `📐 **Coordinates:**\n`;
    formatted += `Latitude: ${lat}\n`;
    formatted += `Longitude: ${lng}\n\n`;
    formatted += `🔗 [View on Google Maps](https://www.google.com/maps/search/?api=1&query=${lat},${lng})`;
    
    return formatted;
}

// ==========================================
// FORMAT PLACE DETAILS
// ==========================================
function formatPlaceDetails(place) {
    const name = place.name;
    const address = place.formatted_address;
    const phone = place.formatted_phone_number;
    const website = place.website;
    const rating = place.rating;
    const totalRatings = place.user_ratings_total;
    const priceLevel = place.price_level;
    
    let formatted = `📍 **${name}**\n\n`;
    formatted += `🏠 ${address}\n`;
    
    if (phone) {
        formatted += `📞 ${phone}\n`;
    }
    
    if (rating) {
        formatted += `⭐ ${rating}/5`;
        if (totalRatings) {
            formatted += ` (${totalRatings} reviews)`;
        }
        formatted += '\n';
    }
    
    if (priceLevel) {
        formatted += `💵 ${'$'.repeat(priceLevel)}\n`;
    }
    
    if (place.opening_hours) {
        const isOpen = place.opening_hours.open_now;
        formatted += `${isOpen ? '🟢 Open now' : '🔴 Closed'}\n`;
        
        if (place.opening_hours.weekday_text) {
            formatted += `\n**Hours:**\n`;
            place.opening_hours.weekday_text.forEach(day => {
                formatted += `${day}\n`;
            });
        }
    }
    
    if (website) {
        formatted += `\n🌐 [Website](${website})`;
    }
    
    return formatted;
}
```

---

## **🔑 API KEY SETUP:**

1. Go to: https://console.cloud.google.com/google/maps-apis
2. Enable these APIs:
   - **Maps JavaScript API**
   - **Places API**
   - **Directions API**
   - **Geocoding API**
3. Create credentials → API Key
4. Restrict the key to your domain
5. Free tier: **$200 credit/month** (plenty for most use)
6. Add to Vercel:
```
   GOOGLE_MAPS_API_KEY=your_key_here
