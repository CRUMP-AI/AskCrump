// ==========================================
// CRUMP AI - STOCKS API
// Alpha Vantage Integration (FREE)
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
        const apiKey = process.env.ALPHA_VANTAGE_API_KEY;
        
        if (!apiKey) {
            console.warn('⚠️ Alpha Vantage API key not configured');
            return res.status(503).json({ 
                error: 'Stocks API key not configured',
                fallback: true,
                message: 'Please add ALPHA_VANTAGE_API_KEY to environment variables'
            });
        }
        
        console.log(`📈 Stock query: ${query}`);
        
        // Extract ticker symbol
        const ticker = extractTicker(query);
        
        if (!ticker) {
            return res.status(400).json({ 
                error: 'Could not determine stock ticker',
                hint: 'Try: "Tesla stock price" or "What\'s AAPL trading at?"'
            });
        }
        
        console.log(`🎯 Looking up ticker: ${ticker}`);
        
        // Determine what data to fetch
        const intent = detectStockIntent(query);
        
        let result;
        
        switch (intent) {
            case 'quote':
                result = await getStockQuote(ticker, apiKey);
                break;
            
            case 'overview':
                result = await getStockOverview(ticker, apiKey);
                break;
            
            case 'news':
                result = await getStockNews(ticker, apiKey);
                break;
            
            default:
                // Default to quote
                result = await getStockQuote(ticker, apiKey);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'stocks',
            ticker: ticker,
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Stocks API error:', error);
        return res.status(500).json({ 
            error: 'Stock lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// EXTRACT TICKER SYMBOL
// ==========================================
function extractTicker(query) {
    const text = query.toUpperCase().trim();
    
    // Common stock tickers (explicit matches)
    const tickerMap = {
        'TESLA': 'TSLA',
        'APPLE': 'AAPL',
        'GOOGLE': 'GOOGL',
        'ALPHABET': 'GOOGL',
        'MICROSOFT': 'MSFT',
        'AMAZON': 'AMZN',
        'META': 'META',
        'FACEBOOK': 'META',
        'NVIDIA': 'NVDA',
        'NETFLIX': 'NFLX',
        'AMD': 'AMD',
        'INTEL': 'INTC',
        'TWITTER': 'TWTR',
        'UBER': 'UBER',
        'LYFT': 'LYFT',
        'AIRBNB': 'ABNB',
        'COINBASE': 'COIN',
        'ROBINHOOD': 'HOOD',
        'PAYPAL': 'PYPL',
        'SQUARE': 'SQ',
        'SHOPIFY': 'SHOP',
        'ZOOM': 'ZM',
        'SLACK': 'WORK',
        'PALANTIR': 'PLTR',
        'SNOWFLAKE': 'SNOW',
        'ROBLOX': 'RBLX',
        'RIVIAN': 'RIVN',
        'LUCID': 'LCID',
        'GM': 'GM',
        'FORD': 'F',
        'GENERAL MOTORS': 'GM',
        'GENERAL ELECTRIC': 'GE',
        'GE': 'GE',
        'BOEING': 'BA',
        'DISNEY': 'DIS',
        'WALMART': 'WMT',
        'COSTCO': 'COST',
        'TARGET': 'TGT',
        'NIKE': 'NKE',
        'STARBUCKS': 'SBUX',
        'MCDONALD': 'MCD',
        'MCDONALDS': 'MCD',
        'COCA COLA': 'KO',
        'PEPSI': 'PEP',
        'PROCTER': 'PG',
        'JOHNSON': 'JNJ',
        'PFIZER': 'PFE',
        'MODERNA': 'MRNA',
        'VISA': 'V',
        'MASTERCARD': 'MA',
        'JPMORGAN': 'JPM',
        'BANK OF AMERICA': 'BAC',
        'WELLS FARGO': 'WFC',
        'GOLDMAN SACHS': 'GS',
        'MORGAN STANLEY': 'MS',
        'EXXON': 'XOM',
        'CHEVRON': 'CVX',
        'BP': 'BP',
        'SHELL': 'SHEL',
        'AT&T': 'T',
        'ATT': 'T',
        'VERIZON': 'VZ',
        'T-MOBILE': 'TMUS',
        'COMCAST': 'CMCSA',
        'ORACLE': 'ORCL',
        'SALESFORCE': 'CRM',
        'IBM': 'IBM',
        'CISCO': 'CSCO',
        'DELL': 'DELL',
        'HP': 'HPQ',
        'SONY': 'SONY',
        'SAMSUNG': 'SSNLF',
        'TOYOTA': 'TM'
    };
    
    // Check for explicit company name matches
    for (const [company, ticker] of Object.entries(tickerMap)) {
        if (text.includes(company)) {
            return ticker;
        }
    }
    
    // Pattern 1: Look for ticker symbols (2-5 uppercase letters)
    const tickerMatch = text.match(/\b([A-Z]{2,5})\b/);
    if (tickerMatch) {
        const potential = tickerMatch[1];
        // Exclude common words that might match
        const excludeWords = ['STOCK', 'PRICE', 'WHAT', 'WHATS', 'THE', 'IS', 'AT', 'FOR'];
        if (!excludeWords.includes(potential)) {
            return potential;
        }
    }
    
    // Pattern 2: "stock" or "price" followed by company name
    const companyMatch = text.match(/(?:STOCK|PRICE|TRADING|VALUE).*?([A-Z]{2,5})/);
    if (companyMatch) {
        return companyMatch[1];
    }
    
    return null;
}

// ==========================================
// DETECT STOCK INTENT
// ==========================================
function detectStockIntent(query) {
    const text = query.toLowerCase();
    
    if (text.includes('overview') || text.includes('about') || text.includes('info')) {
        return 'overview';
    }
    
    if (text.includes('news') || text.includes('headlines')) {
        return 'news';
    }
    
    // Default to quote (price)
    return 'quote';
}

// ==========================================
// GET STOCK QUOTE
// ==========================================
async function getStockQuote(ticker, apiKey) {
    try {
        // Use Global Quote endpoint
        const url = `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${ticker}&apikey=${apiKey}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        // Check for errors
        if (data['Error Message']) {
            return {
                success: false,
                error: `Stock ticker "${ticker}" not found`,
                hint: 'Make sure you\'re using the correct ticker symbol (e.g., AAPL for Apple)'
            };
        }
        
        if (data['Note']) {
            return {
                success: false,
                error: 'API rate limit reached',
                hint: 'Alpha Vantage free tier: 25 requests per day. Please try again later.'
            };
        }
        
        const quote = data['Global Quote'];
        
        if (!quote || Object.keys(quote).length === 0) {
            return {
                success: false,
                error: `No data available for "${ticker}"`,
                hint: 'The ticker might be invalid or market might be closed'
            };
        }
        
        // Format response
        const formatted = formatStockQuote(ticker, quote);
        
        return {
            success: true,
            data: quote,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error fetching stock quote:', error);
        return {
            success: false,
            error: 'Failed to fetch stock quote'
        };
    }
}

// ==========================================
// GET STOCK OVERVIEW
// ==========================================
async function getStockOverview(ticker, apiKey) {
    try {
        const url = `https://www.alphavantage.co/query?function=OVERVIEW&symbol=${ticker}&apikey=${apiKey}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data['Error Message']) {
            return {
                success: false,
                error: `Stock ticker "${ticker}" not found`
            };
        }
        
        if (data['Note']) {
            return {
                success: false,
                error: 'API rate limit reached'
            };
        }
        
        if (!data.Symbol) {
            return {
                success: false,
                error: `No overview data available for "${ticker}"`
            };
        }
        
        // Format response
        const formatted = formatStockOverview(data);
        
        return {
            success: true,
            data: data,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error fetching stock overview:', error);
        return {
            success: false,
            error: 'Failed to fetch stock overview'
        };
    }
}

// ==========================================
// GET STOCK NEWS (Using overview as fallback)
// ==========================================
async function getStockNews(ticker, apiKey) {
    // Alpha Vantage doesn't have a direct news endpoint in free tier
    // Fall back to overview
    return await getStockOverview(ticker, apiKey);
}

// ==========================================
// FORMAT STOCK QUOTE
// ==========================================
function formatStockQuote(ticker, quote) {
    const symbol = quote['01. symbol'];
    const price = parseFloat(quote['05. price']);
    const change = parseFloat(quote['09. change']);
    const changePercent = quote['10. change percent'];
    const volume = parseInt(quote['06. volume']);
    const open = parseFloat(quote['02. open']);
    const high = parseFloat(quote['03. high']);
    const low = parseFloat(quote['04. low']);
    const previousClose = parseFloat(quote['08. previous close']);
    
    // Determine if stock is up or down
    const isUp = change >= 0;
    const arrow = isUp ? '📈' : '📉';
    const changeColor = isUp ? '🟢' : '🔴';
    
    let formatted = `${arrow} **${symbol}** Stock Quote\n\n`;
    formatted += `💰 **Current Price:** $${price.toFixed(2)}\n`;
    formatted += `${changeColor} **Change:** ${change >= 0 ? '+' : ''}$${change.toFixed(2)} (${changePercent})\n`;
    formatted += `📊 **Volume:** ${formatNumber(volume)}\n`;
    formatted += `📈 **Day High:** $${high.toFixed(2)}\n`;
    formatted += `📉 **Day Low:** $${low.toFixed(2)}\n`;
    formatted += `🔓 **Open:** $${open.toFixed(2)}\n`;
    formatted += `🔒 **Previous Close:** $${previousClose.toFixed(2)}\n`;
    
    // Add market commentary
    if (Math.abs(change) > price * 0.05) {
        formatted += `\n⚡ **Significant movement today!**`;
    } else if (Math.abs(change) < price * 0.01) {
        formatted += `\n😴 **Relatively stable today**`;
    }
    
    return formatted;
}

// ==========================================
// FORMAT STOCK OVERVIEW
// ==========================================
function formatStockOverview(data) {
    const symbol = data.Symbol;
    const name = data.Name;
    const sector = data.Sector;
    const industry = data.Industry;
    const marketCap = data.MarketCapitalization;
    const pe = data.PERatio;
    const eps = data.EPS;
    const dividend = data.DividendYield;
    const description = data.Description;
    
    let formatted = `📊 **${name} (${symbol})**\n\n`;
    
    if (sector) formatted += `🏢 **Sector:** ${sector}\n`;
    if (industry) formatted += `🏭 **Industry:** ${industry}\n`;
    if (marketCap) formatted += `💎 **Market Cap:** $${formatNumber(parseInt(marketCap))}\n`;
    if (pe) formatted += `📈 **P/E Ratio:** ${pe}\n`;
    if (eps) formatted += `💵 **EPS:** $${eps}\n`;
    if (dividend) formatted += `💰 **Dividend Yield:** ${(parseFloat(dividend) * 100).toFixed(2)}%\n`;
    
    if (description) {
        // Truncate description
        const shortDesc = description.length > 300 
            ? description.substring(0, 300) + '...' 
            : description;
        formatted += `\n${shortDesc}`;
    }
    
    return formatted;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function formatNumber(num) {
    if (num >= 1000000000) {
        return (num / 1000000000).toFixed(2) + 'B';
    } else if (num >= 1000000) {
        return (num / 1000000).toFixed(2) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(2) + 'K';
    }
    return num.toString();
}
```

---

## **🔑 API KEY SETUP:**

1. Go to: https://www.alphavantage.co/support/#api-key
2. Get your **FREE** API key (no credit card)
3. Free tier: **25 requests per day**
4. Add to Vercel:
```
   ALPHA_VANTAGE_API_KEY=your_key_here
