// =====================================================
// AUTHENTICATION MIDDLEWARE
// Location: /api/middleware/auth.js
// =====================================================

import { parse } from 'cookie';
import { verifyToken } from '../utils/jwt.js';
import { supabase } from '../utils/supabase.js';

/**
 * Verify user authentication from request.
 * - Looks for Bearer token in Authorization header first
 * - Falls back to auth_token cookie
 * - Verifies JWT and loads full user record from Supabase
 * @param {Object} req - Request object
 * @returns {Object|null} User data or null if not authenticated
 */
export async function verifyAuth(req) {
    try {
        let token = null;

        // 1) Prefer Authorization: Bearer <token>
        const authHeader = req.headers.authorization || req.headers.Authorization;
        if (authHeader && authHeader.startsWith('Bearer ')) {
            token = authHeader.substring(7);
        }

        // 2) Fallback to auth_token cookie
        if (!token) {
            const cookies = parse(req.headers.cookie || '');
            if (cookies && cookies.auth_token) {
                token = cookies.auth_token;
            }
        }

        // 3) If no token, not authenticated
        if (!token) {
            return null;
        }

        // 4) Verify JWT token
        let decoded;
        try {
            decoded = verifyToken(token);
        } catch (err) {
            console.warn('Invalid auth token:', err.message);
            return null;
        }

        if (!decoded || !decoded.userId) {
            return null;
        }

        // 5) Load user from Supabase
        const { data: user, error } = await supabase
            .from('users')
            .select('*')
            .eq('id', decoded.userId)
            .single();

        if (error || !user) {
            console.warn('User not found for token userId', decoded.userId, error);
            return null;
        }

        // Optional: sanity-check email match if present in token
        if (decoded.email && user.email && decoded.email.toLowerCase() !== user.email.toLowerCase()) {
            console.warn('Token email does not match user record for userId', decoded.userId);
            return null;
        }

        return user;
    } catch (error) {
        console.error('verifyAuth error:', error);
        return null;
    }
}

/**
 * Middleware-style helper: ensures request is authenticated.
 * Attaches req.user on success, otherwise returns 401 JSON.
 */
export async function requireAuth(req, res, handler) {
    const user = await verifyAuth(req);

    if (!user) {
        return res.status(401).json({
            success: false,
            error: 'Authentication required'
        });
    }

    // Attach user to request
    req.user = user;

    // Call the handler
    return handler(req, res);
}

/**
 * Middleware to require email verification.
 * Returns 403 if email not verified.
 */
export async function requireVerified(req, res, handler) {
    return requireAuth(req, res, async (req, res) => {
        if (!req.user.is_verified) {
            return res.status(403).json({
                success: false,
                error: 'Email verification required'
            });
        }
        return handler(req, res);
    });
}
