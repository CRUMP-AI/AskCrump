// ==========================================
// CRUMP AI - LOGIN API
// Handles user authentication
// ==========================================

import { kv } from '@vercel/kv';
import crypto from 'crypto';

function hashPassword(password, salt) {
    return crypto.pbkdf2Sync(password, salt, 100000, 64, 'sha512').toString('hex');
}

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    try {
        const { email, password, rememberMe } = req.body;

        if (!email || !password) {
            return res.status(400).json({ error: 'Missing email or password' });
        }

        // Get user
        const user = await kv.get(`user:${email.toLowerCase()}`);

        if (!user) {
            return res.status(401).json({ error: 'Invalid email or password' });
        }

        if (!user.verified) {
            return res.status(401).json({ error: 'Email not verified' });
        }

        // Verify password
        const hashedPassword = hashPassword(password, user.salt);
        if (hashedPassword !== user.passwordHash) {
            return res.status(401).json({ error: 'Invalid email or password' });
        }

        // Create session token
        const sessionToken = crypto.randomBytes(32).toString('hex');
        const sessionData = {
            userId: user.userId,
            email: user.email,
            name: user.name,
            createdAt: Date.now()
        };

        // Store session (7 days or 30 days if remember me)
        const expiration = rememberMe ? 2592000 : 604800;
        await kv.set(`session:${sessionToken}`, sessionData, { ex: expiration });

        // Update last login
        await kv.set(`user:${email.toLowerCase()}`, {
            ...user,
            lastLoginAt: Date.now()
        });

        res.status(200).json({
            success: true,
            message: 'Login successful',
            token: sessionToken,
            user: {
                userId: user.userId,
                email: user.email,
                name: user.name
            }
        });

    } catch (error) {
        console.error('Login error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
}
