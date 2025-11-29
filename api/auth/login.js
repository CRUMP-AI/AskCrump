// =====================================================
// LOGIN API ENDPOINT
// Location: /api/auth/login.js
// =====================================================

import bcrypt from 'bcryptjs';
import { serialize } from 'cookie';
import jwt from 'jsonwebtoken';           // ✅ use jsonwebtoken directly
import { supabase } from '../utils/supabase.js';

// ---- JWT CONFIG (must match jwt.js) -----------------
const JWT_SECRET =
    process.env.JWT_SECRET || 'crump_ai_super_secret_fallback';

const ACCESS_TOKEN_EXPIRES_IN = '15m';
const REFRESH_TOKEN_EXPIRES_IN = '30d';

// Helper: create access token
function generateAccessToken(payload) {
    return jwt.sign(
        { ...payload, type: 'access' },
        JWT_SECRET,
        { expiresIn: ACCESS_TOKEN_EXPIRES_IN }
    );
}

// Helper: create refresh token
function generateRefreshToken(payload) {
    return jwt.sign(
        { ...payload, type: 'refresh' },
        JWT_SECRET,
        { expiresIn: REFRESH_TOKEN_EXPIRES_IN }
    );
}

// -----------------------------------------------------

export default async function handler(req, res) {
    // Only allow POST requests
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        const { email, password, rememberMe = false } = req.body || {};

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
        const isPasswordValid = await bcrypt.compare(
            password,
            user.password_hash
        );

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

        // =====================================================
        // SESSION & TOKEN SETUP (ACCESS + REFRESH MODEL)
        // =====================================================

        // 1) Session lifetime – conceptual "stay signed in" window
        const SESSION_DURATION_MS =
            365 * 24 * 60 * 60 * 1000; // 1 year
        const expiresAt = new Date(Date.now() + SESSION_DURATION_MS);

        // 2) Generate tokens (now using local helpers)
        const accessToken = generateAccessToken({
            userId: user.id,
            email: user.email
        });

        const refreshToken = generateRefreshToken({
            userId: user.id,
            email: user.email
        });

        // 3) Device / request info
        const userAgent = req.headers['user-agent'] || 'Unknown';
        const ipHeader =
            req.headers['x-forwarded-for'] ||
            req.headers['x-real-ip'] ||
            req.connection?.remoteAddress ||
            null;

        const ipAddress = Array.isArray(ipHeader)
            ? ipHeader[0]
            : typeof ipHeader === 'string'
            ? ipHeader.split(',')[0].trim()
            : ipHeader;

        // 4) Create session in database – store the refresh token
        const { data: session, error: sessionError } = await supabase
            .from('sessions')
            .insert([
                {
                    user_id: user.id,
                    session_token: refreshToken, // store refresh token for audit / revocation
                    expires_at: expiresAt.toISOString(),
                    ip_address: ipAddress,
                    user_agent: userAgent,
                    device_info: {
                        userAgent,
                        platform:
                            req.headers['sec-ch-ua-platform'] || 'Unknown',
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

        // 5) Update last login
        await supabase
            .from('users')
            .update({ last_login: new Date().toISOString() })
            .eq('id', user.id);

        // =====================================================
        // COOKIES
        // =====================================================

        // a) Long-lived refresh token (httpOnly; used by /api/auth/refresh)
        const refreshCookie = serialize('crump_refresh_token', refreshToken, {
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'lax',
            maxAge: 365 * 24 * 60 * 60, // 1 year in seconds
            path: '/'
        });

        // b) Short-lived auth cookie (backward compatibility with middleware)
        const authCookie = serialize('auth_token', accessToken, {
            httpOnly: true,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'lax',
            maxAge: 15 * 60, // 15 minutes in seconds
            path: '/'
        });

        // Attach both cookies
        res.setHeader('Set-Cookie', [refreshCookie, authCookie]);

        // =====================================================
        // USER SETTINGS
        // =====================================================
        const { data: settings } = await supabase
            .from('user_settings')
            .select('*')
            .eq('user_id', user.id)
            .single();

        // =====================================================
        // RESPONSE
        // =====================================================
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
                // Keep original field name so existing frontend still works:
                token: accessToken,
                accessToken,
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
