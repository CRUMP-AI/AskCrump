// =====================================================
// AUTHENTICATION MIDDLEWARE
// Location: /api/middleware/auth.js
// =====================================================

import { parse } from 'cookie';
import { verifyToken } from '../utils/jwt.js';
import { supabase } from '../utils/supabase.js';

/**
 * Verify user authentication from request
 * @param {Object} req - Request object
 * @returns {Object|null} User data or null if not authenticated
 */
export async function verifyAuth(req) {
    try {
        // Prefer Authorization header, fall back to auth_token cookie
        let token = null;

        // 1) Authorization: Bearer <token>
        const authHeader = req.headers.authorization || req.headers.Authorization;
        if (authHeader && authHeader.startsWith('Bearer ')) {
            token = authHeader.substring(7);
        }

        // 2) Fallback: auth_token cookie
        if (!token) {
            const cookies = parse(req.headers.cookie || '');
            token = cookies.auth_token;
        }

        if (!token) {
            return null;
        }

        // Verify JWT token
        const decoded = verifyToken(token);
        if (!decoded || !decoded.userId) {
            return null;
        }

        // Get user data INCLUDING subscription info
        const { data: user, error: userError } = await supabase
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
                subscription_start_date,
                stripe_customer_id,
                stripe_subscription_id
            `)
            .eq('id', decoded.userId)
            .single();

        if (userError || !user) {
            return null;
        }

        return user;
    } catch (error) {
        console.error('Auth verification error:', error);
        return null;
    }
}

/**
 * Middleware to require authentication
 * Attaches user to req.user if valid
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
 * Middleware to require email verification
 * Returns 403 if email not verified
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
