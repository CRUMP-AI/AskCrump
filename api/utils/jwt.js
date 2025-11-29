// =====================================================
// JWT UTILITIES
// Location: /api/utils/jwt.js
// =====================================================

import jwt from 'jsonwebtoken';

const ACCESS_TOKEN_TTL = '15m';      // Short-lived access token (good for security)
const REFRESH_TOKEN_TTL = '365d';    // 1-year persistent login (your Option A)

// Use separate secrets if you have them, otherwise fall back to one
const JWT_SECRET = process.env.JWT_SECRET;
const JWT_REFRESH_SECRET = process.env.JWT_REFRESH_SECRET || JWT_SECRET;

function getSecret(isRefresh = false) {
    const base = isRefresh ? JWT_REFRESH_SECRET : JWT_SECRET;
    if (!base) {
        // Dev-only fallback to avoid hard crash if env is missing
        console.warn('⚠️ JWT secret missing. Using insecure dev secret. Set JWT_SECRET in production.');
        return 'INSECURE_DEV_SECRET_CHANGE_ME';
    }
    return base;
}

/**
 * Create an access token for the user
 * Payload keeps things simple but compatible with existing code.
 */
export function signAccessToken(user) {
    if (!user || !user.id) {
        throw new Error('signAccessToken: user.id is required');
    }

    const payload = {
        userId: user.id,
        email: user.email || null,
        created_at: user.created_at || user.createdAt || null,
        tier: user.tier || user.subscription_tier || 'free',
        type: 'access'
    };

    return jwt.sign(payload, getSecret(false), {
        expiresIn: ACCESS_TOKEN_TTL
    });
}

/**
 * Create a long-lived refresh token
 */
export function signRefreshToken(user) {
    if (!user || !user.id) {
        throw new Error('signRefreshToken: user.id is required');
    }

    const payload = {
        userId: user.id,
        type: 'refresh'
    };

    return jwt.sign(payload, getSecret(true), {
        expiresIn: REFRESH_TOKEN_TTL
    });
}

/**
 * Verify an access token (used all over the app)
 * Returns decoded payload or null.
 */
export function verifyToken(token, options = {}) {
    if (!token) return null;
    try {
        const decoded = jwt.verify(token, getSecret(false), {
            ignoreExpiration: options.ignoreExpiration === true
        });
        return decoded;
    } catch (err) {
        return null;
    }
}

/**
 * Verify a refresh token
 */
export function verifyRefreshToken(token) {
    if (!token) return null;
    try {
        const decoded = jwt.verify(token, getSecret(true));
        // Ensure this is actually a refresh token
        if (!decoded || decoded.type !== 'refresh') return null;
        return decoded;
    } catch (err) {
        return null;
    }
}
