// =====================================================
// STRIPE WEBHOOK HANDLER
// Location: /api/stripe/webhook.js
// =====================================================

import Stripe from 'stripe';
import { supabase } from '../utils/supabase.js';

const stripeSecretKey = process.env.STRIPE_SECRET_KEY;
const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
const professionalPriceId = process.env.STRIPE_PROFESSIONAL_PRICE_ID;
const enterprisePriceId = process.env.STRIPE_ENTERPRISE_PRICE_ID;

const stripe = new Stripe(stripeSecretKey);


// We need the raw body for Stripe signature verification
export const config = {
    api: {
        bodyParser: false,
    },
};

// Helper to collect the raw request body into a Buffer
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

    let event;

    try {
        const buf = await buffer(req);
        const signature = req.headers['stripe-signature'];

        if (!signature || !webhookSecret) {
            console.error('❌ Missing Stripe signature or webhook secret');
            return res.status(400).json({ error: 'Webhook configuration error' });
        }

        // Verify the event came from Stripe
        event = stripe.webhooks.constructEvent(buf, signature, webhookSecret);
    } catch (err) {
        console.error('❌ Stripe webhook signature verification failed:', err.message);
        return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    console.log(`📬 Stripe event received: ${event.id} (${event.type})`);

    try {
        switch (event.type) {
            // ==========================================
            // CHECKOUT COMPLETED → NEW SUBSCRIPTION
            // ==========================================
            case 'checkout.session.completed': {
                const session = event.data.object;

                // Only handle subscription checkouts
                if (session.mode !== 'subscription') {
                    console.log('ℹ️ Ignoring non-subscription checkout.session.completed');
                    break;
                }

               // Match the actual metadata from create-checkout-session.js
const userId = session.metadata?.user_id;
const tier = session.metadata?.selected_tier; // 'professional' | 'enterprise'
const customerId = session.customer;
const subscriptionId = session.subscription;


                if (!userId || !tier || !customerId || !subscriptionId) {
                    console.error('❌ Missing metadata or IDs on checkout.session.completed', {
                        userId,
                        tier,
                        customerId,
                        subscriptionId,
                    });
                    break;
                }

                const { error } = await supabase
                    .from('users')
                    .update({
                        subscription_tier: tier,
                        stripe_customer_id: customerId,
                        stripe_subscription_id: subscriptionId,
                        subscription_status: 'active',
                        subscription_start_date: new Date().toISOString(),
                        updated_at: new Date().toISOString(),
                    })
                    .eq('id', userId);

                if (error) {
                    console.error('❌ Failed to update user subscription after checkout:', error);
                } else {
                    console.log(`✅ User ${userId} upgraded to ${tier}`);
                }

                break;
            }

            // ==========================================
            // SUBSCRIPTION UPDATED (UPGRADE/DOWNGRADE/STATUS)
            // ==========================================
            case 'customer.subscription.updated': {
                const subscription = event.data.object;
                const customerId = subscription.customer;
                const subscriptionId = subscription.id;
                const stripeStatus = subscription.status; // trialing, active, past_due, canceled, unpaid, etc.

                // Try to infer tier from the price ID
                const priceId = subscription.items?.data?.[0]?.price?.id || null;
                let inferredTier = null;

                if (priceId && priceId === process.env.STRIPE_PROFESSIONAL_PRICE_ID) {
                    inferredTier = 'professional';
                } else if (priceId && priceId === process.env.STRIPE_ENTERPRISE_PRICE_ID) {
                    inferredTier = 'enterprise';
                }

                const { data: user, error: userError } = await supabase
                    .from('users')
                    .select('id')
                    .eq('stripe_customer_id', customerId)
                    .single();

                if (userError || !user) {
                    console.error(
                        '❌ User not found for customer.subscription.updated. Customer:',
                        customerId,
                        userError
                    );
                    break;
                }

                // Normalize Stripe status → our DB status
                let mappedStatus = 'active';
                if (stripeStatus === 'past_due' || stripeStatus === 'unpaid') {
                    mappedStatus = 'past_due';
                } else if (stripeStatus === 'canceled') {
                    mappedStatus = 'cancelled';
                } else if (stripeStatus === 'incomplete' || stripeStatus === 'incomplete_expired') {
                    mappedStatus = 'incomplete';
                }

                const updatePayload = {
                    stripe_subscription_id: subscriptionId,
                    subscription_status: mappedStatus,
                    updated_at: new Date().toISOString(),
                };

                if (inferredTier) {
                    updatePayload.subscription_tier = inferredTier;
                }

                const { error } = await supabase
                    .from('users')
                    .update(updatePayload)
                    .eq('id', user.id);

                if (error) {
                    console.error('❌ Failed to update user on customer.subscription.updated:', error);
                } else {
                    console.log(
                        `🔄 Subscription updated for user ${user.id} → ${mappedStatus}` +
                            (inferredTier ? ` (tier: ${inferredTier})` : '')
                    );
                }

                break;
            }

            // ==========================================
            // SUBSCRIPTION DELETED → DOWNGRADE TO FREE
            // ==========================================
            case 'customer.subscription.deleted': {
                const subscription = event.data.object;
                const customerId = subscription.customer;

                const { data: user, error: userError } = await supabase
                    .from('users')
                    .select('id')
                    .eq('stripe_customer_id', customerId)
                    .single();

                if (userError || !user) {
                    console.error(
                        '❌ User not found for customer.subscription.deleted. Customer:',
                        customerId,
                        userError
                    );
                    break;
                }

                const { error } = await supabase
                    .from('users')
                    .update({
                        subscription_tier: 'free',
                        subscription_status: 'cancelled',
                        stripe_subscription_id: null,
                        updated_at: new Date().toISOString(),
                    })
                    .eq('id', user.id);

                if (error) {
                    console.error('❌ Failed to downgrade user on subscription deleted:', error);
                } else {
                    console.log(
                        `❌ User ${user.id} subscription cancelled and downgraded to free tier.`
                    );
                }

                break;
            }

            // ==========================================
            // PAYMENT FAILED → MARK AS PAST_DUE
            // ==========================================
            case 'invoice.payment_failed': {
                const invoice = event.data.object;
                const customerId = invoice.customer;

                const { data: user, error: userError } = await supabase
                    .from('users')
                    .select('id, email')
                    .eq('stripe_customer_id', customerId)
                    .single();

                if (userError || !user) {
                    console.error(
                        '❌ User not found for invoice.payment_failed. Customer:',
                        customerId,
                        userError
                    );
                    break;
                }

                const { error } = await supabase
                    .from('users')
                    .update({
                        subscription_status: 'past_due',
                        updated_at: new Date().toISOString(),
                    })
                    .eq('id', user.id);

                if (error) {
                    console.error('❌ Failed to update user on invoice.payment_failed:', error);
                } else {
                    console.log(`⚠️ Marked user ${user.id} as past_due (payment failed).`);
                }

                // Hook for future: send "payment failed" email here
                break;
            }

            // ==========================================
            // PAYMENT SUCCEEDED → KEEP / SET ACTIVE
            // ==========================================
            case 'invoice.paid': {
                const invoice = event.data.object;
                const customerId = invoice.customer;

                const { data: user, error: userError } = await supabase
                    .from('users')
                    .select('id')
                    .eq('stripe_customer_id', customerId)
                    .single();

                if (userError || !user) {
                    console.error('❌ User not found for invoice.paid. Customer:', customerId, userError);
                    break;
                }

                const { error } = await supabase
                    .from('users')
                    .update({
                        subscription_status: 'active',
                        updated_at: new Date().toISOString(),
                    })
                    .eq('id', user.id);

                if (error) {
                    console.error('❌ Failed to update user on invoice.paid:', error);
                } else {
                    console.log(`💸 Payment succeeded for user ${user.id} (invoice.paid).`);
                }

                break;
            }

            // ==========================================
            // ANYTHING ELSE → JUST LOG IT
            // ==========================================
            default: {
                console.log(`ℹ️ Unhandled Stripe event type: ${event.type}`);
            }
        }

        // Stripe requires a 2xx to mark the webhook as delivered
        return res.status(200).json({ received: true });
    } catch (error) {
        console.error('❌ Webhook handler error:', error);
        return res.status(500).json({ error: 'Webhook handler failed' });
    }
}
