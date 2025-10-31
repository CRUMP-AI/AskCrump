// =====================================================
// JWT UTILITY FUNCTIONS
// Location: /api/utils/jwt.js
// =====================================================

import jwt from 'jsonwebtoken';

const JWT_SECRET = process.env.JWT_SECRET;
const JWT_EXPIRES_IN = '30d'; // 30 days

if (!JWT_SECRET) {
    throw new Error('JWT_SECRET environment variable is not set');
}

/**
 * Generate JWT token for user
 * @param {Object} payload - User data to encode
 * @returns {string} JWT token
 */
export function generateToken(payload) {
    return jwt.sign(payload, JWT_SECRET, {
        expiresIn: JWT_EXPIRES_IN
    });
}

/**
 * Verify JWT token
 * @param {string} token - JWT token to verify
 * @returns {Object|null} Decoded token data or null if invalid
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
 * Generate email verification token
 * @param {string} email - User email
 * @returns {string} Verification token
 */
export function generateVerificationToken(email) {
    return jwt.sign({ email, purpose: 'email-verification' }, JWT_SECRET, {
        expiresIn: '24h' // 24 hours for email verification
    });
}

/**
 * Generate password reset token
 * @param {string} email - User email
 * @returns {string} Reset token
 */
export function generateResetToken(email) {
    return jwt.sign({ email, purpose: 'password-reset' }, JWT_SECRET, {
        expiresIn: '1h' // 1 hour for password reset
    });
}

/**
 * Verify special purpose token (email verification, password reset)
 * @param {string} token - Token to verify
 * @param {string} purpose - Expected purpose ('email-verification' or 'password-reset')
 * @returns {Object|null} Decoded token data or null if invalid
 */
export function verifySpecialToken(token, purpose) {
    try {
        const decoded = jwt.verify(token, JWT_SECRET);
        if (decoded.purpose !== purpose) {
            return null;
        }
        return decoded;
    } catch (error) {
        console.error('Special token verification failed:', error.message);
        return null;
    }
}
