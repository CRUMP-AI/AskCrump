// =====================================================
// VERIFY EMAIL API ENDPOINT
// Location: /api/auth/verify-email.js
// =====================================================

import { supabase } from '../utils/supabase.js';
import { verifySpecialToken } from '../utils/jwt.js';
import { sendWelcomeEmail } from '../utils/email.js';

export default async function handler(req, res) {
    // Allow both GET and POST
    if (req.method !== 'GET' && req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        // Get token from query or body
        const token = req.method === 'GET' ? req.query.token : req.body.token;

        if (!token) {
            return res.status(400).json({
                success: false,
                error: 'Verification token is required'
            });
        }

        // Verify the token
        const decoded = verifySpecialToken(token, 'email-verification');
        
        if (!decoded) {
            return res.status(400).json({
                success: false,
                error: 'Invalid or expired verification token'
            });
        }

        // Find user by email
        const { data: user, error: userError } = await supabase
            .from('users')
            .select('*')
            .eq('email', decoded.email.toLowerCase())
            .single();

        if (userError || !user) {
            return res.status(404).json({
                success: false,
                error: 'User not found'
            });
        }

        // Check if already verified
        if (user.is_verified) {
            return res.status(200).json({
                success: true,
                message: 'Email already verified',
                data: {
                    email: user.email,
                    isVerified: true
                }
            });
        }

        // Check if token matches and is not expired
        if (user.verification_token !== token) {
            return res.status(400).json({
                success: false,
                error: 'Invalid verification token'
            });
        }

        const tokenExpiry = new Date(user.verification_token_expires);
        if (tokenExpiry < new Date()) {
            return res.status(400).json({
                success: false,
                error: 'Verification token has expired. Please request a new one.'
            });
        }

        // Update user as verified
        const { error: updateError } = await supabase
            .from('users')
            .update({
                is_verified: true,
                verification_token: null,
                verification_token_expires: null
            })
            .eq('id', user.id);

        if (updateError) {
            console.error('Verification update error:', updateError);
            return res.status(500).json({
                success: false,
                error: 'Failed to verify email'
            });
        }

        // Send welcome email (non-blocking)
        try {
            await sendWelcomeEmail(user.email, user.full_name);
        } catch (emailError) {
            console.error('Failed to send welcome email:', emailError);
            // Don't fail verification if welcome email fails
        }

        return res.status(200).json({
            success: true,
            message: 'Email verified successfully! You can now log in.',
            data: {
                email: user.email,
                isVerified: true,
                fullName: user.full_name
            }
        });

    } catch (error) {
        console.error('Email verification error:', error);
        return res.status(500).json({
            success: false,
            error: 'An unexpected error occurred. Please try again.'
        });
    }
}
