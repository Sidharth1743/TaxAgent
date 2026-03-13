// ---------------------------------------------------------------------------
// KLIPY API client + emotion extraction for TaxClarity
// Docs: docs/klipy/KLIPY_API.md
// ---------------------------------------------------------------------------

const BASE_URL =
  process.env.NEXT_PUBLIC_KLIPY_BASE_URL ?? "https://api.klipy.com/api/v1";
const APP_KEY =
  process.env.NEXT_PUBLIC_KLIPY_APP_KEY ??
  process.env.NEXT_PUBLIC_KLIPY_API_KEY ??
  "";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface KlipyMedia {
  url: string;
  format: "gif" | "webp" | "mp4" | "webm" | "png";
  width?: number;
  height?: number;
  alt: string;
}

type ContentApi = "gifs" | "static-memes" | "stickers";
type Emotion = "celebration" | "urgency" | "confusion" | "resolved" | "neutral";
type Jurisdiction = "india" | "us" | "global";

export interface EmotionResult {
  emotion: Emotion;
  jurisdiction: Jurisdiction;
}

interface ContentRequest {
  api: ContentApi;
  query: string;
  locale?: string;
}

// ---------------------------------------------------------------------------
// Keyword scoring — pure client-side, zero API calls
// ---------------------------------------------------------------------------

const EMOTION_KEYWORDS: Record<Emotion, string[]> = {
  celebration: [
    "saved", "refund", "deduction", "great news", "congratulations",
    "₹", "successfully filed", "good news", "you qualify", "eligible for",
    "you can claim", "tax benefit",
  ],
  urgency: [
    "deadline", "penalty", "due by", "last date", "urgent", "advance tax",
    "overdue", "late fee", "immediately", "as soon as possible",
  ],
  confusion: [
    "however", "depends on", "subject to", "note that", "complex",
    "consult", "it varies", "on the other hand", "but keep in mind",
    "in some cases", "exceptions apply",
  ],
  resolved: [
    "in summary", "to summarize", "hope this helps", "let me know if",
    "in conclusion", "to recap", "to wrap up", "that covers",
  ],
  neutral: [],
};

const JURISDICTION_KEYWORDS: Record<Jurisdiction, string[]> = {
  india: [
    "section 80", "itr", "tds", "gst", "₹", "cbdt", " ay ", "pan",
    "income tax india", "caclubindia", "taxtmi", "advance tax",
    "form 16", "hra", "epf", "ppf", "elss", "nps", "lakh",
  ],
  us: [
    "w-2", "1040", "401k", "irs", "agi", "fica", "federal",
    "turbotax", "schedule c", "roth", "social security",
  ],
  global: [
    "dtaa", "double taxation", "cross-border", "nri", "foreign tax credit",
    "treaty", "expat",
  ],
};

function scoreKeywords(text: string, keywords: string[]): number {
  const lower = text.toLowerCase();
  return keywords.filter((kw) => lower.includes(kw)).length;
}

export function extractEmotion(text: string): EmotionResult {
  // Emotion — highest score wins; neutral is the fallback
  const emotions: Emotion[] = ["celebration", "urgency", "confusion", "resolved"];
  let bestEmotion: Emotion = "neutral";
  let bestScore = 0;
  for (const emotion of emotions) {
    const score = scoreKeywords(text, EMOTION_KEYWORDS[emotion]);
    if (score > bestScore) {
      bestScore = score;
      bestEmotion = emotion;
    }
  }

  // Jurisdiction — highest score wins; global is the fallback
  const jurisdictions: Jurisdiction[] = ["india", "us", "global"];
  let bestJurisdiction: Jurisdiction = "global";
  let bestJScore = 0;
  for (const j of jurisdictions) {
    const score = scoreKeywords(text, JURISDICTION_KEYWORDS[j]);
    if (score > bestJScore) {
      bestJScore = score;
      bestJurisdiction = j;
    }
  }

  return { emotion: bestEmotion, jurisdiction: bestJurisdiction };
}

// ---------------------------------------------------------------------------
// Emotion → content mapping
// ---------------------------------------------------------------------------

export function selectContent(
  emotion: Emotion,
  jurisdiction: Jurisdiction,
  text: string,
  opts?: { allowMeme?: boolean; allowSticker?: boolean; allowGif?: boolean; rng?: () => number },
): ContentRequest | null {
  if (emotion === "neutral") return null;
  const lower = text.toLowerCase();
  const allowMeme = opts?.allowMeme ?? true;
  const allowSticker = opts?.allowSticker ?? true;
  const allowGif = opts?.allowGif ?? true;
  const rng = opts?.rng ?? Math.random;

  // Decide format by context + a bit of randomness so it feels fresh.
  // Memes: confusion/absurdity and text-heavy reactions.
  // Stickers: short, friendly acknowledgements.
  // GIFs: energetic or urgent reactions.
  let preferred: ContentApi = "gifs";
  if (emotion === "confusion" && allowMeme) {
    preferred = "static-memes";
  } else if (emotion === "resolved" && allowSticker && /thanks|got it|ok|okay|understood|cool|great/.test(lower)) {
    preferred = "stickers";
  } else if (emotion === "celebration" && allowGif) {
    preferred = "gifs";
  } else if (emotion === "urgency" && allowGif) {
    preferred = "gifs";
  } else if (allowSticker && rng() < 0.35) {
    preferred = "stickers";
  } else if (allowMeme && rng() < 0.2) {
    preferred = "static-memes";
  } else if (allowGif) {
    preferred = "gifs";
  }

  const byType: Record<ContentApi, Partial<Record<Jurisdiction, ContentRequest>> & { any?: ContentRequest }> = {
    "static-memes": {
      india: { api: "static-memes", query: "paisa hi paisa", locale: "in" },
      us: { api: "static-memes", query: "math lady confused", locale: "us" },
      global: { api: "static-memes", query: "math lady confused" },
    },
    stickers: {
      india: { api: "stickers", query: "namaste thanks", locale: "in" },
      us: { api: "stickers", query: "thumbs up thanks", locale: "us" },
      global: { api: "stickers", query: "thumbs up thanks" },
    },
    gifs: {
      india: { api: "gifs", query: "celebration success", locale: "in" },
      us: { api: "gifs", query: "money rain victory", locale: "us" },
      global: { api: "gifs", query: "victory dance celebration" },
    },
  };

  const entry = byType[preferred];
  return (entry as any)[jurisdiction] ?? (entry as any).any ?? null;
}

// ---------------------------------------------------------------------------
// Response shape discovery — data is undocumented, try multiple paths
// ---------------------------------------------------------------------------

function extractMediaUrl(data: unknown): Pick<KlipyMedia, "url" | "format"> | null {
  if (process.env.NODE_ENV === "development") {
    console.log("[KLIPY] raw data:", JSON.stringify(data, null, 2));
  }

  // Try every known GIF-API pattern in order of likelihood
  const candidates: Array<() => { url: string; format: string } | undefined> = [
    // Pattern A: { items: [{ images: { sm: { webp: { url } } } }] }
    () => {
      const item = (data as any)?.items?.[0];
      const sm = item?.images?.sm;
      return (
        sm?.webp?.url && { url: sm.webp.url, format: "webp" } ||
        sm?.gif?.url  && { url: sm.gif.url,  format: "gif"  } ||
        sm?.mp4?.url  && { url: sm.mp4.url,  format: "mp4"  } ||
        sm?.png?.url  && { url: sm.png.url,  format: "png"  }
      ) || undefined;
    },
    // Pattern B: { items: [{ sm: { url, format } }] }
    () => {
      const sm = (data as any)?.items?.[0]?.sm;
      return sm?.url ? { url: sm.url, format: sm.format ?? "gif" } : undefined;
    },
    // Pattern C: array root [{ images: { sm: { webp: { url } } } }]
    () => {
      const item = Array.isArray(data) ? data[0] : undefined;
      const sm = item?.images?.sm;
      return (
        sm?.webp?.url && { url: sm.webp.url, format: "webp" } ||
        sm?.gif?.url  && { url: sm.gif.url,  format: "gif"  }
      ) || undefined;
    },
    // Pattern D: array root [{ sm: { url } }]
    () => {
      const sm = Array.isArray(data) ? (data[0] as any)?.sm : undefined;
      return sm?.url ? { url: sm.url, format: sm.format ?? "gif" } : undefined;
    },
    // Pattern E: { results: [{ url }] }
    () => {
      const r = (data as any)?.results?.[0];
      return r?.url ? { url: r.url, format: r.format ?? "gif" } : undefined;
    },
    // Pattern F: { items: [{ url }] } — flat
    () => {
      const item = (data as any)?.items?.[0];
      return item?.url ? { url: item.url, format: item.format ?? "gif" } : undefined;
    },
    // Pattern G: KLIPY v1 { data: [{ file: { sm: { gif: { url } } } }] }
    () => {
      const item = Array.isArray(data) ? (data[0] as any) : (data as any)?.data?.[0];
      const file = item?.file;
      if (!file) return undefined;
      const sizes = ["md", "sm", "xs", "hd"];
      const formats = ["gif", "webp", "png", "webm"];
      for (const size of sizes) {
        const bucket = file[size];
        if (!bucket) continue;
        for (const fmt of formats) {
          const entry = bucket[fmt];
          if (entry?.url) return { url: entry.url, format: fmt };
        }
      }
      return undefined;
    },
  ];

  for (const try_ of candidates) {
    const result = try_();
    if (result?.url) {
      return { url: result.url, format: result.format as KlipyMedia["format"] };
    }
  }

  if (process.env.NODE_ENV === "development") {
    console.warn("[KLIPY] could not parse media URL from response — check raw data above");
  }
  return null;
}

// ---------------------------------------------------------------------------
// Fetch
// ---------------------------------------------------------------------------

export async function fetchKlipyContent(
  api: ContentApi,
  query: string,
  locale: string | undefined,
  customerId: string,
): Promise<KlipyMedia | null> {
  if (!APP_KEY) {
    if (process.env.NODE_ENV === "development") {
      console.warn("[KLIPY] NEXT_PUBLIC_KLIPY_APP_KEY is not set");
    }
    return null;
  }

  const formatFilter =
    api === "static-memes"
      ? "webp,png"
      : api === "stickers"
        ? "webp,gif,webm,png"
        : "webp,gif,mp4,webm";

  const params = new URLSearchParams({
    q: query,
    customer_id: customerId,
    per_page: "1",
    content_filter: "medium",
    format_filter: formatFilter,
  });
  if (locale) params.set("locale", locale);

  const url = `${BASE_URL}/${APP_KEY}/${api}/search?${params}`;

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2000); // 2s timeout

    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timer);

    if (!res.ok) {
      if (process.env.NODE_ENV === "development") {
        console.warn(`[KLIPY] HTTP ${res.status} for ${url}`);
      }
      return null;
    }

    const json = await res.json();
    if (!json.result) return null;

    const media = extractMediaUrl(json.data);
    if (!media) return null;

    return {
      ...media,
      alt: query,
    };
  } catch {
    // Network error or timeout — silently skip
    return null;
  }
}
