// ==========================================
// CRUMP AI - RECIPES API
// Spoonacular API Integration
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
        
        // Check for API key
        const apiKey = process.env.SPOONACULAR_API_KEY;
        
        if (!apiKey) {
            console.warn('⚠️ Spoonacular API key not configured');
            return res.status(503).json({ 
                error: 'Recipes API key not configured',
                fallback: true,
                message: 'Please add SPOONACULAR_API_KEY to environment variables'
            });
        }
        
        console.log(`🍳 Recipe query: ${query}`);
        
        // Detect intent
        const intent = detectRecipeIntent(query);
        
        if (!intent) {
            return res.status(400).json({ 
                error: 'Could not understand recipe query',
                hint: 'Try: "Recipe for chocolate chip cookies" or "How to make pasta carbonara"'
            });
        }
        
        console.log(`🎯 Detected intent:`, intent);
        
        let result;
        
        switch (intent.type) {
            case 'recipe_search':
                result = await searchRecipes(intent.query, intent.cuisine, intent.diet, apiKey);
                break;
            
            case 'ingredient_search':
                result = await searchByIngredients(intent.ingredients, apiKey);
                break;
            
            case 'random_recipe':
                result = await getRandomRecipe(intent.tags, apiKey);
                break;
            
            case 'recipe_details':
                // For now, search and show first result details
                result = await searchRecipes(intent.query, null, null, apiKey);
                break;
            
            default:
                result = await searchRecipes(intent.query, null, null, apiKey);
        }
        
        if (!result.success) {
            return res.status(404).json(result);
        }
        
        return res.status(200).json({
            success: true,
            api: 'recipes',
            intent: intent,
            data: result.data,
            formatted: result.formatted
        });
        
    } catch (error) {
        console.error('❌ Recipe API error:', error);
        return res.status(500).json({ 
            error: 'Recipe lookup failed',
            details: error.message 
        });
    }
}

// ==========================================
// DETECT RECIPE INTENT
// ==========================================
function detectRecipeIntent(query) {
    const text = query.toLowerCase().trim();
    
    // Pattern 1: "recipe for [dish]"
    let match = text.match(/recipe\s+for\s+(.+)/i);
    if (match) {
        return {
            type: 'recipe_search',
            query: match[1].trim(),
            cuisine: detectCuisine(text),
            diet: detectDiet(text)
        };
    }
    
    // Pattern 2: "how to make [dish]" or "how to cook [dish]"
    match = text.match(/how\s+to\s+(?:make|cook|prepare|bake)\s+(.+)/i);
    if (match) {
        return {
            type: 'recipe_search',
            query: match[1].trim(),
            cuisine: detectCuisine(text),
            diet: detectDiet(text)
        };
    }
    
    // Pattern 3: "recipes with [ingredients]"
    match = text.match(/recipes?\s+with\s+(.+)/i);
    if (match) {
        const ingredients = match[1].split(/,|\sand\s/).map(i => i.trim());
        return {
            type: 'ingredient_search',
            ingredients: ingredients
        };
    }
    
    // Pattern 4: "what can I make with [ingredients]"
    match = text.match(/what\s+can\s+i\s+(?:make|cook)\s+with\s+(.+)/i);
    if (match) {
        const ingredients = match[1].split(/,|\sand\s/).map(i => i.trim());
        return {
            type: 'ingredient_search',
            ingredients: ingredients
        };
    }
    
    // Pattern 5: "[cuisine] recipes"
    const cuisine = detectCuisine(text);
    if (cuisine && text.includes('recipe')) {
        return {
            type: 'recipe_search',
            query: text.replace(/recipe|recipes/gi, '').trim(),
            cuisine: cuisine,
            diet: detectDiet(text)
        };
    }
    
    // Pattern 6: "[diet] recipes"
    const diet = detectDiet(text);
    if (diet && text.includes('recipe')) {
        return {
            type: 'recipe_search',
            query: text.replace(/recipe|recipes/gi, '').trim(),
            cuisine: detectCuisine(text),
            diet: diet
        };
    }
    
    // Pattern 7: "random recipe"
    if (text.includes('random') || text.includes('surprise me')) {
        return {
            type: 'random_recipe',
            tags: detectCuisine(text) || detectDiet(text)
        };
    }
    
    // Default: recipe search
    return {
        type: 'recipe_search',
        query: text.replace(/recipe|recipes|find|search|show me/gi, '').trim(),
        cuisine: detectCuisine(text),
        diet: detectDiet(text)
    };
}

// ==========================================
// DETECT CUISINE
// ==========================================
function detectCuisine(text) {
    const cuisines = {
        'african': 'African',
        'american': 'American',
        'british': 'British',
        'cajun': 'Cajun',
        'caribbean': 'Caribbean',
        'chinese': 'Chinese',
        'eastern european': 'Eastern European',
        'european': 'European',
        'french': 'French',
        'german': 'German',
        'greek': 'Greek',
        'indian': 'Indian',
        'irish': 'Irish',
        'italian': 'Italian',
        'japanese': 'Japanese',
        'jewish': 'Jewish',
        'korean': 'Korean',
        'latin american': 'Latin American',
        'mediterranean': 'Mediterranean',
        'mexican': 'Mexican',
        'middle eastern': 'Middle Eastern',
        'nordic': 'Nordic',
        'southern': 'Southern',
        'spanish': 'Spanish',
        'thai': 'Thai',
        'vietnamese': 'Vietnamese'
    };
    
    for (const [keyword, cuisine] of Object.entries(cuisines)) {
        if (text.includes(keyword)) {
            return cuisine;
        }
    }
    
    return null;
}

// ==========================================
// DETECT DIET
// ==========================================
function detectDiet(text) {
    const diets = {
        'gluten free': 'Gluten Free',
        'ketogenic': 'Ketogenic',
        'keto': 'Ketogenic',
        'vegetarian': 'Vegetarian',
        'lacto-vegetarian': 'Lacto-Vegetarian',
        'ovo-vegetarian': 'Ovo-Vegetarian',
        'vegan': 'Vegan',
        'pescetarian': 'Pescetarian',
        'paleo': 'Paleo',
        'primal': 'Primal',
        'whole30': 'Whole30'
    };
    
    for (const [keyword, diet] of Object.entries(diets)) {
        if (text.includes(keyword)) {
            return diet;
        }
    }
    
    return null;
}

// ==========================================
// SEARCH RECIPES
// ==========================================
async function searchRecipes(query, cuisine, diet, apiKey) {
    try {
        let url = `https://api.spoonacular.com/recipes/complexSearch?query=${encodeURIComponent(query)}&number=10&addRecipeInformation=true&fillIngredients=true&apiKey=${apiKey}`;
        
        if (cuisine) {
            url += `&cuisine=${encodeURIComponent(cuisine)}`;
        }
        
        if (diet) {
            url += `&diet=${encodeURIComponent(diet)}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (response.status === 402) {
            return {
                success: false,
                error: 'Recipe API quota exceeded',
                hint: 'Free tier: 150 requests per day. Please try again tomorrow.'
            };
        }
        
        if (!response.ok) {
            throw new Error(`Spoonacular API returned ${response.status}`);
        }
        
        if (!data.results || data.results.length === 0) {
            return {
                success: false,
                error: `No recipes found for "${query}"`,
                hint: 'Try a different dish or be less specific'
            };
        }
        
        const recipes = data.results;
        
        // Format response
        const formatted = formatRecipes(recipes, query);
        
        return {
            success: true,
            data: recipes,
            formatted: formatted,
            totalResults: data.totalResults
        };
        
    } catch (error) {
        console.error('Error searching recipes:', error);
        return {
            success: false,
            error: 'Failed to search recipes',
            details: error.message
        };
    }
}

// ==========================================
// SEARCH BY INGREDIENTS
// ==========================================
async function searchByIngredients(ingredients, apiKey) {
    try {
        const ingredientList = ingredients.join(',+');
        const url = `https://api.spoonacular.com/recipes/findByIngredients?ingredients=${encodeURIComponent(ingredientList)}&number=10&ranking=1&apiKey=${apiKey}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (response.status === 402) {
            return {
                success: false,
                error: 'Recipe API quota exceeded'
            };
        }
        
        if (!response.ok) {
            throw new Error(`Spoonacular API returned ${response.status}`);
        }
        
        if (!data || data.length === 0) {
            return {
                success: false,
                error: `No recipes found with ingredients: ${ingredients.join(', ')}`,
                hint: 'Try fewer or more common ingredients'
            };
        }
        
        // Get recipe information for each result
        const recipeIds = data.slice(0, 5).map(r => r.id).join(',');
        const infoUrl = `https://api.spoonacular.com/recipes/informationBulk?ids=${recipeIds}&apiKey=${apiKey}`;
        
        const infoResponse = await fetch(infoUrl);
        const infoData = await infoResponse.json();
        
        // Format response
        const formatted = formatIngredientRecipes(infoData || data, ingredients);
        
        return {
            success: true,
            data: infoData || data,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error searching by ingredients:', error);
        return {
            success: false,
            error: 'Failed to search by ingredients'
        };
    }
}

// ==========================================
// GET RANDOM RECIPE
// ==========================================
async function getRandomRecipe(tags, apiKey) {
    try {
        let url = `https://api.spoonacular.com/recipes/random?number=5&apiKey=${apiKey}`;
        
        if (tags) {
            url += `&tags=${encodeURIComponent(tags)}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (response.status === 402) {
            return {
                success: false,
                error: 'Recipe API quota exceeded'
            };
        }
        
        if (!response.ok) {
            throw new Error(`Spoonacular API returned ${response.status}`);
        }
        
        if (!data.recipes || data.recipes.length === 0) {
            return {
                success: false,
                error: 'No random recipes found'
            };
        }
        
        const recipes = data.recipes;
        
        // Format response
        const formatted = formatRecipes(recipes, 'Random Recipes');
        
        return {
            success: true,
            data: recipes,
            formatted: formatted
        };
        
    } catch (error) {
        console.error('Error getting random recipe:', error);
        return {
            success: false,
            error: 'Failed to get random recipe'
        };
    }
}

// ==========================================
// FORMAT RECIPES
// ==========================================
function formatRecipes(recipes, query) {
    let formatted = `🍳 **Recipes: ${query}**\n\n`;
    formatted += `Found ${recipes.length} recipes:\n\n`;
    
    recipes.slice(0, 8).forEach((recipe, index) => {
        const title = recipe.title;
        const readyInMinutes = recipe.readyInMinutes;
        const servings = recipe.servings;
        const sourceUrl = recipe.sourceUrl || recipe.spoonacularSourceUrl;
        const image = recipe.image;
        
        formatted += `**${index + 1}. ${title}**\n`;
        
        if (readyInMinutes) {
            formatted += `   ⏱️ ${readyInMinutes} minutes`;
        }
        
        if (servings) {
            formatted += ` • 🍽️ ${servings} servings`;
        }
        
        // Add diet/cuisine tags
        const tags = [];
        if (recipe.vegetarian) tags.push('🥬 Vegetarian');
        if (recipe.vegan) tags.push('🌱 Vegan');
        if (recipe.glutenFree) tags.push('🌾 Gluten-Free');
        if (recipe.dairyFree) tags.push('🥛 Dairy-Free');
        
        if (tags.length > 0) {
            formatted += `\n   ${tags.join(' • ')}`;
        }
        
        formatted += '\n';
        
        // Add ingredients if available
        if (recipe.extendedIngredients && recipe.extendedIngredients.length > 0) {
            const ingredientList = recipe.extendedIngredients
                .slice(0, 5)
                .map(i => i.name)
                .join(', ');
            formatted += `   📝 ${ingredientList}`;
            if (recipe.extendedIngredients.length > 5) {
                formatted += ` (+${recipe.extendedIngredients.length - 5} more)`;
            }
            formatted += '\n';
        }
        
        if (sourceUrl) {
            formatted += `   🔗 [View Recipe](${sourceUrl})\n`;
        }
        
        formatted += '\n';
    });
    
    return formatted;
}

// ==========================================
// FORMAT INGREDIENT RECIPES
// ==========================================
function formatIngredientRecipes(recipes, ingredients) {
    let formatted = `🍳 **Recipes with: ${ingredients.join(', ')}**\n\n`;
    
    recipes.slice(0, 8).forEach((recipe, index) => {
        const title = recipe.title;
        const usedIngredients = recipe.usedIngredientCount || 0;
        const missedIngredients = recipe.missedIngredientCount || 0;
        const readyInMinutes = recipe.readyInMinutes;
        const servings = recipe.servings;
        const sourceUrl = recipe.sourceUrl || recipe.spoonacularSourceUrl;
        
        formatted += `**${index + 1}. ${title}**\n`;
        formatted += `   ✅ Uses ${usedIngredients} of your ingredients`;
        
        if (missedIngredients > 0) {
            formatted += ` • ➕ Needs ${missedIngredients} more`;
        }
        
        if (readyInMinutes) {
            formatted += `\n   ⏱️ ${readyInMinutes} minutes`;
        }
        
        if (servings) {
            formatted += ` • 🍽️ ${servings} servings`;
        }
        
        // Show missing ingredients
        if (recipe.missedIngredients && recipe.missedIngredients.length > 0) {
            const missing = recipe.missedIngredients
                .slice(0, 3)
                .map(i => i.name)
                .join(', ');
            formatted += `\n   🛒 You'll need: ${missing}`;
        }
        
        if (sourceUrl) {
            formatted += `\n   🔗 [View Recipe](${sourceUrl})`;
        }
        
        formatted += '\n\n';
    });
    
    return formatted;
}
```

---

## **🔑 API KEY SETUP:**

1. Go to: https://spoonacular.com/food-api/console#Dashboard
2. Sign up for free account
3. Get your API key
4. Free tier: **150 requests per day**
5. Add to Vercel:
```
   SPOONACULAR_API_KEY=your_key_here
