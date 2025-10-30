// ==========================================
// CRUMP AI - EMAIL VERIFICATION API
// Verifies user email and activates account
// ==========================================

import { kv } from '@vercel/kv';

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    try {
        const { email, code } = req.body;

        if (!email || !code) {
            return res.status(400).json({ error: 'Missing email or code' });
        }

        // Get pending user
        const pendingUser = await kv.get(`pending:${email.toLowerCase()}`);

        if (!pendingUser) {
            return res.status(400).json({ error: 'Verification expired or invalid' });
        }

        // Check code
        if (pendingUser.verificationCode !== code) {
            return res.status(400).json({ error: 'Invalid verification code' });
        }

        // Activate user
        const activatedUser = {
            ...pendingUser,
            verified: true,
            verifiedAt: Date.now()
        };
        delete activatedUser.verificationCode;

        // Store verified user permanently
        await kv.set(`user:${email.toLowerCase()}`, activatedUser);
        await kv.set(`userid:${activatedUser.userId}`, activatedUser);

        // Delete pending user
        await kv.del(`pending:${email.toLowerCase()}`);

        // Create session token
        const crypto = await import('crypto');
        const sessionToken = crypto.randomBytes(32).toString('hex');
        const sessionData = {
            userId: activatedUser.userId,
            email: activatedUser.email,
            name: activatedUser.name,
            createdAt: Date.now()
        };

        // Store session (30 days)
        await kv.set(`session:${sessionToken}`, sessionData, { ex: 2592000 });

        res.status(200).json({
            success: true,
            message: 'Email verified successfully',
            token: sessionToken,
            user: {
                userId: activatedUser.userId,
                email: activatedUser.email,
                name: activatedUser.name
            }
        });

    } catch (error) {
        console.error('Verification error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
}
