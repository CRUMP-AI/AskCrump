// api/consciousness/test.js
export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({
      success: false,
      message: 'Method not allowed. Use GET for consciousness test.',
    });
  }

  return res.status(200).json({
    success: true,
    status: 'online',
    message: 'Consciousness test endpoint is wired correctly.',
    timestamp: new Date().toISOString(),
  });
}
