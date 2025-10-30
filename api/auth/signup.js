// ==========================================
// CRUMP AI - SIGNUP API
// Handles user registration with email verification
// ==========================================

import { kv } from '@vercel/kv';
import crypto from 'crypto';

// Email service (using Resend - free tier: 100 emails/day)
const RESEND_API_KEY = process.env.RESEND_API_KEY;

async function sendVerificationEmail(email, code) {
    if (!RESEND_API_KEY) {
        console.warn('⚠️ RESEND_API_KEY not set - skipping email');
        return { success: true }; // Dev mode - skip email
    }

    try {
        const response = await fetch('https://api.resend.com/emails', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${RESEND_API_KEY}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                from: 'Crump AI <noreply@crumpai.com>',
                to: email,
                subject: 'Verify Your Crump AI Account',
                html: `
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #c9b892;">Welcome to Crump AI</h2>
                        <p>Your verification code is:</p>
                        <div style="background: #0f1419; color: #c9b892; padding: 20px; text-align: center; font-size: 32px; font-weight: bold; letter-spacing: 5px; border-radius: 8px;">
                            ${code}
                        </div>
                        <p style="color: #666; margin-top: 20px;">This code expires in 15 minutes.</p>
                        <p style="color: #666;">If you didn't request this, please ignore this email.</p>
                    </div>
                `
            })
        });

        return { success: response.ok };
    } catch (error) {
        console.error('Email send error:', error);
        return { success: false, error: error.message };
    }
}

function hashPassword(password, salt) {
    return crypto.pbkdf2Sync(password, salt, 100000, 64, 'sha512').toString('hex');
}

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    try {
        const { email, password, name } = req.body;

        // Validation
        if (!email || !password || !name) {
            return res.status(400).json({ error: 'Missing required fields' });
        }

        if (password.length < 8) {
            return res.status(400).json({ error: 'Password must be at least 8 characters' });
        }

        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            return res.status(400).json({ error: 'Invalid email format' });
        }

        // Check if user already exists
        const existingUser = await kv.get(`user:${email.toLowerCase()}`);
        if (existingUser) {
            return res.status(400).json({ error: 'Email already registered' });
        }

        // Generate verification code
        const verificationCode = Math.floor(100000 + Math.random() * 900000).toString();
        
        // Hash password
        const salt = crypto.randomBytes(16).toString('hex');
        const hashedPassword = hashPassword(password, salt);

        // Create user ID
        const userId = `user_${Date.now()}_${crypto.randomBytes(8).toString('hex')}`;

        // Store pending user (unverified)
        const pendingUser = {
            userId,
            email: email.toLowerCase(),
            name,
            passwordHash: hashedPassword,
            salt,
            verificationCode,
            verified: false,
            createdAt: Date.now()
        };

        // Store with 15-minute expiration
        await kv.set(`pending:${email.toLowerCase()}`, pendingUser, { ex: 900 });

        // Send verification email
        const emailResult = await sendVerificationEmail(email, verificationCode);

        if (!emailResult.success && RESEND_API_KEY) {
            return res.status(500).json({ 
                error: 'Failed to send verification email',
                devMode: !RESEND_API_KEY 
            });
        }

        res.status(200).json({ 
            success: true,
            message: 'Verification code sent to your email',
            devMode: !RESEND_API_KEY,
            devCode: !RESEND_API_KEY ? verificationCode : undefined // Only in dev
        });

    } catch (error) {
        console.error('Signup error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
}
