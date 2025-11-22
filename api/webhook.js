// =====================================================
// STRIPE WEBHOOK HANDLER
// Location: /api/stripe/webhook.js
// =====================================================

import Stripe from 'stripe';
import { supabase } from '../utils/supabase.js';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);
const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

export const config = {
    api: {
        bodyParser: false,
    },
};

async function buffer(readable) {
    const chunks = [];
    for await (const chunk of readable) {
        chunks.push(typeof chunk === 'string' ? Buffer.from(chunk) : chunk);
    }
    return Buffer.concat(chunks);
}

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    const buf = await buffer(req);
    const sig = req.headers['stripe-signature'];

    let event;

    try {
        event = stripe.webhooks.constructEvent(buf, sig, webhookSecret);
    } catch (err) {
        console.error('Webhook signature verification failed:', err.message);
        return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    // Handle the event
    try {
        switch (event.type) {
            case 'checkout.session.completed': {
                const session = event.data.object;
                
                // Update user subscription in database
                const userId = session.metadata.userId;
                const tier = session.metadata.tier;
                const customerId = session.customer;
                const subscriptionId = session.subscription;

                const { error } = await supabase
                    .from('users')
                    .update({
                        subscription_tier: tier,
                        stripe_customer_id: customerId,
                        stripe_subscription_id: subscriptionId,
                        subscription_status: 'active',
                        subscription_start_date: new Date().toISOString(),
                        updated_at: new Date().toISOString()
                    })
                    .eq('id', userId);

                if (error) {
                    console.error('Failed to update user subscription:', error);
                } else {
                    console.log(`✅ User ${userId} upgraded to ${tier}`);
                }
                break;
            }

            case 'customer.subscription.updated': {
                const subscription = event.data.object;
                const customerId = subscription.customer;
                
                // Get user by stripe customer ID
                const { data: user, error: userError } = await supabase
                    .from('users')
                    .select('id')
                    .eq('stripe_customer_id', customerId)
                    .single();

                if (userError || !user) {
                    console.error('User not found for customer:', customerId);
                    break;
                }

                // Update subscription status
                const { error } = await supabase
                    .from('users')
                    .update({
                        subscription_status: subscription.status,
                        updated_at: new Date().toISOString()
                    })
                    .eq('id', user.id);

                if (error) {
                    console.error('Failed to update subscription status:', error);
                }
                break;
            }

            case 'customer.subscription.deleted': {
                const subscription = event.data.object;
                const customerId = subscription.customer;
                
                // Get user by stripe customer ID
                const { data: user, error: userError } = await supabase
                    .from('users')
                    .select('id')
                    .eq('stripe_customer_id', customerId)
                    .single();

                if (userError || !user) {
                    console.error('User not found for customer:', customerId);
                    break;
                }

                // Downgrade user to free tier
                const { error } = await supabase
                    .from('users')
                    .update({
                        subscription_tier: 'free',
                        subscription_status: 'cancelled',
                        stripe_subscription_id: null,
                        updated_at: new Date().toISOString()
                    })
                    .eq('id', user.id);

                if (error) {
                    console.error('Failed to cancel subscription:', error);
                } else {
                    console.log(`❌ User ${user.id} subscription cancelled`);
                }
                break;
            }

            case 'invoice.payment_failed': {
                const invoice = event.data.object;
                const customerId = invoice.customer;
                
                // Get user by stripe customer ID
                const { data: user, error: userError } = await supabase
                    .from('users')
                    .select('id, email')
                    .eq('stripe_customer_id', customerId)
                    .single();

                if (userError || !user) {
                    console.error('User not found for customer:', customerId);
                    break;
                }

                // Update subscription status to past_due
                const { error } = await supabase
                    .from('users')
                    .update({
                        subscription_status: 'past_due',
                        updated_at: new Date().toISOString()
                    })
                    .eq('id', user.id);

                if (error) {
                    console.error('Failed to update payment failed status:', error);
                }
                
                // TODO: Send payment failed email to user
                console.log(`⚠️ Payment failed for user ${user.email}`);
                break;
            }

            default:
                console.log(`Unhandled event type: ${event.type}`);
        }

        res.status(200).json({ received: true });
    } catch (error) {
        console.error('Webhook handler error:', error);
        res.status(500).json({ error: 'Webhook handler failed' });
    }
}
