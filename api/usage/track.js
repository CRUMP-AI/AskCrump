// =====================================================
// SERVER-SIDE USAGE TRACKING (Supabase)
// Location: /api/usage/track.js
// =====================================================

import { supabase } from '../utils/supabase.js';

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        const { userId, type } = req.body;
        
        if (!userId || !type) {
            return res.status(400).json({
                success: false,
                error: 'Missing userId or type'
            });
        }

        // Get current month
        const now = new Date();
        const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

        // Get user's current usage
        const { data: user, error: userError } = await supabase
            .from('users')
            .select('usage_messages, usage_images, usage_searches, usage_weather, usage_news, usage_sports, usage_stocks, usage_movies, usage_month, subscription_tier')
            .eq('id', userId)
            .single();

        if (userError || !user) {
            console.error('[Usage Track] User not found:', userError);
            return res.status(404).json({
                success: false,
                error: 'User not found'
            });
        }

        const tier = user.subscription_tier || 'free';

        // Define tier limits (matches profile-manager.js)
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

        // Reset usage if new month
        if (user.usage_month !== currentMonth) {
            const { error: resetError } = await supabase
                .from('users')
                .update({
                    usage_messages: 0,
                    usage_images: 0,
                    usage_searches: 0,
                    usage_weather: 0,
                    usage_news: 0,
                    usage_sports: 0,
                    usage_stocks: 0,
                    usage_movies: 0,
                    usage_month: currentMonth,
                    usage_reset_at: new Date().toISOString()
                })
                .eq('id', userId);

            if (resetError) {
                console.error('[Usage Track] Reset error:', resetError);
            }

            user.usage_messages = 0;
            user.usage_images = 0;
            user.usage_searches = 0;
            user.usage_weather = 0;
            user.usage_news = 0;
            user.usage_sports = 0;
            user.usage_stocks = 0;
            user.usage_movies = 0;
        }

        // Check limits
        const limits = tierLimits[tier] || tierLimits.free;
        const columnMap = {
            messages: 'usage_messages',
            images: 'usage_images',
            searches: 'usage_searches',
            weather: 'usage_weather',
            news: 'usage_news',
            sports: 'usage_sports',
            stocks: 'usage_stocks',
            movies: 'usage_movies'
        };

        const column = columnMap[type];
        if (!column) {
            return res.status(400).json({
                success: false,
                error: 'Invalid usage type'
            });
        }

        const currentUsage = user[column] || 0;
        const limit = limits[type];

        // Check if over limit (unless unlimited)
        if (limit !== -1 && currentUsage >= limit) {
            return res.status(403).json({
                success: false,
                error: 'Usage limit reached',
                usage: {
                    used: currentUsage,
                    limit: limit,
                    type: type
                }
            });
        }

        // Increment usage
        const { error: updateError } = await supabase
            .from('users')
            .update({ [column]: currentUsage + 1 })
            .eq('id', userId);

        if (updateError) {
            console.error('[Usage Track] Update error:', updateError);
            return res.status(500).json({
                success: false,
                error: 'Failed to update usage'
            });
        }

        console.log(`[Usage Track] ${type} tracked for user ${userId}: ${currentUsage + 1}/${limit === -1 ? 'unlimited' : limit}`);

        return res.json({
            success: true,
            usage: {
                used: currentUsage + 1,
                limit: limit,
                type: type
            }
        });

    } catch (error) {
        console.error('[Usage Tracking Error]', error);
        return res.status(500).json({
            success: false,
            error: 'Server error'
        });
    }
}
