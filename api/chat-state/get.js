// api/chat-state/get.js
// Returns the saved chats for the authenticated user

import { supabase } from '../utils/supabase.js';
import { requireAuth } from '../middleware/auth.js';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.writeHead(405, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Method not allowed' }));
    return;
  }

  const sessionUser = await requireAuth(req, res);
  if (!sessionUser) {
    // requireAuth already sent 401
    return;
  }

  try {
    const { data, error } = await supabase
      .from('profiles')
      .select('chat_state')
      .eq('id', sessionUser.userId)
      .single();

    if (error && error.code !== 'PGRST116') {
      console.error('❌ Failed to load chat_state from profiles:', error);
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Failed to load chats' }));
      return;
    }

    const chatState = data?.chat_state || null;

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(
      JSON.stringify({
        ok: true,
        chatState, // { chats: [...], selectedChatId: string | null } or null
      })
    );
  } catch (err) {
    console.error('❌ Unexpected error loading chat_state:', err);
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Unexpected server error' }));
  }
}
