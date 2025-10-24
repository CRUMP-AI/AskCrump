// ==========================================
// CRUMP AI - TRANSLATION API
// LibreTranslate (Free) + Google Translate (Premium)
// ==========================================

export default async function handler(req, res) {
    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }
    
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }
    
    try {
        const { query, context } = req.body;
        
        if (!query) {
            return res.status(400).json({ error: 'Query is required' });
        }
        
        console.log(`🌐 Translation query: ${query}`);
        
        // Detect intent
        const intent = detectTranslationIntent(query);
        
        if (!intent) {
            return res.status(400).json({ 
                error: 'Could not understand translation query',
                hint: 'Try: "Translate hello to Spanish" or "How do you say thank you in French?"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        // Check for Google Translate API key (Premium)
        const googleApiKey = process.env.GOOGLE_TRANSLATE_API_KEY;
        
        let result;
        
        if (googleApiKey) {
            // Use Google Translate (Premium - more accurate)
            console.log('🔷 Using Google Translate API (Premium)');
            result = await translateWithGoogle(intent.text, intent.targetLang, intent.sourceLang, googleApiKey);
        } else {
            // Use LibreTranslate (Free)
            console.log('🔷 Using LibreTranslate API (Free)');
            result = await translateWithLibre(intent.text, intent.targetLang, intent.sourceLang);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'translation',
            intent: intent,
            data: result.data,
            formatted: result.formatted,
            engine: result.engine
        });
        
    } catch (error) {
        console.error('❌ Translation API error:', error);
        return res.status(500).json({ 
            error: 'Translation failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT TRANSLATION INTENT
// ==========================================
function detectTranslationIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: "translate [text] to [language]"
    let match = text.match(/translate\s+(.+?)\s+(?:to|into|in)\s+(\w+)/i);
    if (match) {
        return {
            text: match[1].trim(),
            targetLang: getLanguageCode(match[2].trim()),
            sourceLang: 'auto'
        };
    }
    
    // Pattern 2: "how do you say [text] in [language]"
    match = text.match(/how\s+do\s+you\s+say\s+(.+?)\s+in\s+(\w+)/i);
    if (match) {
        return {
            text: match[1].trim(),
            targetLang: getLanguageCode(match[2].trim()),
            sourceLang: 'auto'
        };
    }
    
    // Pattern 3: "what does [text] mean in [language]"
    match = text.match(/what\s+does\s+(.+?)\s+mean\s+in\s+(\w+)/i);
    if (match) {
        return {
            text: match[1].trim(),
            targetLang: getLanguageCode(match[2].trim()),
            sourceLang: 'auto'
        };
    }
    
    // Pattern 4: "[language] for [text]"
    match = text.match(/(\w+)\s+for\s+(.+)/i);
    if (match) {
        const lang = getLanguageCode(match[1].trim());
        if (lang) {
            return {
                text: match[2].trim(),
                targetLang: lang,
                sourceLang: 'auto'
            };
        }
    }
    
    // Pattern 5: "[language] translation of [text]"
    match = text.match(/(\w+)\s+translation\s+of\s+(.+)/i);
    if (match) {
        return {
            text: match[2].trim(),
            targetLang: getLanguageCode(match[1].trim()),
            sourceLang: 'auto'
        };
    }
    
    // Pattern 6: "[text] in [language]"
    match = text.match(/(.+?)\s+in\s+(\w+)$/i);
    if (match) {
        const lang = getLanguageCode(match[2].trim());
        if (lang) {
            return {
                text: match[1].trim(),
                targetLang: lang,
                sourceLang: 'auto'
            };
        }
    }
    
    return null;
}

// ==========================================
// GET LANGUAGE CODE
// ==========================================
function getLanguageCode(language) {
    const languageMap = {
        // Major languages
        'spanish': 'es',
        'french': 'fr',
        'german': 'de',
        'italian': 'it',
        'portuguese': 'pt',
        'russian': 'ru',
        'chinese': 'zh',
        'japanese': 'ja',
        'korean': 'ko',
        'arabic': 'ar',
        'hindi': 'hi',
        'english': 'en',
        
        // European languages
        'dutch': 'nl',
        'polish': 'pl',
        'swedish': 'sv',
        'norwegian': 'no',
        'danish': 'da',
        'finnish': 'fi',
        'greek': 'el',
        'czech': 'cs',
        'hungarian': 'hu',
        'romanian': 'ro',
        'bulgarian': 'bg',
        'croatian': 'hr',
        'slovak': 'sk',
        'slovenian': 'sl',
        'lithuanian': 'lt',
        'latvian': 'lv',
        'estonian': 'et',
        'irish': 'ga',
        'maltese': 'mt',
        
        // Asian languages
        'thai': 'th',
        'vietnamese': 'vi',
        'indonesian': 'id',
        'malay': 'ms',
        'filipino': 'fil',
        'tagalog': 'tl',
        'bengali': 'bn',
        'urdu': 'ur',
        'persian': 'fa',
        'turkish': 'tr',
        'hebrew': 'he',
        
        // Other languages
        'swahili': 'sw',
        'ukrainian': 'uk',
        'catalan': 'ca',
        'afrikaans': 'af',
        'icelandic': 'is',
        'albanian': 'sq',
        'basque': 'eu',
        'galician': 'gl',
        'welsh': 'cy',
        'macedonian': 'mk',
        'serbian': 'sr',
        'bosnian': 'bs',
        'georgian': 'ka',
        'armenian': 'hy',
        'azerbaijani': 'az',
        'kazakh': 'kk',
        'uzbek': 'uz',
        'mongolian': 'mn',
        'nepali': 'ne',
        'sinhala': 'si',
        'lao': 'lo',
        'burmese': 'my',
        'khmer': 'km',
        'esperanto': 'eo',
        'latin': 'la'
    };
    
    const lower = language.toLowerCase();
    
    // Check if it's already a language code
    if (lower.length === 2) {
        return lower;
    }
    
    return languageMap[lower] || null;
}

// ==========================================
// TRANSLATE WITH GOOGLE (PREMIUM)
// ==========================================
async function translateWithGoogle(text, targetLang, sourceLang, apiKey) {
    try {
        let url = `https://translation.googleapis.com/language/translate/v2?key=${apiKey}`;
        url += `&q=${encodeURIComponent(text)}`;
        url += `&target=${targetLang}`;
        
        if (sourceLang && sourceLang !== 'auto') {
            url += `&source=${sourceLang}`;
        }
        
        const response = await fetch(url, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error(`Google Translate API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.data || !data.data.translations || data.data.translations.length === 0) {
            return {
                success: false,
                error: 'Translation failed'
            };
        }
        
        const translation = data.data.translations[0];
        const translatedText = translation.translatedText;
        const detectedSourceLang = translation.detectedSourceLanguage || sourceLang;
        
        // Format response
        const formatted = formatTranslation(
            text, 
            translatedText, 
            detectedSourceLang, 
            targetLang,
            'Google Translate'
        );
        
        return {
            success: true,
            engine: 'google',
            data: {
                originalText: text,
                translatedText: translatedText,
                sourceLang: detectedSourceLang,
                targetLang: targetLang
            },
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error with Google Translate:', error);
        return {
            success: false,
            error: 'Google Translate failed',
            details: error.message
        };
    }
}

// ==========================================
// TRANSLATE WITH LIBRETRANSLATE (FREE)
// ==========================================
async function translateWithLibre(text, targetLang, sourceLang) {
    try {
        // Use public LibreTranslate instance
        const url = 'https://libretranslate.com/translate';
        
        const body = {
            q: text,
            source: sourceLang === 'auto' ? 'auto' : sourceLang,
            target: targetLang,
            format: 'text'
        };
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(body)
        });
        
        if (!response.ok) {
            throw new Error(`LibreTranslate API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.translatedText) {
            return {
                success: false,
                error: 'Translation failed'
            };
        }
        
        const translatedText = data.translatedText;
        const detectedSourceLang = data.detectedLanguage?.language || sourceLang;
        
        // Format response
        const formatted = formatTranslation(
            text, 
            translatedText, 
            detectedSourceLang, 
            targetLang,
            'LibreTranslate'
        );
        
        return {
            success: true,
            engine: 'libretranslate',
            data: {
                originalText: text,
                translatedText: translatedText,
                sourceLang: detectedSourceLang,
                targetLang: targetLang
            },
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error with LibreTranslate:', error);
        
        // Fallback: Try alternative LibreTranslate instance
        try {
            return await translateWithLibreBackup(text, targetLang, sourceLang);
        } catch (backupError) {
            return {
                success: false,
                error: 'Translation service unavailable',
                details: error.message,
                hint: 'Try again in a moment or use simpler text'
            };
        }
    }
}

// ==========================================
// LIBRETRANSLATE BACKUP (Alternative server)
// ==========================================
async function translateWithLibreBackup(text, targetLang, sourceLang) {
    // Try alternative public instance
    const url = 'https://translate.argosopentech.com/translate';
    
    const body = {
        q: text,
        source: sourceLang === 'auto' ? 'auto' : sourceLang,
        target: targetLang,
        format: 'text'
    };
    
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
    });
    
    if (!response.ok) {
        throw new Error('Backup translation service failed');
    }
    
    const data = await response.json();
    
    if (!data.translatedText) {
        throw new Error('No translation returned');
    }
    
    const formatted = formatTranslation(
        text, 
        data.translatedText, 
        sourceLang, 
        targetLang,
        'LibreTranslate'
    );
    
    return {
        success: true,
        engine: 'libretranslate',
        data: {
            originalText: text,
            translatedText: data.translatedText,
            sourceLang: sourceLang,
            targetLang: targetLang
        },
        formatted: formatted
    };
}

// ==========================================
// FORMAT TRANSLATION
// ==========================================
function formatTranslation(originalText, translatedText, sourceLang, targetLang, engine) {
    const sourceLanguage = getLanguageName(sourceLang);
    const targetLanguage = getLanguageName(targetLang);
    
    let formatted = `🌐 **Translation** (${engine})\n\n`;
    
    formatted += `**${sourceLanguage}:**\n`;
    formatted += `"${originalText}"\n\n`;
    
    formatted += `**${targetLanguage}:**\n`;
    formatted += `"${translatedText}"\n\n`;
    
    formatted += `🔄 ${sourceLanguage} → ${targetLanguage}`;
    
    return formatted;
}

// ==========================================
// GET LANGUAGE NAME FROM CODE
// ==========================================
function getLanguageName(code) {
    const languageNames = {
        'en': 'English',
        'es': 'Spanish',
        'fr': 'French',
        'de': 'German',
        'it': 'Italian',
        'pt': 'Portuguese',
        'ru': 'Russian',
        'zh': 'Chinese',
        'ja': 'Japanese',
        'ko': 'Korean',
        'ar': 'Arabic',
        'hi': 'Hindi',
        'nl': 'Dutch',
        'pl': 'Polish',
        'sv': 'Swedish',
        'no': 'Norwegian',
        'da': 'Danish',
        'fi': 'Finnish',
        'el': 'Greek',
        'cs': 'Czech',
        'hu': 'Hungarian',
        'ro': 'Romanian',
        'bg': 'Bulgarian',
        'hr': 'Croatian',
        'sk': 'Slovak',
        'sl': 'Slovenian',
        'lt': 'Lithuanian',
        'lv': 'Latvian',
        'et': 'Estonian',
        'ga': 'Irish',
        'mt': 'Maltese',
        'th': 'Thai',
        'vi': 'Vietnamese',
        'id': 'Indonesian',
        'ms': 'Malay',
        'fil': 'Filipino',
        'tl': 'Tagalog',
        'bn': 'Bengali',
        'ur': 'Urdu',
        'fa': 'Persian',
        'tr': 'Turkish',
        'he': 'Hebrew',
        'sw': 'Swahili',
        'uk': 'Ukrainian',
        'ca': 'Catalan',
        'af': 'Afrikaans',
        'is': 'Icelandic',
        'sq': 'Albanian',
        'eu': 'Basque',
        'gl': 'Galician',
        'cy': 'Welsh',
        'mk': 'Macedonian',
        'sr': 'Serbian',
        'bs': 'Bosnian',
        'ka': 'Georgian',
        'hy': 'Armenian',
        'az': 'Azerbaijani',
        'kk': 'Kazakh',
        'uz': 'Uzbek',
        'mn': 'Mongolian',
        'ne': 'Nepali',
        'si': 'Sinhala',
        'lo': 'Lao',
        'my': 'Burmese',
        'km': 'Khmer',
        'eo': 'Esperanto',
        'la': 'Latin',
        'auto': 'Auto-detected'
    };
    
    return languageNames[code] || code.toUpperCase();
}
```

---

## **🔑 API KEY SETUP:**

### **FREE (LibreTranslate - Works Immediately!):**
✅ **No API key needed!** Uses public LibreTranslate servers
- Supports 30+ languages
- Free forever
- May have occasional rate limits

### **PREMIUM (Google Translate - Optional):**
1. Go to: https://console.cloud.google.com/apis/library/translate.googleapis.com
2. Enable **Cloud Translation API**
3. Create credentials → API Key
4. Free tier: **$10 credit/month** (500K characters)
5. Add to Vercel (optional):
```
   GOOGLE_TRANSLATE_API_KEY=your_key_here
