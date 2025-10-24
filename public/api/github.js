// ==========================================
// CRUMP AI - GITHUB API
// GitHub REST API v3 Integration
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
        
        console.log(`💻 GitHub query: ${query}`);
        
        // GitHub API token (optional but recommended for higher rate limits)
        const githubToken = process.env.GITHUB_API_TOKEN;
        
        if (!githubToken) {
            console.warn('⚠️ GitHub API token not configured - using lower rate limits');
        }
        
        // Detect intent
        const intent = detectGitHubIntent(query);
        
        if (!intent) {
            return res.status(400).json({ 
                error: 'Could not understand GitHub query',
                hint: 'Try: "Search GitHub for React hooks" or "Find machine learning repositories"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        switch (intent.type) {
            case 'repo_search':
                result = await searchRepositories(intent.query, intent.language, intent.sort, githubToken);
                break;
            
            case 'user_search':
                result = await searchUsers(intent.username, githubToken);
                break;
            
            case 'user_repos':
                result = await getUserRepositories(intent.username, githubToken);
                break;
            
            case 'trending':
                result = await getTrendingRepos(intent.language, intent.since, githubToken);
                break;
            
            case 'repo_details':
                result = await getRepositoryDetails(intent.owner, intent.repo, githubToken);
                break;
            
            case 'code_search':
                result = await searchCode(intent.query, intent.language, githubToken);
                break;
            
            default:
                result = await searchRepositories(intent.query, null, 'stars', githubToken);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'github',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ GitHub API error:', error);
        return res.status(500).json({ 
            error: 'GitHub lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT GITHUB INTENT
// ==========================================
function detectGitHubIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: "search github for [query]"
    let match = text.match(/search\s+github\s+for\s+(.+)/i);
    if (match) {
        return {
            type: 'repo_search',
            query: match[1].trim(),
            language: detectLanguage(text),
            sort: 'stars'
        };
    }
    
    // Pattern 2: "find [query] on github"
    match = text.match(/find\s+(.+?)\s+(?:on|in)\s+github/i);
    if (match) {
        return {
            type: 'repo_search',
            query: match[1].trim(),
            language: detectLanguage(text),
            sort: 'stars'
        };
    }
    
    // Pattern 3: "github [query]"
    match = text.match(/github\s+(.+)/i);
    if (match) {
        const queryText = match[1].trim();
        
        // Check if it's a user search
        if (queryText.includes('user') || queryText.includes('profile')) {
            const username = queryText.replace(/user|profile/gi, '').trim();
            return {
                type: 'user_search',
                username: username
            };
        }
        
        return {
            type: 'repo_search',
            query: queryText,
            language: detectLanguage(text),
            sort: 'stars'
        };
    }
    
    // Pattern 4: "[language] repositories" or "[language] projects"
    const language = detectLanguage(text);
    if (language && (text.includes('repositor') || text.includes('project') || text.includes('library'))) {
        return {
            type: 'repo_search',
            query: text.replace(/repository|repositories|project|projects|library|libraries|github/gi, '').trim(),
            language: language,
            sort: 'stars'
        };
    }
    
    // Pattern 5: "trending [language] repos"
    if (text.includes('trending') || text.includes('popular')) {
        return {
            type: 'trending',
            language: detectLanguage(text),
            since: 'weekly'
        };
    }
    
    // Pattern 6: "[owner]/[repo]" format
    match = text.match(/([a-zA-Z0-9-]+)\/([a-zA-Z0-9-_.]+)/);
    if (match) {
        return {
            type: 'repo_details',
            owner: match[1],
            repo: match[2]
        };
    }
    
    // Pattern 7: "repos by [username]" or "[username]'s repos"
    match = text.match(/(?:repos|repositories)\s+by\s+([a-zA-Z0-9-]+)/i);
    if (!match) {
        match = text.match(/([a-zA-Z0-9-]+)'?s?\s+(?:repos|repositories)/i);
    }
    if (match) {
        return {
            type: 'user_repos',
            username: match[1]
        };
    }
    
    // Pattern 8: "search code for [query]"
    if (text.includes('search code') || text.includes('find code')) {
        const codeQuery = text.replace(/search|find|code|for|in|github/gi, '').trim();
        return {
            type: 'code_search',
            query: codeQuery,
            language: detectLanguage(text)
        };
    }
    
    // Default: repo search
    return {
        type: 'repo_search',
        query: text.replace(/github|repository|repo|project/gi, '').trim(),
        language: detectLanguage(text),
        sort: 'stars'
    };
}

// ==========================================
// DETECT PROGRAMMING LANGUAGE
// ==========================================
function detectLanguage(text) {
    const languages = {
        'javascript': 'JavaScript',
        'typescript': 'TypeScript',
        'python': 'Python',
        'java': 'Java',
        'c++': 'C++',
        'cpp': 'C++',
        'c#': 'C#',
        'csharp': 'C#',
        'ruby': 'Ruby',
        'go': 'Go',
        'golang': 'Go',
        'rust': 'Rust',
        'swift': 'Swift',
        'kotlin': 'Kotlin',
        'php': 'PHP',
        'html': 'HTML',
        'css': 'CSS',
        'shell': 'Shell',
        'bash': 'Shell',
        'sql': 'SQL',
        'r': 'R',
        'scala': 'Scala',
        'dart': 'Dart',
        'lua': 'Lua',
        'perl': 'Perl',
        'haskell': 'Haskell',
        'elixir': 'Elixir',
        'clojure': 'Clojure',
        'vue': 'Vue',
        'react': 'JavaScript',
        'angular': 'TypeScript',
        'node': 'JavaScript'
    };
    
    for (const [keyword, language] of Object.entries(languages)) {
        if (text.includes(keyword)) {
            return language;
        }
    }
    
    return null;
}

// ==========================================
// SEARCH REPOSITORIES
// ==========================================
async function searchRepositories(query, language, sort, token) {
    try {
        let searchQuery = query;
        
        if (language) {
            searchQuery += ` language:${language}`;
        }
        
        const url = `https://api.github.com/search/repositories?q=${encodeURIComponent(searchQuery)}&sort=${sort}&order=desc&per_page=15`;
        
        const headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Crump-AI-App'
        };
        
        if (token) {
            headers['Authorization'] = `token ${token}`;
        }
        
        const response = await fetch(url, { headers });
        
        if (response.status === 403) {
            return {
                success: false,
                error: 'GitHub API rate limit exceeded',
                hint: 'Add GITHUB_API_TOKEN to environment variables for higher limits'
            };
        }
        
        if (!response.ok) {
            throw new Error(`GitHub API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: `No repositories found for "${query}"`,
                hint: 'Try a different search term'
            };
        }
        
        // Format response
        const formatted = formatRepositories(data.items, query);
        
        return {
            success: true,
            data: data.items,
            formatted: formatted,
            totalResults: data.total_count
        };
        
    } catch (error) {
        console.error('Error searching GitHub repositories:', error);
        return {
            success: false,
            error: 'Failed to search repositories',
            details: error.message
        };
    }
}

// ==========================================
// SEARCH USERS
// ==========================================
async function searchUsers(username, token) {
    try {
        const url = `https://api.github.com/users/${encodeURIComponent(username)}`;
        
        const headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Crump-AI-App'
        };
        
        if (token) {
            headers['Authorization'] = `token ${token}`;
        }
        
        const response = await fetch(url, { headers });
        
        if (response.status === 404) {
            return {
                success: false,
                error: `GitHub user "${username}" not found`,
                hint: 'Check the username spelling'
            };
        }
        
        if (!response.ok) {
            throw new Error(`GitHub API returned ${response.status}`);
        }
        
        const user = await response.json();
        
        // Format response
        const formatted = formatUser(user);
        
        return {
            success: true,
            data: user,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching GitHub user:', error);
        return {
            success: false,
            error: 'Failed to find user'
        };
    }
}

// ==========================================
// GET USER REPOSITORIES
// ==========================================
async function getUserRepositories(username, token) {
    try {
        const url = `https://api.github.com/users/${encodeURIComponent(username)}/repos?sort=stars&per_page=10`;
        
        const headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Crump-AI-App'
        };
        
        if (token) {
            headers['Authorization'] = `token ${token}`;
        }
        
        const response = await fetch(url, { headers });
        
        if (response.status === 404) {
            return {
                success: false,
                error: `GitHub user "${username}" not found`
            };
        }
        
        if (!response.ok) {
            throw new Error(`GitHub API returned ${response.status}`);
        }
        
        const repos = await response.json();
        
        if (repos.length === 0) {
            return {
                success: false,
                error: `No public repositories found for ${username}`
            };
        }
        
        // Format response
        const formatted = formatUserRepositories(repos, username);
        
        return {
            success: true,
            data: repos,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting user repositories:', error);
        return {
            success: false,
            error: 'Failed to get user repositories'
        };
    }
}

// ==========================================
// GET TRENDING REPOS (Using GitHub Search)
// ==========================================
async function getTrendingRepos(language, since, token) {
    try {
        // Calculate date for "since" period
        const date = new Date();
        if (since === 'daily') {
            date.setDate(date.getDate() - 1);
        } else if (since === 'weekly') {
            date.setDate(date.getDate() - 7);
        } else {
            date.setMonth(date.getMonth() - 1);
        }
        const dateString = date.toISOString().split('T')[0];
        
        let searchQuery = `created:>${dateString}`;
        
        if (language) {
            searchQuery += ` language:${language}`;
        }
        
        const url = `https://api.github.com/search/repositories?q=${encodeURIComponent(searchQuery)}&sort=stars&order=desc&per_page=15`;
        
        const headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Crump-AI-App'
        };
        
        if (token) {
            headers['Authorization'] = `token ${token}`;
        }
        
        const response = await fetch(url, { headers });
        
        if (!response.ok) {
            throw new Error(`GitHub API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: `No trending repositories found`,
                hint: 'Try a different language or time period'
            };
        }
        
        // Format response
        const formatted = formatTrendingRepos(data.items, language, since);
        
        return {
            success: true,
            data: data.items,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting trending repos:', error);
        return {
            success: false,
            error: 'Failed to get trending repositories'
        };
    }
}

// ==========================================
// GET REPOSITORY DETAILS
// ==========================================
async function getRepositoryDetails(owner, repo, token) {
    try {
        const url = `https://api.github.com/repos/${owner}/${repo}`;
        
        const headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Crump-AI-App'
        };
        
        if (token) {
            headers['Authorization'] = `token ${token}`;
        }
        
        const response = await fetch(url, { headers });
        
        if (response.status === 404) {
            return {
                success: false,
                error: `Repository "${owner}/${repo}" not found`
            };
        }
        
        if (!response.ok) {
            throw new Error(`GitHub API returned ${response.status}`);
        }
        
        const repoData = await response.json();
        
        // Format response
        const formatted = formatRepositoryDetails(repoData);
        
        return {
            success: true,
            data: repoData,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting repository details:', error);
        return {
            success: false,
            error: 'Failed to get repository details'
        };
    }
}

// ==========================================
// SEARCH CODE
// ==========================================
async function searchCode(query, language, token) {
    try {
        let searchQuery = query;
        
        if (language) {
            searchQuery += ` language:${language}`;
        }
        
        const url = `https://api.github.com/search/code?q=${encodeURIComponent(searchQuery)}&per_page=10`;
        
        const headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Crump-AI-App'
        };
        
        if (token) {
            headers['Authorization'] = `token ${token}`;
        }
        
        const response = await fetch(url, { headers });
        
        if (response.status === 403) {
            return {
                success: false,
                error: 'GitHub API rate limit exceeded'
            };
        }
        
        if (!response.ok) {
            throw new Error(`GitHub API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.items || data.items.length === 0) {
            return {
                success: false,
                error: `No code found for "${query}"`
            };
        }
        
        // Format response
        const formatted = formatCodeResults(data.items, query);
        
        return {
            success: true,
            data: data.items,
            formatted: formatted,
            totalResults: data.total_count
        };
        
    } catch (error) {
        console.error('Error searching code:', error);
        return {
            success: false,
            error: 'Failed to search code'
        };
    }
}

// ==========================================
// FORMAT REPOSITORIES
// ==========================================
function formatRepositories(repos, query) {
    let formatted = `💻 **GitHub Repositories: ${query}**\n\n`;
    formatted += `Found ${repos.length} repositories:\n\n`;
    
    repos.slice(0, 10).forEach((repo, index) => {
        const name = repo.full_name;
        const description = repo.description || 'No description';
        const stars = formatNumber(repo.stargazers_count);
        const forks = formatNumber(repo.forks_count);
        const language = repo.language || 'N/A';
        const url = repo.html_url;
        
        formatted += `**${index + 1}. ${name}**\n`;
        formatted += `   ${description}\n`;
        formatted += `   ⭐ ${stars} • 🍴 ${forks} • 💻 ${language}\n`;
        formatted += `   🔗 [View Repository](${url})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT USER
// ==========================================
function formatUser(user) {
    const name = user.name || user.login;
    const bio = user.bio || 'No bio';
    const location = user.location || 'N/A';
    const company = user.company || 'N/A';
    const publicRepos = user.public_repos;
    const followers = formatNumber(user.followers);
    const following = formatNumber(user.following);
    const url = user.html_url;
    
    let formatted = `👤 **${name}** (@${user.login})\n\n`;
    formatted += `${bio}\n\n`;
    formatted += `📍 ${location} • 🏢 ${company}\n`;
    formatted += `📦 ${publicRepos} repos • 👥 ${followers} followers • ${following} following\n\n`;
    formatted += `🔗 [View Profile](${url})`;
    
    return formatted;
}

// ==========================================
// FORMAT USER REPOSITORIES
// ==========================================
function formatUserRepositories(repos, username) {
    let formatted = `💻 **Repositories by ${username}**\n\n`;
    
    repos.slice(0, 10).forEach((repo, index) => {
        const name = repo.name;
        const description = repo.description || 'No description';
        const stars = formatNumber(repo.stargazers_count);
        const language = repo.language || 'N/A';
        const url = repo.html_url;
        
        formatted += `**${index + 1}. ${name}**\n`;
        formatted += `   ${description}\n`;
        formatted += `   ⭐ ${stars} • 💻 ${language}\n`;
        formatted += `   🔗 [View](${url})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT TRENDING REPOS
// ==========================================
function formatTrendingRepos(repos, language, since) {
    const langText = language ? ` ${language}` : '';
    const sinceText = since === 'daily' ? 'Today' : since === 'weekly' ? 'This Week' : 'This Month';
    
    let formatted = `🔥 **Trending${langText} Repositories (${sinceText})**\n\n`;
    
    repos.slice(0, 10).forEach((repo, index) => {
        const name = repo.full_name;
        const description = repo.description || 'No description';
        const stars = formatNumber(repo.stargazers_count);
        const url = repo.html_url;
        
        formatted += `**${index + 1}. ${name}**\n`;
        formatted += `   ${description}\n`;
        formatted += `   ⭐ ${stars} stars\n`;
        formatted += `   🔗 [View](${url})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT REPOSITORY DETAILS
// ==========================================
function formatRepositoryDetails(repo) {
    const name = repo.full_name;
    const description = repo.description || 'No description';
    const stars = formatNumber(repo.stargazers_count);
    const forks = formatNumber(repo.forks_count);
    const watchers = formatNumber(repo.watchers_count);
    const language = repo.language || 'N/A';
    const license = repo.license?.name || 'No license';
    const openIssues = repo.open_issues_count;
    const url = repo.html_url;
    const createdAt = new Date(repo.created_at).toLocaleDateString();
    const updatedAt = new Date(repo.updated_at).toLocaleDateString();
    
    let formatted = `💻 **${name}**\n\n`;
    formatted += `${description}\n\n`;
    formatted += `⭐ ${stars} stars • 🍴 ${forks} forks • 👁️ ${watchers} watchers\n`;
    formatted += `💻 ${language} • 📜 ${license}\n`;
    formatted += `🐛 ${openIssues} open issues\n`;
    formatted += `📅 Created: ${createdAt} • Updated: ${updatedAt}\n\n`;
    
    if (repo.homepage) {
        formatted += `🌐 [Website](${repo.homepage})\n`;
    }
    
    formatted += `🔗 [View on GitHub](${url})`;
    
    return formatted;
}

// ==========================================
// FORMAT CODE RESULTS
// ==========================================
function formatCodeResults(results, query) {
    let formatted = `🔍 **Code Search: ${query}**\n\n`;
    
    results.slice(0, 8).forEach((result, index) => {
        const name = result.name;
        const repo = result.repository.full_name;
        const path = result.path;
        const url = result.html_url;
        
        formatted += `**${index + 1}. ${name}**\n`;
        formatted += `   📦 ${repo}\n`;
        formatted += `   📁 ${path}\n`;
        formatted += `   🔗 [View Code](${url})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
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

## **🔑 API KEY SETUP (OPTIONAL):**

### **Without Token (Free - Works Immediately!):**
✅ **60 requests per hour** (good for testing)
- No setup required
- Works out of the box

### **With Token (Recommended):**
1. Go to: https://github.com/settings/tokens
2. Click **Generate new token (classic)**
3. Name it "Crump AI"
4. Select scopes: `public_repo`, `read:user`
5. Generate and copy token
6. **5,000 requests per hour** with token!
7. Add to Vercel:
```
   GITHUB_API_TOKEN=your_token_here
