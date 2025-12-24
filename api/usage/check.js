const pool = require('../../db/pool');

module.exports = async (req, res) => {
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
        const result = await pool.query(
            `SELECT 
                usage_messages, 
                usage_images, 
                usage_searches,
                usage_month,
                subscription_tier
             FROM users 
             WHERE id = $1`,
            [userId]
        );

        if (result.rows.length === 0) {
            return res.status(404).json({
                success: false,
                error: 'User not found'
            });
        }

        const user = result.rows[0];
        const tier = user.subscription_tier || 'free';

        // Define tier limits
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
                messages: -1,
                images: -1,
                searches: -1
            }
        };

        const limits = tierLimits[tier] || tierLimits.free;

        // Reset if new month
        let usage = {
            messages: user.usage_messages || 0,
            images: user.usage_images || 0,
            searches: user.usage_searches || 0
        };

        if (user.usage_month !== currentMonth) {
            usage = { messages: 0, images: 0, searches: 0 };
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
};
