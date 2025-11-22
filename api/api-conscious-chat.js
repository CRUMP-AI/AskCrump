// ==========================================
// CRUMP AI - CONSCIOUS CHAT ENDPOINT v1.1 (Stabilized)
// Legacy endpoint preserved with safe implementation
// ==========================================

export default async function handler(req, res) {
    // Only allow POST for this endpoint
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed. Use POST for conscious chat.',
        });
    }

    try {
        const body = req.body && typeof req.body === 'object'
            ? req.body
            : {};

        const { message, context, mode } = body;

        // Safe legacy response: no server-side consciousness engine,
        // but the endpoint is wired and won’t break deployment.
        return res.status(200).json({
            success: true,
            endpoint: 'api-conscious-chat',
            mode: mode || 'legacy',
            echo: message || null,
            message: 'Conscious chat endpoint is online. Full consciousness processing currently runs on the front-end engine only.',
            note: 'This is a stabilized placeholder implementation to keep the route alive without importing browser-only modules.',
            contextSummary: context ? 'Context received' : 'No context provided',
        });
    } catch (error) {
        console.error('❌ Error in api-conscious-chat:', error);
        return res.status(500).json({
            success: false,
            error: 'Internal server error in conscious chat endpoint',
            detail: error.message,
        });
    }
}
