import { supabase } from '../utils/supabase.js';
import { signAccessToken } from '../utils/jwt.js';

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        const { deviceId } = req.body || {};

        if (!deviceId) {
            return res.status(200).json({
                success: true,
                authenticated: false
            });
        }

        const { data: sessions } = await supabase
            .from('sessions')
            .select('*')
            .eq('device_id', deviceId)
            .gte('expires_at', new Date().toISOString())
            .order('last_activity', { ascending: false })
            .limit(1);

        if (!sessions || sessions.length === 0) {
            return res.status(200).json({
                success: true,
                authenticated: false
            });
        }

        const session = sessions[0];
        const { data: user } = await supabase
            .from('users')
            .select('id, email, created_at, tier, subscription_tier, full_name, profile_picture, is_verified, preferences')
            .eq('id', session.user_id)
            .single();

        if (!user) {
            return res.status(200).json({
                success: true,
                authenticated: false
            });
        }

        await supabase
            .from('sessions')
            .update({ last_activity: new Date().toISOString() })
            .eq('device_id', deviceId)
            .eq('user_id', user.id);

        const accessToken = signAccessToken(user);

        let inTrial = false;
        let trialEndsAt = null;
        if (user.created_at) {
            const createdDate = new Date(user.created_at);
            const end = new Date(createdDate.getTime() + 7 * 24 * 60 * 60 * 1000);
            trialEndsAt = end.toISOString();
            if (new Date() < end) inTrial = true;
        }

        return res.status(200).json({
            success: true,
            authenticated: true,
            data: {
                user,
                inTrial,
                trialEndsAt,
                token: accessToken
            }
        });

    } catch (err) {
        console.error('check-session error:', err);
        return res.status(500).json({
            success: false,
            authenticated: false,
            error: 'Internal server error'
        });
    }
}
