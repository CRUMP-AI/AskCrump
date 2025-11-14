// =====================================================
// RESET PASSWORD API ENDPOINT
// Location: /api/auth/reset-password.js
// =====================================================

import bcrypt from 'bcryptjs';
import { supabase } from '../../supabase.js';
import { verifyPasswordResetToken } from '../../jwt.js';

export default async function handler(req, res) {
    // Only allow POST requests
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        const { token, newPassword } = req.body;

        // Validate input
        if (!token || !newPassword) {
            return res.status(400).json({
                success: false,
                error: 'Token and new password are required'
            });
        }

        // Validate password strength
        if (newPassword.length < 8) {
            return res.status(400).json({
                success: false,
                error: 'Password must be at least 8 characters long'
            });
        }

        // Verify token
        let userId;
        try {
            const decoded = verifyPasswordResetToken(token);
            userId = decoded.userId;
        } catch (tokenError) {
            return res.status(400).json({
                success: false,
                error: 'Invalid or expired reset token'
            });
        }

        // Get user and verify token hasn't expired
        const { data: user, error: userError } = await supabase
            .from('users')
            .select('id, email, password_reset_token, password_reset_expires')
            .eq('id', userId)
            .single();

        if (userError || !user) {
            return res.status(400).json({
                success: false,
                error: 'Invalid reset token'
            });
        }

        // Check if token matches and hasn't expired
        if (user.password_reset_token !== token) {
            return res.status(400).json({
                success: false,
                error: 'Invalid reset token'
            });
        }

        if (new Date() > new Date(user.password_reset_expires)) {
            return res.status(400).json({
                success: false,
                error: 'Reset token has expired. Please request a new one.'
            });
        }

        // Hash new password
        const passwordHash = await bcrypt.hash(newPassword, 12);

        // Update password and clear reset token
        const { error: updateError } = await supabase
            .from('users')
            .update({
                password_hash: passwordHash,
                password_reset_token: null,
                password_reset_expires: null,
                updated_at: new Date().toISOString()
            })
            .eq('id', userId);

        if (updateError) {
            console.error('Failed to update password:', updateError);
            return res.status(500).json({
                success: false,
                error: 'Failed to reset password'
            });
        }

        // Invalidate all existing sessions for security
        await supabase
            .from('sessions')
            .delete()
            .eq('user_id', userId);

        return res.status(200).json({
            success: true,
            message: 'Password has been reset successfully. You can now log in with your new password.'
        });

    } catch (error) {
        console.error('Reset password error:', error);
        return res.status(500).json({
            success: false,
            error: 'An unexpected error occurred'
        });
    }
}
