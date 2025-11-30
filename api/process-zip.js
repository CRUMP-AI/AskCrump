// ==========================================
// ZIP FILE PROCESSOR API
// Receives zip files, extracts, and returns analysis
// ==========================================

export default async function handler(req, res) {
    // CORS
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
        const { fileName, fileData, action = 'analyze' } = req.body;
        
        if (!fileName || !fileData) {
            return res.status(400).json({ 
                error: 'fileName and fileData required' 
            });
        }
        
        // Check file size (limit to 50MB for processing)
        const sizeBytes = Math.ceil(fileData.length * 0.75); // Base64 overhead
        const sizeMB = sizeBytes / (1024 * 1024);
        
        if (sizeMB > 50) {
            return res.status(413).json({
                error: `File too large (${sizeMB.toFixed(1)}MB). Maximum 50MB.`,
                suggestion: 'Try a smaller archive or extract specific files'
            });
        }
        
        // Convert base64 to buffer
        const base64Data = fileData.includes(',') 
            ? fileData.split(',')[1] 
            : fileData;
        const buffer = Buffer.from(base64Data, 'base64');
        
        // Import JSZip dynamically (or use adm-zip)
        const JSZip = (await import('jszip')).default;
        const zip = await JSZip.loadAsync(buffer);
        
        // Extract file list
        const files = [];
        const fileContents = {};
        
        for (const [path, file] of Object.entries(zip.files)) {
            if (!file.dir) {
                files.push({
                    path: path,
                    size: file._data?.uncompressedSize || 0,
                    type: getFileType(path)
                });
                
                // For text files, extract content (up to 100KB each)
                if (isTextFile(path)) {
                    try {
                        const content = await file.async('string');
                        if (content.length < 100000) {
                            fileContents[path] = content;
                        }
                    } catch (e) {
                        console.warn(`Could not extract ${path}:`, e);
                    }
                }
            }
        }
        
        // Build analysis
        const analysis = {
            fileName: fileName,
            totalFiles: files.length,
            totalSize: sizeMB.toFixed(2) + ' MB',
            files: files,
            structure: buildFileTree(files),
            textFiles: Object.keys(fileContents).length,
            codeFiles: files.filter(f => f.type === 'code').length,
            imageFiles: files.filter(f => f.type === 'image').length,
            documentFiles: files.filter(f => f.type === 'document').length
        };
        
        // Include contents if requested
        if (action === 'analyze_full') {
            analysis.contents = fileContents;
        }
        
        return res.status(200).json({
            success: true,
            analysis: analysis,
            message: `Extracted ${files.length} files from ${fileName}`
        });
        
    } catch (error) {
        console.error('ZIP processing error:', error);
        return res.status(500).json({
            error: 'Failed to process ZIP file',
            details: error.message
        });
    }
}

// Helper functions
function getFileType(path) {
    const ext = path.split('.').pop().toLowerCase();
    const codeExts = ['js', 'ts', 'jsx', 'tsx', 'py', 'java', 'cpp', 'c', 'cs', 'go', 'rb', 'php', 'html', 'css', 'json'];
    const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'];
    const docExts = ['pdf', 'doc', 'docx', 'txt', 'md'];
    
    if (codeExts.includes(ext)) return 'code';
    if (imageExts.includes(ext)) return 'image';
    if (docExts.includes(ext)) return 'document';
    return 'other';
}

function isTextFile(path) {
    const ext = path.split('.').pop().toLowerCase();
    const textExts = ['js', 'ts', 'jsx', 'tsx', 'py', 'java', 'txt', 'md', 'json', 'xml', 'html', 'css', 'sql'];
    return textExts.includes(ext);
}

function buildFileTree(files) {
    const tree = {};
    files.forEach(file => {
        const parts = file.path.split('/');
        let current = tree;
        parts.forEach((part, i) => {
            if (i === parts.length - 1) {
                current[part] = file;
            } else {
                current[part] = current[part] || {};
                current = current[part];
            }
        });
    });
    return tree;
}
