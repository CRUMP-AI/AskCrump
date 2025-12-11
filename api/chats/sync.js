// =====================================================
// CHAT SYNC API - Cross-device chat synchronization
// Location: /api/chats/sync.js
// =====================================================
import { supabase } from '../utils/supabase.js';
import { verifyAuth } from '../middleware/auth.js';

export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    
    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }
    
    try {
        // Verify user is authenticated
        const user = await verifyAuth(req);
        if (!user) {
            return res.status(401).json({
                success: false,
                error: 'Unauthorized'
            });
        }
        
        // GET: Fetch user's chats from database
        if (req.method === 'GET') {
            const { data: chats, error } = await supabase
                .from('user_chats')
                .select('*')
                .eq('user_id', user.id)
                .order('updated_at', { ascending: false });
            
            if (error) {
                console.error('Failed to fetch chats:', error);
                return res.status(500).json({
                    success: false,
                    error: 'Failed to fetch chats'
                });
            }
            
            return res.status(200).json({
                success: true,
                chats: chats || []
            });
        }
        
        // POST: Save/update chats to database
        if (req.method === 'POST') {
            const { chats } = req.body;
            
            if (!Array.isArray(chats)) {
                return res.status(400).json({
                    success: false,
                    error: 'Chats must be an array'
                });
            }
            
            // ✅ FIX: Convert JavaScript timestamps to ISO format for PostgreSQL
            const chatData = chats.map(chat => {
                // Convert createdAt from milliseconds to ISO string
                let createdAt = chat.createdAt;
                if (typeof createdAt === 'number') {
                    createdAt = new Date(createdAt).toISOString();
                } else if (!createdAt) {
                    createdAt = new Date().toISOString();
                }
                
                return {
                    id: chat.id,
                    user_id: user.id,
                    title: chat.title || 'New Chat',
                    messages: chat.messages || [],
                    created_at: createdAt,
                    updated_at: new Date().toISOString()
                };
            });
            
            // Upsert chats (insert or update)
            const { error: upsertError } = await supabase
                .from('user_chats')
                .upsert(chatData, {
                    onConflict: 'id',
                    ignoreDuplicates: false
                });
            
            if (upsertError) {
                console.error('Failed to sync chats:', upsertError);
                return res.status(500).json({
                    success: false,
                    error: 'Failed to sync chats',
                    details: upsertError.message
                });
            }
            
            return res.status(200).json({
                success: true,
                message: 'Chats synced successfully',
                count: chatData.length
            });
        }
        
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
        
    } catch (error) {
        console.error('Chat sync error:', error);
        return res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
}
