// =====================================================
// JWT UTILITY FUNCTIONS
// Location: /api/utils/jwt.js
// =====================================================

import jwt from 'jsonwebtoken';

const JWT_SECRET = process.env.JWT_SECRET;

if (!JWT_SECRET) {
    throw new Error('JWT_SECRET environment variable is not set');
}

// Lifetimes
const ACCESS_TOKEN_EXPIRES_IN = '15m';   // short-lived, for API calls
const REFRESH_TOKEN_EXPIRES_IN = '365d'; // long-lived, for staying signed in
const VERIFICATION_TOKEN_EXPIRES_IN = '24h'; // email verification / special flows

/**
 * Generate short-lived access token (used for Authorization: Bearer)
 * @param {Object} payload - Data to encode (e.g., { userId })
 * @returns {string} JWT access token
 */
export function generateAccessToken(payload) {
    return jwt.sign(payload, JWT_SECRET, {
        expiresIn: ACCESS_TOKEN_EXPIRES_IN
    });
}

/**
 * Generate long-lived refresh token (stored in httpOnly cookie)
 * @param {Object} payload - Data to encode (e.g., { userId })
 * @returns {string} JWT refresh token
 */
export function generateRefreshToken(payload) {
    return jwt.sign(payload, JWT_SECRET, {
        expiresIn: REFRESH_TOKEN_EXPIRES_IN
    });
}

/**
 * Backwards-compatible token generator.
 * If older code calls generateToken, it will behave like an access token.
 * @param {Object} payload
 * @returns {string} JWT token (access)
 */
export function generateToken(payload) {
    return generateAccessToken(payload);
}

/**
 * Verify any JWT token (access, refresh, or special)
 * @param {string} token
 * @returns {Object|null} Decoded payload or null if invalid/expired
 */
export function verifyToken(token) {
    try {
        return jwt.verify(token, JWT_SECRET);
    } catch (error) {
        console.error('JWT verification failed:', error.message);
        return null;
    }
}

/**
 * Generate email verification / special-purpose token (24 hours)
 * @param {string} userId
 * @returns {string} Verification token
 */
export function generateVerificationToken(userId) {
    return jwt.sign(
        {
            userId,
            type: 'verify'
        },
        JWT_SECRET,
        {
            expiresIn: VERIFICATION_TOKEN_EXPIRES_IN
        }
    );
}

/**
 * Verify a special-purpose token (e.g., email verification)
 * @param {string} token
 * @returns {Object} Decoded payload if valid, or throws on error
 */
export function verifySpecialToken(token) {
    try {
        const decoded = jwt.verify(token, JWT_SECRET);

        if (!decoded || !decoded.type) {
            throw new Error('Invalid token type');
        }

        return decoded;
    } catch (error) {
        console.error('Special token verification failed:', error.message);
        throw new Error('Invalid or expired token');
    }
}
