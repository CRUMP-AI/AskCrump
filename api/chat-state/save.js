// api/chat-state/save.js
// Saves the user's chats into profiles.chat_state

import { supabase } from '../utils/supabase.js';
import { requireAuth } from '../middleware/auth.js';

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.writeHead(405, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Method not allowed' }));
    return;
  }

  const sessionUser = await requireAuth(req, res);
    // If user is not authenticated, treat chat-state save as a safe no-op.
  // We still protect real data (no write without auth), but we avoid 401
  // so the browser doesn't scream in the console.
  if (!sessionUser || !sessionUser.userId) {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      success: false,
      error: 'Authentication required',
      skipped: true
    }));
    return;
  }


  let body = '';
  for await (const chunk of req) {
    body += chunk;
  }

  let payload;
  try {
    payload = JSON.parse(body || '{}');
  } catch (err) {
    console.warn('⚠️ Invalid JSON in chat-state/save:', err);
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Invalid JSON body' }));
    return;
  }

  const { chats, selectedChatId } = payload || {};

  if (!Array.isArray(chats)) {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Invalid chats payload' }));
    return;
  }

  const chatState = {
    chats,
    selectedChatId: selectedChatId || null,
    updatedAt: new Date().toISOString(),
  };

  try {
    const { error } = await supabase
      .from('profiles')
      .update({ chat_state: chatState })
      .eq('id', sessionUser.userId);

    if (error) {
      console.error('❌ Failed to save chat_state:', error);
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Failed to save chats' }));
      return;
    }

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true }));
  } catch (err) {
    console.error('❌ Unexpected error saving chat_state:', err);
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Unexpected server error' }));
  }
}
