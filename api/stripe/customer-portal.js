// =====================================================
// STRIPE CUSTOMER PORTAL
// Location: /api/stripe/customer-portal.js
// =====================================================

import Stripe from 'stripe';
import { verifyAuth } from '../middleware/auth.js';
import { supabase } from '../utils/supabase.js';

const stripeSecretKey = process.env.STRIPE_SECRET_KEY;
const appBaseUrl = process.env.APP_BASE_URL || process.env.APP_URL || '';

const stripe = new Stripe(stripeSecretKey);

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        // ✅ Use unified auth
        const user = await verifyAuth(req);
        if (!user || !user.id) {
            return res.status(401).json({
                success: false,
                error: 'Authentication required'
            });
        }

        // Fetch latest Stripe customer ID from DB
        const { data: dbUser, error } = await supabase
            .from('users')
            .select('stripe_customer_id')
            .eq('id', user.id)
            .single();

        if (error || !dbUser || !dbUser.stripe_customer_id) {
            return res.status(400).json({
                success: false,
                error: 'No Stripe customer found for this account'
            });
        }

        const portalSession = await stripe.billingPortal.sessions.create({
            customer: dbUser.stripe_customer_id,
            return_url: `${appBaseUrl}?portal=returned`
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
