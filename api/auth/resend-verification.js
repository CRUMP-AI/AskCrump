import { supabase } from '../utils/supabase.js';
import { generateEmailVerificationToken } from '../utils/jwt.js';
import { sendVerificationEmail } from '../utils/email.js';


export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ success: false, error: 'Method not allowed' });
    }

    try {
        const { email } = req.body;
        if (!email) {
            return res.status(400).json({ success: false, error: 'Email is required' });
        }

        const { data: user, error } = await supabase
            .from('users')
            .select('id, email, full_name, is_verified')
            .eq('email', email.toLowerCase().trim())
            .single();

        if (error || !user) {
            return res.status(200).json({ success: true, message: 'If account exists, verification email sent.' });
        }

        if (user.is_verified) {
            return res.status(200).json({ success: true, message: 'Email already verified.' });
        }

        const verificationToken = generateVerificationToken(user.id);
        const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000);

        await supabase
            .from('users')
            .update({
                verification_token: verificationToken,
                verification_token_expires: expiresAt.toISOString()
            })
            .eq('id', user.id);

        await sendVerificationEmail(user.email, verificationToken, user.full_name);

        return res.status(200).json({ success: true, message: 'Verification email sent.' });
    } catch (error) {
        console.error('Resend verification error:', error);
        return res.status(500).json({ success: false, error: 'Server error' });
    }
}
