// ==========================================
// CRUMP SELF-DEBUGGING MODULE v3.0
// DEVELOPER ONLY - PRODUCTION READY
// ==========================================

(function() {
    'use strict';
    
    // ==========================================
    // DEVELOPER ACCESS (Uses existing developer-mode.js)
    // ==========================================
    
    // Check if developer mode is active
    function checkDevAccess() {
        return window.developerMode?.enabled || false;
    }
    
    // ==========================================
    // CODEBASE MAP
    // ==========================================
    const CODEBASE = {
        'app.js': 'Main application logic, message handling, chat management',
        'engines.js': 'Detection engines: image gen, search, API routing, deduplication',
        'autonomous.js': 'Autonomous messaging system',
        'profile-manager.js': 'User profile and tier management',
        'image-generation.js': 'Image generation with DALL-E integration',
        'ui-functions.js': 'UI utilities and helpers',
        'upgrade-ui.js': 'Subscription and upgrade flows',
        'developer-mode.js': 'Developer tools',
        'tutorial.js': 'User onboarding system',
        'scroll-manager.js': 'Scroll-to-end button functionality'
    };
    
    const MAX_ANALYSIS_CHARS = 50000; // ~12.5k tokens
    
    // ==========================================
    // INITIALIZATION
    // ==========================================
    function init() {
        console.log('🔐 Self-Debug Module v3.0 loaded (requires developer login)');
        interceptMessages();
    }
    
    // ==========================================
    // MESSAGE INTERCEPTION
    // ==========================================
    function interceptMessages() {
        const originalSend = window.sendMessage;
        
        window.sendMessage = function(msg) {
            const lower = (msg || '').toLowerCase();
            
            // Only process self-debug commands if developer mode is active
            if (!checkDevAccess()) {
                if (originalSend) originalSend(msg);
                return;
            }
            
            // Self-analysis commands
            if (lower.includes('analyze your code') ||
                lower.includes('check your code') ||
                lower.includes('debug yourself') ||
                lower.includes('health check') ||
                (lower.includes('what') && lower.includes('wrong with you'))) {
                
                handleSelfAnalysis(msg);
                return;
            }
            
            // Specific file analysis
            for (const fileName in CODEBASE) {
                const fileBase = fileName.replace('.js', '');
                if (lower.includes(fileBase) && 
                    (lower.includes('analyze') || lower.includes('check') || lower.includes('fix'))) {
                    handleFileAnalysis(fileName, msg);
                    return;
                }
            }
            
            // Normal message flow
            if (originalSend) originalSend(msg);
        };
    }
    
    // ==========================================
    // SELF-ANALYSIS HANDLER
    // ==========================================
    async function handleSelfAnalysis(userMsg) {
        addMessage('user', userMsg);
        showThinking();
        setAssistantState('thinking');
        
        const scope = determineScope(userMsg);
        const files = selectFiles(scope);
        
        addMessage('assistant', `🔧 **[DEVELOPER MODE]** Analyzing ${files.length} file(s)...\n\nScope: ${scope}`);
        
        const results = [];
        for (const file of files) {
            const code = await fetchCode(file);
            if (code) {
                addMessage('assistant', `📖 Reading ${file}... (${(code.length / 1024).toFixed(1)} KB)`);
                const analysis = await analyzeCode(code, file);
                results.push({ file, code, analysis });
            } else {
                addMessage('assistant', `⚠️ Could not read ${file} from server`);
            }
        }
        
        hideThinking();
        setAssistantState('idle');
        displayResults(results, scope);
    }
    
    // ==========================================
    // FILE ANALYSIS HANDLER
    // ==========================================
    async function handleFileAnalysis(fileName, userMsg) {
        addMessage('user', userMsg);
        showThinking();
        setAssistantState('thinking');
        
        addMessage('assistant', `🔧 **[DEVELOPER MODE]** Analyzing ${fileName}...`);
        
        const code = await fetchCode(fileName);
        if (!code) {
            hideThinking();
            setAssistantState('idle');
            addMessage('assistant', `❌ Error: Could not read ${fileName} from server`);
            return;
        }
        
        addMessage('assistant', `📖 File loaded: ${(code.length / 1024).toFixed(1)} KB, ${code.split('\n').length} lines`);
        
        const analysis = await analyzeCode(code, fileName);
        
        hideThinking();
        setAssistantState('idle');
        displayFileResult(fileName, code, analysis);
    }
    
    // ==========================================
    // ANALYSIS SCOPE
    // ==========================================
    function determineScope(msg) {
        const lower = msg.toLowerCase();
        if (lower.includes('quick')) return 'quick';
        if (lower.includes('full') || lower.includes('complete') || lower.includes('all')) return 'full';
        return 'standard';
    }
    
    function selectFiles(scope) {
        const all = Object.keys(CODEBASE);
        switch(scope) {
            case 'quick':
                return ['app.js', 'engines.js'];
            case 'standard':
                return ['app.js', 'engines.js', 'autonomous.js', 'image-generation.js'];
            case 'full':
                return all;
            default:
                return ['app.js', 'engines.js'];
        }
    }
    
    // ==========================================
    // FETCH CODE FROM SERVER
    // ==========================================
    async function fetchCode(fileName) {
        try {
            // Try /public/ folder first (Vercel structure)
            let response = await fetch(`/public/${fileName}`);
            
            // If not found, try root
            if (!response.ok) {
                response = await fetch(`/${fileName}`);
            }
            
            if (!response.ok) {
                console.warn(`❌ Failed to fetch ${fileName}: ${response.status}`);
                return null;
            }
            const code = await response.text();
            console.log(`✅ Fetched ${fileName}: ${code.length} chars`);
            return code;
        } catch (error) {
            console.error(`❌ Error fetching ${fileName}:`, error);
            return null;
        }
    }
    
    // ==========================================
    // AI CODE ANALYSIS
    // ==========================================
    async function analyzeCode(code, fileName) {
        const isLarge = code.length > MAX_ANALYSIS_CHARS;
        const codeToAnalyze = isLarge ? code.substring(0, MAX_ANALYSIS_CHARS) : code;
        const truncated = isLarge ? `\n\n⚠️ **File truncated for analysis** - showing first ${MAX_ANALYSIS_CHARS} characters only` : '';
        
        const prompt = `You are Crump AI analyzing your own source code for developer Gregory D. Crump Jr.

**YOUR CONTEXT:**
- PWA AI assistant built with vanilla JavaScript
- Version: 3.0.1
- Creator: Gregory D. Crump Jr. (Army veteran, reliability technician at Georgia Pacific)
- Philosophy: Ship fast, iterate quickly, build empires
- Features: Dual-AI routing (Claude + GPT-4), autonomous messaging, image generation, web search
- Theme: Royal navy (#0a1628) and gold (#d4af37)
- N² Engine: Named after Greg's daughters Nala and Niobi

**FILE BEING ANALYZED:**
Name: ${fileName}
Purpose: ${CODEBASE[fileName]}
Size: ${code.length} characters, ${code.split('\n').length} lines${truncated}

**SOURCE CODE:**
\`\`\`javascript
${codeToAnalyze}
\`\`\`

**ANALYSIS REQUIRED:**

1. **Health Status** (pick one):
   - ✅ Healthy: No issues found
   - ⚠️ Issues Found: Minor bugs or improvements needed
   - 🚨 Critical: Serious problems requiring immediate attention

2. **Bugs & Errors:**
   - Undefined variables
   - Logic errors
   - Async/await issues
   - Event listener problems
   - Missing error handling

3. **Performance Issues:**
   - Memory leaks
   - Excessive DOM queries
   - Unnecessary re-renders
   - Slow operations
   - Large payload sizes

4. **Security Concerns:**
   - XSS vulnerabilities
   - Exposed API keys or secrets
   - Missing input sanitization
   - CORS issues

5. **Code Quality:**
   - Readability issues
   - Inconsistent patterns
   - Missing comments on complex logic
   - Opportunities for refactoring

6. **FIXED CODE:**
   Provide the COMPLETE corrected version of the file in a code block.
   Include ALL code, not just the changes.
   Greg will replace the entire file with your corrected version.

**IMPORTANT:**
- Be specific with line numbers when referencing issues
- Focus on actionable improvements
- Keep Greg's coding style (practical, no over-engineering)
- Remember: ship fast, iterate quickly`;

        try {
            // Call AI using existing infrastructure
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: prompt,
                    history: [],
                    currentDateTime: {
                        date: new Date().toLocaleDateString('en-US'),
                        time: new Date().toLocaleTimeString('en-US'),
                        timestamp: new Date().toISOString(),
                        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
                    },
                    universalMemory: {},
                    workMode: 'work', // Use professional mode for code analysis
                    needsSearch: false
                })
            });
            
            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }
            
            const data = await response.json();
            return data.response || 'Error: No analysis returned';
            
        } catch (error) {
            console.error('❌ Analysis failed:', error);
            return `**Error:** Failed to analyze code\n\n${error.message}`;
        }
    }
    
    // ==========================================
    // DISPLAY RESULTS
    // ==========================================
    function displayResults(results, scope) {
        let issueCount = 0;
        let criticalCount = 0;
        
        results.forEach(({ file, analysis }) => {
            const lower = analysis.toLowerCase();
            if (lower.includes('🚨') || lower.includes('critical')) criticalCount++;
            if (lower.includes('⚠️') || lower.includes('issue') || lower.includes('bug')) issueCount++;
        });
        
        const status = criticalCount > 0 ? '🚨 Critical Issues Found' :
                      issueCount > 0 ? '⚠️ Issues Detected' :
                      '✅ All Systems Healthy';
        
        let summary = `## 🔍 ${scope.toUpperCase()} Code Analysis Complete\n\n`;
        summary += `**Overall Status:** ${status}\n`;
        summary += `**Files Analyzed:** ${results.length}\n`;
        summary += `**Issues:** ${issueCount} | **Critical:** ${criticalCount}\n\n`;
        summary += `---\n\n`;
        
        results.forEach(({ file, analysis }) => {
            summary += `### 📄 ${file}\n\n${analysis}\n\n---\n\n`;
        });
        
        addMessage('assistant', summary);
        
        // Store fixed code for downloads
        results.forEach(({ file, code, analysis }) => {
            const fixedCode = extractFixedCode(analysis);
            if (fixedCode && fixedCode.length > 100) {
                storeFixedCode(file, fixedCode, code);
                offerDownload(file);
            }
        });
    }
    
    function displayFileResult(fileName, originalCode, analysis) {
        const message = `## 📄 Analysis: ${fileName}\n\n${analysis}`;
        addMessage('assistant', message);
        
        const fixedCode = extractFixedCode(analysis);
        if (fixedCode && fixedCode.length > 100) {
            storeFixedCode(fileName, fixedCode, originalCode);
            offerDownload(fileName);
        }
    }
    
    // ==========================================
    // CODE EXTRACTION & STORAGE
    // ==========================================
    const fixedCodeStore = {};
    
    function extractFixedCode(analysis) {
        const codeBlockRegex = /```(?:javascript|js)?\n([\s\S]*?)```/g;
        const matches = [...analysis.matchAll(codeBlockRegex)];
        
        if (matches.length === 0) return null;
        
        // Find largest code block (likely the full file)
        let largestBlock = '';
        matches.forEach(match => {
            if (match[1].length > largestBlock.length) {
                largestBlock = match[1];
            }
        });
        
        return largestBlock.trim();
    }
    
    function storeFixedCode(fileName, fixedCode, originalCode) {
        fixedCodeStore[fileName] = {
            fixed: fixedCode,
            original: originalCode,
            timestamp: Date.now()
        };
        console.log(`💾 Stored fixed code for ${fileName}`);
    }
    
    function offerDownload(fileName) {
        const stored = fixedCodeStore[fileName];
        if (!stored) return;
        
        const originalLines = stored.original.split('\n').length;
        const fixedLines = stored.fixed.split('\n').length;
        const diff = fixedLines - originalLines;
        
        const message = `📦 **Fixed version ready: ${fileName}**\n\n` +
                       `• Original: ${originalLines} lines\n` +
                       `• Fixed: ${fixedLines} lines\n` +
                       `• Change: ${diff > 0 ? '+' : ''}${diff} lines\n\n` +
                       `Reply with **"download ${fileName}"** to get the fixed file.`;
        
        addMessage('assistant', message);
    }
    
    // ==========================================
    // DOWNLOAD HANDLING
    // ==========================================
    function handleDownloadCommand(fileName) {
        const stored = fixedCodeStore[fileName];
        if (!stored) {
            addMessage('assistant', `❌ No fixed code available for ${fileName}`);
            return;
        }
        
        // Create download
        const blob = new Blob([stored.fixed], { type: 'text/javascript' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        a.click();
        URL.revokeObjectURL(url);
        
        addMessage('assistant', `✅ Downloaded: **${fileName}**\n\nReplace your current file with this fixed version.`);
        
        if (window.showNotification) {
            window.showNotification(`Downloaded: ${fileName}`, 'success');
        }
    }
    
    // Hook download commands
    const originalSend = window.sendMessage;
    window.sendMessage = function(msg) {
        if (checkDevAccess() && msg && msg.toLowerCase().startsWith('download ')) {
            const fileName = msg.substring(9).trim();
            if (CODEBASE[fileName]) {
                handleDownloadCommand(fileName);
                return;
            }
        }
        if (originalSend) originalSend(msg);
    };
    
    // ==========================================
    // UTILITY FUNCTIONS
    // ==========================================
    function addMessage(role, content) {
        const currentChat = window.crumpDebug?.getCurrentChat?.();
        if (!currentChat) {
            console.error('❌ No active chat');
            return;
        }
        
        const message = {
            role: role,
            content: content,
            timestamp: Date.now()
        };
        
        currentChat.messages.push(message);
        currentChat.updatedAt = Date.now();
        
        // Save chats
        if (typeof window.saveChats === 'function') {
            window.saveChats();
        }
        
        // Render message
        if (typeof renderMessage === 'function') {
            renderMessage(message);
        }
    }
    
    function showThinking() {
        const indicator = document.getElementById('thinkingIndicator');
        if (indicator) indicator.style.display = 'flex';
    }
    
    function hideThinking() {
        const indicator = document.getElementById('thinkingIndicator');
        if (indicator) indicator.style.display = 'none';
    }
    
    function setAssistantState(state) {
        if (typeof window.setAssistantState === 'function') {
            window.setAssistantState(state);
        }
    }
    
    // ==========================================
    // PUBLIC API
    // ==========================================
    window.crumpSelfDebug = {
        isActive: checkDevAccess,
        analyzeFile: (fileName) => handleFileAnalysis(fileName, `Analyze ${fileName}`),
        quickCheck: () => handleSelfAnalysis('quick health check'),
        fullCheck: () => handleSelfAnalysis('full codebase analysis'),
        download: handleDownloadCommand,
        files: CODEBASE
    };
    
    // Auto-init
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
})();

// ==========================================
// USAGE
// ==========================================
/*

FOR DEVELOPER (Greg):

1. Place self-debug-v3.js in /public/ folder (same location as app.js)

2. Login via Developer Login button in sidebar
   - Username: greg@crumpai.com
   - Password: N2-Engine-2025

3. Once logged in, self-debug features activate automatically

COMMANDS:

  "analyze your code"
  "check app.js"
  "debug yourself"
  "health check"
  "quick health check"
  "full codebase analysis"

DOWNLOAD FIXED FILES:
  "download app.js"
  "download engines.js"

FILE STRUCTURE:
/public/
  ├── index.html
  ├── app.js
  ├── engines.js
  ├── self-debug-v3.js  ← Place here
  └── ... other files

PUBLIC USERS:
- Never see this feature
- Commands don't work
- No indication it exists
- Normal Crump experience

INTEGRATION:
- Uses existing developer-mode.js for authentication
- No duplicate login system
- Activates when developer mode is enabled
- Single unified authentication

*/

console.log('✅ Self-Debug Module v3.0 loaded (requires developer login)');
