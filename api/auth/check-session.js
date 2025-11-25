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

        // 7-DAY GLOBAL TRIAL (based on account creation)
        let inTrial = false;
        let trialEndsAt = null;

        if (user.created_at) {
            const createdDate = new Date(user.created_at);
            if (!Number.isNaN(createdDate.getTime())) {
                const end = new Date(createdDate.getTime() + 7 * 24 * 60 * 60 * 1000);
                trialEndsAt = end;
                const now = new Date();
                if (now < end) {
                    inTrial = true;
                }
            }
        }

        const subscriptionTier = user.subscription_tier || 'free';
        const subscriptionStatus = user.subscription_status || 'free';

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
                    createdAt: user.created_at,
                    // NEW: billing info for the front-end
                    subscriptionTier,
                    subscriptionStatus,
                    stripeCustomerId: user.stripe_customer_id || null,
                    stripeSubscriptionId: user.stripe_subscription_id || null,
                    trial: {
                        inTrial,
                        trialEndsAt: trialEndsAt ? trialEndsAt.toISOString() : null
                    }
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
