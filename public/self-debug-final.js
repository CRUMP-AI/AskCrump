// ========================================
// CRUMP SELF-DEBUGGING MODULE - PRODUCTION
// Full file analysis and replacement
// ========================================

(function() {
    'use strict';
    
    // Crump's codebase map
    const CODEBASE = {
        'app.js': 'Main application logic',
        'engines.js': 'AI routing (Claude/GPT-4)',
        'autonomous.js': 'Autonomous messaging',
        'profile-manager.js': 'User profile management',
        'image-generation.js': 'Image generation',
        'ui-functions.js': 'UI utilities',
        'upgrade-ui.js': 'Upgrade flows',
        'developer-mode.js': 'Developer tools',
        'tutorial.js': 'Onboarding',
        'scroll-manager.js': 'Scroll functionality'
    };
    
    // Token limits for AI analysis (characters, roughly 4 chars = 1 token)
    const MAX_ANALYSIS_CHARS = 60000; // ~15k tokens
    
    // Initialize
    function init() {
        console.log('🧠 Self-debug module loaded');
        interceptMessages();
    }
    
    // Intercept messages for self-analysis commands
    function interceptMessages() {
        const originalSend = window.sendMessage;
        
        window.sendMessage = function(msg) {
            const lower = msg.toLowerCase();
            
            // Self-analysis triggers
            if (lower.includes('analyze your code') ||
                lower.includes('check your code') ||
                lower.includes('debug yourself') ||
                lower.includes('health check') ||
                (lower.includes('what') && lower.includes('wrong with you'))) {
                
                handleSelfAnalysis(msg);
                return;
            }
            
            // Specific file check
            for (const file in CODEBASE) {
                if (lower.includes(file.replace('.js', '')) && 
                    (lower.includes('analyze') || lower.includes('check') || lower.includes('fix'))) {
                    handleFileAnalysis(file, msg);
                    return;
                }
            }
            
            // Normal flow
            if (originalSend) originalSend(msg);
        };
    }
    
    // Handle self-analysis request
    async function handleSelfAnalysis(userMsg) {
        addUserMessage(userMsg);
        showThinking();
        
        const scope = determineScope(userMsg);
        const files = selectFiles(scope);
        
        addAssistantMessage(`Analyzing ${files.length} file(s). This may take a moment...`);
        
        const results = [];
        for (const file of files) {
            const code = await fetchMyCode(file);
            if (code) {
                const analysis = await analyzeFile(code, file);
                results.push({ file, code, analysis });
            }
        }
        
        hideThinking();
        displayResults(results, scope);
    }
    
    // Handle specific file analysis
    async function handleFileAnalysis(fileName, userMsg) {
        addUserMessage(userMsg);
        showThinking();
        
        addAssistantMessage(`Analyzing ${fileName}...`);
        
        const code = await fetchMyCode(fileName);
        if (!code) {
            hideThinking();
            addAssistantMessage(`Error: Could not read ${fileName} from server.`);
            return;
        }
        
        const analysis = await analyzeFile(code, fileName);
        
        hideThinking();
        displayFileResult(fileName, code, analysis);
    }
    
    // Determine analysis scope
    function determineScope(msg) {
        const lower = msg.toLowerCase();
        if (lower.includes('quick')) return 'quick';
        if (lower.includes('full') || lower.includes('complete')) return 'full';
        return 'standard';
    }
    
    // Select files based on scope
    function selectFiles(scope) {
        const all = Object.keys(CODEBASE);
        
        switch(scope) {
            case 'quick':
                return ['app.js', 'engines.js'];
            case 'standard':
                return ['app.js', 'engines.js', 'autonomous.js', 'ui-functions.js'];
            case 'full':
                return all;
            default:
                return ['app.js', 'engines.js'];
        }
    }
    
    // Fetch Crump's own code from server
    async function fetchMyCode(fileName) {
        try {
            const response = await fetch(`/${fileName}`);
            if (!response.ok) return null;
            const code = await response.text();
            console.log(`📖 Read ${fileName}: ${code.length} chars`);
            return code;
        } catch (error) {
            console.error(`Error fetching ${fileName}:`, error);
            return null;
        }
    }
    
    // Analyze file with AI
    async function analyzeFile(code, fileName) {
        // Handle large files
        const isLarge = code.length > MAX_ANALYSIS_CHARS;
        const codeToAnalyze = isLarge ? code.substring(0, MAX_ANALYSIS_CHARS) : code;
        
        const prompt = `You are Crump AI analyzing your own source code.

CONTEXT:
- PWA AI assistant, vanilla JavaScript
- Version: 2.11.0
- Features: Dual-AI routing, autonomous messaging, image generation
- Author: Gregory D. Crump Jr.
- Philosophy: Ship fast, iterate quickly

FILE: ${fileName}
Purpose: ${CODEBASE[fileName]}
${isLarge ? `\n⚠️ FILE TOO LARGE: Analyzing first ${MAX_ANALYSIS_CHARS} characters only\n` : ''}

CODE:
\`\`\`javascript
${codeToAnalyze}
\`\`\`

ANALYSIS REQUIRED:
1. **Status**: Healthy / Issues Found / Critical
2. **Bugs**: Errors, undefined vars, logic issues
3. **Performance**: Memory leaks, slow operations
4. **Security**: XSS risks, exposed keys
5. **Fixed Code**: Provide COMPLETE corrected file (all code, not snippets)

CRITICAL: Return the FULL corrected file in a code block, not just the changed lines. Greg will replace the entire file.`;

        return await callAI(prompt);
    }
    
    // Call AI engine
    async function callAI(prompt) {
        try {
            // Use your existing AI infrastructure
            if (window.callAIEngine) {
                return await window.callAIEngine(prompt);
            }
            
            // Fallback: Call your API endpoint
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    message: prompt,
                    model: 'claude-sonnet-4.5' // Prefer Claude for code
                })
            });
            
            const data = await response.json();
            return data.response || data.message || 'Error: No response';
        } catch (error) {
            console.error('AI call failed:', error);
            return 'Error: Could not analyze code';
        }
    }
    
    // Display analysis results
    function displayResults(results, scope) {
        let issueCount = 0;
        let criticalCount = 0;
        
        let summary = `## 🔍 ${scope.toUpperCase()} Analysis Complete\n\n`;
        summary += `**Files Analyzed:** ${results.length}\n\n`;
        
        results.forEach(({ file, analysis }) => {
            const lower = analysis.toLowerCase();
            if (lower.includes('critical')) criticalCount++;
            if (lower.includes('issue') || lower.includes('bug')) issueCount++;
            
            summary += `### ${file}\n${analysis}\n\n---\n\n`;
        });
        
        const status = criticalCount > 0 ? '🚨 Critical Issues' : 
                      issueCount > 0 ? '⚠️ Issues Found' : 
                      '✅ Healthy';
        
        const header = `**Overall Status:** ${status}\n` +
                      `**Issues:** ${issueCount} | **Critical:** ${criticalCount}\n\n---\n\n`;
        
        addAssistantMessage(header + summary);
        
        // Offer downloads for files with issues
        if (issueCount > 0 || criticalCount > 0) {
            offerDownloads(results);
        }
    }
    
    // Display single file result
    function displayFileResult(fileName, originalCode, analysis) {
        const msg = `## 📄 Analysis: ${fileName}\n\n${analysis}`;
        addAssistantMessage(msg);
        
        // Extract fixed code and offer download
        const fixedCode = extractCodeFromAnalysis(analysis);
        if (fixedCode && fixedCode.length > 100) {
            createDownloadButton(fileName, fixedCode, originalCode);
        }
    }
    
    // Offer download buttons
    function offerDownloads(results) {
        setTimeout(() => {
            const msg = `I've identified issues. Would you like to download the corrected files?\n\n` +
                       `Reply with the filename (e.g., "app.js") to download the fixed version.`;
            addAssistantMessage(msg);
            
            // Setup download listeners
            results.forEach(({ file, code, analysis }) => {
                const fixedCode = extractCodeFromAnalysis(analysis);
                if (fixedCode) {
                    storeFixedCode(file, fixedCode, code);
                }
            });
        }, 1000);
    }
    
    // Extract code block from AI response
    function extractCodeFromAnalysis(analysis) {
        // Look for code blocks
        const codeBlockRegex = /```(?:javascript|js)?\n([\s\S]*?)```/g;
        const matches = [...analysis.matchAll(codeBlockRegex)];
        
        if (matches.length === 0) return null;
        
        // Find the largest code block (likely the full file)
        let largestBlock = '';
        matches.forEach(match => {
            if (match[1].length > largestBlock.length) {
                largestBlock = match[1];
            }
        });
        
        return largestBlock.trim();
    }
    
    // Store fixed code for download
    const fixedCodeStore = {};
    function storeFixedCode(fileName, fixedCode, originalCode) {
        fixedCodeStore[fileName] = {
            fixed: fixedCode,
            original: originalCode,
            timestamp: Date.now()
        };
    }
    
    // Create download button in chat
    function createDownloadButton(fileName, fixedCode, originalCode) {
        const chatContainer = document.getElementById('chatContainer');
        const buttonDiv = document.createElement('div');
        buttonDiv.className = 'message assistant-message download-actions';
        buttonDiv.innerHTML = `
            <div style="display: flex; gap: 0.5rem; margin-top: 1rem; padding: 1rem; background: rgba(201, 184, 146, 0.05); border-radius: 8px; border-left: 3px solid var(--color-accent-primary);">
                <button onclick="window.crumpSelfDebug.download('${fileName}')" class="btn btn-primary">
                    📥 Download ${fileName}
                </button>
                <button onclick="window.crumpSelfDebug.compare('${fileName}')" class="btn btn-secondary">
                    🔍 View Changes
                </button>
                <button onclick="window.crumpSelfDebug.copy('${fileName}')" class="btn btn-secondary">
                    📋 Copy Code
                </button>
            </div>
        `;
        chatContainer.appendChild(buttonDiv);
        
        storeFixedCode(fileName, fixedCode, originalCode);
        
        if (window.crumpScrollManager) {
            window.crumpScrollManager.autoScrollToBottom();
        }
    }
    
    // Download fixed file
    function downloadFixed(fileName) {
        const stored = fixedCodeStore[fileName];
        if (!stored) {
            showToast('No fixed code available for ' + fileName, 'error');
            return;
        }
        
        const blob = new Blob([stored.fixed], { type: 'text/javascript' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        a.click();
        URL.revokeObjectURL(url);
        
        showToast(`Downloaded: ${fileName}`, 'success');
    }
    
    // Copy fixed code to clipboard
    function copyFixed(fileName) {
        const stored = fixedCodeStore[fileName];
        if (!stored) {
            showToast('No fixed code available', 'error');
            return;
        }
        
        navigator.clipboard.writeText(stored.fixed).then(() => {
            showToast('Code copied to clipboard!', 'success');
        }).catch(err => {
            showToast('Copy failed', 'error');
        });
    }
    
    // Compare original vs fixed
    function compareVersions(fileName) {
        const stored = fixedCodeStore[fileName];
        if (!stored) {
            showToast('No comparison available', 'error');
            return;
        }
        
        const originalLines = stored.original.split('\n').length;
        const fixedLines = stored.fixed.split('\n').length;
        const lineDiff = fixedLines - originalLines;
        
        const comparison = `## 📊 Comparison: ${fileName}\n\n` +
                          `**Original:** ${originalLines} lines\n` +
                          `**Fixed:** ${fixedLines} lines\n` +
                          `**Difference:** ${lineDiff > 0 ? '+' : ''}${lineDiff} lines\n\n` +
                          `**Changes made by Crump AI**\n\n` +
                          `Download both versions to see detailed differences in your code editor.`;
        
        addAssistantMessage(comparison);
    }
    
    // UI helper functions
    function addUserMessage(text) {
        if (window.displayUserMessage) {
            window.displayUserMessage(text);
        }
    }
    
    function addAssistantMessage(text) {
        if (window.displayAssistantMessage) {
            window.displayAssistantMessage(text);
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
    
    function showToast(message, type = 'info') {
        if (window.showToast) {
            window.showToast(message, type);
        } else {
            console.log(`Toast: ${message}`);
        }
    }
    
    // Public API
    window.crumpSelfDebug = {
        init: init,
        analyzeFile: handleFileAnalysis,
        download: downloadFixed,
        copy: copyFixed,
        compare: compareVersions,
        files: CODEBASE
    };
    
    // Auto-init
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
})();

// ========================================
// USAGE
// ========================================
/*

NATURAL COMMANDS:
"Analyze your code for bugs"
"Check your code"
"Debug yourself"
"Health check"
"What's wrong with you?"
"Analyze app.js"
"Check your engines.js"

BUTTONS APPEAR:
📥 Download [filename]
🔍 View Changes  
📋 Copy Code

FILE SIZE HANDLING:
- Files under 60k chars: Full analysis
- Files over 60k chars: Partial analysis with warning
- Always returns FULL corrected file (not snippets)

*/
