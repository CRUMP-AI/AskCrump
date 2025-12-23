import { supabase } from '../utils/supabase.js';
import { parse } from 'cookie';

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ success: false, error: 'Method not allowed' });
  }

  try {
    const cookies = parse(req.headers.cookie || '');
    const { chats = [], settings = null } = req.body || {};

    const deviceId =
      req.headers['x-device-id'] ||
      cookies.crump_device_id ||
      null;

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

    // Heartbeat device (optional)
    await supabase
      .from('devices')
      .upsert(
        { user_id: userId, device_id: deviceId, last_seen_at: new Date().toISOString() },
        { onConflict: 'user_id,device_id' }
      );

    // Upsert chats
    // Each chat should include: chat_id, title, messages, updated_at
    const upserts = [];
    for (const c of chats) {
      if (!c) continue;

      const chat_id = c.chat_id || c.id || null;
      if (!chat_id) continue;

      upserts.push({
        user_id: userId,
        chat_id,
        title: c.title ?? null,
        messages: c.messages ?? [],
        updated_at: c.updated_at ? new Date(c.updated_at).toISOString() : new Date().toISOString()
      });
    }

    if (upserts.length) {
      // NOTE: this relies on the unique constraint (user_id, chat_id)
      const { error: upsertErr } = await supabase
        .from('user_chats')
        .upsert(upserts, { onConflict: 'user_id,chat_id' });

      if (upsertErr) {
        console.error('user_chats upsert error:', upsertErr);
        return res.status(500).json({ success: false, error: 'Failed to sync chats' });
      }
    }

    // Upsert settings (if provided)
    if (settings && typeof settings === 'object') {
      const payload = {
        user_id: userId,
        ...settings,
        updated_at: new Date().toISOString()
      };

      const { error: settingsErr } = await supabase
        .from('user_settings')
        .upsert(payload, { onConflict: 'user_id' });

      if (settingsErr) {
        console.error('user_settings upsert error:', settingsErr);
        return res.status(500).json({ success: false, error: 'Failed to sync settings' });
      }
    }

    return res.status(200).json({
      success: true,
      serverTime: new Date().toISOString()
    });
  } catch (err) {
    console.error('sync/push error:', err);
    return res.status(500).json({ success: false, error: 'Internal server error' });
  }
}
