import { supabase } from '../utils/supabase.js';
import { signAccessToken } from '../utils/jwt.js';
import { parse } from 'cookie';

export default async function handler(req, res) {
    // Allow GET and POST (GET can restore via cookie/header deviceId)
    if (req.method !== 'POST' && req.method !== 'GET') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        const cookies = parse(req.headers.cookie || '');

        const bodyDeviceId = req.body?.deviceId;
        const headerDeviceId = req.headers['x-device-id'];
        const cookieDeviceId = cookies.crump_device_id;

        const deviceId = bodyDeviceId || headerDeviceId || cookieDeviceId;

        if (!deviceId) {
            return res.status(200).json({
                success: true,
                authenticated: false
            });
        }

        // Find active session by deviceId
        const { data: session, error: sessionError } = await supabase
            .from('sessions')
            .select('id, user_id, device_id, expires_at')
            .eq('device_id', deviceId)
            .gt('expires_at', new Date().toISOString())
            .single();

        if (sessionError || !session) {
            return res.status(200).json({
                success: true,
                authenticated: false
            });
        }

        // Pull user
        const { data: user, error: userError } = await supabase
            .from('users')
            .select('*')
            .eq('id', session.user_id)
            .single();

        if (userError || !user) {
            return res.status(200).json({
                success: true,
                authenticated: false
            });
        }

        // Update last activity
        await supabase
            .from('sessions')
            .update({ last_activity: new Date().toISOString() })
            .eq('device_id', deviceId)
            .eq('user_id', user.id);

        const accessToken = signAccessToken(user);

        // Optional: keep response shape your frontend expects
        return res.status(200).json({
            success: true,
            authenticated: true,
            data: {
                user,
                token: accessToken,
                accessToken,
                expiresAt: session.expires_at
            }
        });
    } catch (error) {
        console.error('Check-session error:', error);
        return res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
}
