// ================================================
// CRUMP AI - CHAT SYNC API
// Location: /api/chats/index.js
// Purpose: Keep chats in Supabase so they follow
//          the user across devices & browsers
// ================================================
import { supabase } from '../utils/supabase.js';
import { verifyAuth } from '../middleware/auth.js';

/*
  REQUIRED SUPABASE TABLE (create this first):
  
  Table name: crump_chats
  
  Columns:
    id         : uuid       (primary key, default uuid_generate_v4())
    user_id    : uuid       (references public.users.id)
    chat_id    : text       (the ID used in the frontend, e.g. "chat_1732409...")
    title      : text
    messages   : jsonb
    created_at : timestamptz (default now())
    updated_at : timestamptz (default now())
    
  Example SQL:
  
  create table public.crump_chats (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references public.users (id) on delete cascade,
    chat_id text not null,
    title text,
    messages jsonb default '[]'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
  );
  
  create index crump_chats_user_id_idx on public.crump_chats(user_id);
  create unique index crump_chats_user_chat_id_idx on public.crump_chats(user_id, chat_id);
*/

export default async function handler(req, res) {

// CORS headers for Safari/iOS
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  
  // Dynamic origin handling for Vercel previews
  const allowedOrigins = [
    'https://clevercrump.com',
    'https://www.clevercrump.com'
  ];
  
  const requestOrigin = req.headers.origin;
  
  // Allow Vercel preview URLs
  if (requestOrigin && (
    allowedOrigins.includes(requestOrigin) || 
    requestOrigin.includes('vercel.app')
  )) {
    res.setHeader('Access-Control-Allow-Origin', requestOrigin);
  } else {
    res.setHeader('Access-Control-Allow-Origin', 'https://clevercrump.com');
  }
  
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  
  // Require authentication for everything
  const user = await verifyAuth(req);
  if (!user || !user.id) {
    return res.status(401).json({
      success: false,
      error: 'Not authenticated',
    });
  }

  try {
    switch (req.method) {
      case 'GET':
        return await handleGetChats(req, res, user);
      case 'POST':
        return await handleSyncChats(req, res, user);
      default:
        res.setHeader('Allow', ['GET', 'POST']);
        return res.status(405).json({
          success: false,
          error: `Method ${req.method} Not Allowed`,
        });
    }
  } catch (err) {
    console.error('❌ /api/chats error:', err);
    return res.status(500).json({
      success: false,
      error: 'Internal server error',
    });
  }
}

// ================================================
// GET: return all chats for the current user
// ================================================
async function handleGetChats(req, res, user) {
  const { data, error } = await supabase
    .from('crump_chats')
    .select('chat_id, title, messages, created_at, updated_at')
    .eq('user_id', user.id)
    .order('updated_at', { ascending: false });

  if (error) {
    console.error('❌ Supabase GET chats error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to load chats from server',
    });
  }

  const chats = (data || []).map((row) => ({
    id: row.chat_id,
    title: row.title || 'New Conversation',
    messages: row.messages || [],
    createdAt: row.created_at ? new Date(row.created_at).getTime() : Date.now(),
    updatedAt: row.updated_at ? new Date(row.updated_at).getTime() : Date.now(),
  }));

  return res.status(200).json({
    success: true,
    chats
  });
}

// ================================================
// POST: sync ALL chats for this user
//  - Frontend sends the entire chats array
//  - We delete old rows for this user & reinsert
// ================================================
async function handleSyncChats(req, res, user) {
  const { chats } = req.body || {};

  if (!Array.isArray(chats)) {
    return res.status(400).json({
      success: false,
      error: 'Invalid payload: "chats" must be an array',
    });
  }

  // Wipe existing chats for this user
  const { error: deleteError } = await supabase
    .from('crump_chats')
    .delete()
    .eq('user_id', user.id);

  if (deleteError) {
    console.error('❌ Supabase delete chats error:', deleteError);
    return res.status(500).json({
      success: false,
      error: 'Failed to reset chats before sync',
    });
  }

  if (chats.length === 0) {
    // Nothing else to do
    return res.status(200).json({
      success: true,
      chats: []
    });
  }

  const nowIso = new Date().toISOString();
  const rows = chats.map((c) => ({
    user_id: user.id,
    chat_id: c.id,
    title: c.title || 'New Conversation',
    messages: c.messages || [],
    created_at: c.createdAt
      ? new Date(c.createdAt).toISOString()
      : nowIso,
    updated_at: c.updatedAt
      ? new Date(c.updatedAt).toISOString()
      : nowIso,
  }));

  const { error: insertError } = await supabase
    .from('crump_chats')
    .insert(rows);

  if (insertError) {
    console.error('❌ Supabase insert chats error:', insertError);
    return res.status(500).json({
      success: false,
      error: 'Failed to sync chats to server',
    });
  }

  return res.status(200).json({
    success: true,
    chats
  });
}
