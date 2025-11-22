// =====================================================
// LOGOUT API ENDPOINT
// Location: /api/auth/logout.js
// =====================================================

import { parse, serialize } from 'cookie';
import { supabase } from '../utils/supabase.js';

export default async function handler(req, res) {
    // Only allow POST requests
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        // Get token from cookie or Authorization header
        const cookies = parse(req.headers.cookie || '');
        let token = cookies.auth_token;

        if (!token && req.headers.authorization) {
            const authHeader = req.headers.authorization;
            if (authHeader.startsWith('Bearer ')) {
                token = authHeader.substring(7);
            }
        }

        if (token) {
            // Delete session from database
            await supabase
                .from('sessions')
                .delete()
                .eq('session_token', token);
        }

        // Clear auth cookie
        const cookie = serialize('auth_token', '', {
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'strict',
            maxAge: 0, // Expire immediately
            path: '/'
        });

        res.setHeader('Set-Cookie', cookie);

        return res.status(200).json({
            success: true,
            message: 'Logged out successfully'
        });

    } catch (error) {
        console.error('Logout error:', error);
        return res.status(500).json({
            success: false,
            error: 'An unexpected error occurred during logout'
        });
    }
}
