// =====================================================
// STRIPE CREATE CHECKOUT SESSION
// Location: /api/stripe/create-checkout-session.js
// =====================================================

import Stripe from 'stripe';
import { supabase } from '../utils/supabase.js';

const stripeSecretKey = process.env.STRIPE_SECRET_KEY;
const professionalPriceId = process.env.STRIPE_PROFESSIONAL_PRICE_ID;
const enterprisePriceId = process.env.STRIPE_ENTERPRISE_PRICE_ID;

// Fallback: allow either APP_BASE_URL or APP_URL
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
        const { tier, deviceId } = req.body || {};
        
        if (!deviceId) {
            return res.status(400).json({
                success: false,
                error: 'Device ID required'
            });
        }

       // ✅ Look up session by deviceId
const { data: userSession, error: sessionError } = await supabase
            .from('sessions')
            .select('user_id')
            .eq('device_id', deviceId)
            .gt('expires_at', new Date().toISOString())
            .single();

        if (sessionError || !userSession) {
    return res.status(401).json({
        success: false,
        error: 'Authentication required - please log in'
    });
}

        // ✅ Load user data
        const { data: user, error: userError } = await supabase
            .from('users')
            .select(`
                id,
                email,
                full_name,
                stripe_customer_id
            `)
            .eq('id', userSession.user_id)
            .single();

        if (userError || !user) {
            return res.status(401).json({
                success: false,
                error: 'User not found'
            });
        }

        const normalizedTier = (tier || '').toLowerCase();

        let priceId = null;
        if (normalizedTier === 'professional' || normalizedTier === 'pro') {
            priceId = professionalPriceId;
        } else if (normalizedTier === 'enterprise' || normalizedTier === 'premium') {
            priceId = enterprisePriceId;
        }

        if (!priceId) {
            return res.status(400).json({
                success: false,
                error: 'Invalid tier selected'
            });
        }

        // Make sure we have a Stripe customer ID for this user
        let stripeCustomerId = user.stripe_customer_id;

        if (!stripeCustomerId) {
            const customer = await stripe.customers.create({
                email: user.email,
                metadata: {
                    user_id: user.id
                }
            });

            stripeCustomerId = customer.id;

            // Persist customer ID
            const { error: updateError } = await supabase
                .from('users')
                .update({ stripe_customer_id: stripeCustomerId })
                .eq('id', user.id);

            if (updateError) {
                console.error('❌ Failed to store stripe_customer_id:', updateError);
            }
        }

        const session = await stripe.checkout.sessions.create({
            mode: 'subscription',
            payment_method_types: ['card'],
            customer: stripeCustomerId,
            line_items: [
                {
                    price: priceId,
                    quantity: 1
                }
            ],
            allow_promotion_codes: true,
            success_url: `${appBaseUrl}/?checkout=success`,
            cancel_url: `${appBaseUrl}/?checkout=cancelled`,
            metadata: {
                user_id: user.id,
                selected_tier: normalizedTier
            }
        });

        return res.status(200).json({
            success: true,
            sessionId: session.id,
            url: session.url
        });
    } catch (error) {
        console.error('Stripe checkout error:', error);
        return res.status(500).json({
            success: false,
            error: 'Failed to create checkout session'
        });
    }
}
