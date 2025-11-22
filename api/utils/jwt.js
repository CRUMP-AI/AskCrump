// =====================================================
// JWT UTILITY FUNCTIONS
// Location: /jwt.js
// =====================================================

import jwt from 'jsonwebtoken';

const JWT_SECRET = process.env.JWT_SECRET;
const JWT_EXPIRES_IN = '30d'; // 30 days

if (!JWT_SECRET) {
    throw new Error('JWT_SECRET environment variable is not set');
}

/**
 * Generate JWT token for user session
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
 * Generate email verification token (24 hours)
 * @param {string} userId - User ID
 * @returns {string} Verification token
 */
export function generateVerificationToken(userId) {
    return jwt.sign(
        { userId, type: 'email_verification' },
        JWT_SECRET,
        { expiresIn: '24h' }
    );
}

/**
 * Generate password reset token (1 hour)
 * @param {string} userId - User ID
 * @returns {string} Reset token
 */
export function generatePasswordResetToken(userId) {
    return jwt.sign(
        { userId, type: 'password_reset' },
        JWT_SECRET,
        { expiresIn: '1h' }
    );
}

/**
 * Verify password reset token
 * @param {string} token - Token to verify
 * @returns {Object} Decoded token data
 * @throws {Error} If token is invalid or expired
 */
export function verifyPasswordResetToken(token) {
    try {
        const decoded = jwt.verify(token, JWT_SECRET);
        if (decoded.type !== 'password_reset') {
            throw new Error('Invalid token type');
        }
        return decoded;
    } catch (error) {
        throw new Error('Invalid or expired token');
    }
}

/**
 * Verify special tokens (verification, password reset, etc.)
 * @param {string} token - Token to verify
 * @returns {Object} Decoded token data
 * @throws {Error} If token is invalid or expired
 */
export function verifySpecialToken(token) {
    try {
        const decoded = jwt.verify(token, JWT_SECRET);
        return decoded;
    } catch (error) {
        throw new Error('Invalid or expired token');
    }
}
