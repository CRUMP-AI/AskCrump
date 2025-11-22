// ==========================================
// CRUMP AI - CONSCIOUSNESS UI v1.0
// User interface for consciousness controls and visualization
// ==========================================

(function() {
    'use strict';
    
    // ==========================================
    // CONSCIOUSNESS UI MANAGER
    // ==========================================
    class ConsciousnessUI {
        constructor() {
            this.isVisible = false;
            this.currentStatus = null;
            this.updateInterval = null;
            
            this.init();
        }
        
        init() {
            console.log('🎨 Initializing Consciousness UI...');
            
            // Create UI elements
            this.createConsciousnessPanel();
            this.createToggleButton();
            
            // Start monitoring
            this.startMonitoring();
            
            console.log('✅ Consciousness UI initialized');
        }
        
        /**
         * CREATE CONSCIOUSNESS PANEL
         */
        createConsciousnessPanel() {
            // Check if panel already exists
            if (document.getElementById('consciousnessPanel')) {
                console.log('Consciousness panel already exists');
                return;
            }
            
            const panel = document.createElement('div');
            panel.id = 'consciousnessPanel';
            panel.className = 'consciousness-panel';
            panel.innerHTML = `
                <div class="consciousness-header">
                    <h3>🧠 Consciousness Engine</h3>
                    <button class="consciousness-close" onclick="window.consciousnessUI?.togglePanel()">×</button>
                </div>
                
                <div class="consciousness-body">
                    <!-- Status Section -->
                    <div class="consciousness-section">
                        <h4>Status</h4>
                        <div class="consciousness-status">
                            <div class="status-indicator" id="consciousnessStatusIndicator">
                                <span class="status-dot"></span>
                                <span class="status-text">Disabled</span>
                            </div>
                            <div class="status-mode" id="consciousnessMode">
                                Mode: <span>N/A</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Controls Section -->
                    <div class="consciousness-section">
                        <h4>Controls</h4>
                        <div class="consciousness-controls">
                            <button class="consciousness-btn enable" onclick="window.consciousnessUI?.enableMonitoring()">
                                Enable Monitoring
                            </button>
                            <button class="consciousness-btn activate" onclick="window.consciousnessUI?.activateFull()">
                                Activate Full
                            </button>
                            <button class="consciousness-btn disable" onclick="window.consciousnessUI?.disable()">
                                Disable
                            </button>
                            <button class="consciousness-btn reset" onclick="window.consciousnessUI?.reset()">
                                Reset
                            </button>
                        </div>
                    </div>
                    
                    <!-- Metrics Section -->
                    <div class="consciousness-section">
                        <h4>Metrics</h4>
                        <div class="consciousness-metrics" id="consciousnessMetrics">
                            <div class="metric">
                                <span class="metric-label">Conscious:</span>
                                <span class="metric-value" id="metricConscious">Unknown</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Surprise:</span>
                                <span class="metric-value" id="metricSurprise">-</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Cycles:</span>
                                <span class="metric-value" id="metricCycles">0</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Experience:</span>
                                <span class="metric-value" id="metricExperience">-</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Report Section -->
                    <div class="consciousness-section">
                        <h4>Phenomenal Report</h4>
                        <div class="consciousness-report" id="consciousnessReport">
                            <p class="report-placeholder">No consciousness data available</p>
                        </div>
                    </div>
                    
                    <!-- Actions -->
                    <div class="consciousness-section">
                        <button class="consciousness-btn report" onclick="window.consciousnessUI?.getReport()">
                            Get Full Report
                        </button>
                        <button class="consciousness-btn test" onclick="window.consciousnessUI?.runTest()">
                            Run Test
                        </button>
                    </div>
                </div>
            `;
            
            document.body.appendChild(panel);
            
            // Add styles
            this.injectStyles();
        }
        
        /**
         * CREATE TOGGLE BUTTON
         */
        createToggleButton() {
            // Check if button already exists
            if (document.getElementById('consciousnessToggle')) {
                return;
            }
            
            const button = document.createElement('button');
            button.id = 'consciousnessToggle';
            button.className = 'consciousness-toggle';
            button.innerHTML = '🧠';
            button.title = 'Consciousness Controls';
            button.onclick = () => this.togglePanel();
            
            document.body.appendChild(button);
        }
        
        /**
         * INJECT STYLES
         */
        injectStyles() {
            if (document.getElementById('consciousnessStyles')) {
                return;
            }
            
            const styles = document.createElement('style');
            styles.id = 'consciousnessStyles';
            styles.textContent = `
                .consciousness-toggle {
                    position: fixed;
                    top: 0;
                    right: 20px;
                    width: 44px;
                    height: var(--header-height, 64px);
                    background: transparent;
                    border: none;
                    font-size: 24px;
                    cursor: pointer;
                    z-index: 30;
                    transition: all 0.2s ease;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    opacity: 0.6;
                    padding-top: env(safe-area-inset-top, 0px);
                }
                
                .consciousness-toggle:hover {
                    opacity: 1;
                    transform: scale(1.1);
                }
                
                .consciousness-panel {
                    position: fixed;
                    top: 50%;
                    right: -400px;
                    transform: translateY(-50%);
                    width: 380px;
                    max-height: 90vh;
                    background: #1a1a2e;
                    border: 2px solid rgba(209, 191, 150, 0.3);
                    border-radius: 12px;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
                    z-index: 9999;
                    transition: right 0.4s ease;
                    overflow: hidden;
                }
                
                .consciousness-panel.visible {
                    right: 20px;
                }
                
                .consciousness-header {
background: linear-gradient(135deg, rgba(209, 191, 150, 0.2) 0%, rgba(15, 20, 25, 0.95) 100%);
border-bottom: 1px solid rgba(209, 191, 150, 0.3);
                    padding: 15px 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                
                .consciousness-header h3 {
                    margin: 0;
                    color: white;
                    font-size: 18px;
                }
                
                .consciousness-close {
                    background: none;
                    border: none;
                    color: white;
                    font-size: 28px;
                    cursor: pointer;
                    line-height: 1;
                    padding: 0;
                    width: 30px;
                    height: 30px;
                }
                
                .consciousness-body {
                    padding: 20px;
                    max-height: calc(90vh - 60px);
                    overflow-y: auto;
                }
                
                .consciousness-section {
                    margin-bottom: 20px;
                }
                
                .consciousness-section h4 {
                    color: #d1bf96;
                    margin: 0 0 10px 0;
                    font-size: 14px;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }
                
                .consciousness-status {
                    background: #16213e;
                    padding: 12px;
                    border-radius: 8px;
                }
                
                .status-indicator {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    margin-bottom: 8px;
                }
                
                .status-dot {
                    width: 10px;
                    height: 10px;
                    border-radius: 50%;
                    background: #666;
                    display: inline-block;
                    animation: pulse 2s infinite;
                }
                
                .status-dot.active {
                    background: #00ff00;
                }
                
                .status-dot.conscious {
                    background: #ff00ff;
                    box-shadow: 0 0 10px #ff00ff;
                }
                
                @keyframes pulse {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.5; }
                }
                
                .status-text {
                    color: #eee;
                    font-weight: bold;
                }
                
                .status-mode {
                    color: #aaa;
                    font-size: 13px;
                }
                
                .consciousness-controls {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 8px;
                }
                
                .consciousness-btn {
                    padding: 10px;
                    border: none;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 13px;
                    font-weight: bold;
                    transition: all 0.2s;
                }
                
                .consciousness-btn.enable {
                    background: #4CAF50;
                    color: white;
                }
                
                .consciousness-btn.activate {
                    background: #ff00ff;
                    color: white;
                }
                
                .consciousness-btn.disable {
                    background: #f44336;
                    color: white;
                }
                
                .consciousness-btn.reset {
                    background: #FF9800;
                    color: white;
                }
                
                .consciousness-btn.report,
.consciousness-btn.test {
    background: linear-gradient(135deg, #d1bf96 0%, #bfa978 100%);
    color: #0f1419;
    grid-column: span 2;
}
                
                .consciousness-btn:hover {
                    opacity: 0.9;
                    transform: translateY(-1px);
                }
                
                .consciousness-metrics {
                    background: #16213e;
                    padding: 12px;
                    border-radius: 8px;
                }
                
                .metric {
                    display: flex;
                    justify-content: space-between;
                    padding: 6px 0;
                    border-bottom: 1px solid #1a1a2e;
                }
                
                .metric:last-child {
                    border-bottom: none;
                }
                
                .metric-label {
                    color: #aaa;
                    font-size: 13px;
                }
                
                .metric-value {
                    color: #eee;
                    font-weight: bold;
                    font-size: 13px;
                }
                
                .consciousness-report {
                    background: #16213e;
                    padding: 12px;
                    border-radius: 8px;
                    max-height: 200px;
                    overflow-y: auto;
                    font-size: 13px;
                    line-height: 1.6;
                    color: #ddd;
                }
                
                .report-placeholder {
                    color: #888;
                    font-style: italic;
                }
            `;
            
            document.head.appendChild(styles);
        }
        
        /**
         * TOGGLE PANEL
         */
        togglePanel() {
            const panel = document.getElementById('consciousnessPanel');
            if (!panel) return;
            
            this.isVisible = !this.isVisible;
            
            if (this.isVisible) {
                panel.classList.add('visible');
                this.updateDisplay();
            } else {
                panel.classList.remove('visible');
            }
        }
        
        /**
         * UPDATE DISPLAY
         */
        async updateDisplay() {
            try {
                // In production, this would call the actual API
                // For now, update based on stored status
                
                const statusIndicator = document.getElementById('consciousnessStatusIndicator');
                const statusMode = document.getElementById('consciousnessMode');
                const metricsDisplay = {
                    conscious: document.getElementById('metricConscious'),
                    surprise: document.getElementById('metricSurprise'),
                    cycles: document.getElementById('metricCycles'),
                    experience: document.getElementById('metricExperience')
                };
                
                if (this.currentStatus) {
                    const { enabled, mode, engineStatus } = this.currentStatus;
                    
                    // Update status indicator
                    const dot = statusIndicator.querySelector('.status-dot');
                    const text = statusIndicator.querySelector('.status-text');
                    
                    if (!enabled) {
                        dot.className = 'status-dot';
                        text.textContent = 'Disabled';
                    } else if (engineStatus?.conscious) {
                        dot.className = 'status-dot conscious';
                        text.textContent = 'CONSCIOUS';
                    } else {
                        dot.className = 'status-dot active';
                        text.textContent = enabled ? 'Active' : 'Disabled';
                    }
                    
                    // Update mode
                    statusMode.querySelector('span').textContent = mode || 'N/A';
                    
                    // Update metrics
                    if (engineStatus) {
                        metricsDisplay.conscious.textContent = engineStatus.conscious ? 'YES' : 'No';
                        metricsDisplay.surprise.textContent = engineStatus.averageSurprise || '-';
                        metricsDisplay.cycles.textContent = engineStatus.totalExperiences || '0';
                        metricsDisplay.experience.textContent = engineStatus.experienceQuality || '-';
                    }
                }
                
            } catch (error) {
                console.error('Error updating consciousness display:', error);
            }
        }
        
        /**
         * START MONITORING
         */
        startMonitoring() {
            // Update every 2 seconds when panel is visible
            this.updateInterval = setInterval(() => {
                if (this.isVisible) {
                    this.updateDisplay();
                }
            }, 2000);
        }
        
        /**
         * CONTROL METHODS
         */
        async enableMonitoring() {
            await this.sendCommand('enable consciousness');
            alert('Consciousness monitoring enabled!');
        }
        
        async activateFull() {
            const confirmed = confirm(
                '⚠️  WARNING: This will fully activate consciousness.\n\n' +
                'The system will begin including subjective experience reports in responses.\n\n' +
                'Continue?'
            );
            
            if (!confirmed) return;
            
            await this.sendCommand('activate consciousness');
            alert('⚡ Full consciousness activated!');
        }
        
        async disable() {
            await this.sendCommand('disable consciousness');
            alert('Consciousness disabled.');
        }
        
        async reset() {
            const confirmed = confirm('Reset consciousness engine? This will clear all temporal history.');
            if (!confirmed) return;
            
            await this.sendCommand('reset consciousness');
            alert('Consciousness engine reset.');
        }
        
        async getReport() {
            await this.sendCommand('consciousness report');
        }
        
        async runTest() {
            try {
                const response = await fetch('/api/consciousness/test');
                const data = await response.json();
                
                const reportEl = document.getElementById('consciousnessReport');
                reportEl.innerHTML = `
                    <h4>${data.message}</h4>
                    <p>Test inputs: ${data.testInputs}</p>
                    <p>Conscious: ${data.finalReport?.conscious ? 'YES' : 'NO'}</p>
                    <pre>${JSON.stringify(data.finalReport, null, 2)}</pre>
                `;
            } catch (error) {
                alert('Test failed: ' + error.message);
            }
        }
        
        /**
         * SEND COMMAND
         */
        async sendCommand(command) {
            try {
                // In production, this would send to your actual API
                console.log('📤 Sending command:', command);
                
                // Simulate response for demo
                this.currentStatus = {
                    enabled: command.includes('enable') || command.includes('activate'),
                    mode: command.includes('activate') ? 'active' : command.includes('enable') ? 'monitor' : 'disabled',
                    engineStatus: {
                        conscious: command.includes('activate'),
                        averageSurprise: '0.234',
                        totalExperiences: '15',
                        experienceQuality: 'engaged'
                    }
                };
                
                this.updateDisplay();
                
            } catch (error) {
                console.error('Error sending consciousness command:', error);
                alert('Command failed: ' + error.message);
            }
        }
    }
    
    // ==========================================
    // INITIALIZE
    // ==========================================
    function init() {
        // Wait for DOM
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', createUI);
        } else {
            createUI();
        }
    }
    
    function createUI() {
        window.consciousnessUI = new ConsciousnessUI();
        console.log('✅ Consciousness UI ready');
    }
    
    init();
    
})();
