// =====================================================
// STRIPE CREATE CHECKOUT SESSION
// Location: /api/stripe/create-checkout-session.js
// =====================================================

import Stripe from 'stripe';
import { verifyToken } from '../utils/jwt.js';

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
        if (!stripeSecretKey) {
            console.error('❌ STRIPE_SECRET_KEY is not set');
            return res.status(500).json({
                success: false,
                error: 'Stripe is not configured'
            });
        }

        if (!appBaseUrl) {
            console.error('❌ APP_BASE_URL or APP_URL is not set');
            return res.status(500).json({
                success: false,
                error: 'App URL is not configured'
            });
        }

        // Verify user is authenticated
        const authHeader = req.headers.authorization || req.headers.Authorization;
        if (!authHeader || !authHeader.startsWith('Bearer ')) {
            return res.status(401).json({
                success: false,
                error: 'Unauthorized'
            });
        }

        const token = authHeader.substring(7);
        let userId, userEmail;

        try {
            const decoded = verifyToken(token);
            userId = decoded.userId;
            userEmail = decoded.email;
        } catch (error) {
            return res.status(401).json({
                success: false,
                error: 'Invalid token'
            });
        }

        // Get tier from request body
        const { tier } = req.body;

        if (!tier || !['professional', 'enterprise'].includes(tier)) {
            return res.status(400).json({
                success: false,
                error: 'Invalid subscription tier'
            });
        }

        // Define pricing
        const prices = {
            professional: {
                priceId: professionalPriceId,
                amount: 2999,
                name: 'Professional Plan',
                description:
                    'Unlimited conversations, priority support, advanced features'
            },
            enterprise: {
                priceId: enterprisePriceId,
                amount: 9999,
                name: 'Enterprise Plan',
                description:
                    'White-label, dedicated support, custom integrations, SLA'
            }
        };

        const selectedPrice = prices[tier];

        if (!selectedPrice || !selectedPrice.priceId) {
            console.error('❌ Missing Stripe price ID for tier:', tier, {
                professionalPriceId,
                enterprisePriceId
            });
            return res.status(500).json({
                success: false,
                error: 'Subscription pricing is not configured correctly'
            });
        }

        // ===============================
        // ✅ Create Stripe checkout session WITH free trial
        // ===============================
        const session = await stripe.checkout.sessions.create({
            customer_email: userEmail,
            client_reference_id: userId,
            line_items: [
                {
                    price: selectedPrice.priceId,
                    quantity: 1
                }
            ],
            mode: 'subscription',

            // Success & cancel URLs
            success_url: `${appBaseUrl}?upgrade=success&tier=${tier}`,
            cancel_url: `${appBaseUrl}?upgrade=cancelled`,

            metadata: {
                userId: userId,
                tier: tier
            },

            subscription_data: {
                trial_period_days: 7
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
