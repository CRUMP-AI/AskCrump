import { supabase } from '../utils/supabase.js';

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
            return res.status(400).json({
                success: false,
                error: 'Device ID required'
            });
        }

        await supabase
            .from('sessions')
            .delete()
            .eq('device_id', deviceId);

        return res.status(200).json({
            success: true,
            message: 'Logged out successfully'
        });

    } catch (err) {
        console.error('Logout error:', err);
        return res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
}
