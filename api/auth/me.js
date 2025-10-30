// ==========================================
// CRUMP AI - GET USER INFO API
// Returns current user data if authenticated
// ==========================================

import { kv } from '@vercel/kv';

export default async function handler(req, res) {
    if (req.method !== 'GET') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    try {
        const token = req.headers.authorization?.replace('Bearer ', '');

        if (!token) {
            return res.status(401).json({ error: 'Not authenticated' });
        }

        // Get session
        const session = await kv.get(`session:${token}`);

        if (!session) {
            return res.status(401).json({ error: 'Session expired' });
        }

        res.status(200).json({
            userId: session.userId,
            email: session.email,
            name: session.name
        });

    } catch (error) {
        console.error('Get user error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
}
