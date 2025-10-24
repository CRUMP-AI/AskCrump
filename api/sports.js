// ==========================================
// CRUMP AI - SPORTS API
// The Sports DB Integration (FREE)
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
        
        console.log(`🏈 Sports query: ${query}`);
        
        // The Sports DB has a free tier with API key "3" for testing
        // Get your own key at: https://www.thesportsdb.com/api.php
        const apiKey = process.env.SPORTSDB_API_KEY || '3';
        
        // Detect what the user is asking for
        const intent = detectSportsIntent(query);
        
        if (!intent) {
            return res.status(400).json({
                error: 'Could not understand sports query',
                hint: 'Try: "Who won the Cowboys game?" or "NBA scores today"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        // Route to appropriate handler
        switch (intent.type) {
            case 'team_results':
                result = await getTeamResults(intent.team, intent.league, apiKey);
                break;
            
            case 'league_scores':
                result = await getLeagueScores(intent.league, apiKey);
                break;
            
            case 'team_schedule':
                result = await getTeamSchedule(intent.team, intent.league, apiKey);
                break;
            
            case 'team_info':
                result = await getTeamInfo(intent.team, intent.league, apiKey);
                break;
            
            default:
                return res.status(400).json({ 
                    error: 'Unsupported sports query type',
                    detected: intent.type
                });
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'sports',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Sports API error:', error);
        return res.status(500).json({ 
            error: 'Sports lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT SPORTS INTENT
// ==========================================
function detectSportsIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Detect league
    const league = detectLeague(text);
    
    // Pattern 1: "Who won the [team] game?"
    let match = text.match(/who\s+won\s+(?:the\s+)?(.+?)\s+game/i);
    if (match) {
        return {
            type: 'team_results',
            team: match[1].trim(),
            league: league
        };
    }
    
    // Pattern 2: "[team] score" or "[team] game"
    match = text.match(/^(.+?)\s+(?:score|game|result)/i);
    if (match) {
        return {
            type: 'team_results',
            team: match[1].trim(),
            league: league
        };
    }
    
    // Pattern 3: "[league] scores" or "[league] games"
    if (text.includes('scores') || text.includes('games')) {
        if (league) {
            return {
                type: 'league_scores',
                league: league
            };
        }
    }
    
    // Pattern 4: "when do [team] play" or "[team] schedule"
    if (text.includes('schedule') || text.match(/when\s+(?:do|does)/i)) {
        match = text.match(/(?:when\s+(?:do|does)\s+(?:the\s+)?|schedule\s+for\s+)?(.+?)(?:\s+play|\s+schedule|$)/i);
        if (match) {
            return {
                type: 'team_schedule',
                team: match[1].trim(),
                league: league
            };
        }
    }
    
    // Pattern 5: "tell me about [team]"
    match = text.match(/(?:tell me about|info on|about)\s+(?:the\s+)?(.+)/i);
    if (match) {
        return {
            type: 'team_info',
            team: match[1].trim(),
            league: league
        };
    }
    
    // Default: try team results
    const teamName = extractTeamName(text);
    if (teamName) {
        return {
            type: 'team_results',
            team: teamName,
            league: league
        };
    }
    
    return null;
}

// ==========================================
// DETECT LEAGUE
// ==========================================
function detectLeague(text) {
    if (text.includes('nfl') || text.includes('football') && !text.includes('soccer')) {
        return 'NFL';
    }
    if (text.includes('nba') || text.includes('basketball')) {
        return 'NBA';
    }
    if (text.includes('mlb') || text.includes('baseball')) {
        return 'MLB';
    }
    if (text.includes('nhl') || text.includes('hockey')) {
        return 'NHL';
    }
    if (text.includes('soccer') || text.includes('premier league') || text.includes('mls')) {
        return 'Soccer';
    }
    
    // Default to NFL if mentioning common NFL teams
    const nflTeams = ['cowboys', 'patriots', 'packers', 'chiefs', '49ers', 'eagles', 'steelers'];
    if (nflTeams.some(team => text.includes(team))) {
        return 'NFL';
    }
    
    return null;
}

// ==========================================
// EXTRACT TEAM NAME
// ==========================================
function extractTeamName(text) {
    // Remove common words
    const cleaned = text
        .replace(/who|won|the|game|score|result|today|yesterday|last|night|match/gi, '')
        .trim();
    
    return cleaned.length > 2 ? cleaned : null;
}

// ==========================================
// GET TEAM RESULTS
// ==========================================
async function getTeamResults(teamName, league, apiKey) {
    try {
        // Search for team
        const teamSearchUrl = `https://www.thesportsdb.com/api/v1/json/${apiKey}/searchteams.php?t=${encodeURIComponent(teamName)}`;
        
        const teamResponse = await fetch(teamSearchUrl);
        const teamData = await teamResponse.json();
        
        if (!teamData.teams || teamData.teams.length === 0) {
            return {
                success: false,
                error: `Team "${teamName}" not found`,
                hint: 'Try using the full team name (e.g., "Dallas Cowboys" instead of "Cowboys")'
            };
        }
        
        const team = teamData.teams[0];
        const teamId = team.idTeam;
        
        // Get last 5 events
        const eventsUrl = `https://www.thesportsdb.com/api/v1/json/${apiKey}/eventslast.php?id=${teamId}`;
        
        const eventsResponse = await fetch(eventsUrl);
        const eventsData = await eventsResponse.json();
        
        if (!eventsData.results || eventsData.results.length === 0) {
            return {
                success: false,
                error: `No recent games found for ${team.strTeam}`,
                hint: 'The season may not have started yet'
            };
        }
        
        // Format the response
        const formatted = formatTeamResults(team, eventsData.results);
        
        return {
            success: true,
            data: {
                team: team,
                events: eventsData.results
            },
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error fetching team results:', error);
        return {
            success: false,
            error: 'Failed to fetch team results'
        };
    }
}

// ==========================================
// GET LEAGUE SCORES
// ==========================================
async function getLeagueScores(league, apiKey) {
    try {
        // Map league names to Sports DB league IDs
        const leagueMap = {
            'NFL': '4391',
            'NBA': '4387',
            'MLB': '4424',
            'NHL': '4380'
        };
        
        const leagueId = leagueMap[league];
        
        if (!leagueId) {
            return {
                success: false,
                error: `League "${league}" not supported yet`,
                hint: 'Supported leagues: NFL, NBA, MLB, NHL'
            };
        }
        
        // Get events for today
        const today = new Date().toISOString().split('T')[0];
        const eventsUrl = `https://www.thesportsdb.com/api/v1/json/${apiKey}/eventsday.php?d=${today}&l=${leagueId}`;
        
        const eventsResponse = await fetch(eventsUrl);
        const eventsData = await eventsResponse.json();
        
        if (!eventsData.events || eventsData.events.length === 0) {
            return {
                success: false,
                error: `No ${league} games today`,
                hint: 'Try checking a specific team instead'
            };
        }
        
        // Format the response
        const formatted = formatLeagueScores(league, eventsData.events);
        
        return {
            success: true,
            data: {
                league: league,
                events: eventsData.events
            },
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error fetching league scores:', error);
        return {
            success: false,
            error: 'Failed to fetch league scores'
        };
    }
}

// ==========================================
// GET TEAM SCHEDULE
// ==========================================
async function getTeamSchedule(teamName, league, apiKey) {
    try {
        // Search for team
        const teamSearchUrl = `https://www.thesportsdb.com/api/v1/json/${apiKey}/searchteams.php?t=${encodeURIComponent(teamName)}`;
        
        const teamResponse = await fetch(teamSearchUrl);
        const teamData = await teamResponse.json();
        
        if (!teamData.teams || teamData.teams.length === 0) {
            return {
                success: false,
                error: `Team "${teamName}" not found`
            };
        }
        
        const team = teamData.teams[0];
        const teamId = team.idTeam;
        
        // Get next 5 events
        const eventsUrl = `https://www.thesportsdb.com/api/v1/json/${apiKey}/eventsnext.php?id=${teamId}`;
        
        const eventsResponse = await fetch(eventsUrl);
        const eventsData = await eventsResponse.json();
        
        if (!eventsData.events || eventsData.events.length === 0) {
            return {
                success: false,
                error: `No upcoming games found for ${team.strTeam}`
            };
        }
        
        // Format the response
        const formatted = formatTeamSchedule(team, eventsData.events);
        
        return {
            success: true,
            data: {
                team: team,
                events: eventsData.events
            },
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error fetching team schedule:', error);
        return {
            success: false,
            error: 'Failed to fetch team schedule'
        };
    }
}

// ==========================================
// GET TEAM INFO
// ==========================================
async function getTeamInfo(teamName, league, apiKey) {
    try {
        // Search for team
        const teamSearchUrl = `https://www.thesportsdb.com/api/v1/json/${apiKey}/searchteams.php?t=${encodeURIComponent(teamName)}`;
        
        const teamResponse = await fetch(teamSearchUrl);
        const teamData = await teamResponse.json();
        
        if (!teamData.teams || teamData.teams.length === 0) {
            return {
                success: false,
                error: `Team "${teamName}" not found`
            };
        }
        
        const team = teamData.teams[0];
        
        // Format the response
        const formatted = formatTeamInfo(team);
        
        return {
            success: true,
            data: { team: team },
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error fetching team info:', error);
        return {
            success: false,
            error: 'Failed to fetch team info'
        };
    }
}

// ==========================================
// FORMAT TEAM RESULTS
// ==========================================
function formatTeamResults(team, events) {
    const leagueEmoji = getLeagueEmoji(team.strLeague);
    
    let formatted = `${leagueEmoji} **${team.strTeam}** - Recent Results\n\n`;
    
    // Show last 5 games
    events.slice(0, 5).forEach(event => {
        const homeTeam = event.strHomeTeam;
        const awayTeam = event.strAwayTeam;
        const homeScore = event.intHomeScore;
        const awayScore = event.intAwayScore;
        const date = formatDate(event.dateEvent);
        
        // Determine if team won
        const isHome = homeTeam === team.strTeam;
        const teamScore = isHome ? homeScore : awayScore;
        const opponentScore = isHome ? awayScore : homeScore;
        const opponent = isHome ? awayTeam : homeTeam;
        
        let result = '❓';
        if (homeScore !== null && awayScore !== null) {
            if (teamScore > opponentScore) {
                result = '✅ W';
            } else if (teamScore < opponentScore) {
                result = '❌ L';
            } else {
                result = '➖ T';
            }
        }
        
        formatted += `${result} **${teamScore}-${opponentScore}** vs ${opponent} (${date})\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT LEAGUE SCORES
// ==========================================
function formatLeagueScores(league, events) {
    const leagueEmoji = getLeagueEmoji(league);
    
    let formatted = `${leagueEmoji} **${league} Games Today**\n\n`;
    
    events.forEach(event => {
        const homeTeam = event.strHomeTeam;
        const awayTeam = event.strAwayTeam;
        const homeScore = event.intHomeScore || '-';
        const awayScore = event.intAwayScore || '-';
        const time = event.strTime || 'TBD';
        
        formatted += `${awayTeam} @ ${homeTeam}: **${awayScore}-${homeScore}** (${time})\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT TEAM SCHEDULE
// ==========================================
function formatTeamSchedule(team, events) {
    const leagueEmoji = getLeagueEmoji(team.strLeague);
    
    let formatted = `${leagueEmoji} **${team.strTeam}** - Upcoming Games\n\n`;
    
    events.slice(0, 5).forEach(event => {
        const homeTeam = event.strHomeTeam;
        const awayTeam = event.strAwayTeam;
        const date = formatDate(event.dateEvent);
        const time = event.strTime || 'TBD';
        
        const isHome = homeTeam === team.strTeam;
        const opponent = isHome ? awayTeam : homeTeam;
        const location = isHome ? 'vs' : '@';
        
        formatted += `📅 **${date}** ${time} - ${location} ${opponent}\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT TEAM INFO
// ==========================================
function formatTeamInfo(team) {
    const leagueEmoji = getLeagueEmoji(team.strLeague);
    
    let formatted = `${leagueEmoji} **${team.strTeam}**\n\n`;
    formatted += `🏆 **League:** ${team.strLeague}\n`;
    formatted += `🏟️ **Stadium:** ${team.strStadium}\n`;
    formatted += `📍 **Location:** ${team.strStadiumLocation}\n`;
    
    if (team.intFormedYear) {
        formatted += `📅 **Founded:** ${team.intFormedYear}\n`;
    }
    
    if (team.strDescriptionEN) {
        const description = team.strDescriptionEN.substring(0, 300) + '...';
        formatted += `\n${description}`;
    }
    
    return formatted;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function getLeagueEmoji(league) {
    const emojiMap = {
        'NFL': '🏈',
        'NBA': '🏀',
        'MLB': '⚾',
        'NHL': '🏒',
        'English Premier League': '⚽',
        'MLS': '⚽'
    };
    
    return emojiMap[league] || '🏆';
}

function formatDate(dateString) {
    if (!dateString) return 'TBD';
    
    const date = new Date(dateString);
    const options = { month: 'short', day: 'numeric' };
    return date.toLocaleDateString('en-US', options);
}
```

---

## **🔑 API KEY SETUP (OPTIONAL - FREE WORKS):**

The Sports DB has a **free test key** (`"3"`) that works immediately!

**For production (better rate limits):**
1. Go to: https://www.thesportsdb.com/api.php
2. Get your free API key (or upgrade to Patreon for more calls)
3. Add to Vercel:
```
   SPORTSDB_API_KEY=your_key_here
