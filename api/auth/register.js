// =====================================================
// REGISTER API ENDPOINT
// Location: /api/auth/register.js
// =====================================================

import bcrypt from 'bcryptjs';
import { supabase } from '../utils/supabase.js';
import { generateVerificationToken } from '../utils/jwt.js';
import { sendVerificationEmail } from '../utils/email.js';

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        const { email, password, fullName } = req.body;

        if (!email || !password) {
            return res.status(400).json({
                success: false,
                error: 'Email and password are required'
            });
        }

        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            return res.status(400).json({
                success: false,
                error: 'Invalid email format'
            });
        }

        if (password.length < 8) {
            return res.status(400).json({
                success: false,
                error: 'Password must be at least 8 characters long'
            });
        }

        // Check if user already exists
        const { data: existingUser } = await supabase
            .from('users')
            .select('id, email, is_verified')
            .eq('email', email.toLowerCase())
            .single();

        if (existingUser) {
            if (existingUser.is_verified) {
                return res.status(409).json({
                    success: false,
                    error: 'An account with this email already exists'
                });
            } else {
                // Resend verification for unverified account
                const verificationToken = generateVerificationToken(existingUser.id);
                
                await supabase
                    .from('users')
                    .update({
                        verification_token: verificationToken,
                        verification_token_expires: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
                    })
                    .eq('id', existingUser.id);

                await sendVerificationEmail(email, verificationToken, fullName);

                return res.status(200).json({
                    success: true,
                    message: 'Verification email resent. Please check your inbox.'
                });
            }
        }

        // Hash password
        const passwordHash = await bcrypt.hash(password, 12);

        // Generate verification token
        const tempToken = generateVerificationToken(email); // Temporary token using email
        const tokenExpires = new Date(Date.now() + 24 * 60 * 60 * 1000);

        // Create user
        const { data: newUser, error: insertError } = await supabase
            .from('users')
            .insert([
                {
                    email: email.toLowerCase(),
                    password_hash: passwordHash,
                    full_name: fullName || null,
                    is_verified: false,
                    verification_token: tempToken,
                    verification_token_expires: tokenExpires.toISOString(),
                    preferences: {
                        theme: 'dark',
                        language: 'en',
                        notifications: true
                    }
                }
            ])
            .select()
            .single();

        if (insertError) {
            console.error('Database error:', insertError);
            return res.status(500).json({
                success: false,
                error: 'Failed to create account. Please try again.'
            });
        }

        // Now generate proper token with userId and update
        const verificationToken = generateVerificationToken(newUser.id);
        
        await supabase
            .from('users')
            .update({
                verification_token: verificationToken,
                verification_token_expires: tokenExpires.toISOString()
            })
            .eq('id', newUser.id);

        // Create default user settings
        await supabase
            .from('user_settings')
            .insert([
                {
                    user_id: newUser.id,
                    theme: 'dark',
                    language: 'en',
                    notifications_enabled: true,
                    email_notifications: true
                }
            ]);

        // Send verification email
        try {
            await sendVerificationEmail(email, verificationToken, fullName);
        } catch (emailError) {
            console.error('Failed to send verification email:', emailError);
        }

        return res.status(201).json({
            success: true,
            message: 'Account created successfully! Please check your email to verify your account.',
            data: {
                email: newUser.email,
                fullName: newUser.full_name,
                createdAt: newUser.created_at
            }
        });

    } catch (error) {
        console.error('Registration error:', error);
        return res.status(500).json({
            success: false,
            error: 'An unexpected error occurred. Please try again.'
        });
    }
}
