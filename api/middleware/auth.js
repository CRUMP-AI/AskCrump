// =====================================================
// AUTHENTICATION MIDDLEWARE
// Location: /api/middleware/auth.js
// =====================================================

import { parse } from 'cookie';
import { verifyToken } from '../utils/jwt.js';
import { supabase } from '../utils/supabase.js';

/**
 * Verify user authentication from request
 * - Prefers Authorization: Bearer <accessToken>
 * - Falls back to auth_token cookie (short-lived access token)
 * - Loads user from Supabase
 * @param {Object} req - Request object
 * @returns {Object|null} User data or null if not authenticated
 */
export async function verifyAuth(req) {
    try {
        let token = null;

        // 1) Prefer Authorization header
        const authHeader = req.headers.authorization || req.headers.Authorization || '';
        if (authHeader && authHeader.startsWith('Bearer ')) {
            token = authHeader.substring(7);
        }

        // 2) Fallback: auth_token cookie (set on login)
        if (!token) {
            const cookies = parse(req.headers.cookie || '');
            if (cookies.auth_token) {
                token = cookies.auth_token;
            }
        }

        if (!token) {
            return null;
        }

        // 3) Verify JWT token
        const decoded = verifyToken(token);
        if (!decoded || !decoded.userId) {
            return null;
        }

        // 4) Load user from Supabase
        const { data: user, error } = await supabase
            .from('users')
            .select(`
                id,
                email,
                full_name,
                is_verified,
                profile_picture,
                preferences,
                created_at,
                subscription_tier,
                subscription_status,
                stripe_customer_id,
                stripe_subscription_id
            `)
            .eq('id', decoded.userId)
            .single();

        if (error || !user) {
            console.error('verifyAuth user lookup error:', error);
            return null;
        }

        return user;
    } catch (err) {
        console.error('Auth verification error:', err);
        return null;
    }
}

/**
 * Require that the user is authenticated.
 * Attaches `req.user` if successful.
 */
export async function requireAuth(req, res, handler) {
    const user = await verifyAuth(req);

    if (!user) {
        return res.status(401).json({
            success: false,
            error: 'Authentication required'
        });
    }

    req.user = user;
    return handler(req, res);
}

/**
 * Require that the user is authenticated AND verified.
 */
export async function requireVerified(req, res, handler) {
    return requireAuth(req, res, async (reqWithUser, resWithUser) => {
        if (!reqWithUser.user.is_verified) {
            return resWithUser.status(403).json({
                success: false,
                error: 'Email verification required'
            });
        }

        return handler(reqWithUser, resWithUser);
    });
}
