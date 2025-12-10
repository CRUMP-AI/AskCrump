export default function handler(req, res) {
    const cookies = req.headers.cookie || 'No cookies';
    const host = req.headers.host;
    
    return res.status(200).json({
        cookies: cookies,
        host: host,
        hasCrumpRefresh: cookies.includes('crump_refresh_token'),
        hasAuthToken: cookies.includes('auth_token')
    });
}
