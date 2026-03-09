# KLIPY API Reference

## Base URL
```
https://api.klipy.com/api/v1/{app_key}
```

## Auth
- `app_key` — path parameter in every URL (get yours at https://partner.klipy.com/)
- No headers required beyond `Content-Type: application/json`

---

## Content Types & Endpoints

### 1. GIFs
| Action | URL |
|--------|-----|
| Search | `GET /{app_key}/gifs/search?q={q}&customer_id={id}&locale={locale}` |
| Trending | `GET /{app_key}/gifs/trending?customer_id={id}&locale={locale}` |
| Categories | `GET /{app_key}/gifs/categories?locale={locale}` |

**Available formats:** gif, webp, webm, mp4, jpg
**Available sizes:** hd, md, sm, xs

File size reference (sm):
- sm/gif ~330 KB median | sm/webp ~178 KB median | sm/webm ~74 KB | sm/mp4 ~98 KB

### 2. Memes (static images)
| Action | URL |
|--------|-----|
| Search | `GET /{app_key}/static-memes/search?q={q}&customer_id={id}&locale={locale}` |
| Trending | `GET /{app_key}/static-memes/trending?customer_id={id}&locale={locale}` |
| Categories | `GET /{app_key}/static-memes/categories?locale={locale}` |

**Available formats:** webp, png (static — no video)
**Available sizes:** hd, md, sm, xs

File size reference (sm):
- sm/webp ~10 KB median | sm/png ~27 KB median

### 3. Stickers
| Action | URL |
|--------|-----|
| Search | `GET /{app_key}/stickers/search?q={q}&customer_id={id}&locale={locale}` |
| Trending | `GET /{app_key}/stickers/trending?customer_id={id}&locale={locale}` |
| Categories | `GET /{app_key}/stickers/categories?locale={locale}` |

**Available formats:** gif, webp, webm, png
**Available sizes:** hd, md, sm, xs

File size reference (sm):
- sm/gif ~159 KB | sm/webp ~97 KB | sm/webm ~250 KB | sm/png ~6 KB

### 4. AI Emojis
| Action | URL |
|--------|-----|
| Search | `GET /{app_key}/emojis/search?q={q}&customer_id={id}&locale={locale}` |
| Trending | `GET /{app_key}/emojis/trending?customer_id={id}&locale={locale}` |
| Categories | `GET /{app_key}/emojis/categories?locale={locale}` |

**Available formats:** webp, png (static — no video)
**Available sizes:** hd, md, sm, xs

File size reference (sm):
- sm/webp ~10 KB | sm/png ~27 KB

### 5. Utilities
| Action | URL |
|--------|-----|
| Autocomplete | `GET /{app_key}/autocomplete/{q}?limit=10` |
| Search Suggestions | `GET /{app_key}/search-suggestions/{q}?limit=10` |

---

## Query Parameters

### All Search endpoints share these params:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | YES | Search keyword |
| `customer_id` | string | **YES** | Stable unique user ID in your system — keep consistent per user |
| `locale` | string | no | ISO 3166-1 Alpha-2 country code: `in`, `us`, `uk`, `ru`, etc. Enables localized/regional content |
| `content_filter` | string | no | `off` / `low` / `medium` / `high` |
| `format_filter` | string | no | Comma-separated: `gif,webp` — restrict to these formats only |
| `page` | integer | no | Default: 1, min: 1 |
| `per_page` | integer | no | Default: 24, min: 8, max: 50 |

### All Trending endpoints share these params:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `customer_id` | string | **YES** | Same as above |
| `locale` | string | no | Same as above |
| `page` / `per_page` | integer | no | Same as above |

---

## Response Shape

All endpoints return:
```json
{
  "result": true,
  "data": { ... }
}
```

> ⚠️ **The internal structure of `data` is NOT documented.** Must be discovered by calling the API and inspecting the raw response. Common GIF API patterns to try:
> - `data.items[0].images.sm.webp.url`
> - `data.items[0].images.sm.gif.url`
> - `data[0].sm.url`
> - `data.results[0].url`
> - `data.items[0].url`

---

## Recommended Setup for TaxClarity

**For the 240px chat card, use `sm` size + `webp` format:**
- Memes: sm/webp ~10 KB — extremely lightweight
- GIFs: sm/webp ~178 KB — acceptable
- Stickers: sm/webp ~97 KB — acceptable

**Locale mapping:**
- India context → `locale=in`
- US context → `locale=us`
- Global/cross-border → omit locale

**customer_id:** Use the session's `userId` (already available as `userId.current` in `tax-app.tsx`)

**Example search URL:**
```
GET https://api.klipy.com/api/v1/MY_APP_KEY/static-memes/search
  ?q=math+lady+confused
  &customer_id=user_abc123
  &locale=in
  &per_page=1
  &format_filter=webp
  &content_filter=medium
```
