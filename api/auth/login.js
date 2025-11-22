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
        const { email, password, rememberMe = false } = req.body;

        // Validate input
        if (!email || !password) {
            return res.status(400).json({
                success: false,
                error: 'Email and password are required'
            });
        }

        // Find user by email
        const { data: user, error: userError } = await supabase
            .from('users')
            .select('*')
            .eq('email', email.toLowerCase())
            .single();

        if (userError || !user) {
            return res.status(401).json({
                success: false,
                error: 'Invalid email or password'
            });
        }

        // Verify password
        const isPasswordValid = await bcrypt.compare(password, user.password_hash);
        
        if (!isPasswordValid) {
            return res.status(401).json({
                success: false,
                error: 'Invalid email or password'
            });
        }
 
 // Check if email is verified
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

        // Session expiry (30 days for remember me, 7 days otherwise)
        const sessionDuration = rememberMe ? 30 * 24 * 60 * 60 * 1000 : 7 * 24 * 60 * 60 * 1000;
        const expiresAt = new Date(Date.now() + sessionDuration);

        // Get device info from request
        const userAgent = req.headers['user-agent'] || 'Unknown';
        const ipAddress = req.headers['x-forwarded-for'] || req.headers['x-real-ip'] || req.connection.remoteAddress || null;

        // Create session in database
        const { data: session, error: sessionError } = await supabase
            .from('sessions')
            .insert([
                {
                    user_id: user.id,
                    session_token: token,
                    expires_at: expiresAt.toISOString(),
                    ip_address: ipAddress,
                    user_agent: userAgent,
                    device_info: {
                        userAgent,
                        platform: req.headers['sec-ch-ua-platform'] || 'Unknown',
                        mobile: req.headers['sec-ch-ua-mobile'] === '?1'
                    }
                }
            ])
            .select()
            .single();

        if (sessionError) {
            console.error('Session creation error:', sessionError);
            return res.status(500).json({
                success: false,
                error: 'Failed to create session'
            });
        }

        // Update last login
        await supabase
            .from('users')
            .update({ last_login: new Date().toISOString() })
            .eq('id', user.id);

      // Set HTTP-only cookie (persistent across app restarts)
const cookie = serialize('auth_token', token, {
    httpOnly: true,
    // keep this exactly as you had it so dev vs prod still works
    secure: process.env.NODE_ENV === 'production',
    // LAX is more forgiving than STRICT, especially with PWAs / redirects
    sameSite: 'lax',
    // 30 days vs 7 days, but you can make both 30 if you want “always stay signed in”
    maxAge: rememberMe
        ? 30 * 24 * 60 * 60   // 30 days
        : 7  * 24 * 60 * 60,  // 7 days
    path: '/'
});


        res.setHeader('Set-Cookie', cookie);

        // Get user settings
        const { data: settings } = await supabase
            .from('user_settings')
            .select('*')
            .eq('user_id', user.id)
            .single();

        return res.status(200).json({
            success: true,
            message: 'Login successful',
            data: {
                user: {
                    id: user.id,
                    email: user.email,
                    fullName: user.full_name,
                    profilePicture: user.profile_picture,
                    isVerified: user.is_verified,
                    createdAt: user.created_at,
                    preferences: user.preferences
                },
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
