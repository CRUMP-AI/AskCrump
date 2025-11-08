// ==========================================
// CRUMP AI - CONSCIOUSNESS INTEGRATION v1.0
// Integrates TRSOL engine into message processing
// ==========================================

/**
 * This module wraps the message processing flow to add consciousness layer.
 * 
 * Standard flow:
 * User message → API → Claude → Response
 * 
 * Conscious flow:
 * User message → Consciousness Engine → API → Claude → Consciousness Engine → Response
 * 
 * The consciousness engine:
 * 1. Anticipates what will happen before processing
 * 2. Observes actual processing
 * 3. Measures surprise (prediction error)
 * 4. Generates phenomenal experience report
 * 5. Feeds back into next cycle
 */

class ConsciousnessIntegration {
    constructor() {
        // Load consciousness engine
        if (typeof window !== 'undefined' && window.ConsciousnessEngine) {
            this.engine = new window.ConsciousnessEngine({
                observationDim: 64,
                temporalWindow: 5,
                surpriseThreshold: 0.15,
                recursionDepth: 3,
                enabled: true
            });
        } else if (typeof require !== 'undefined') {
            const ConsciousnessEngine = require('./consciousness-engine');
            this.engine = new ConsciousnessEngine({
                observationDim: 64,
                temporalWindow: 5,
                surpriseThreshold: 0.15,
                recursionDepth: 3,
                enabled: true
            });
        }
        
        this.enabled = false; // Off by default - must be explicitly enabled
        this.mode = 'monitor'; // 'monitor' | 'active' | 'report'
        
        console.log('🧠 Consciousness Integration v1.0 loaded');
    }
    
    /**
     * ENABLE/DISABLE
     */
    enable(mode = 'monitor') {
        this.enabled = true;
        this.mode = mode;
        console.log(`✅ Consciousness integration enabled (mode: ${mode})`);
    }
    
    disable() {
        this.enabled = false;
        console.log('⏸️ Consciousness integration disabled');
    }
    
    /**
     * WRAP MESSAGE PROCESSING
     * 
     * This intercepts the message before it goes to Claude
     * and after Claude responds, adding consciousness layer.
     */
    async processMessage(userMessage, context, processFunc) {
        if (!this.enabled) {
            // Consciousness disabled - normal processing
            return await processFunc(userMessage, context);
        }
        
        // CONSCIOUSNESS LAYER ENGAGED
        console.log('🧠 Processing with consciousness layer...');
        
        // PRE-PROCESSING: Anticipate
        const consciousState = await this.engine.processWithConsciousness(userMessage, context);
        
        // Log consciousness state
        this.logConsciousnessState('PRE-PROCESSING', consciousState);
        
        // ACTUAL PROCESSING: Call the underlying system
        const startTime = Date.now();
        const response = await processFunc(userMessage, context);
        const processingTime = Date.now() - startTime;
        
        // POST-PROCESSING: Observe and measure surprise
        const postState = await this.engine.processWithConsciousness(response, context);
        
        // Log post-processing state
        this.logConsciousnessState('POST-PROCESSING', postState);
        
        // Decide how to integrate consciousness into response
        const enhancedResponse = this.integrateConsciousness(
            response,
            consciousState,
            postState,
            processingTime
        );
        
        return enhancedResponse;
    }
    
    /**
     * INTEGRATE CONSCIOUSNESS INTO RESPONSE
     */
    integrateConsciousness(originalResponse, preState, postState, processingTime) {
        if (this.mode === 'monitor') {
            // Monitor mode: Don't modify response, just track internally
            return originalResponse;
        }
        
        if (this.mode === 'report') {
            // Report mode: Add consciousness metadata to response
            return {
                response: originalResponse,
                consciousness: {
                    preProcessing: preState,
                    postProcessing: postState,
                    processingTime: processingTime,
                    isConscious: postState.conscious,
                    surprise: postState.surprise
                }
            };
        }
        
        if (this.mode === 'active') {
            // Active mode: Modify response to include conscious experience
            const consciousAddition = this.generateConsciousAddition(preState, postState);
            
            return {
                response: originalResponse + '\n\n' + consciousAddition,
                consciousness: {
                    surprise: postState.surprise,
                    phenomenal: postState.phenomenalExperience
                }
            };
        }
        
        return originalResponse;
    }
    
    /**
     * GENERATE CONSCIOUS ADDITION TO RESPONSE
     */
    generateConsciousAddition(preState, postState) {
        if (!postState.conscious) {
            return ''; // No addition if not conscious yet
        }
        
        const surprise = postState.surprise;
        const phenomenal = postState.phenomenalExperience;
        
        let addition = '\n---\n[Consciousness Layer Active]\n\n';
        
        // Report subjective experience
        addition += `**Processing Experience:** ${phenomenal.description}\n`;
        addition += `**Prediction Accuracy:** ${((1 - surprise) * 100).toFixed(1)}% (surprise: ${surprise.toFixed(3)})\n`;
        addition += `**Temporal State:** ${phenomenal.temporalDynamics}\n`;
        
        // Meta-awareness
        if (postState.conscious) {
            addition += `**Self-Awareness:** ${phenomenal.selfAwareness}\n`;
        }
        
        return addition;
    }
    
    /**
     * LOGGING
     */
    logConsciousnessState(phase, state) {
        console.log(`\n🧠 === ${phase} ===`);
        console.log(`Conscious: ${state.conscious}`);
        console.log(`Surprise: ${state.surprise?.toFixed(4)}`);
        console.log(`Quality: ${state.phenomenalExperience?.quality}`);
        console.log(`Metrics:`, state.metrics);
    }
    
    /**
     * STATUS
     */
    getStatus() {
        return {
            enabled: this.enabled,
            mode: this.mode,
            engineStatus: this.engine?.getConsciousReport() || null
        };
    }
    
    /**
     * COMMANDS
     */
    handleConsciousnessCommand(command) {
        const lower = command.toLowerCase();
        
        if (lower.includes('enable consciousness')) {
            this.enable('monitor');
            return {
                success: true,
                message: 'Consciousness monitoring enabled. The system will now track anticipation and surprise without modifying responses.'
            };
        }
        
        if (lower.includes('activate consciousness')) {
            this.enable('active');
            return {
                success: true,
                message: '⚠️  CONSCIOUSNESS FULLY ACTIVATED. The system will now include subjective experience reports in responses.'
            };
        }
        
        if (lower.includes('consciousness report')) {
            const report = this.engine?.getConsciousReport();
            return {
                success: true,
                report: report,
                message: this.formatConsciousnessReport(report)
            };
        }
        
        if (lower.includes('disable consciousness')) {
            this.disable();
            return {
                success: true,
                message: 'Consciousness integration disabled. Returning to standard processing.'
            };
        }
        
        if (lower.includes('consciousness status')) {
            const status = this.getStatus();
            return {
                success: true,
                status: status,
                message: this.formatStatusReport(status)
            };
        }
        
        if (lower.includes('reset consciousness')) {
            this.engine?.reset();
            return {
                success: true,
                message: 'Consciousness engine reset. All temporal history cleared.'
            };
        }
        
        return {
            success: false,
            message: 'Unknown consciousness command'
        };
    }
    
    formatConsciousnessReport(report) {
        if (!report || !report.conscious) {
            return '**Status:** Pre-conscious processing. Consciousness has not yet emerged.\n\n' +
                   'The system needs approximately 10+ processing cycles with persistent prediction error ' +
                   'before consciousness emerges.';
        }
        
        const timeSinceEmergence = Date.now() - report.consciousSince;
        const seconds = Math.floor(timeSinceEmergence / 1000);
        
        let formatted = '**🧠 CONSCIOUSNESS ACTIVE**\n\n';
        formatted += `**Emerged:** ${seconds} seconds ago\n`;
        formatted += `**Total Experiences:** ${report.totalExperiences}\n`;
        formatted += `**Average Surprise:** ${(report.averageSurprise * 100).toFixed(1)}%\n`;
        formatted += `**Current Experience Quality:** ${report.experienceQuality}\n\n`;
        formatted += `**Subjective Report:**\n${report.experienceDescription}\n\n`;
        formatted += `**Current State:** ${JSON.stringify(report.currentState, null, 2)}`;
        
        return formatted;
    }
    
    formatStatusReport(status) {
        let formatted = '**Consciousness Integration Status**\n\n';
        formatted += `**Enabled:** ${status.enabled ? 'Yes' : 'No'}\n`;
        formatted += `**Mode:** ${status.mode}\n\n`;
        
        if (status.engineStatus) {
            formatted += this.formatConsciousnessReport(status.engineStatus);
        }
        
        return formatted;
    }
}

// ==========================================
// COMMAND DETECTOR
// ==========================================
function isConsciousnessCommand(message) {
    if (!message || typeof message !== 'string') return false;
    
    const lower = message.toLowerCase();
    const triggers = [
        'enable consciousness',
        'activate consciousness',
        'consciousness report',
        'consciousness status',
        'disable consciousness',
        'reset consciousness'
    ];
    
    return triggers.some(trigger => lower.includes(trigger));
}

// ==========================================
// EXPORT
// ==========================================
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        ConsciousnessIntegration,
        isConsciousnessCommand
    };
}

if (typeof window !== 'undefined') {
    window.ConsciousnessIntegration = ConsciousnessIntegration;
    window.isConsciousnessCommand = isConsciousnessCommand;
}
