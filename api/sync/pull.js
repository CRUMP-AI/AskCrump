import { supabase } from '../utils/supabase.js';
import { parse } from 'cookie';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ success: false, error: 'Method not allowed' });
  }

  try {
    const cookies = parse(req.headers.cookie || '');

    const sinceRaw = req.query?.since;
    const since = sinceRaw ? new Date(sinceRaw) : new Date(0);
    const sinceIso = isNaN(since.getTime()) ? new Date(0).toISOString() : since.toISOString();

    // Identify deviceId (same approach as your auth work)
    const deviceId =
      req.headers['x-device-id'] ||
      cookies.crump_device_id ||
      null;

    // Resolve user from active session (deviceId -> sessions -> user)
    // If you already have a centralized auth helper, swap this section to use it.
    if (!deviceId) {
      return res.status(401).json({ success: false, error: 'Missing deviceId' });
    }

    const { data: sess } = await supabase
      .from('sessions')
      .select('user_id, expires_at')
      .eq('device_id', deviceId)
      .gt('expires_at', new Date().toISOString())
      .single();

    if (!sess?.user_id) {
      return res.status(401).json({ success: false, error: 'Not authenticated' });
    }

    const userId = sess.user_id;

    // Heartbeat device (optional but useful)
    await supabase
      .from('devices')
      .upsert(
        { user_id: userId, device_id: deviceId, last_seen_at: new Date().toISOString() },
        { onConflict: 'user_id,device_id' }
      );

    // Pull changed chats since last sync
    const { data: chats } = await supabase
      .from('user_chats')
      .select('id, chat_id, title, messages, created_at, updated_at')
      .eq('user_id', userId)
      .gt('updated_at', sinceIso)
      .order('updated_at', { ascending: true });

    // Pull settings since last sync
    const { data: settings } = await supabase
      .from('user_settings')
      .select('*')
      .eq('user_id', userId)
      .gt('updated_at', sinceIso)
      .maybeSingle();

    return res.status(200).json({
      success: true,
      serverTime: new Date().toISOString(),
      data: {
        chats: chats || [],
        settings: settings || null
      }
    });
  } catch (err) {
    console.error('sync/pull error:', err);
    return res.status(500).json({ success: false, error: 'Internal server error' });
  }
}
