// =====================================================
// CHECK SESSION API ENDPOINT
// Location: /api/auth/check-session.js
// =====================================================

import { verifyAuth } from '../middleware/auth.js';

export default async function handler(req, res) {
    // Only allow GET requests
    if (req.method !== 'GET') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        const user = await verifyAuth(req);

        // Not authenticated – this is a normal state, not an error
        if (!user) {
            return res.status(200).json({
                success: true,
                authenticated: false,
                data: null
            });
        }

        // Shape the user payload consistently with login.js
        const userPayload = {
            id: user.id,
            email: user.email,
            fullName: user.full_name || null,
            isVerified: !!user.is_verified,
            preferences: user.preferences || null,
            createdAt: user.created_at
        };

        return res.status(200).json({
            success: true,
            authenticated: true,
            data: {
                user: userPayload
            }
        });

    } catch (error) {
        console.error('[check-session] Session check error:', error);
        return res.status(500).json({
            success: false,
            authenticated: false,
            error: 'Failed to verify session'
        });
    }
}
