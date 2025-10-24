// ==========================================
// CRUMP AI - FLIGHTS API
// AviationStack API Integration
// THE FINAL API - #22 OF 22
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
        const apiKey = process.env.AVIATIONSTACK_API_KEY;
        
        if (!apiKey) {
            console.warn('⚠️ AviationStack API key not configured');
            return res.status(503).json({ 
                error: 'Flights API key not configured',
                fallback: true,
                message: 'Please add AVIATIONSTACK_API_KEY to environment variables'
            });
        }
        
        console.log(`✈️ Flight query: ${query}`);
        
        // Detect intent
        const intent = detectFlightIntent(query);
        
        if (!intent) {
            return res.status(400).json({ 
                error: 'Could not understand flight query',
                hint: 'Try: "Track flight AA123" or "Flights from JFK to LAX"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        switch (intent.type) {
            case 'track_flight':
                result = await trackFlight(intent.flightNumber, apiKey);
                break;
            
            case 'route':
                result = await searchRoute(intent.departure, intent.arrival, apiKey);
                break;
            
            case 'airport':
                result = await getAirportFlights(intent.airport, intent.direction, apiKey);
                break;
            
            case 'airline':
                result = await getAirlineFlights(intent.airline, apiKey);
                break;
            
            case 'flight_status':
                result = await getFlightStatus(intent.flightNumber, apiKey);
                break;
            
            default:
                result = await trackFlight(query, apiKey);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'flights',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Flights API error:', error);
        return res.status(500).json({ 
            error: 'Flight lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT FLIGHT INTENT
// ==========================================
function detectFlightIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: Track specific flight
    if (text.match(/track|status|where is|locate/i) && text.match(/flight/i)) {
        const flightMatch = text.match(/([A-Z]{2,3}\s?\d{1,4})/i);
        if (flightMatch) {
            return {
                type: 'track_flight',
                flightNumber: flightMatch[1].replace(/\s/g, '')
            };
        }
    }
    
    // Pattern 2: Route search (from X to Y)
    const routeMatch = text.match(/(?:flights?|routes?)\s+from\s+([A-Z]{3}|\w+)\s+to\s+([A-Z]{3}|\w+)/i);
    if (routeMatch) {
        return {
            type: 'route',
            departure: routeMatch[1].toUpperCase(),
            arrival: routeMatch[2].toUpperCase()
        };
    }
    
    // Pattern 3: Airport departures/arrivals
    if (text.match(/departures?|arrivals?|leaving|arriving/i)) {
        const airportMatch = text.match(/(?:from|at|in)\s+([A-Z]{3}|\w+)/i);
        if (airportMatch) {
            const direction = text.includes('arrival') ? 'arrival' : 'departure';
            return {
                type: 'airport',
                airport: airportMatch[1].toUpperCase(),
                direction: direction
            };
        }
    }
    
    // Pattern 4: Airline flights
    if (text.match(/airline|carrier/i)) {
        const airlineMatch = text.match(/airline\s+([A-Z]{2,3})/i) || text.match(/([A-Z]{2,3})\s+(?:flights|airline)/i);
        if (airlineMatch) {
            return {
                type: 'airline',
                airline: airlineMatch[1].toUpperCase()
            };
        }
    }
    
    // Pattern 5: Flight status by number
    const flightMatch = text.match(/([A-Z]{2,3}\s?\d{1,4})/i);
    if (flightMatch) {
        return {
            type: 'flight_status',
            flightNumber: flightMatch[1].replace(/\s/g, '')
        };
    }
    
    return null;
}

// ==========================================
// TRACK FLIGHT
// ==========================================
async function trackFlight(flightNumber, apiKey) {
    try {
        // Clean flight number
        const cleanedFlight = flightNumber.replace(/\s/g, '').toUpperCase();
        
        const url = `http://api.aviationstack.com/v1/flights?access_key=${apiKey}&flight_iata=${cleanedFlight}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            if (response.status === 401) {
                return {
                    success: false,
                    error: 'Invalid AviationStack API key',
                    hint: 'Check your AVIATIONSTACK_API_KEY environment variable'
                };
            }
            if (response.status === 429) {
                return {
                    success: false,
                    error: 'Flight API rate limit exceeded',
                    hint: 'Free tier: 100 requests/month. Upgrade for more requests.'
                };
            }
            throw new Error(`AviationStack API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.data || data.data.length === 0) {
            return {
                success: false,
                error: `Flight not found: ${flightNumber}`,
                hint: 'Check the flight number and try again. Format: AA123 or UAL456'
            };
        }
        
        const flight = data.data[0];
        
        // Format response
        const formatted = formatFlightDetails(flight);
        
        return {
            success: true,
            data: flight,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error tracking flight:', error);
        return {
            success: false,
            error: 'Failed to track flight'
        };
    }
}

// ==========================================
// SEARCH ROUTE
// ==========================================
async function searchRoute(departure, arrival, apiKey) {
    try {
        const url = `http://api.aviationstack.com/v1/flights?access_key=${apiKey}&dep_iata=${departure}&arr_iata=${arrival}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`AviationStack API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.data || data.data.length === 0) {
            return {
                success: false,
                error: `No flights found from ${departure} to ${arrival}`,
                hint: 'Try different airport codes'
            };
        }
        
        const flights = data.data.slice(0, 10);
        
        // Format response
        const formatted = formatRouteResults(flights, departure, arrival);
        
        return {
            success: true,
            data: flights,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching route:', error);
        return {
            success: false,
            error: 'Failed to search route'
        };
    }
}

// ==========================================
// GET AIRPORT FLIGHTS
// ==========================================
async function getAirportFlights(airport, direction, apiKey) {
    try {
        const param = direction === 'arrival' ? 'arr_iata' : 'dep_iata';
        const url = `http://api.aviationstack.com/v1/flights?access_key=${apiKey}&${param}=${airport}&limit=10`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`AviationStack API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.data || data.data.length === 0) {
            return {
                success: false,
                error: `No ${direction}s found at ${airport}`,
                hint: 'Try a different airport code'
            };
        }
        
        const flights = data.data;
        
        // Format response
        const formatted = formatAirportFlights(flights, airport, direction);
        
        return {
            success: true,
            data: flights,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting airport flights:', error);
        return {
            success: false,
            error: 'Failed to get airport flights'
        };
    }
}

// ==========================================
// GET AIRLINE FLIGHTS
// ==========================================
async function getAirlineFlights(airline, apiKey) {
    try {
        const url = `http://api.aviationstack.com/v1/flights?access_key=${apiKey}&airline_iata=${airline}&limit=10`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`AviationStack API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.data || data.data.length === 0) {
            return {
                success: false,
                error: `No flights found for airline ${airline}`,
                hint: 'Try a different airline code'
            };
        }
        
        const flights = data.data;
        
        // Format response
        const formatted = formatAirlineFlights(flights, airline);
        
        return {
            success: true,
            data: flights,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting airline flights:', error);
        return {
            success: false,
            error: 'Failed to get airline flights'
        };
    }
}

// ==========================================
// GET FLIGHT STATUS
// ==========================================
async function getFlightStatus(flightNumber, apiKey) {
    try {
        const cleanedFlight = flightNumber.replace(/\s/g, '').toUpperCase();
        
        const url = `http://api.aviationstack.com/v1/flights?access_key=${apiKey}&flight_iata=${cleanedFlight}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`AviationStack API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.data || data.data.length === 0) {
            return {
                success: false,
                error: `Flight status not available for ${flightNumber}`
            };
        }
        
        const flight = data.data[0];
        
        // Format response
        const formatted = formatFlightStatus(flight);
        
        return {
            success: true,
            data: flight,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting flight status:', error);
        return {
            success: false,
            error: 'Failed to get flight status'
        };
    }
}

// ==========================================
// FORMAT FLIGHT DETAILS
// ==========================================
function formatFlightDetails(flight) {
    const flightNumber = flight.flight?.iata || 'N/A';
    const airline = flight.airline?.name || 'Unknown Airline';
    const status = flight.flight_status || 'Unknown';
    
    const depAirport = flight.departure?.airport || 'Unknown';
    const depCode = flight.departure?.iata || 'N/A';
    const depTime = flight.departure?.scheduled || 'N/A';
    const depTerminal = flight.departure?.terminal || 'N/A';
    const depGate = flight.departure?.gate || 'N/A';
    
    const arrAirport = flight.arrival?.airport || 'Unknown';
    const arrCode = flight.arrival?.iata || 'N/A';
    const arrTime = flight.arrival?.scheduled || 'N/A';
    const arrTerminal = flight.arrival?.terminal || 'N/A';
    const arrGate = flight.arrival?.gate || 'N/A';
    
    const statusEmoji = getStatusEmoji(status);
    
    let formatted = `✈️ **Flight ${flightNumber} - ${airline}**\n\n`;
    formatted += `${statusEmoji} **Status:** ${status.toUpperCase()}\n\n`;
    
    formatted += `**🛫 Departure:**\n`;
    formatted += `   📍 ${depAirport} (${depCode})\n`;
    formatted += `   🕐 ${formatTime(depTime)}\n`;
    formatted += `   🚪 Terminal ${depTerminal} • Gate ${depGate}\n\n`;
    
    formatted += `**🛬 Arrival:**\n`;
    formatted += `   📍 ${arrAirport} (${arrCode})\n`;
    formatted += `   🕐 ${formatTime(arrTime)}\n`;
    formatted += `   🚪 Terminal ${arrTerminal} • Gate ${arrGate}\n`;
    
    // Add delay info if available
    if (flight.departure?.delay) {
        formatted += `\n⚠️ **Departure Delay:** ${flight.departure.delay} minutes`;
    }
    if (flight.arrival?.delay) {
        formatted += `\n⚠️ **Arrival Delay:** ${flight.arrival.delay} minutes`;
    }
    
    // Add aircraft info if available
    if (flight.aircraft?.registration) {
        formatted += `\n\n✈️ **Aircraft:** ${flight.aircraft.registration}`;
    }
    
    return formatted;
}

// ==========================================
// FORMAT ROUTE RESULTS
// ==========================================
function formatRouteResults(flights, departure, arrival) {
    let formatted = `✈️ **Flights from ${departure} to ${arrival}**\n\n`;
    formatted += `Found ${flights.length} flight${flights.length === 1 ? '' : 's'}:\n\n`;
    
    flights.forEach((flight, index) => {
        const flightNumber = flight.flight?.iata || 'N/A';
        const airline = flight.airline?.name || 'Unknown';
        const status = flight.flight_status || 'Unknown';
        const depTime = flight.departure?.scheduled || 'N/A';
        const arrTime = flight.arrival?.scheduled || 'N/A';
        const statusEmoji = getStatusEmoji(status);
        
        formatted += `**${index + 1}. ${airline} ${flightNumber}**\n`;
        formatted += `   ${statusEmoji} Status: ${status}\n`;
        formatted += `   🛫 Departs: ${formatTime(depTime)}\n`;
        formatted += `   🛬 Arrives: ${formatTime(arrTime)}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT AIRPORT FLIGHTS
// ==========================================
function formatAirportFlights(flights, airport, direction) {
    const directionLabel = direction === 'arrival' ? 'Arrivals' : 'Departures';
    
    let formatted = `✈️ **${directionLabel} at ${airport}**\n\n`;
    formatted += `Found ${flights.length} flight${flights.length === 1 ? '' : 's'}:\n\n`;
    
    flights.forEach((flight, index) => {
        const flightNumber = flight.flight?.iata || 'N/A';
        const airline = flight.airline?.name || 'Unknown';
        const status = flight.flight_status || 'Unknown';
        const statusEmoji = getStatusEmoji(status);
        
        let origin, destination, time;
        
        if (direction === 'arrival') {
            origin = flight.departure?.iata || 'N/A';
            destination = airport;
            time = flight.arrival?.scheduled || 'N/A';
        } else {
            origin = airport;
            destination = flight.arrival?.iata || 'N/A';
            time = flight.departure?.scheduled || 'N/A';
        }
        
        formatted += `**${index + 1}. ${airline} ${flightNumber}**\n`;
        formatted += `   ${statusEmoji} Status: ${status}\n`;
        formatted += `   📍 ${origin} → ${destination}\n`;
        formatted += `   🕐 ${formatTime(time)}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT AIRLINE FLIGHTS
// ==========================================
function formatAirlineFlights(flights, airline) {
    const airlineName = flights[0]?.airline?.name || airline;
    
    let formatted = `✈️ **${airlineName} Flights**\n\n`;
    formatted += `Found ${flights.length} flight${flights.length === 1 ? '' : 's'}:\n\n`;
    
    flights.forEach((flight, index) => {
        const flightNumber = flight.flight?.iata || 'N/A';
        const status = flight.flight_status || 'Unknown';
        const depCode = flight.departure?.iata || 'N/A';
        const arrCode = flight.arrival?.iata || 'N/A';
        const depTime = flight.departure?.scheduled || 'N/A';
        const statusEmoji = getStatusEmoji(status);
        
        formatted += `**${index + 1}. Flight ${flightNumber}**\n`;
        formatted += `   ${statusEmoji} Status: ${status}\n`;
        formatted += `   📍 ${depCode} → ${arrCode}\n`;
        formatted += `   🕐 Departs: ${formatTime(depTime)}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT FLIGHT STATUS
// ==========================================
function formatFlightStatus(flight) {
    const flightNumber = flight.flight?.iata || 'N/A';
    const airline = flight.airline?.name || 'Unknown';
    const status = flight.flight_status || 'Unknown';
    const statusEmoji = getStatusEmoji(status);
    
    const depCode = flight.departure?.iata || 'N/A';
    const arrCode = flight.arrival?.iata || 'N/A';
    const depTime = flight.departure?.scheduled || 'N/A';
    const arrTime = flight.arrival?.scheduled || 'N/A';
    
    let formatted = `✈️ **${airline} ${flightNumber}**\n\n`;
    formatted += `${statusEmoji} **Status:** ${status.toUpperCase()}\n\n`;
    formatted += `📍 **Route:** ${depCode} → ${arrCode}\n`;
    formatted += `🛫 **Departure:** ${formatTime(depTime)}\n`;
    formatted += `🛬 **Arrival:** ${formatTime(arrTime)}\n`;
    
    // Add delay warnings
    if (flight.departure?.delay) {
        formatted += `\n⚠️ Departure delayed by ${flight.departure.delay} minutes`;
    }
    if (flight.arrival?.delay) {
        formatted += `\n⚠️ Arrival delayed by ${flight.arrival.delay} minutes`;
    }
    
    return formatted;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function getStatusEmoji(status) {
    const statusLower = status.toLowerCase();
    
    if (statusLower.includes('active') || statusLower.includes('en-route')) {
        return '✈️';
    } else if (statusLower.includes('landed')) {
        return '🛬';
    } else if (statusLower.includes('scheduled')) {
        return '🕐';
    } else if (statusLower.includes('cancelled')) {
        return '❌';
    } else if (statusLower.includes('delayed')) {
        return '⚠️';
    } else {
        return '📍';
    }
}

function formatTime(timeString) {
    if (!timeString || timeString === 'N/A') {
        return 'N/A';
    }
    
    try {
        const date = new Date(timeString);
        const options = { 
            month: 'short', 
            day: 'numeric', 
            hour: '2-digit', 
            minute: '2-digit',
            timeZoneName: 'short'
        };
        return date.toLocaleString('en-US', options);
    } catch (error) {
        return timeString;
    }
}
