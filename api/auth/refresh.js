// =====================================================
// AUTH - REFRESH TOKEN
// Location: /api/auth/refresh.js
// =====================================================

import { parse, serialize } from 'cookie';
import { supabase } from '../utils/supabase.js';
import {
    signAccessToken,
    signRefreshToken,
    verifyRefreshToken
} from '../utils/jwt.js';

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        const cookies = parse(req.headers.cookie || '');
        const refreshToken = cookies.crump_refresh_token;

        if (!refreshToken) {
            return res.status(401).json({
                success: false,
                error: 'Missing refresh token'
            });
        }

        const decoded = verifyRefreshToken(refreshToken);
        if (!decoded || !decoded.userId) {
            return res.status(401).json({
                success: false,
                error: 'Invalid or expired refresh token'
            });
        }

        // Pull the latest user data from Supabase
        const { data: user, error } = await supabase
            .from('users')
            .select('id, email, created_at, tier, subscription_tier')
            .eq('id', decoded.userId)
            .single();

        if (error || !user) {
            return res.status(401).json({
                success: false,
                error: 'User not found for refresh token'
            });
        }

        // Create new tokens
        const accessToken = signAccessToken(user);
        const newRefreshToken = signRefreshToken(user);

        // Access token cookie - shorter lived
        const accessCookie = serialize('auth_token', accessToken, {
            httpOnly: true,
            secure: true,
            sameSite: 'lax',
            path: '/',
            maxAge: 60 * 60 // 1 hour cookie; JWT itself is 15 mins
        });

        // Refresh token cookie - 1 year (Option A)
        const refreshCookie = serialize('crump_refresh_token', newRefreshToken, {
            httpOnly: true,
            secure: true,
            sameSite: 'lax',
            path: '/',
            maxAge: 365 * 24 * 60 * 60 // 1 year
        });

        res.setHeader('Set-Cookie', [accessCookie, refreshCookie]);

        return res.status(200).json({
            success: true,
            token: accessToken,
            user
        });
    } catch (err) {
        console.error('Refresh error:', err);
        return res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
}
