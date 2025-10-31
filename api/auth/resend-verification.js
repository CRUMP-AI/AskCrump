// =====================================================
// RESEND VERIFICATION API ENDPOINT
// Location: /api/auth/resend-verification.js
// =====================================================

import { supabase } from '../utils/supabase.js';
import { generateVerificationToken } from '../utils/jwt.js';
import { sendVerificationEmail } from '../utils/email.js';

export default async function handler(req, res) {
    // Only allow POST requests
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        const { email } = req.body;

        if (!email) {
            return res.status(400).json({
                success: false,
                error: 'Email is required'
            });
        }

        // Find user
        const { data: user, error: userError } = await supabase
            .from('users')
            .select('*')
            .eq('email', email.toLowerCase())
            .single();

        if (userError || !user) {
            // Don't reveal if user exists or not for security
            return res.status(200).json({
                success: true,
                message: 'If an account exists with this email, a verification email has been sent.'
            });
        }

        // Check if already verified
        if (user.is_verified) {
            return res.status(400).json({
                success: false,
                error: 'Email is already verified'
            });
        }

        // Generate new verification token
        const verificationToken = generateVerificationToken(email);
        const verificationExpires = new Date(Date.now() + 24 * 60 * 60 * 1000); // 24 hours

        // Update user with new token
        const { error: updateError } = await supabase
            .from('users')
            .update({
                verification_token: verificationToken,
                verification_token_expires: verificationExpires.toISOString()
            })
            .eq('id', user.id);

        if (updateError) {
            console.error('Token update error:', updateError);
            return res.status(500).json({
                success: false,
                error: 'Failed to generate verification token'
            });
        }

        // Send verification email
        try {
            await sendVerificationEmail(email, verificationToken, user.full_name);
        } catch (emailError) {
            console.error('Failed to send verification email:', emailError);
            return res.status(500).json({
                success: false,
                error: 'Failed to send verification email'
            });
        }

        return res.status(200).json({
            success: true,
            message: 'Verification email sent successfully. Please check your inbox.'
        });

    } catch (error) {
        console.error('Resend verification error:', error);
        return res.status(500).json({
            success: false,
            error: 'An unexpected error occurred. Please try again.'
        });
    }
}
