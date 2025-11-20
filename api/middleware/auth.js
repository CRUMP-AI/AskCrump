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
        if (!req || !req.headers) {
            console.warn('[verifyAuth] Called without valid req/headers');
            return null;
        }

        let token = null;

        // 1) Prefer Authorization: Bearer <token>
        const authHeader = req.headers.authorization || req.headers.Authorization;
        if (authHeader && typeof authHeader === 'string' && authHeader.startsWith('Bearer ')) {
            token = authHeader.substring(7).trim();
        }

        // 2) Fallback to auth_token cookie
        if (!token) {
            try {
                const rawCookieHeader = req.headers.cookie || '';
                const cookies = parse(rawCookieHeader);
                if (cookies && cookies.auth_token) {
                    token = cookies.auth_token;
                }
            } catch (cookieError) {
                console.warn('[verifyAuth] Failed to parse cookies:', cookieError?.message || cookieError);
            }
        }

        // 3) If no token, not authenticated
        if (!token) {
            // This is normal for unauthenticated users, so keep log minimal
            return null;
        }

        // 4) Verify JWT token
        let decoded;
        try {
            decoded = verifyToken(token);
        } catch (err) {
            console.warn('[verifyAuth] Invalid auth token:', err?.message || err);
            return null;
        }

        if (!decoded || !decoded.userId) {
            console.warn('[verifyAuth] Decoded token missing userId');
            return null;
        }

        // 5) Load user from Supabase
        const { data: user, error } = await supabase
            .from('users')
            .select('*')
            .eq('id', decoded.userId)
            .single();

        if (error || !user) {
            console.warn(
                '[verifyAuth] User not found for token userId',
                decoded.userId,
                error || '(no Supabase error object)'
            );
            return null;
        }

        // Optional: sanity-check email match if present in token
        if (
            decoded.email &&
            user.email &&
            typeof decoded.email === 'string' &&
            typeof user.email === 'string' &&
            decoded.email.toLowerCase() !== user.email.toLowerCase()
        ) {
            console.warn(
                '[verifyAuth] Token email does not match user record for userId',
                decoded.userId
            );
            return null;
        }

        return user;
    } catch (error) {
        console.error('[verifyAuth] Unexpected error:', error);
        return null;
    }
}

/**
 * Middleware-style helper: ensures request is authenticated.
 * Attaches req.user on success, otherwise returns 401 JSON.
 *
 * Usage:
 *   export default function handler(req, res) {
 *     return requireAuth(req, res, async (req, res) => {
 *       // req.user is guaranteed here
 *     });
 *   }
 */
export async function requireAuth(req, res, handler) {
    try {
        const user = await verifyAuth(req);

        if (!user) {
            return res.status(401).json({
                success: false,
                error: 'Authentication required'
            });
        }

        // Attach user to request for downstream handlers
        req.user = user;

        // Call the wrapped handler
        return handler(req, res);
    } catch (error) {
        console.error('[requireAuth] Unexpected error:', error);
        return res.status(500).json({
            success: false,
            error: 'Internal authentication error'
        });
    }
}

/**
 * Middleware to require email verification.
 * Returns 403 if email not verified.
 *
 * Usage:
 *   export default function handler(req, res) {
 *     return requireVerified(req, res, async (req, res) => {
 *       // req.user.is_verified === true here
 *     });
 *   }
 */
export async function requireVerified(req, res, handler) {
    return requireAuth(req, res, async (req, res) => {
        try {
            if (!req.user || !req.user.is_verified) {
                return res.status(403).json({
                    success: false,
                    error: 'Email verification required'
                });
            }

            return handler(req, res);
        } catch (error) {
            console.error('[requireVerified] Unexpected error:', error);
            return res.status(500).json({
                success: false,
                error: 'Internal verification error'
            });
        }
    });
}
