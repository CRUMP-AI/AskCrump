// ==========================================
// CRUMP AI - GOOGLE DRIVE API
// Google Drive API Integration (OAuth Required)
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
        const { query, context, accessToken } = req.body;
        
        if (!query) {
            return res.status(400).json({ error: 'Query is required' });
        }
        
        // Check for access token (user must authorize)
        if (!accessToken) {
            return res.status(401).json({ 
                error: 'Drive access not authorized',
                authRequired: true,
                message: 'User must authorize Google Drive access via OAuth 2.0'
            });
        }
        
        console.log(`📁 Drive query: ${query}`);
        
        // Detect intent
        const intent = detectDriveIntent(query);
        
        if (!intent) {
            return res.status(400).json({ 
                error: 'Could not understand Drive query',
                hint: 'Try: "Find files named report" or "Show me recent documents"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        switch (intent.type) {
            case 'search':
                result = await searchFiles(accessToken, intent.searchQuery, intent.mimeType);
                break;
            
            case 'recent':
                result = await getRecentFiles(accessToken, intent.maxResults);
                break;
            
            case 'file_info':
                result = await getFileInfo(accessToken, intent.fileId);
                break;
            
            case 'shared_with_me':
                result = await getSharedFiles(accessToken);
                break;
            
            case 'starred':
                result = await getStarredFiles(accessToken);
                break;
            
            case 'by_type':
                result = await getFilesByType(accessToken, intent.fileType);
                break;
            
            case 'storage':
                result = await getStorageInfo(accessToken);
                break;
            
            case 'folders':
                result = await getFolders(accessToken);
                break;
            
            default:
                result = await searchFiles(accessToken, query, null);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'googleDrive',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Drive API error:', error);
        
        // Handle OAuth errors
        if (error.message.includes('401')) {
            return res.status(401).json({
                error: 'Drive authorization expired',
                authRequired: true,
                message: 'Please re-authorize Google Drive access'
            });
        }
        
        return res.status(500).json({ 
            error: 'Drive lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT DRIVE INTENT
// ==========================================
function detectDriveIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: Search by name
    if (text.match(/find|search|look for|locate/i)) {
        const mimeType = extractMimeType(text);
        const searchQuery = text
            .replace(/find|search|look for|locate|files?|documents?|in\s+(?:my\s+)?drive/gi, '')
            .replace(/named?|called?|with\s+name/gi, '')
            .trim();
        
        return {
            type: 'search',
            searchQuery: searchQuery,
            mimeType: mimeType
        };
    }
    
    // Pattern 2: Recent files
    if (text.match(/recent|latest|last\s+modified/i)) {
        const match = text.match(/(?:last|recent)\s+(\d+)/i);
        const maxResults = match ? parseInt(match[1]) : 10;
        
        return {
            type: 'recent',
            maxResults: Math.min(maxResults, 50)
        };
    }
    
    // Pattern 3: Shared with me
    if (text.match(/shared\s+with\s+me|shared\s+files/i)) {
        return {
            type: 'shared_with_me'
        };
    }
    
    // Pattern 4: Starred files
    if (text.match(/starred|favorites?|important/i)) {
        return {
            type: 'starred'
        };
    }
    
    // Pattern 5: By file type
    const fileType = extractFileType(text);
    if (fileType) {
        return {
            type: 'by_type',
            fileType: fileType
        };
    }
    
    // Pattern 6: Storage info
    if (text.match(/storage|space|quota|how\s+much\s+space/i)) {
        return {
            type: 'storage'
        };
    }
    
    // Pattern 7: Folders
    if (text.match(/folders?|directories/i)) {
        return {
            type: 'folders'
        };
    }
    
    // Pattern 8: Specific file by name
    const searchQuery = text
        .replace(/in\s+(?:my\s+)?drive|files?|documents?|show\s+me/gi, '')
        .trim();
    
    return {
        type: 'search',
        searchQuery: searchQuery,
        mimeType: null
    };
}

// ==========================================
// EXTRACT MIME TYPE
// ==========================================
function extractMimeType(text) {
    const mimeTypes = {
        'document': 'application/vnd.google-apps.document',
        'doc': 'application/vnd.google-apps.document',
        'docs': 'application/vnd.google-apps.document',
        'sheet': 'application/vnd.google-apps.spreadsheet',
        'sheets': 'application/vnd.google-apps.spreadsheet',
        'spreadsheet': 'application/vnd.google-apps.spreadsheet',
        'slide': 'application/vnd.google-apps.presentation',
        'slides': 'application/vnd.google-apps.presentation',
        'presentation': 'application/vnd.google-apps.presentation',
        'pdf': 'application/pdf',
        'image': 'image/',
        'photo': 'image/',
        'video': 'video/',
        'folder': 'application/vnd.google-apps.folder'
    };
    
    for (const [key, value] of Object.entries(mimeTypes)) {
        if (text.includes(key)) {
            return value;
        }
    }
    
    return null;
}

// ==========================================
// EXTRACT FILE TYPE
// ==========================================
function extractFileType(text) {
    const types = ['documents', 'spreadsheets', 'presentations', 'pdfs', 'images', 'videos'];
    
    for (const type of types) {
        if (text.includes(type)) {
            return type;
        }
    }
    
    return null;
}

// ==========================================
// SEARCH FILES
// ==========================================
async function searchFiles(accessToken, searchQuery, mimeType = null) {
    try {
        let q = `name contains '${searchQuery}' and trashed=false`;
        
        if (mimeType) {
            if (mimeType.endsWith('/')) {
                // Partial match for image/, video/, etc.
                q += ` and mimeType contains '${mimeType}'`;
            } else {
                q += ` and mimeType='${mimeType}'`;
            }
        }
        
        const url = `https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(q)}&pageSize=20&fields=files(id,name,mimeType,modifiedTime,size,webViewLink,iconLink,owners)&orderBy=modifiedTime desc`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Drive API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.files || data.files.length === 0) {
            return {
                success: false,
                error: `No files found matching "${searchQuery}"`,
                hint: 'Try a different search term or check file name spelling'
            };
        }
        
        // Format response
        const formatted = formatFileList(data.files, `Search Results: ${searchQuery}`);
        
        return {
            success: true,
            data: data.files,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching files:', error);
        return {
            success: false,
            error: 'Failed to search files'
        };
    }
}

// ==========================================
// GET RECENT FILES
// ==========================================
async function getRecentFiles(accessToken, maxResults = 10) {
    try {
        const url = `https://www.googleapis.com/drive/v3/files?pageSize=${maxResults}&fields=files(id,name,mimeType,modifiedTime,size,webViewLink,iconLink,owners)&orderBy=modifiedTime desc&q=trashed=false`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Drive API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.files || data.files.length === 0) {
            return {
                success: false,
                error: 'No files found in Drive'
            };
        }
        
        // Format response
        const formatted = formatFileList(data.files, 'Recent Files');
        
        return {
            success: true,
            data: data.files,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting recent files:', error);
        return {
            success: false,
            error: 'Failed to get recent files'
        };
    }
}

// ==========================================
// GET FILE INFO
// ==========================================
async function getFileInfo(accessToken, fileId) {
    try {
        const url = `https://www.googleapis.com/drive/v3/files/${fileId}?fields=id,name,mimeType,description,createdTime,modifiedTime,size,webViewLink,iconLink,owners,sharingUser,shared,permissions`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            if (response.status === 404) {
                return {
                    success: false,
                    error: 'File not found'
                };
            }
            throw new Error(`Drive API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatFileDetails(data);
        
        return {
            success: true,
            data: data,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting file info:', error);
        return {
            success: false,
            error: 'Failed to get file info'
        };
    }
}

// ==========================================
// GET SHARED FILES
// ==========================================
async function getSharedFiles(accessToken) {
    try {
        const url = `https://www.googleapis.com/drive/v3/files?q=sharedWithMe=true and trashed=false&pageSize=20&fields=files(id,name,mimeType,modifiedTime,size,webViewLink,iconLink,owners,sharingUser)&orderBy=modifiedTime desc`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Drive API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.files || data.files.length === 0) {
            return {
                success: false,
                error: 'No files shared with you'
            };
        }
        
        // Format response
        const formatted = formatSharedFiles(data.files);
        
        return {
            success: true,
            data: data.files,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting shared files:', error);
        return {
            success: false,
            error: 'Failed to get shared files'
        };
    }
}

// ==========================================
// GET STARRED FILES
// ==========================================
async function getStarredFiles(accessToken) {
    try {
        const url = `https://www.googleapis.com/drive/v3/files?q=starred=true and trashed=false&pageSize=20&fields=files(id,name,mimeType,modifiedTime,size,webViewLink,iconLink,owners)&orderBy=modifiedTime desc`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Drive API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.files || data.files.length === 0) {
            return {
                success: false,
                error: 'No starred files'
            };
        }
        
        // Format response
        const formatted = formatFileList(data.files, 'Starred Files');
        
        return {
            success: true,
            data: data.files,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting starred files:', error);
        return {
            success: false,
            error: 'Failed to get starred files'
        };
    }
}

// ==========================================
// GET FILES BY TYPE
// ==========================================
async function getFilesByType(accessToken, fileType) {
    try {
        const mimeTypeMap = {
            'documents': 'application/vnd.google-apps.document',
            'spreadsheets': 'application/vnd.google-apps.spreadsheet',
            'presentations': 'application/vnd.google-apps.presentation',
            'pdfs': 'application/pdf',
            'images': 'image/',
            'videos': 'video/'
        };
        
        const mimeType = mimeTypeMap[fileType];
        
        if (!mimeType) {
            return {
                success: false,
                error: `Unknown file type: ${fileType}`
            };
        }
        
        let q = 'trashed=false';
        
        if (mimeType.endsWith('/')) {
            q += ` and mimeType contains '${mimeType}'`;
        } else {
            q += ` and mimeType='${mimeType}'`;
        }
        
        const url = `https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(q)}&pageSize=20&fields=files(id,name,mimeType,modifiedTime,size,webViewLink,iconLink,owners)&orderBy=modifiedTime desc`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Drive API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.files || data.files.length === 0) {
            return {
                success: false,
                error: `No ${fileType} found`
            };
        }
        
        // Format response
        const formatted = formatFileList(data.files, fileType.charAt(0).toUpperCase() + fileType.slice(1));
        
        return {
            success: true,
            data: data.files,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting files by type:', error);
        return {
            success: false,
            error: 'Failed to get files by type'
        };
    }
}

// ==========================================
// GET STORAGE INFO
// ==========================================
async function getStorageInfo(accessToken) {
    try {
        const url = 'https://www.googleapis.com/drive/v3/about?fields=storageQuota,user';
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Drive API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Format response
        const formatted = formatStorageInfo(data.storageQuota);
        
        return {
            success: true,
            data: data.storageQuota,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting storage info:', error);
        return {
            success: false,
            error: 'Failed to get storage info'
        };
    }
}

// ==========================================
// GET FOLDERS
// ==========================================
async function getFolders(accessToken) {
    try {
        const url = `https://www.googleapis.com/drive/v3/files?q=mimeType='application/vnd.google-apps.folder' and trashed=false&pageSize=20&fields=files(id,name,modifiedTime,webViewLink)&orderBy=name`;
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Drive API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.files || data.files.length === 0) {
            return {
                success: false,
                error: 'No folders found'
            };
        }
        
        // Format response
        const formatted = formatFolders(data.files);
        
        return {
            success: true,
            data: data.files,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting folders:', error);
        return {
            success: false,
            error: 'Failed to get folders'
        };
    }
}

// ==========================================
// FORMAT FILE LIST
// ==========================================
function formatFileList(files, title) {
    let formatted = `📁 **${title}**\n\n`;
    formatted += `Found ${files.length} file${files.length === 1 ? '' : 's'}:\n\n`;
    
    files.forEach((file, index) => {
        const name = file.name;
        const type = getFileTypeIcon(file.mimeType);
        const size = file.size ? formatFileSize(parseInt(file.size)) : 'N/A';
        const modified = formatDate(file.modifiedTime);
        const owner = file.owners && file.owners[0] ? file.owners[0].displayName : 'Unknown';
        const link = file.webViewLink;
        
        formatted += `**${index + 1}. ${type} ${name}**\n`;
        formatted += `   📊 ${size} • 📅 ${modified}\n`;
        formatted += `   👤 Owner: ${owner}\n`;
        formatted += `   🔗 [Open File](${link})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT SHARED FILES
// ==========================================
function formatSharedFiles(files) {
    let formatted = `🤝 **Files Shared With You**\n\n`;
    formatted += `Found ${files.length} file${files.length === 1 ? '' : 's'}:\n\n`;
    
    files.forEach((file, index) => {
        const name = file.name;
        const type = getFileTypeIcon(file.mimeType);
        const sharedBy = file.sharingUser ? file.sharingUser.displayName : 
                        (file.owners && file.owners[0] ? file.owners[0].displayName : 'Unknown');
        const modified = formatDate(file.modifiedTime);
        const link = file.webViewLink;
        
        formatted += `**${index + 1}. ${type} ${name}**\n`;
        formatted += `   👥 Shared by: ${sharedBy}\n`;
        formatted += `   📅 ${modified}\n`;
        formatted += `   🔗 [Open File](${link})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// FORMAT FILE DETAILS
// ==========================================
function formatFileDetails(file) {
    const name = file.name;
    const type = getFileTypeIcon(file.mimeType);
    const size = file.size ? formatFileSize(parseInt(file.size)) : 'N/A';
    const created = formatDate(file.createdTime);
    const modified = formatDate(file.modifiedTime);
    const owner = file.owners && file.owners[0] ? file.owners[0].displayName : 'Unknown';
    const shared = file.shared ? 'Yes' : 'No';
    const link = file.webViewLink;
    
    let formatted = `📁 **${type} ${name}**\n\n`;
    formatted += `📊 **Size:** ${size}\n`;
    formatted += `📅 **Created:** ${created}\n`;
    formatted += `📅 **Modified:** ${modified}\n`;
    formatted += `👤 **Owner:** ${owner}\n`;
    formatted += `🤝 **Shared:** ${shared}\n`;
    
    if (file.description) {
        formatted += `\n📝 **Description:**\n${file.description}\n`;
    }
    
    formatted += `\n🔗 [Open File](${link})`;
    
    return formatted;
}

// ==========================================
// FORMAT STORAGE INFO
// ==========================================
function formatStorageInfo(quota) {
    const limit = parseInt(quota.limit);
    const usage = parseInt(quota.usage);
    const usageInDrive = parseInt(quota.usageInDrive);
    const usageInTrash = parseInt(quota.usageInDriveTrash);
    
    const percentUsed = ((usage / limit) * 100).toFixed(1);
    
    let formatted = `💾 **Google Drive Storage**\n\n`;
    formatted += `📊 **Total:** ${formatFileSize(limit)}\n`;
    formatted += `📈 **Used:** ${formatFileSize(usage)} (${percentUsed}%)\n`;
    formatted += `📉 **Available:** ${formatFileSize(limit - usage)}\n\n`;
    
    formatted += `**Breakdown:**\n`;
    formatted += `• Drive Files: ${formatFileSize(usageInDrive)}\n`;
    formatted += `• Trash: ${formatFileSize(usageInTrash)}\n`;
    
    // Storage warning
    if (percentUsed > 90) {
        formatted += `\n🚨 **Warning:** Storage is almost full!`;
    } else if (percentUsed > 75) {
        formatted += `\n⚠️ **Notice:** Storage is getting full.`;
    } else {
        formatted += `\n✅ **Healthy** storage levels.`;
    }
    
    return formatted;
}

// ==========================================
// FORMAT FOLDERS
// ==========================================
function formatFolders(folders) {
    let formatted = `📂 **Your Folders**\n\n`;
    formatted += `Found ${folders.length} folder${folders.length === 1 ? '' : 's'}:\n\n`;
    
    folders.forEach((folder, index) => {
        const name = folder.name;
        const modified = formatDate(folder.modifiedTime);
        const link = folder.webViewLink;
        
        formatted += `**${index + 1}. 📁 ${name}**\n`;
        formatted += `   📅 ${modified}\n`;
        formatted += `   🔗 [Open Folder](${link})\n\n`;
    });
    
    return formatted;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function getFileTypeIcon(mimeType) {
    const typeMap = {
        'application/vnd.google-apps.document': '📄',
        'application/vnd.google-apps.spreadsheet': '📊',
        'application/vnd.google-apps.presentation': '📽️',
        'application/vnd.google-apps.folder': '📁',
        'application/pdf': '📕',
        'image/': '🖼️',
        'video/': '🎥',
        'audio/': '🎵'
    };
    
    for (const [key, value] of Object.entries(typeMap)) {
        if (mimeType.includes(key)) {
            return value;
        }
    }
    
    return '📄';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) {
        return 'Just now';
    } else if (diffMins < 60) {
        return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`;
    } else if (diffHours < 24) {
        return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
    } else if (diffDays < 7) {
        return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
    } else {
        const options = { month: 'short', day: 'numeric', year: 'numeric' };
        return date.toLocaleDateString('en-US', options);
    }
}
