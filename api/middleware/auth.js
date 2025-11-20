// =====================================================
// AUTHENTICATION MIDDLEWARE
// Location: /api/middleware/auth.js
// =====================================================

import { parse } from 'cookie';
import { verifyToken } from '../utils/jwt.js';
import { supabase } from '../utils/supabase.js';

/**
 * Core auth verifier.
 * - Reads token from Authorization: Bearer <token> or auth_token cookie
 * - Verifies JWT
 * - Loads matching profile from Supabase
 * - Returns a normalized user object with userId set
 */
export async function verifyAuth(req) {
  try {
    if (!req || !req.headers) {
      console.warn('[verifyAuth] Called without valid req/headers');
      return null;
    }

    let token = null;

    // 1) Prefer Authorization header
    const authHeader = req.headers.authorization || req.headers.Authorization;
    if (authHeader && typeof authHeader === 'string' && authHeader.startsWith('Bearer ')) {
      token = authHeader.substring(7).trim();
    }

    // 2) Fallback to auth_token cookie
    if (!token) {
      try {
        const rawCookieHeader = req.headers.cookie || '';
        const cookies = parse(rawCookieHeader);
        if (cookies && cookies.auth_token) {
          token = cookies.auth_token;
        }
      } catch (cookieError) {
        console.warn('[verifyAuth] Failed to parse cookies:', cookieError?.message || cookieError);
      }
    }

    // 3) No token → unauthenticated
    if (!token) {
      return null;
    }

    // 4) Verify JWT
    let decoded;
    try {
      decoded = verifyToken(token);
    } catch (err) {
      console.warn('[verifyAuth] Invalid auth token:', err?.message || err);
      return null;
    }

    if (!decoded || !decoded.userId) {
      console.warn('[verifyAuth] Decoded token missing userId');
      return null;
    }

    // 5) Load profile from Supabase
    // NOTE: we use the "profiles" table because that's where chat_state lives
    const { data: profile, error } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', decoded.userId)
      .single();

    if (error || !profile) {
      console.warn(
        '[verifyAuth] Profile not found for token userId',
        decoded.userId,
        error || '(no Supabase error object)'
      );
      return null;
    }

    // Optional sanity check if email is present in both places
    if (
      decoded.email &&
      profile.email &&
      typeof decoded.email === 'string' &&
      typeof profile.email === 'string' &&
      decoded.email.toLowerCase() !== profile.email.toLowerCase()
    ) {
      console.warn(
        '[verifyAuth] Token email does not match profile record for userId',
        decoded.userId
      );
      return null;
    }

    // Normalize shape: keep full profile AND add userId for convenience
    return {
      ...profile,
      userId: profile.id,
    };
  } catch (error) {
    console.error('[verifyAuth] Unexpected error:', error);
    return null;
  }
}

/**
 * requireAuth – supports TWO patterns:
 *
 * 1) "Give me the user" style:
 *    const user = await requireAuth(req, res);
 *    if (!user) {
 *      // unauthenticated – caller decides how to respond
 *      return;
 *    }
 *
 * 2) Middleware style:
 *    export default function handler(req, res) {
 *      return requireAuth(req, res, async (req, res) => {
 *        // req.user is guaranteed
 *      });
 *    }
 */
export async function requireAuth(req, res, handler) {
  const user = await verifyAuth(req);

  // Pattern 2: called with handler → we handle 401 responses
  if (typeof handler === 'function') {
    if (!user) {
      return res.status(401).json({
        success: false,
        error: 'Authentication required',
      });
    }

    req.user = user;
    return handler(req, res);
  }

  // Pattern 1: no handler → just return user or null
  return user;
}

/**
 * Middleware to require email verification.
 * Returns 403 if email not verified.
 *
 * Usage:
 *   export default function handler(req, res) {
 *     return requireVerified(req, res, async (req, res) => {
 *       // req.user.is_verified === true here
 *     });
 *   }
 */
export async function requireVerified(req, res, handler) {
  return requireAuth(req, res, async (req, res) => {
    try {
      if (!req.user || !req.user.is_verified) {
        return res.status(403).json({
          success: false,
          error: 'Email verification required',
        });
      }

      return handler(req, res);
    } catch (error) {
      console.error('[requireVerified] Unexpected error:', error);
      return res.status(500).json({
        success: false,
        error: 'Internal verification error',
      });
    }
  });
}
