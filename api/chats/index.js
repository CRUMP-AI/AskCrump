// /api/chats/index.js
import { supabase } from '../utils/supabase.js';
import { verifyAuth } from '../middleware/auth.js';

/**
 * GET /api/chats
 * Return all chats for the current user.
 */
export async function getChats(req, res) {
  try {
    const user = await verifyAuth(req);
    if (!user) {
      return res.status(401).json({ success: false, error: 'Not authenticated' });
    }

    const { data, error } = await supabase
      .from('crump_chats')
      .select('*')
      .eq('user_id', user.id)
      .order('updated_at', { ascending: false });

    if (error) throw error;

    // Each row.data is your stored chat object
    const chats = (data || []).map(row => row.data);

    return res.json({ success: true, data: { chats } });
  } catch (err) {
    console.error('[getChats] error', err);
    return res.status(500).json({ success: false, error: 'Failed to load chats' });
  }
}

/**
 * POST /api/chats
 * Upsert a chat.
 * body: { chat: { id, title, messages, ... } }
 */
export async function saveChat(req, res) {
  try {
    const user = await verifyAuth(req);
    if (!user) {
      return res.status(401).json({ success: false, error: 'Not authenticated' });
    }

    const { chat } = req.body || {};
    if (!chat || !chat.id) {
      return res.status(400).json({ success: false, error: 'Chat with id is required' });
    }

    const now = new Date().toISOString();
    const payload = {
      user_id: user.id,
      title: chat.title || 'Conversation',
      data: { ...chat, updatedAt: chat.updatedAt || now },
      updated_at: now
    };

    const { error } = await supabase
      .from('crump_chats')
      .upsert(payload, { onConflict: 'user_id,title' });

    if (error) throw error;

    return res.json({ success: true });
  } catch (err) {
    console.error('[saveChat] error', err);
    return res.status(500).json({ success: false, error: 'Failed to save chat' });
  }
}

/**
 * DELETE /api/chats
 * Clear all chats for current user
 */
export async function deleteAllChats(req, res) {
  try {
    const user = await verifyAuth(req);
    if (!user) {
      return res.status(401).json({ success: false, error: 'Not authenticated' });
    }

    const { error } = await supabase
      .from('crump_chats')
      .delete()
      .eq('user_id', user.id);

    if (error) throw error;

    return res.json({ success: true });
  } catch (err) {
    console.error('[deleteAllChats] error', err);
    return res.status(500).json({ success: false, error: 'Failed to clear chats' });
  }
}
