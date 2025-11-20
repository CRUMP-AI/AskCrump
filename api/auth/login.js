// =====================================================
// LOGIN API ENDPOINT
// Location: /api/auth/login.js
// =====================================================

import bcrypt from 'bcryptjs';
import { serialize } from 'cookie';
import { supabase } from '../utils/supabase.js';
import { generateToken } from '../utils/jwt.js';

export default async function handler(req, res) {
    // Only allow POST requests
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        // Support both parsed and raw JSON body
        let body = req.body;
        if (typeof body === 'string') {
            try {
                body = JSON.parse(body);
            } catch (parseError) {
                console.warn('[login] Failed to parse JSON body:', parseError?.message || parseError);
                return res.status(400).json({
                    success: false,
                    error: 'Invalid request body'
                });
            }
        }

        if (!body || typeof body !== 'object') {
            return res.status(400).json({
                success: false,
                error: 'Request body is required'
            });
        }

        let { email, password, rememberMe } = body;

        email = typeof email === 'string' ? email.trim() : '';
        password = typeof password === 'string' ? password : '';
        rememberMe = Boolean(rememberMe);

        if (!email || !password) {
            return res.status(400).json({
                success: false,
                error: 'Email and password are required'
            });
        }

        // Basic email validation
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            return res.status(400).json({
                success: false,
                error: 'Invalid email format'
            });
        }

        if (password.length < 8) {
            return res.status(400).json({
                success: false,
                error: 'Password must be at least 8 characters long'
            });
        }

        // Normalize email for lookup
        const normalizedEmail = email.toLowerCase();

        // Fetch user from Supabase
        const { data: user, error: userError } = await supabase
            .from('users')
            .select('*')
            .eq('email', normalizedEmail)
            .single();

        if (userError) {
            // If Supabase explicitly says row not found, treat as invalid creds
            if (userError.code === 'PGRST116' || userError.details?.includes('Results contain 0 rows')) {
                return res.status(401).json({
                    success: false,
                    error: 'Invalid email or password'
                });
            }

            console.error('[login] Database error fetching user:', userError);
            return res.status(500).json({
                success: false,
                error: 'An unexpected error occurred. Please try again.'
            });
        }

        if (!user) {
            // No user found for that email
            return res.status(401).json({
                success: false,
                error: 'Invalid email or password'
            });
        }

        // Verify password
        if (!user.password_hash) {
            console.warn('[login] User record missing password_hash for id:', user.id);
            return res.status(401).json({
                success: false,
                error: 'Invalid email or password'
            });
        }

        const passwordMatches = await bcrypt.compare(password, user.password_hash);
        if (!passwordMatches) {
            return res.status(401).json({
                success: false,
                error: 'Invalid email or password'
            });
        }

        // Require verified email before allowing login
        if (!user.is_verified) {
            return res.status(403).json({
                success: false,
                error: 'Please verify your email before logging in.',
                needsVerification: true,
                email: user.email
            });
        }

        // Generate JWT token
        const token = generateToken({
            userId: user.id,
            email: user.email
        });

        // Session expiry:
        // - rememberMe = true  => 30 days
        // - rememberMe = false => 7 days
        const days = rememberMe ? 30 : 7;
        const expiresAt = new Date(Date.now() + days * 24 * 60 * 60 * 1000);

        // Set HTTP-only auth cookie
        const cookie = serialize('auth_token', token, {
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'lax',
            maxAge: Math.floor((expiresAt.getTime() - Date.now()) / 1000),
            path: '/'
        });

        res.setHeader('Set-Cookie', cookie);

        // Try to load user settings (non-fatal if it fails)
        let settings = null;
        try {
            const { data: settingsRow, error: settingsError } = await supabase
                .from('user_settings')
                .select('*')
                .eq('user_id', user.id)
                .single();

            if (settingsError && settingsError.code !== 'PGRST116') {
                console.warn('[login] Failed to load user settings:', settingsError);
            } else {
                settings = settingsRow || null;
            }
        } catch (settingsCatchError) {
            console.warn('[login] Unexpected error loading user settings:', settingsCatchError);
        }

        // Shape the user object exactly as other endpoints expect
        const userPayload = {
            id: user.id,
            email: user.email,
            fullName: user.full_name || null,
            isVerified: !!user.is_verified,
            preferences: user.preferences || null,
            createdAt: user.created_at
        };

        return res.status(200).json({
            success: true,
            message: 'Login successful',
            data: {
                user: userPayload,
                settings: settings || null,
                token: token,
                expiresAt: expiresAt.toISOString()
            }
        });

    } catch (error) {
        console.error('Login error:', error);
        return res.status(500).json({
            success: false,
            error: 'An unexpected error occurred. Please try again.'
        });
    }
}
