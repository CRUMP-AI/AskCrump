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
        // Get token from query params (GET) or body (POST)
        const token = req.method === 'GET' ? req.query.token : req.body.token;

        if (!token) {
            return res.status(400).json({
                success: false,
                error: 'Verification token is required'
            });
        }

        // Verify token
        let userId;
        try {
            const decoded = verifySpecialToken(token);
            userId = decoded.userId;
        } catch (tokenError) {
            // For GET requests, redirect to app with error
            if (req.method === 'GET') {
                return res.redirect(`${process.env.APP_URL}?verification=failed&reason=invalid_token`);
            }
            
            return res.status(400).json({
                success: false,
                error: 'Invalid or expired verification token'
            });
        }

        // Get user from database
        const { data: user, error: userError } = await supabase
            .from('users')
            .select('id, email, full_name, is_verified, verification_token, verification_token_expires')
            .eq('id', userId)
            .single();

        if (userError || !user) {
            if (req.method === 'GET') {
                return res.redirect(`${process.env.APP_URL}?verification=failed&reason=user_not_found`);
            }
            
            return res.status(400).json({
                success: false,
                error: 'Invalid verification token'
            });
        }

        // Check if already verified
        if (user.is_verified) {
            if (req.method === 'GET') {
                return res.redirect(`${process.env.APP_URL}?verification=already_verified`);
            }
            
            return res.status(200).json({
                success: true,
                message: 'Email already verified. You can log in now.',
                alreadyVerified: true
            });
        }

        // Verify token matches
        if (user.verification_token !== token) {
            if (req.method === 'GET') {
                return res.redirect(`${process.env.APP_URL}?verification=failed&reason=token_mismatch`);
            }
            
            return res.status(400).json({
                success: false,
                error: 'Invalid verification token'
            });
        }

        // Check if token expired
        if (user.verification_token_expires && new Date() > new Date(user.verification_token_expires)) {
            if (req.method === 'GET') {
                return res.redirect(`${process.env.APP_URL}?verification=failed&reason=expired`);
            }
            
            return res.status(400).json({
                success: false,
                error: 'Verification token has expired. Please request a new one.',
                expired: true
            });
        }

        // Update user to verified
        const { error: updateError } = await supabase
            .from('users')
            .update({
                is_verified: true,
                verification_token: null,
                verification_token_expires: null,
                updated_at: new Date().toISOString()
            })
            .eq('id', userId);

        if (updateError) {
            console.error('Failed to verify user:', updateError);
            
            if (req.method === 'GET') {
                return res.redirect(`${process.env.APP_URL}?verification=failed&reason=update_error`);
            }
            
            return res.status(500).json({
                success: false,
                error: 'Failed to verify email'
            });
        }

        // Send welcome email (don't fail if this errors)
        try {
            await sendWelcomeEmail(user.email, user.full_name);
        } catch (emailError) {
            console.error('Failed to send welcome email:', emailError);
            // Continue anyway - user is verified
        }

        // For GET requests, redirect to app with success
        if (req.method === 'GET') {
            return res.redirect(`${process.env.APP_URL}?verification=success`);
        }

        // For POST requests, return JSON
        return res.status(200).json({
            success: true,
            message: 'Email verified successfully! You can now log in.',
            data: {
                email: user.email,
                verified: true
            }
        });

    } catch (error) {
        console.error('Email verification error:', error);
        
        if (req.method === 'GET') {
            return res.redirect(`${process.env.APP_URL}?verification=failed&reason=server_error`);
        }
        
        return res.status(500).json({
            success: false,
            error: 'An unexpected error occurred'
        });
    }
}
