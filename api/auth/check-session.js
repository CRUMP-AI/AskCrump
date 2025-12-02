// =====================================================
// AUTH - CHECK SESSION
// Location: /api/auth/check-session.js
// =====================================================

import { parse, serialize } from 'cookie';
import { verifyAuth } from '../middleware/auth.js';
import { supabase } from '../utils/supabase.js';
import {
    verifyRefreshToken,
    signAccessToken,
    signRefreshToken
} from '../utils/jwt.js';

export default async function handler(req, res) {
    if (req.method !== 'GET') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        // 1) Try normal auth first (auth_token cookie or Authorization header)
        let user = await verifyAuth(req);

        if (!user) {
            // 2) If no valid access token, try refresh token
            const cookies = parse(req.headers.cookie || '');
            const refreshToken = cookies.crump_refresh_token;

            if (refreshToken) {
                const decoded = verifyRefreshToken(refreshToken);
                if (decoded && decoded.userId) {
                    const { data: dbUser, error } = await supabase
                        .from('users')
                        .select('id, email, created_at, tier, subscription_tier')
                        .eq('id', decoded.userId)
                        .single();

                    if (!error && dbUser) {
                        user = dbUser;

                        // Issue fresh tokens
                                               const newAccessToken = signAccessToken(dbUser);
                        const newRefreshToken = signRefreshToken(dbUser);

                        const accessCookie = serialize('auth_token', newAccessToken, {
                            httpOnly: true,
                            secure: process.env.NODE_ENV === 'production',
                            sameSite: 'lax',
                            path: '/',
                            maxAge: 60 * 60 // 1 hour
                        });

                        const refreshCookie = serialize('crump_refresh_token', newRefreshToken, {
                            httpOnly: true,
                            secure: process.env.NODE_ENV === 'production',
                            sameSite: 'lax',
                            path: '/',
                            maxAge: 365 * 24 * 60 * 60 // 1 year
                        });

                        res.setHeader('Set-Cookie', [accessCookie, refreshCookie]);

                    }
                }
            }
        }

        // If still no user → not authenticated
        if (!user) {
            return res.status(200).json({
                success: true,
                authenticated: false,
                user: null,
                inTrial: false,
                trialEndsAt: null
            });
        }

        // 7-DAY GLOBAL TRIAL (based on account creation)
        let inTrial = false;
        let trialEndsAt = null;

        if (user.created_at) {
            const createdDate = new Date(user.created_at);
            if (!Number.isNaN(createdDate.getTime())) {
                const end = new Date(
                    createdDate.getTime() + 7 * 24 * 60 * 60 * 1000
                );
                trialEndsAt = end.toISOString();
                const now = new Date();
                if (now < end) {
                    inTrial = true;
                }
            }
        }

        return res.status(200).json({
            success: true,
            authenticated: true,
            user,
            inTrial,
            trialEndsAt
        });
    } catch (err) {
        console.error('check-session error:', err);
        return res.status(500).json({
            success: false,
            authenticated: false,
            error: 'Internal server error'
        });
    }
}
