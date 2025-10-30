// ==========================================
// CRUMP AI - PERFORMANCE MONITOR v1.0
// Claude-level performance tracking
// ==========================================

class PerformanceMonitor {
    constructor() {
        this.metrics = {
            load: null,
            fcp: null, // First Contentful Paint
            lcp: null, // Largest Contentful Paint
            fid: null, // First Input Delay
            cls: null, // Cumulative Layout Shift
            ttfb: null // Time to First Byte
        };
        
        this.enabled = true;
        this.init();
        
        console.log('📊 Performance Monitor initialized');
    }

    init() {
        if (!this.enabled) return;

        // Measure page load time
        window.addEventListener('load', () => {
            this.measurePageLoad();
        });

        // Observe Web Vitals
        this.observeWebVitals();

        // Monitor API response times
        this.monitorAPIPerformance();

        // Track memory usage
        this.monitorMemory();
    }

    measurePageLoad() {
        if (!performance || !performance.timing) return;

        const timing = performance.timing;
        const loadTime = timing.loadEventEnd - timing.navigationStart;
        const domReady = timing.domContentLoadedEventEnd - timing.navigationStart;
        const ttfb = timing.responseStart - timing.navigationStart;

        this.metrics.load = loadTime;
        this.metrics.ttfb = ttfb;

        console.log('⚡ Performance Metrics:');
        console.log(`  Load Time: ${loadTime}ms`);
        console.log(`  DOM Ready: ${domReady}ms`);
        console.log(`  TTFB: ${ttfb}ms`);

        // Log warnings for slow performance
        if (loadTime > 3000) {
            console.warn('⚠️ Slow page load detected:', loadTime + 'ms');
        }
        if (ttfb > 600) {
            console.warn('⚠️ Slow server response:', ttfb + 'ms');
        }
    }

    observeWebVitals() {
        // Use Performance Observer API for modern metrics
        if (!('PerformanceObserver' in window)) return;

        // First Contentful Paint
        try {
            const fcpObserver = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                const lastEntry = entries[entries.length - 1];
                this.metrics.fcp = lastEntry.startTime;
                console.log(`🎨 FCP: ${lastEntry.startTime.toFixed(2)}ms`);
            });
            fcpObserver.observe({ entryTypes: ['paint'] });
        } catch (e) {
            console.warn('FCP observation failed:', e);
        }

        // Largest Contentful Paint
        try {
            const lcpObserver = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                const lastEntry = entries[entries.length - 1];
                this.metrics.lcp = lastEntry.startTime;
                console.log(`🖼️ LCP: ${lastEntry.startTime.toFixed(2)}ms`);
                
                if (lastEntry.startTime > 2500) {
                    console.warn('⚠️ Poor LCP performance');
                }
            });
            lcpObserver.observe({ entryTypes: ['largest-contentful-paint'] });
        } catch (e) {
            console.warn('LCP observation failed:', e);
        }

        // First Input Delay
        try {
            const fidObserver = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                entries.forEach(entry => {
                    this.metrics.fid = entry.processingStart - entry.startTime;
                    console.log(`⚡ FID: ${this.metrics.fid.toFixed(2)}ms`);
                    
                    if (this.metrics.fid > 100) {
                        console.warn('⚠️ Poor input responsiveness');
                    }
                });
            });
            fidObserver.observe({ entryTypes: ['first-input'] });
        } catch (e) {
            console.warn('FID observation failed:', e);
        }

        // Cumulative Layout Shift
        try {
            let clsScore = 0;
            const clsObserver = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (!entry.hadRecentInput) {
                        clsScore += entry.value;
                    }
                }
                this.metrics.cls = clsScore;
                
                if (clsScore > 0.1) {
                    console.warn(`⚠️ Layout shift detected: ${clsScore.toFixed(3)}`);
                }
            });
            clsObserver.observe({ entryTypes: ['layout-shift'] });
        } catch (e) {
            console.warn('CLS observation failed:', e);
        }
    }

    monitorAPIPerformance() {
        // Track API call performance
        const originalFetch = window.fetch;
        
        window.fetch = async (...args) => {
            const startTime = performance.now();
            const url = args[0];
            
            try {
                const response = await originalFetch(...args);
                const endTime = performance.now();
                const duration = endTime - startTime;
                
                // Only log for our API calls
                if (typeof url === 'string' && url.includes('/api/')) {
                    console.log(`📡 API call to ${url}: ${duration.toFixed(2)}ms`);
                    
                    if (duration > 5000) {
                        console.warn(`⚠️ Slow API response: ${duration.toFixed(2)}ms`);
                    }
                }
                
                return response;
            } catch (error) {
                const endTime = performance.now();
                const duration = endTime - startTime;
                console.error(`❌ API call failed (${duration.toFixed(2)}ms):`, url, error);
                throw error;
            }
        };
    }

    monitorMemory() {
        // Monitor memory usage (Chrome only)
        if (!performance.memory) return;

        setInterval(() => {
            const memory = performance.memory;
            const usedMB = (memory.usedJSHeapSize / 1048576).toFixed(2);
            const totalMB = (memory.totalJSHeapSize / 1048576).toFixed(2);
            const limitMB = (memory.jsHeapSizeLimit / 1048576).toFixed(2);
            
            const usagePercent = ((memory.usedJSHeapSize / memory.jsHeapSizeLimit) * 100).toFixed(1);
            
            if (usagePercent > 90) {
                console.warn(`⚠️ High memory usage: ${usedMB}MB / ${limitMB}MB (${usagePercent}%)`);
            }
            
            // Log every 5 minutes
            if (Math.random() < 0.001) {
                console.log(`💾 Memory: ${usedMB}MB / ${limitMB}MB (${usagePercent}%)`);
            }
        }, 1000);
    }

    getMetrics() {
        return { ...this.metrics };
    }

    logReport() {
        console.log('📊 Performance Report:');
        console.log('  Load Time:', this.metrics.load ? `${this.metrics.load}ms` : 'N/A');
        console.log('  TTFB:', this.metrics.ttfb ? `${this.metrics.ttfb}ms` : 'N/A');
        console.log('  FCP:', this.metrics.fcp ? `${this.metrics.fcp.toFixed(2)}ms` : 'N/A');
        console.log('  LCP:', this.metrics.lcp ? `${this.metrics.lcp.toFixed(2)}ms` : 'N/A');
        console.log('  FID:', this.metrics.fid ? `${this.metrics.fid.toFixed(2)}ms` : 'N/A');
        console.log('  CLS:', this.metrics.cls ? this.metrics.cls.toFixed(3) : 'N/A');
        
        // Overall score
        const score = this.calculateScore();
        console.log(`  Overall Score: ${score}/100`);
    }

    calculateScore() {
        let score = 100;
        
        // Deduct points for poor metrics
        if (this.metrics.lcp > 2500) score -= 20;
        if (this.metrics.fid > 100) score -= 20;
        if (this.metrics.cls > 0.1) score -= 20;
        if (this.metrics.ttfb > 600) score -= 20;
        if (this.metrics.load > 3000) score -= 20;
        
        return Math.max(0, score);
    }

    // Enable/disable monitoring
    toggle(enabled) {
        this.enabled = enabled;
        console.log(`📊 Performance monitoring ${enabled ? 'enabled' : 'disabled'}`);
    }
}

// ==========================================
// RESOURCE TIMING HELPER
// ==========================================
class ResourceTiming {
    static analyzeResources() {
        if (!performance.getEntriesByType) return;
        
        const resources = performance.getEntriesByType('resource');
        const analysis = {
            scripts: [],
            styles: [],
            images: [],
            fonts: [],
            other: []
        };
        
        resources.forEach(resource => {
            const item = {
                name: resource.name,
                duration: resource.duration.toFixed(2),
                size: resource.transferSize || 0
            };
            
            if (resource.name.endsWith('.js')) {
                analysis.scripts.push(item);
            } else if (resource.name.endsWith('.css')) {
                analysis.styles.push(item);
            } else if (/\.(png|jpg|jpeg|gif|webp|svg)$/i.test(resource.name)) {
                analysis.images.push(item);
            } else if (/\.(woff2?|ttf|otf)$/i.test(resource.name)) {
                analysis.fonts.push(item);
            } else {
                analysis.other.push(item);
            }
        });
        
        return analysis;
    }
    
    static logSlowResources(threshold = 1000) {
        const resources = performance.getEntriesByType('resource');
        const slow = resources.filter(r => r.duration > threshold);
        
        if (slow.length > 0) {
            console.warn(`⚠️ ${slow.length} slow resources detected:`);
            slow.forEach(r => {
                console.warn(`  ${r.name}: ${r.duration.toFixed(2)}ms`);
            });
        }
    }
}

// ==========================================
// INITIALIZE
// ==========================================
window.performanceMonitor = new PerformanceMonitor();
window.PerformanceMonitor = PerformanceMonitor;
window.ResourceTiming = ResourceTiming;

// Auto-log report after 10 seconds
setTimeout(() => {
    window.performanceMonitor.logReport();
    ResourceTiming.logSlowResources(1000);
}, 10000);

console.log('✅ Performance Monitor v1.0 loaded');
