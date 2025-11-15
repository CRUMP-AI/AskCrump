// =====================================================
// STRIPE CUSTOMER PORTAL
// Location: /api/stripe/customer-portal.js
// =====================================================

import Stripe from 'stripe';
import { verifyToken } from '../utils/jwt.js';
import { supabase } from '../utils/supabase.js';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        // Verify user is authenticated
        const authHeader = req.headers.authorization;
        if (!authHeader || !authHeader.startsWith('Bearer ')) {
            return res.status(401).json({
                success: false,
                error: 'Unauthorized'
            });
        }

        const token = authHeader.substring(7);
        let userId;
        
        try {
            const decoded = verifyToken(token);
            userId = decoded.userId;
        } catch (error) {
            return res.status(401).json({
                success: false,
                error: 'Invalid token'
            });
        }

        // Get user's Stripe customer ID
        const { data: user, error: userError } = await supabase
            .from('users')
            .select('stripe_customer_id')
            .eq('id', userId)
            .single();

        if (userError || !user) {
            return res.status(404).json({
                success: false,
                error: 'User not found'
            });
        }

        if (!user.stripe_customer_id) {
            return res.status(400).json({
                success: false,
                error: 'No active subscription found'
            });
        }

        // Create portal session
        const portalSession = await stripe.billingPortal.sessions.create({
            customer: user.stripe_customer_id,
            return_url: `${process.env.APP_URL}?portal=returned`,
        });

        return res.status(200).json({
            success: true,
            url: portalSession.url
        });

    } catch (error) {
        console.error('Customer portal error:', error);
        return res.status(500).json({
            success: false,
            error: 'Failed to create portal session'
        });
    }
}
