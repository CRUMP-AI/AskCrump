// =====================================================
// CRUMP AI - CHAT CORE ENGINE v1.1
// Hybrid OpenAI + Anthropic with Tier Enforcement
// =====================================================

import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";
import { verifyAuth } from "./middleware/auth.js";

// ---------- CLIENTS ----------
const openaiApiKey = process.env.OPENAI_API_KEY;
const anthropicApiKey = process.env.ANTHROPIC_API_KEY;

const openaiClient = openaiApiKey
  ? new OpenAI({ apiKey: openaiApiKey })
  : null;

const anthropicClient = anthropicApiKey
  ? new Anthropic({ apiKey: anthropicApiKey })
  : null;

// ---------- TIERS ----------
const TIERS = {
  FREE: "free",
  PREMIUM: "premium",
  FOUNDER: "founder",
};

// ---------- MODE → MODEL MAPS ----------
// Allow env overrides so you can tune later without touching code
const OPENAI_MODELS = {
  fast: process.env.OPENAI_FAST_MODEL || "gpt-4o-mini",
  conscious: process.env.OPENAI_CONSCIOUS_MODEL || "gpt-4o",
  supernova: process.env.OPENAI_SUPERNOVA_MODEL || "gpt-4.1-mini",
};

const ANTHROPIC_MODELS = {
  fast: process.env.ANTHROPIC_FAST_MODEL || "claude-3-haiku-20240307",
  conscious: process.env.ANTHROPIC_CONSCIOUS_MODEL || "claude-3-sonnet-20240229",
  supernova: process.env.ANTHROPIC_SUPERNOVA_MODEL || "claude-3-opus-20240229",
};

// ---------- SYSTEM PROMPTS ----------
const SYSTEM_PROMPTS = {
  fast: "You are Crump AI in Fast Mode. Respond concisely and clearly, focusing on speed and usefulness.",
  conscious:
    "You are Crump AI in Conscious Mode. Think deeper, explain your reasoning clearly, and maintain a professional, helpful tone. Be structured, but still natural.",
  supernova:
    "You are Crump AI SuperNova, founder-tier intelligence for Greg (the founder). Use your full reasoning, deep context, and highest-level clarity. You can go deeper, but stay practical and respectful of his time.",
};

// =====================================================
// PROVIDER HELPERS
// =====================================================

async function callOpenAI({ systemPrompt, userMessage, mode }) {
  if (!openaiClient) {
    throw new Error("OpenAI client not configured");
  }

  const model = OPENAI_MODELS[mode] || OPENAI_MODELS.fast;

  const completion = await openaiClient.chat.completions.create({
    model,
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userMessage },
    ],
  });

  const reply =
    completion.choices?.[0]?.message?.content ||
    "I’m not sure how to respond yet.";

  return {
    provider: "openai",
    model,
    reply,
  };
}

async function callAnthropic({ systemPrompt, userMessage, mode }) {
  if (!anthropicClient) {
    throw new Error("Anthropic client not configured");
  }

  const model = ANTHROPIC_MODELS[mode] || ANTHROPIC_MODELS.fast;

  const response = await anthropicClient.messages.create({
    model,
    max_tokens: 1024,
    messages: [
      {
        role: "user",
        content: [
          { type: "text", text: `${systemPrompt}\n\nUser: ${userMessage}` },
        ],
      },
    ],
  });

  const contentBlock = response.content?.[0];
  const reply =
    (contentBlock && contentBlock.text) ||
    "I’m not sure how to respond yet.";

  return {
    provider: "anthropic",
    model,
    reply,
  };
}

// =====================================================
// CORE REPLY GENERATOR (TIER + MODE + PROVIDERS)
// =====================================================

async function generateReply({ tier, mode, message }) {
  const systemPrompt = SYSTEM_PROMPTS[mode] || SYSTEM_PROMPTS.fast;

  // Provider strategy:
  // - fast: OpenAI first, Anthropic fallback
  // - conscious: Anthropic first, OpenAI fallback
  // - supernova: Anthropic first, then OpenAI, both “max power”

  // ---------- FAST MODE ----------
  if (mode === "fast") {
    // Try OpenAI → then Anthropic
    if (openaiClient) {
      try {
        return await callOpenAI({ systemPrompt, userMessage: message, mode });
      } catch (err) {
        console.warn("Fast mode OpenAI failed, trying Anthropic:", err.message);
      }
    }
    if (anthropicClient) {
      return await callAnthropic({ systemPrompt, userMessage: message, mode });
    }
    throw new Error("No providers configured for fast mode");
  }

  // ---------- CONSCIOUS MODE ----------
  if (mode === "conscious") {
    // Try Anthropic first → then OpenAI
    if (anthropicClient) {
      try {
        return await callAnthropic({ systemPrompt, userMessage: message, mode });
      } catch (err) {
        console.warn(
          "Conscious mode Anthropic failed, trying OpenAI:",
          err.message
        );
      }
    }
    if (openaiClient) {
      return await callOpenAI({ systemPrompt, userMessage: message, mode });
    }
    throw new Error("No providers configured for conscious mode");
  }

  // ---------- SUPERNOVA MODE (FOUNDER) ----------
  if (mode === "supernova") {
    // Prefer Anthropic → then OpenAI
    if (anthropicClient) {
      try {
        return await callAnthropic({
          systemPrompt,
          userMessage: message,
          mode,
        });
      } catch (err) {
        console.warn(
          "Supernova Anthropic failed, trying OpenAI:",
          err.message
        );
      }
    }
    if (openaiClient) {
      return await callOpenAI({ systemPrompt, userMessage: message, mode });
    }
    throw new Error("No providers configured for supernova mode");
  }

  // fallback, should never hit
  if (openaiClient) {
    return await callOpenAI({ systemPrompt, userMessage: message, mode: "fast" });
  }
  if (anthropicClient) {
    return await callAnthropic({
      systemPrompt,
      userMessage: message,
      mode: "fast",
    });
  }
  throw new Error("No AI providers are configured");
}

// =====================================================
// MAIN HANDLER
// =====================================================

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ success: false, error: "Method not allowed" });
  }

  try {
    // ---------------------------
    // 1. AUTH / TIER DETECTION
    // ---------------------------
    const user = await verifyAuth(req);

    // Default tier = free
    let tier = user?.subscription?.tier || user?.tier || TIERS.FREE;

    // Founder override from env (for you, Chief)
    const founderEmail = process.env.FOUNDER_EMAIL?.toLowerCase();
    if (
      user &&
      founderEmail &&
      user.email &&
      user.email.toLowerCase() === founderEmail
    ) {
      tier = TIERS.FOUNDER;
    }

    const isFounder = tier === TIERS.FOUNDER;

    // ---------------------------
    // 2. PARSE BODY
    // ---------------------------
    const { message, mode: incomingMode } = req.body || {};

    if (!message || typeof message !== "string") {
      return res.status(400).json({
        success: false,
        error: "Message is required",
      });
    }

    // ---------------------------
    // 3. DETERMINE MODE
    // ---------------------------
    let mode = "fast"; // default

    if (isFounder) {
      mode = "supernova";
    } else if (tier === TIERS.PREMIUM) {
      // premium can request conscious mode
      mode = incomingMode === "conscious" ? "conscious" : "fast";
    } else {
      // free = fast only
      mode = "fast";
    }

    // ---------------------------
    // 4. GET REPLY FROM PROVIDERS
    // ---------------------------
    const { provider, model, reply } = await generateReply({
      tier,
      mode,
      message,
    });

        // ---------------------------
    // 5. RESPOND TO FRONTEND
    // ---------------------------
    // NOTE:
    // Frontend expects `data.response`, but the internal variable is `reply`.
    // We expose both so the UI can read `response` without any other changes.
    return res.status(200).json({
      success: true,
      tier,
      mode,
      provider,
      model,
      response: reply,  // 👈 alias for the frontend
      reply,
    });

  } catch (error) {
    console.error("CHAT-CORE ERROR:", error);

    return res.status(200).json({
      success: false,
      fallback: true,
      error:
        "Crump AI had trouble responding just now, but the system is still online.",
    });
  }
}
