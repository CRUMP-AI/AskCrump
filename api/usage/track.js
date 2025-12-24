const pool = require('../../db/pool');

module.exports = async (req, res) => {
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
        const userResult = await pool.query(
            'SELECT usage_messages, usage_images, usage_searches, usage_month, subscription_tier FROM users WHERE id = $1',
            [userId]
        );

        if (userResult.rows.length === 0) {
            return res.status(404).json({
                success: false,
                error: 'User not found'
            });
        }

        const user = userResult.rows[0];
        const tier = user.subscription_tier || 'free';

        // Define tier limits (matches profile-manager.js)
        const tierLimits = {
            free: {
                messages: 10,
                images: 3,
                searches: 5
            },
            professional: {
                messages: 1000,
                images: 100,
                searches: 200
            },
            enterprise: {
                messages: -1,  // unlimited
                images: -1,
                searches: -1
            }
        };

        // Reset usage if new month
        if (user.usage_month !== currentMonth) {
            await pool.query(
                `UPDATE users 
                 SET usage_messages = 0, 
                     usage_images = 0, 
                     usage_searches = 0,
                     usage_month = $1,
                     usage_reset_at = NOW()
                 WHERE id = $2`,
                [currentMonth, userId]
            );
            user.usage_messages = 0;
            user.usage_images = 0;
            user.usage_searches = 0;
        }

        // Check limits
        const limits = tierLimits[tier] || tierLimits.free;
        const columnMap = {
            messages: 'usage_messages',
            images: 'usage_images',
            searches: 'usage_searches'
        };

        const column = columnMap[type];
        if (!column) {
            return res.status(400).json({
                success: false,
                error: 'Invalid usage type'
            });
        }

        const currentUsage = user[column];
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
        await pool.query(
            `UPDATE users SET ${column} = ${column} + 1 WHERE id = $1`,
            [userId]
        );

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
};
