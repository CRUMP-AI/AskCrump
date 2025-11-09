// ==========================================
// CRUMP AI - TIME AWARENESS MODULE v1.0
// Comprehensive datetime and timezone handling
// ==========================================

/**

- TIME AWARENESS MODULE
- 
- This module provides comprehensive, accurate datetime information
- throughout the Crump AI system. It ensures:
- 
- 1. Accurate timezone-aware datetime
- 1. Multiple format options for different use cases
- 1. Human-readable time context
- 1. Consistent time awareness across all systems
   */

class TimeAwareness {
constructor(timezone = null) {
// If no timezone provided, use browser’s timezone
this.timezone = timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
this.lastUpdate = null;
this.cache = {};
this.cacheTimeout = 30000; // 30 seconds
}

```
/**
 * Get current datetime in all formats needed by the system
 */
getCurrentDateTime() {
    const now = new Date();
    
    return {
        // ISO 8601 format (machine-readable)
        iso: now.toISOString(),
        
        // Unix timestamp (milliseconds)
        timestamp: now.getTime(),
        
        // Human-readable formats
        date: this.formatDate(now),
        time: this.formatTime(now),
        datetime: this.formatDateTime(now),
        
        // Day of week
        dayOfWeek: this.getDayOfWeek(now),
        
        // Timezone info
        timezone: this.timezone,
        timezoneOffset: now.getTimezoneOffset(),
        timezoneAbbr: this.getTimezoneAbbreviation(now),
        
        // Time period (morning, afternoon, etc.)
        period: this.getTimePeriod(now),
        
        // Hour for contextual behavior
        hour: now.getHours(),
        
        // Full context string
        fullContext: this.getFullContext(now)
    };
}

/**
 * Format date as "Sunday, November 9, 2025"
 */
formatDate(date = new Date()) {
    return date.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        timeZone: this.timezone
    });
}

/**
 * Format time as "8:43 AM"
 */
formatTime(date = new Date()) {
    return date.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
        timeZone: this.timezone
    });
}

/**
 * Format datetime as "Sunday, November 9, 2025 at 8:43 AM"
 */
formatDateTime(date = new Date()) {
    return `${this.formatDate(date)} at ${this.formatTime(date)}`;
}

/**
 * Get day of week
 */
getDayOfWeek(date = new Date()) {
    return date.toLocaleDateString('en-US', {
        weekday: 'long',
        timeZone: this.timezone
    });
}

/**
 * Get timezone abbreviation (EST, PST, etc.)
 */
getTimezoneAbbreviation(date = new Date()) {
    const timeString = date.toLocaleTimeString('en-US', {
        timeZone: this.timezone,
        timeZoneName: 'short'
    });
    
    // Extract timezone abbreviation from the formatted string
    const match = timeString.match(/\b[A-Z]{3,4}\b/);
    return match ? match[0] : this.timezone;
}

/**
 * Get time period (early morning, morning, afternoon, etc.)
 */
getTimePeriod(date = new Date()) {
    const hour = date.getHours();
    
    if (hour >= 0 && hour < 5) return 'late night';
    if (hour >= 5 && hour < 9) return 'early morning';
    if (hour >= 9 && hour < 12) return 'morning';
    if (hour >= 12 && hour < 17) return 'afternoon';
    if (hour >= 17 && hour < 21) return 'evening';
    return 'night';
}

/**
 * Get full context string for system prompts
 */
getFullContext(date = new Date()) {
    const dateStr = this.formatDate(date);
    const timeStr = this.formatTime(date);
    const tzAbbr = this.getTimezoneAbbreviation(date);
    const period = this.getTimePeriod(date);
    
    return `${dateStr} at ${timeStr} ${tzAbbr} (${period})`;
}

/**
 * Get time-based behavioral context for AI
 */
getTimeContext(date = new Date()) {
    const hour = date.getHours();
    const period = this.getTimePeriod(date);

    if (hour >= 22 || hour < 2) {
        return {
            period: 'late night',
            suggestion: 'Late night (10pm-2am). Tone: Supportive, casual. Gently suggest wrapping up if user seems tired. Show concern for wellbeing.',
            alertLevel: 'notice'
        };
    } else if (hour >= 2 && hour < 5) {
        return {
            period: 'very late',
            suggestion: 'Very late (2am-5am). Tone: Concerned but not preachy. Acknowledge dedication, but suggest rest. Be direct: Seriously, you should get some sleep.',
            alertLevel: 'warning'
        };
    } else if (hour >= 5 && hour < 9) {
        return {
            period: 'early morning',
            suggestion: 'Early morning (5am-9am). Tone: Gentle, energetic. Check if they got enough sleep. Suggest prioritizing focus work.',
            alertLevel: 'normal'
        };
    } else if (hour >= 9 && hour < 12) {
        return {
            period: 'morning',
            suggestion: 'Morning (9am-12pm). Tone: Energetic, action-oriented. Prime time for tackling big tasks.',
            alertLevel: 'normal'
        };
    } else if (hour >= 12 && hour < 17) {
        return {
            period: 'afternoon',
            suggestion: 'Afternoon (12pm-5pm). Tone: Efficient, focused. Good for optimization and workflow improvements.',
            alertLevel: 'normal'
        };
    } else if (hour >= 17 && hour < 22) {
        return {
            period: 'evening',
            suggestion: 'Evening (5pm-10pm). Tone: Reflective, planning. Good time to wrap up or prepare for tomorrow.',
            alertLevel: 'normal'
        };
    }

    return {
        period: period,
        suggestion: '',
        alertLevel: 'normal'
    };
}

/**
 * Check if current time is within working hours
 */
isWorkingHours(startHour = 9, endHour = 17, date = new Date()) {
    const hour = date.getHours();
    return hour >= startHour && hour < endHour;
}

/**
 * Get relative time string (e.g., "2 hours ago")
 */
getRelativeTime(timestamp) {
    const now = Date.now();
    const diff = now - timestamp;
    
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    
    if (seconds < 60) return 'just now';
    if (minutes < 60) return `${minutes} minute${minutes !== 1 ? 's' : ''} ago`;
    if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
    if (days < 7) return `${days} day${days !== 1 ? 's' : ''} ago`;
    if (days < 30) return `${Math.floor(days / 7)} week${Math.floor(days / 7) !== 1 ? 's' : ''} ago`;
    if (days < 365) return `${Math.floor(days / 30)} month${Math.floor(days / 30) !== 1 ? 's' : ''} ago`;
    return `${Math.floor(days / 365)} year${Math.floor(days / 365) !== 1 ? 's' : ''} ago`;
}

/**
 * Format datetime for logging
 */
getLogTimestamp(date = new Date()) {
    return date.toLocaleString('en-US', {
        timeZone: this.timezone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
}

/**
 * Get cached datetime (to avoid excessive date object creation)
 */
getCachedDateTime() {
    const now = Date.now();
    
    if (!this.lastUpdate || (now - this.lastUpdate) > this.cacheTimeout) {
        this.cache = this.getCurrentDateTime();
        this.lastUpdate = now;
    }
    
    return this.cache;
}

/**
 * Update timezone
 */
setTimezone(timezone) {
    this.timezone = timezone;
    this.cache = {}; // Clear cache
    this.lastUpdate = null;
}
```

}

// ==========================================
// GLOBAL INSTANCE & EXPORT
// ==========================================

// Create global instance
if (typeof window !== ‘undefined’) {
window.TimeAwareness = TimeAwareness;

```
// Create default instance
if (!window.timeAwareness) {
    window.timeAwareness = new TimeAwareness();
    console.log('⏰ Time Awareness initialized:', window.timeAwareness.getCurrentDateTime().fullContext);
}
```

}

// Node.js export
if (typeof module !== ‘undefined’ && module.exports) {
module.exports = TimeAwareness;
}
