// =====================================================
// SUPABASE CLIENT CONFIGURATION
// Location: /api/utils/supabase.js
// =====================================================

import { createClient } from '@supabase/supabase-js';

// Initialize Supabase client
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_KEY;

if (!supabaseUrl || !supabaseServiceKey) {
    throw new Error('Missing Supabase environment variables');
}

// Create Supabase client with service role key (for server-side operations)
export const supabase = createClient(supabaseUrl, supabaseServiceKey, {
    auth: {
        autoRefreshToken: false,
        persistSession: false
    }
});

// Create Supabase client with anon key (for client-side operations)
export const supabaseAnon = createClient(
    supabaseUrl, 
    process.env.SUPABASE_ANON_KEY || supabaseServiceKey
);

export default supabase;
