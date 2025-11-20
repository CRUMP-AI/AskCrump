// api/chat-state/save.js
// Saves the user's chats into profiles.chat_state

import { supabase } from '../utils/supabase.js';
import { verifyAuth } from '../middleware/auth.js';

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.writeHead(405, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Method not allowed' }));
    return;
  }

  // 🔐 Use verifyAuth directly (no middleware wrapper)
  const sessionUser = await verifyAuth(req);

  if (!sessionUser) {
    res.writeHead(401, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not authenticated' }));
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
      // 🔑 IMPORTANT: verifyAuth returns { id: ... }, not userId
      .eq('id', sessionUser.id);

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
