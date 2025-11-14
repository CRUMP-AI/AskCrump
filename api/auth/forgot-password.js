// =====================================================
// FORGOT PASSWORD API ENDPOINT
// Location: /api/auth/forgot-password.js
// =====================================================

import { supabase } from '../../supabase.js';
import { generatePasswordResetToken } from '../../jwt.js';
import { sendPasswordResetEmail } from '../../email.js';

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

        // Validate input
        if (!email) {
            return res.status(400).json({
                success: false,
                error: 'Email is required'
            });
        }

        // Check if user exists
        const { data: user, error: userError } = await supabase
            .from('users')
            .select('id, email, full_name')
            .eq('email', email.toLowerCase().trim())
            .single();

        // Always return success even if user doesn't exist (security best practice)
        // This prevents email enumeration attacks
        if (userError || !user) {
            return res.status(200).json({
                success: true,
                message: 'If an account exists with that email, a password reset link has been sent.'
            });
        }

        // Generate password reset token (expires in 1 hour)
        const resetToken = generatePasswordResetToken(user.id);
        const expiresAt = new Date(Date.now() + 60 * 60 * 1000); // 1 hour from now

        // Store reset token in database
        const { error: updateError } = await supabase
            .from('users')
            .update({
                password_reset_token: resetToken,
                password_reset_expires: expiresAt.toISOString()
            })
            .eq('id', user.id);

        if (updateError) {
            console.error('Failed to store reset token:', updateError);
            return res.status(500).json({
                success: false,
                error: 'Failed to process password reset request'
            });
        }

        // Send password reset email
        try {
            await sendPasswordResetEmail(user.email, resetToken, user.full_name);
        } catch (emailError) {
            console.error('Failed to send reset email:', emailError);
            // Don't fail the request if email fails - user can try again
        }

        return res.status(200).json({
            success: true,
            message: 'If an account exists with that email, a password reset link has been sent.'
        });

    } catch (error) {
        console.error('Forgot password error:', error);
        return res.status(500).json({
            success: false,
            error: 'An unexpected error occurred'
        });
    }
}
