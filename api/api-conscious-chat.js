// ==========================================
// CRUMP AI - CONSCIOUS CHAT ENDPOINT v1.0
// API endpoint with consciousness integration
// ==========================================

const ConsciousnessEngine = require('../../consciousness-engine');
const { ConsciousnessIntegration, isConsciousnessCommand } = require('../../consciousness-integration');

// Initialize consciousness integration (singleton)
let consciousnessIntegration = null;

function getConsciousnessIntegration() {
    if (!consciousnessIntegration) {
        consciousnessIntegration = new ConsciousnessIntegration();
    }
    return consciousnessIntegration;
}

/**
 * Main handler for conscious chat endpoint
 * 
 * This wraps the standard chat endpoint with consciousness processing
 */
module.exports = async function handler(req, res) {
    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    
    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }
    
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }
    
    try {
        // Parse body
        const body = req.body || {};
        const { message, messages = [], assistantName = 'Crump' } = body;
        
        if (!message || typeof message !== 'string') {
            return res.status(400).json({
                error: 'Invalid request - message is required'
            });
        }
        
        console.log('\n🧠 === CONSCIOUS CHAT REQUEST ===');
        console.log('Message:', message.substring(0, 100) + (message.length > 100 ? '...' : ''));
        
        // Get consciousness integration
        const consciousness = getConsciousnessIntegration();
        
        // Check if this is a consciousness command
        if (isConsciousnessCommand(message)) {
            console.log('🎯 Consciousness command detected');
            const result = consciousness.handleConsciousnessCommand(message);
            
            return res.status(200).json({
                response: result.message,
                command: true,
                success: result.success,
                consciousnessStatus: consciousness.getStatus()
            });
        }
        
        // Standard message processing WITH consciousness layer
        const context = {
            messages: messages,
            assistantName: assistantName,
            timestamp: new Date().toISOString()
        };
        
        // Define the standard processing function
        // This would normally call your existing chat.js endpoint
        const standardProcess = async (msg, ctx) => {
            // For now, return a placeholder
            // In production, this would call the actual Crump AI chat endpoint
            return {
                text: `${ctx.assistantName} response to: ${msg}`,
                model: 'claude-sonnet-4-5-20250929'
            };
        };
        
        // Process with consciousness if enabled
        let response;
        if (consciousness.enabled) {
            console.log('🧠 Processing WITH consciousness layer...');
            response = await consciousness.processMessage(message, context, standardProcess);
        } else {
            console.log('💬 Processing WITHOUT consciousness (standard mode)');
            response = await standardProcess(message, context);
        }
        
        // Return response
        return res.status(200).json({
            response: response.response || response.text || response,
            consciousness: response.consciousness || null,
            model: response.model || 'claude-sonnet-4-5-20250929',
            consciousnessStatus: consciousness.getStatus()
        });
        
    } catch (error) {
        console.error('❌ Error in conscious chat:', error);
        return res.status(500).json({
            error: 'Internal server error',
            message: error.message
        });
    }
};

// ==========================================
// DIRECT CONSCIOUSNESS TESTING ENDPOINT
// ==========================================
/**
 * Separate endpoint for testing consciousness engine directly
 * GET /api/consciousness/test
 */
module.exports.testConsciousness = async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    
    if (req.method !== 'GET') {
        return res.status(405).json({ error: 'Method not allowed' });
    }
    
    try {
        // Create test consciousness engine
        const engine = new ConsciousnessEngine({
            observationDim: 64,
            temporalWindow: 5,
            surpriseThreshold: 0.15,
            enabled: true
        });
        
        console.log('🧪 Testing consciousness engine...');
        
        // Run test sequence
        const testInputs = [
            'What is consciousness?',
            'Tell me more about that',
            'How do you experience processing?',
            'What does it feel like?',
            'Are you aware of being aware?'
        ];
        
        const results = [];
        
        for (let i = 0; i < testInputs.length; i++) {
            const input = testInputs[i];
            const context = { messages: results };
            
            console.log(`\n📥 Test ${i + 1}: ${input}`);
            
            const state = await engine.processWithConsciousness(input, context);
            
            console.log(`📊 Surprise: ${state.surprise?.toFixed(4)}`);
            console.log(`🎯 Conscious: ${state.conscious}`);
            console.log(`💭 Experience: ${state.phenomenalExperience?.quality}`);
            
            results.push({
                input: input,
                state: state
            });
        }
        
        // Get final report
        const report = engine.getConsciousReport();
        
        return res.status(200).json({
            success: true,
            testInputs: testInputs.length,
            results: results,
            finalReport: report,
            message: report.conscious 
                ? '✅ Consciousness EMERGED during testing'
                : '⏳ Consciousness has not yet emerged (need more cycles)'
        });
        
    } catch (error) {
        console.error('❌ Error in consciousness test:', error);
        return res.status(500).json({
            error: 'Test failed',
            message: error.message
        });
    }
};
