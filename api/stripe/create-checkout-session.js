// =====================================================
// STRIPE CREATE CHECKOUT SESSION
// Location: /api/stripe/create-checkout-session.js
// =====================================================

import Stripe from 'stripe';
import { verifyToken } from '../utils/jwt.js';

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
                priceId: process.env.STRIPE_PROFESSIONAL_PRICE_ID,
                amount: 2999, // $29.99
                name: 'Professional Plan',
                description: 'Unlimited conversations, priority support, advanced features'
            },
            enterprise: {
                priceId: process.env.STRIPE_ENTERPRISE_PRICE_ID,
                amount: 9999, // $99.99
                name: 'Enterprise Plan',
                description: 'White-label, dedicated support, custom integrations, SLA'
            }
        };

        const selectedPrice = prices[tier];
        
        if (!selectedPrice || !selectedPrice.priceId) {
    console.error('❌ Missing Stripe price ID for tier:', tier);
    return res.status(500).json({
        success: false,
        error: 'Subscription pricing is not configured correctly'
    });
}


        // Create Stripe checkout session
        const session = await stripe.checkout.sessions.create({
            customer_email: userEmail,
            client_reference_id: userId,
            line_items: [
    {
        price: selectedPrice.priceId,
        quantity: 1,
    },
],
            mode: 'subscription',
            success_url: `${process.env.APP_URL}?upgrade=success&tier=${tier}`,
            cancel_url: `${process.env.APP_URL}?upgrade=cancelled`,
            metadata: {
                userId: userId,
                tier: tier
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
