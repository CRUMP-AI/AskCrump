export default async function handler(req, res) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Credentials', true);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS,PATCH,DELETE,POST,PUT');
  res.setHeader('Access-Control-Allow-Headers', 'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version');
  
  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { message, history, fileData } = req.body;

    // Validate message
    if (!message || typeof message !== 'string' || message.trim() === '') {
      return res.status(400).json({ error: 'Invalid message' });
    }

    // Filter empty messages from history
    const cleanHistory = (history || []).filter(msg => 
      msg.content && 
      typeof msg.content === 'string' && 
      msg.content.trim() !== ''
    );

    // Determine which AI to use based on keywords
    const lowerMessage = message.toLowerCase();
    const claudeKeywords = ['code', 'debug', 'algorithm', 'explain', 'analyze', 'fix', 'error', 'function', 'technical'];
    const openaiKeywords = ['write', 'story', 'poem', 'creative', 'imagine', 'chat', 'casual'];
    
    const useOpenAI = openaiKeywords.some(keyword => lowerMessage.includes(keyword)) &&
                      !claudeKeywords.some(keyword => lowerMessage.includes(keyword));

    // Handle file processing (images only for now - PDFs need additional setup)
    if (fileData && fileData.type && fileData.data) {
      if (fileData.type.startsWith('image/')) {
        // Use Claude for image analysis
        const response = await fetch('https://api.anthropic.com/v1/messages', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-api-key': process.env.CLAUDE_API_KEY,
            'anthropic-version': '2023-06-01'
          },
          body: JSON.stringify({
            model: 'claude-sonnet-4-20250514',
            max_tokens: 1024,
            messages: [
              ...cleanHistory.map(msg => ({
                role: msg.role === 'user' ? 'user' : 'assistant',
                content: msg.content
              })),
              {
                role: 'user',
                content: [
                  {
                    type: 'image',
                    source: {
                      type: 'base64',
                      media_type: fileData.type,
                      data: fileData.data.split(',')[1] || fileData.data
                    }
                  },
                  {
                    type: 'text',
                    text: message
                  }
                ]
              }
            ]
          })
        });

        if (!response.ok) {
          throw new Error(`Claude API error: ${response.status}`);
        }

        const data = await response.json();
        return res.status(200).json({
          response: data.content[0].text,
          model: 'claude-vision'
        });
      } else {
        return res.status(400).json({ 
          error: 'File type not supported yet. Currently only images are supported.' 
        });
      }
    }

    // Normal text message processing
    if (useOpenAI) {
      // Use OpenAI for creative tasks
      const response = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
        },
        body: JSON.stringify({
          model: 'gpt-4',
          messages: [
            { role: 'system', content: 'You are Crump AI, a helpful and creative assistant.' },
            ...cleanHistory.map(msg => ({
              role: msg.role,
              content: msg.content
            })),
            { role: 'user', content: message }
          ],
          max_tokens: 800,
          temperature: 0.8
        })
      });

      if (!response.ok) {
        throw new Error(`OpenAI API error: ${response.status}`);
      }

      const data = await response.json();
      return res.status(200).json({
        response: data.choices[0].message.content,
        model: 'openai'
      });
    } else {
      // Use Claude for technical/analytical tasks
      const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': process.env.CLAUDE_API_KEY,
          'anthropic-version': '2023-06-01'
        },
        body: JSON.stringify({
          model: 'claude-sonnet-4-20250514',
          max_tokens: 1024,
          messages: [
            ...cleanHistory.map(msg => ({
              role: msg.role === 'user' ? 'user' : 'assistant',
              content: msg.content
            })),
            {
              role: 'user',
              content: message
            }
          ]
        })
      });

      if (!response.ok) {
        throw new Error(`Claude API error: ${response.status}`);
      }

      const data = await response.json();
      return res.status(200).json({
        response: data.content[0].text,
        model: 'claude'
      });
    }

  } catch (error) {
    console.error('API Error:', error);
    return res.status(500).json({
      error: 'Failed to process request',
      details: error.message
    });
  }
}
