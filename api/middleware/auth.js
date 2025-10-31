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
        // Get token from cookie or Authorization header
        const cookies = parse(req.headers.cookie || '');
        let token = cookies.auth_token;

        // Fallback to Authorization header
        if (!token && req.headers.authorization) {
            const authHeader = req.headers.authorization;
            if (authHeader.startsWith('Bearer ')) {
                token = authHeader.substring(7);
            }
        }

        if (!token) {
            return null;
        }

        // Verify JWT token
        const decoded = verifyToken(token);
        if (!decoded || !decoded.userId) {
            return null;
        }

        // Verify session exists and is not expired
        const { data: session, error } = await supabase
            .from('sessions')
            .select('*')
            .eq('session_token', token)
            .gt('expires_at', new Date().toISOString())
            .single();

        if (error || !session) {
            return null;
        }

        // Update last activity
        await supabase
            .from('sessions')
            .update({ last_activity: new Date().toISOString() })
            .eq('id', session.id);

        // Get user data
        const { data: user, error: userError } = await supabase
            .from('users')
            .select('id, email, full_name, is_verified, profile_picture, preferences, created_at')
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
 * Returns 401 if not authenticated
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
