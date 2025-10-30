// ==========================================
// CRUMP AI - LOGOUT API
// Invalidates user session
// ==========================================

import { kv } from '@vercel/kv';

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    try {
        const token = req.headers.authorization?.replace('Bearer ', '');

        if (token) {
            // Delete session
            await kv.del(`session:${token}`);
        }

        res.status(200).json({ success: true, message: 'Logged out successfully' });

    } catch (error) {
        console.error('Logout error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
}
