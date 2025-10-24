// ==========================================
// CRUMP AI - CRYPTO API
// CoinGecko API Integration (FREE)
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
        
        // CoinGecko API key (optional - works without it!)
        // Free tier: 10-30 calls/minute
        // With API key: Higher rate limits
        const apiKey = process.env.COINGECKO_API_KEY;
        
        console.log(`₿ Crypto query: ${query}`);
        
        // Detect intent
        const intent = detectCryptoIntent(query);
        
        if (!intent) {
            return res.status(400).json({ 
                error: 'Could not understand crypto query',
                hint: 'Try: "Bitcoin price" or "Top 10 cryptocurrencies"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        switch (intent.type) {
            case 'price':
                result = await getCryptoPrice(intent.crypto, apiKey);
                break;
            
            case 'market':
                result = await getMarketData(intent.crypto, apiKey);
                break;
            
            case 'top':
                result = await getTopCryptos(intent.limit, apiKey);
                break;
            
            case 'trending':
                result = await getTrendingCryptos(apiKey);
                break;
            
            case 'compare':
                result = await compareCryptos(intent.cryptos, apiKey);
                break;
            
            case 'global':
                result = await getGlobalMarket(apiKey);
                break;
            
            default:
                result = await getCryptoPrice(intent.crypto, apiKey);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'crypto',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Crypto API error:', error);
        return res.status(500).json({ 
            error: 'Crypto lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT CRYPTO INTENT
// ==========================================
function detectCryptoIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: Price query
    if (text.match(/price|value|worth|cost|trading/i)) {
        const crypto = extractCrypto(text);
        if (crypto) {
            return {
                type: 'price',
                crypto: crypto
            };
        }
    }
    
    // Pattern 2: Market data
    if (text.match(/market\s+(?:data|cap|info)|stats|statistics/i)) {
        const crypto = extractCrypto(text);
        if (crypto) {
            return {
                type: 'market',
                crypto: crypto
            };
        }
    }
    
    // Pattern 3: Top cryptocurrencies
    if (text.match(/top|best|leading/i)) {
        const match = text.match(/top\s+(\d+)/i);
        const limit = match ? parseInt(match[1]) : 10;
        
        return {
            type: 'top',
            limit: Math.min(limit, 50) // Cap at 50
        };
    }
    
    // Pattern 4: Trending
    if (text.match(/trending|hot|popular|gainers|losers/i)) {
        return {
            type: 'trending'
        };
    }
    
    // Pattern 5: Compare
    if (text.match(/compare|vs|versus|difference/i)) {
        const cryptos = extractMultipleCryptos(text);
        if (cryptos.length >= 2) {
            return {
                type: 'compare',
                cryptos: cryptos
            };
        }
    }
    
    // Pattern 6: Global market
    if (text.match(/global|overall|total\s+market|crypto\s+market/i)) {
        return {
            type: 'global'
        };
    }
    
    // Default: try to extract crypto and get price
    const crypto = extractCrypto(text);
    if (crypto) {
        return {
            type: 'price',
            crypto: crypto
        };
    }
    
    return null;
}

// ==========================================
// EXTRACT CRYPTO
// ==========================================
function extractCrypto(text) {
    const cryptoMap = {
        'bitcoin': 'bitcoin',
        'btc': 'bitcoin',
        'ethereum': 'ethereum',
        'eth': 'ethereum',
        'tether': 'tether',
        'usdt': 'tether',
        'bnb': 'binancecoin',
        'binance coin': 'binancecoin',
        'xrp': 'ripple',
        'ripple': 'ripple',
        'cardano': 'cardano',
        'ada': 'cardano',
        'dogecoin': 'dogecoin',
        'doge': 'dogecoin',
        'solana': 'solana',
        'sol': 'solana',
        'polkadot': 'polkadot',
        'dot': 'polkadot',
        'litecoin': 'litecoin',
        'ltc': 'litecoin',
        'shiba': 'shiba-inu',
        'shib': 'shiba-inu',
        'avalanche': 'avalanche-2',
        'avax': 'avalanche-2',
        'polygon': 'matic-network',
        'matic': 'matic-network',
        'chainlink': 'chainlink',
        'link': 'chainlink',
        'uniswap': 'uniswap',
        'uni': 'uniswap',
        'stellar': 'stellar',
        'xlm': 'stellar',
        'monero': 'monero',
        'xmr': 'monero',
        'cosmos': 'cosmos',
        'atom': 'cosmos',
        'tron': 'tron',
        'trx': 'tron',
        'filecoin': 'filecoin',
        'fil': 'filecoin',
        'aave': 'aave',
        'maker': 'maker',
        'mkr': 'maker',
        'eos': 'eos',
        'tezos': 'tezos',
        'xtz': 'tezos'
    };
    
    const normalized = text.toLowerCase();
    
    for (const [key, value] of Object.entries(cryptoMap)) {
        if (normalized.includes(key)) {
            return value;
        }
    }
    
    return null;
}

// ==========================================
// EXTRACT MULTIPLE CRYPTOS
// ==========================================
function extractMultipleCryptos(text) {
    const cryptos = [];
    const allCryptos = ['bitcoin', 'ethereum', 'cardano', 'solana', 'dogecoin', 'ripple', 'polkadot', 'litecoin', 'avalanche', 'polygon'];
    
    allCryptos.forEach(crypto => {
        if (text.toLowerCase().includes(crypto) || text.toLowerCase().includes(crypto.substring(0, 3))) {
            const mapped = extractCrypto(crypto);
            if (mapped && !cryptos.includes(mapped)) {
                cryptos.push(mapped);
            }
        }
    });
    
    return cryptos;
}

// ==========================================
// GET CRYPTO PRICE
// ==========================================
async function getCryptoPrice(cryptoId, apiKey) {
    try {
        let url = `https://api.coingecko.com/api/v3/simple/price?ids=${cryptoId}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_market_cap=true`;
        
        const headers = {
            'Accept': 'application/json'
        };
        
        if (apiKey) {
            headers['x-cg-demo-api-key'] = apiKey;
        }
        
        const response = await fetch(url, { headers });
        
        if (!response.ok) {
            if (response.status === 429) {
                return {
                    success: false,
                    error: 'CoinGecko rate limit exceeded',
                    hint: 'Free tier: 10-30 calls/minute. Add COINGECKO_API_KEY for higher limits.'
                };
            }
            throw new Error(`CoinGecko API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data[cryptoId]) {
            return {
                success: false,
                error: `Cryptocurrency "${cryptoId}" not found`,
                hint: 'Try using the full name or common ticker symbol'
            };
        }
        
        const priceData = data[cryptoId];
        
        // Format response
        const formatted = formatPrice(cryptoId, priceData);
        
        return {
            success: true,
            data: priceData,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting crypto price:', error);
        return {
            success: false,
            error: 'Failed to get crypto price'
        };
    }
}

// ==========================================
// GET MARKET DATA
// ==========================================
async function getMarketData(cryptoId, apiKey) {
    try {
        let url = `https://api.coingecko.com/api/v3/coins/${cryptoId}?localization=false&tickers=false&community_data=false&developer_data=false`;
        
        const headers = {
            'Accept': 'application/json'
        };
        
        if (apiKey) {
            headers['x-cg-demo-api-key'] = apiKey;
        }
        
        const response = await fetch(url, { headers });
        
        if (!response.ok) {
            throw new Error(`CoinGecko API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatMarketData(data);
        
        return {
            success: true,
            data: data,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting market data:', error);
        return {
            success: false,
            error: 'Failed to get market data'
        };
    }
}

// ==========================================
// GET TOP CRYPTOS
// ==========================================
async function getTopCryptos(limit, apiKey) {
    try {
        let url = `https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=${limit}&page=1&sparkline=false&price_change_percentage=24h`;
        
        const headers = {
            'Accept': 'application/json'
        };
        
        if (apiKey) {
            headers['x-cg-demo-api-key'] = apiKey;
        }
        
        const response = await fetch(url, { headers });
        
        if (!response.ok) {
            throw new Error(`CoinGecko API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatTopCryptos(data);
        
        return {
            success: true,
            data: data,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting top cryptos:', error);
        return {
            success: false,
            error: 'Failed to get top cryptocurrencies'
        };
    }
}

// ==========================================
// GET TRENDING CRYPTOS
// ==========================================
async function getTrendingCryptos(apiKey) {
    try {
        let url = 'https://api.coingecko.com/api/v3/search/trending';
        
        const headers = {
            'Accept': 'application/json'
        };
        
        if (apiKey) {
            headers['x-cg-demo-api-key'] = apiKey;
        }
        
        const response = await fetch(url, { headers });
        
        if (!response.ok) {
            throw new Error(`CoinGecko API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatTrendingCryptos(data.coins);
        
        return {
            success: true,
            data: data.coins,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting trending cryptos:', error);
        return {
            success: false,
            error: 'Failed to get trending cryptocurrencies'
        };
    }
}

// ==========================================
// COMPARE CRYPTOS
// ==========================================
async function compareCryptos(cryptoIds, apiKey) {
    try {
        const ids = cryptoIds.join(',');
        let url = `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd&include_24hr_change=true&include_market_cap=true`;
        
        const headers = {
            'Accept': 'application/json'
        };
        
        if (apiKey) {
            headers['x-cg-demo-api-key'] = apiKey;
        }
        
        const response = await fetch(url, { headers });
        
        if (!response.ok) {
            throw new Error(`CoinGecko API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatComparison(data);
        
        return {
            success: true,
            data: data,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error comparing cryptos:', error);
        return {
            success: false,
            error: 'Failed to compare cryptocurrencies'
        };
    }
}

// ==========================================
// GET GLOBAL MARKET
// ==========================================
async function getGlobalMarket(apiKey) {
    try {
        let url = 'https://api.coingecko.com/api/v3/global';
        
        const headers = {
            'Accept': 'application/json'
        };
        
        if (apiKey) {
            headers['x-cg-demo-api-key'] = apiKey;
        }
        
        const response = await fetch(url, { headers });
        
        if (!response.ok) {
            throw new Error(`CoinGecko API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatGlobalMarket(data.data);
        
        return {
            success: true,
            data: data.data,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting global market:', error);
        return {
            success: false,
            error: 'Failed to get global market data'
        };
    }
}

// ==========================================
// FORMAT PRICE
// ==========================================
function formatPrice(cryptoId, data) {
    const name = cryptoId.charAt(0).toUpperCase() + cryptoId.slice(1);
    const price = data.usd;
    const change24h = data.usd_24h_change;
    const marketCap = data.usd_market_cap;
    const volume24h = data.usd_24h_vol;
    
    const changeEmoji = change24h >= 0 ? '📈' : '📉';
    const changeColor = change24h >= 0 ? '🟢' : '🔴';
    
    let formatted = `₿ **${name} Price**\n\n`;
    formatted += `💰 **Current Price:** $${formatCurrency(price)}\n`;
    formatted += `${changeColor} **24h Change:** ${change24h >= 0 ? '+' : ''}${change24h.toFixed(2)}% ${changeEmoji}\n`;
    
    if (marketCap) {
        formatted += `📊 **Market Cap:** $${formatCurrency(marketCap)}\n`;
    }
    
    if (volume24h) {
        formatted += `📈 **24h Volume:** $${formatCurrency(volume24h)}\n`;
    }
    
    // Add market sentiment
    if (Math.abs(change24h) > 10) {
        formatted += `\n🔥 **High volatility!** ${Math.abs(change24h).toFixed(1)}% movement in 24h`;
    } else if (Math.abs(change24h) < 1) {
        formatted += `\n😴 **Stable price** with minimal movement`;
    }
    
    return formatted;
}

// ==========================================
// FORMAT MARKET DATA
// ==========================================
function formatMarketData(data) {
    const name = data.name;
    const symbol = data.symbol.toUpperCase();
    const price = data.market_data.current_price.usd;
    const marketCap = data.market_data.market_cap.usd;
    const rank = data.market_cap_rank;
    const change24h = data.market_data.price_change_percentage_24h;
    const change7d = data.market_data.price_change_percentage_7d;
    const change30d = data.market_data.price_change_percentage_30d;
    const ath = data.market_data.ath.usd;
    const atl = data.market_data.atl.usd;
    
    let formatted = `₿ **${name} (${symbol})** - Rank #${rank}\n\n`;
    formatted += `💰 **Price:** $${formatCurrency(price)}\n`;
    formatted += `📊 **Market Cap:** $${formatCurrency(marketCap)}\n\n`;
    
    formatted += `**Price Changes:**\n`;
    formatted += `• 24h: ${change24h >= 0 ? '🟢 +' : '🔴 '}${change24h.toFixed(2)}%\n`;
    formatted += `• 7d: ${change7d >= 0 ? '🟢 +' : '🔴 '}${change7d.toFixed(2)}%\n`;
    formatted += `• 30d: ${change30d >= 0 ? '🟢 +' : '🔴 '}${change30d.toFixed(2)}%\n\n`;
    
    formatted += `**All-Time:**\n`;
    formatted += `• High: $${formatCurrency(ath)}\n`;
    formatted += `• Low: $${formatCurrency(atl)}\n`;
    
    return formatted;
}

// ==========================================
// FORMAT TOP CRYPTOS
// ==========================================
function formatTopCryptos(cryptos) {
    let formatted = `🏆 **Top ${cryptos.length} Cryptocurrencies by Market Cap**\n\n`;
    
    cryptos.forEach((crypto, index) => {
        const name = crypto.name;
        const symbol = crypto.symbol.toUpperCase();
        const price = crypto.current_price;
        const change24h = crypto.price_change_percentage_24h;
        const marketCap = crypto.market_cap;
        
        const changeEmoji = change24h >= 0 ? '📈' : '📉';
        
        formatted += `**${index + 1}. ${name} (${symbol})**\n`;
        formatted += `   💰 $${formatCurrency(price)} • `;
        formatted += `${change24h >= 0 ? '🟢' : '🔴'} ${change24h >= 0 ? '+' : ''}${change24h.toFixed(2)}% ${changeEmoji}\n`;
        formatted += `   📊 Market Cap: $${formatCurrency(marketCap)}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT TRENDING CRYPTOS
// ==========================================
function formatTrendingCryptos(coins) {
    let formatted = `🔥 **Trending Cryptocurrencies**\n\n`;
    
    coins.forEach((item, index) => {
        const coin = item.item;
        const name = coin.name;
        const symbol = coin.symbol;
        const rank = coin.market_cap_rank;
        
        formatted += `**${index + 1}. ${name} (${symbol})**\n`;
        formatted += `   📊 Market Cap Rank: #${rank}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT COMPARISON
// ==========================================
function formatComparison(data) {
    let formatted = `⚖️ **Cryptocurrency Comparison**\n\n`;
    
    Object.entries(data).forEach(([id, values]) => {
        const name = id.charAt(0).toUpperCase() + id.slice(1);
        const price = values.usd;
        const change24h = values.usd_24h_change;
        const marketCap = values.usd_market_cap;
        
        formatted += `**${name}**\n`;
        formatted += `💰 $${formatCurrency(price)} • `;
        formatted += `${change24h >= 0 ? '🟢' : '🔴'} ${change24h >= 0 ? '+' : ''}${change24h.toFixed(2)}%\n`;
        formatted += `📊 Market Cap: $${formatCurrency(marketCap)}\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT GLOBAL MARKET
// ==========================================
function formatGlobalMarket(data) {
    const totalMarketCap = data.total_market_cap.usd;
    const totalVolume = data.total_volume.usd;
    const btcDominance = data.market_cap_percentage.btc;
    const ethDominance = data.market_cap_percentage.eth;
    const activeCryptos = data.active_cryptocurrencies;
    const markets = data.markets;
    
    let formatted = `🌍 **Global Crypto Market**\n\n`;
    formatted += `📊 **Total Market Cap:** $${formatCurrency(totalMarketCap)}\n`;
    formatted += `📈 **24h Volume:** $${formatCurrency(totalVolume)}\n`;
    formatted += `₿ **Bitcoin Dominance:** ${btcDominance.toFixed(2)}%\n`;
    formatted += `⟠ **Ethereum Dominance:** ${ethDominance.toFixed(2)}%\n`;
    formatted += `🪙 **Active Cryptocurrencies:** ${activeCryptos.toLocaleString()}\n`;
    formatted += `🏪 **Markets:** ${markets.toLocaleString()}\n`;
    
    return formatted;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function formatCurrency(num) {
    if (num >= 1000000000000) {
        return (num / 1000000000000).toFixed(2) + 'T';
    } else if (num >= 1000000000) {
        return (num / 1000000000).toFixed(2) + 'B';
    } else if (num >= 1000000) {
        return (num / 1000000).toFixed(2) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(2) + 'K';
    } else if (num >= 1) {
        return num.toFixed(2);
    } else if (num >= 0.01) {
        return num.toFixed(4);
    } else {
        return num.toFixed(8);
    }
}
