// =====================================================
// AUTH REFRESH ENDPOINT
// Location: /api/auth/refresh.js
// Purpose: Issue a new short-lived access token
//          using a long-lived refresh token cookie.
// =====================================================

import { parse, serialize } from 'cookie';
import { verifyToken, generateAccessToken } from '../utils/jwt.js';
import { supabase } from '../utils/supabase.js';

const REFRESH_COOKIE_NAME = 'crump_refresh_token';

// Optional: 15 minutes for access token lifetime on the client side
// (actual expiry is controlled in generateAccessToken)
const ACCESS_TOKEN_MAX_AGE_SECONDS = 15 * 60;

/**
 * Refresh the access token using the httpOnly refresh token cookie.
 * 
 * Flow:
 * 1. Read refresh token from cookie.
 * 2. Verify token & extract userId.
 * 3. Load user from Supabase.
 * 4. Issue new access token.
 * 5. Return access token + basic user info.
 */
export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        // -------------------------------------------------
        // 1. Read refresh token from cookies
        // -------------------------------------------------
        const cookies = parse(req.headers.cookie || '');
        const refreshToken = cookies[REFRESH_COOKIE_NAME];

        if (!refreshToken) {
            return res.status(401).json({
                success: false,
                error: 'Refresh token missing'
            });
        }

        // -------------------------------------------------
        // 2. Verify refresh token
        //    (We rely on verifyToken() + expiry encoded in JWT)
        // -------------------------------------------------
        const decoded = verifyToken(refreshToken);

        if (!decoded || !decoded.userId) {
            return res.status(401).json({
                success: false,
                error: 'Invalid or expired refresh token'
            });
        }

        const userId = decoded.userId;

        // -------------------------------------------------
        // 3. Load user from Supabase
        // -------------------------------------------------
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
                subscription_status
            `)
            .eq('id', userId)
            .single();

        if (userError || !user) {
            console.error('Refresh error: user not found', userError);
            return res.status(401).json({
                success: false,
                error: 'User not found for this refresh token'
            });
        }

        // -------------------------------------------------
        // 4. Issue new access token
        // -------------------------------------------------
        const accessToken = generateAccessToken({ userId: user.id });

        // (Optional) If you want to "slide" the refresh window,
        // you can re-set the refresh cookie here with a new token.
        // For now we ONLY issue a new access token and keep the
        // original refresh cookie as-is.

        // -------------------------------------------------
        // 5. Return new access token + user payload
        // -------------------------------------------------
        return res.status(200).json({
            success: true,
            accessToken,
            // Keep user payload shape consistent with login/check-session
            user: {
                id: user.id,
                email: user.email,
                full_name: user.full_name,
                is_verified: user.is_verified,
                profile_picture: user.profile_picture,
                preferences: user.preferences,
                created_at: user.created_at,
                subscri

