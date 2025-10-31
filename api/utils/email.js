// =====================================================
// EMAIL SERVICE (RESEND)
// Location: /api/utils/email.js
// =====================================================

import { Resend } from 'resend';

const resend = new Resend(process.env.RESEND_API_KEY);
const FROM_EMAIL = process.env.FROM_EMAIL || 'noreply@yourdomain.com';
const APP_NAME = process.env.APP_NAME || 'AI Assistant';
const APP_URL = process.env.APP_URL || 'http://localhost:3000';

/**
 * Send email verification email
 * @param {string} email - Recipient email
 * @param {string} verificationToken - Verification token
 * @param {string} userName - User's name
 */
export async function sendVerificationEmail(email, verificationToken, userName = '') {
    const verificationUrl = `${APP_URL}/verify-email?token=${verificationToken}`;
    
    try {
        const { data, error } = await resend.emails.send({
            from: `${APP_NAME} <${FROM_EMAIL}>`,
            to: email,
            subject: `Verify your ${APP_NAME} account`,
            html: `
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; }
                        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
                        .content { background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }
                        .button { display: inline-block; padding: 15px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold; }
                        .footer { text-align: center; margin-top: 30px; color: #666; font-size: 14px; }
                        .code { background: #e9ecef; padding: 10px 15px; border-radius: 5px; font-family: monospace; font-size: 18px; letter-spacing: 2px; margin: 15px 0; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Welcome to ${APP_NAME}! 🎉</h1>
                        </div>
                        <div class="content">
                            <h2>Hi ${userName || 'there'}!</h2>
                            <p>Thanks for signing up! We're excited to have you on board.</p>
                            <p>To get started, please verify your email address by clicking the button below:</p>
                            <div style="text-align: center;">
                                <a href="${verificationUrl}" class="button">Verify Email Address</a>
                            </div>
                            <p>Or copy and paste this link into your browser:</p>
                            <div class="code">${verificationUrl}</div>
                            <p><strong>This link will expire in 24 hours.</strong></p>
                            <p>If you didn't create an account with ${APP_NAME}, you can safely ignore this email.</p>
                        </div>
                        <div class="footer">
                            <p>&copy; ${new Date().getFullYear()} ${APP_NAME}. All rights reserved.</p>
                        </div>
                    </div>
                </body>
                </html>
            `
        });

        if (error) {
            throw error;
        }

        return { success: true, data };
    } catch (error) {
        console.error('Error sending verification email:', error);
        throw new Error('Failed to send verification email');
    }
}

/**
 * Send password reset email
 * @param {string} email - Recipient email
 * @param {string} resetToken - Password reset token
 * @param {string} userName - User's name
 */
export async function sendPasswordResetEmail(email, resetToken, userName = '') {
    const resetUrl = `${APP_URL}/reset-password?token=${resetToken}`;
    
    try {
        const { data, error } = await resend.emails.send({
            from: `${APP_NAME} <${FROM_EMAIL}>`,
            to: email,
            subject: `Reset your ${APP_NAME} password`,
            html: `
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; }
                        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
                        .content { background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }
                        .button { display: inline-block; padding: 15px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold; }
                        .footer { text-align: center; margin-top: 30px; color: #666; font-size: 14px; }
                        .warning { background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Password Reset Request</h1>
                        </div>
                        <div class="content">
                            <h2>Hi ${userName || 'there'}!</h2>
                            <p>We received a request to reset your password for your ${APP_NAME} account.</p>
                            <p>Click the button below to reset your password:</p>
                            <div style="text-align: center;">
                                <a href="${resetUrl}" class="button">Reset Password</a>
                            </div>
                            <div class="warning">
                                <strong>⚠️ Security Notice:</strong>
                                <p>This link will expire in 1 hour for security reasons.</p>
                                <p>If you didn't request a password reset, please ignore this email or contact support if you have concerns.</p>
                            </div>
                        </div>
                        <div class="footer">
                            <p>&copy; ${new Date().getFullYear()} ${APP_NAME}. All rights reserved.</p>
                        </div>
                    </div>
                </body>
                </html>
            `
        });

        if (error) {
            throw error;
        }

        return { success: true, data };
    } catch (error) {
        console.error('Error sending password reset email:', error);
        throw new Error('Failed to send password reset email');
    }
}

/**
 * Send welcome email after successful verification
 * @param {string} email - Recipient email
 * @param {string} userName - User's name
 */
export async function sendWelcomeEmail(email, userName = '') {
    try {
        const { data, error } = await resend.emails.send({
            from: `${APP_NAME} <${FROM_EMAIL}>`,
            to: email,
            subject: `Welcome to ${APP_NAME}! 🚀`,
            html: `
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; }
                        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
                        .content { background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }
                        .feature { background: white; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #667eea; }
                        .footer { text-align: center; margin-top: 30px; color: #666; font-size: 14px; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>You're All Set! 🎉</h1>
                        </div>
                        <div class="content">
                            <h2>Welcome aboard, ${userName || 'friend'}!</h2>
                            <p>Your account is now verified and ready to use. Here's what you can do:</p>
                            <div class="feature">
                                <strong>💬 Chat with AI</strong>
                                <p>Get instant, intelligent responses to your questions</p>
                            </div>
                            <div class="feature">
                                <strong>🔄 Multi-Device Sync</strong>
                                <p>Access your conversations from any device</p>
                            </div>
                            <div class="feature">
                                <strong>🎨 Personalization</strong>
                                <p>Customize your experience to fit your needs</p>
                            </div>
                            <p style="margin-top: 30px;">Ready to get started?</p>
                            <div style="text-align: center;">
                                <a href="${APP_URL}" style="display: inline-block; padding: 15px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold;">Start Chatting</a>
                            </div>
                        </div>
                        <div class="footer">
                            <p>Need help? Contact us at ${process.env.SUPPORT_EMAIL || 'support@yourdomain.com'}</p>
                            <p>&copy; ${new Date().getFullYear()} ${APP_NAME}. All rights reserved.</p>
                        </div>
                    </div>
                </body>
                </html>
            `
        });

        if (error) {
            throw error;
        }

        return { success: true, data };
    } catch (error) {
        console.error('Error sending welcome email:', error);
        // Don't throw error for welcome email - it's not critical
        return { success: false, error };
    }
}
