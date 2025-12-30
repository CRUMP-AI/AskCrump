// =====================================================
// SERVER-SIDE USAGE CHECK (Supabase)
// Location: /api/usage/check.js
// =====================================================

import { supabase } from '../utils/supabase.js';

export default async function handler(req, res) {
    if (req.method !== 'GET') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        const { userId } = req.query;
        
        if (!userId) {
            return res.status(400).json({
                success: false,
                error: 'Missing userId'
            });
        }

        // Get current month
        const now = new Date();
        const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

        // Get user's usage
        const { data: user, error: userError } = await supabase
            .from('users')
            .select(`
                usage_messages,
                usage_images,
                usage_searches,
                usage_weather,
                usage_news,
                usage_sports,
                usage_stocks,
                usage_movies,
                usage_month,
                subscription_tier
            `)
            .eq('id', userId)
            .single();

        if (userError || !user) {
            console.error('[Usage Check] User not found:', userError);
            return res.status(404).json({
                success: false,
                error: 'User not found'
            });
        }

        const tier = user.subscription_tier || 'free';

        // Define tier limits
        const tierLimits = {
            free: {
                messages: 10,
                images: 3,
                searches: 5,
                weather: 5,
                news: 5,
                sports: 5,
                stocks: 3,
                movies: 3
            },
            professional: {
                messages: 1000,
                images: 100,
                searches: 200,
                weather: 200,
                news: 200,
                sports: 200,
                stocks: 100,
                movies: 100
            },
            enterprise: {
                messages: -1,
                images: -1,
                searches: -1,
                weather: -1,
                news: -1,
                sports: -1,
                stocks: -1,
                movies: -1
            }
        };

        const limits = tierLimits[tier] || tierLimits.free;

        // Reset if new month
        let usage = {
            messages: user.usage_messages || 0,
            images: user.usage_images || 0,
            searches: user.usage_searches || 0,
            weather: user.usage_weather || 0,
            news: user.usage_news || 0,
            sports: user.usage_sports || 0,
            stocks: user.usage_stocks || 0,
            movies: user.usage_movies || 0
        };

        if (user.usage_month !== currentMonth) {
            usage = {
                messages: 0,
                images: 0,
                searches: 0,
                weather: 0,
                news: 0,
                sports: 0,
                stocks: 0,
                movies: 0
            };
        }

        return res.json({
            success: true,
            tier: tier,
            usage: usage,
            limits: limits,
            month: currentMonth
        });

    } catch (error) {
        console.error('[Usage Check Error]', error);
        return res.status(500).json({
            success: false,
            error: 'Server error'
        });
    }
}
