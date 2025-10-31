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

        if (!user) {
            return res.status(401).json({
                success: false,
                authenticated: false,
                error: 'Not authenticated'
            });
        }

        return res.status(200).json({
            success: true,
            authenticated: true,
            data: {
                user: {
                    id: user.id,
                    email: user.email,
                    fullName: user.full_name,
                    profilePicture: user.profile_picture,
                    isVerified: user.is_verified,
                    preferences: user.preferences,
                    createdAt: user.created_at
                }
            }
        });

    } catch (error) {
        console.error('Session check error:', error);
        return res.status(500).json({
            success: false,
            authenticated: false,
            error: 'Failed to verify session'
        });
    }
}
