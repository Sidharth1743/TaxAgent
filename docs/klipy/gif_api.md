Getting Started
Welcome to KLIPY API! KLIPY gives you lifetime access to a high-performance API for Clips, GIFs, Stickers, Memes and AI Emojis, designed to make your app more fun, expressive, and sticky. For platforms looking to generate revenue, our Ads API offers seamless monetization with high-fill programmatic & direct demand.

To get started, create an API key at: https://partner.klipy.com/

Leverage our Demo App Source Code to explore how KLIPY integrates with modern apps - with or without ads. It’s built to help you launch fast and scale smoothly with clean UX and minimal latency.

GIF API
The KLIPY GIF API gives you instant access to a curated, fast-loading library of trending and high-quality GIFs.

With a single integration, you can search, preview, and serve the most popular and localized GIFs in real time, delivering a smooth and engaging user experience across messaging, social apps, keyboards, and more.

All content is fully licensed and categorized, with support for tracking, personalization, and optional monetization via native ads.

Use this section to:

Fetch trending or recent GIFs
Search by keyword or tag
Browse by category
Track user interactions (views, shares, reports)


GIF - Trending API
import requests
import json

url = "https://api.klipy.com/api/v1/{app_key}/gifs/trending?page={page}&per_page={per_page}&customer_id={customer_id}&locale={locale}"

payload = {}
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)

Use this endpoint to fetch the most popular and viral GIFs of the moment, automatically tailored to your user’s language and location.

Trending content is updated throughout the day and optimized for engagement across social, messaging, and keyboard experiences.

To monetize this feature, check out the Advertisements section

See our Demo App Source Code for an example of Trending API integration.

Query Parameters
page
integer
The requested page number

Minimum
1
Default value
1
per_page
integer
The number of content items per page

Minimum
1
Maximum
50
Default value
24
customer_id
string
Required
A unique user identifier in your system. Please make sure that the value remains consistent for the same user.

locale
string
Country code / language of the customer ISO 3166 (ge; us; uk; ru etc) (Alpha-2) (https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2#Officially_assigned_code_elements)

format_filter
string
Comma-separated list of desired formats. Results will include only these formats, even if other formats exist. Possible values: gif, webp, jpg, mp4, webm.

Path Parameters
app_key
string
Required
The unique app key issued by KLIPY for your system

ResponseExpand all
200
Object
Response Attributes
result
boolean
data
object

GIF - Search API
import requests
import json

url = "https://api.klipy.com/api/v1/{app_key}/gifs/search?page={page}&per_page={per_page}&q={q}&customer_id={customer_id}&locale={country_code}&content_filter={content_filter}"

payload = {}
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)

Use this endpoint to search KLIPY’s full GIF library by keyword or phrase. Results are ranked by relevance, popularity, and language context to ensure highly engaging, localized results.

The search engine supports fuzzy matching, custom pagination, and optional content filters to help you deliver the right result in every user flow.

Looking to monetize your search results? See the Advertisements section

Query Parameters
page
integer
The requested page number

Minimum
1
Default value
1
per_page
integer
The number of content items per page

Minimum
8
Maximum
50
Default value
24
q
string
The search keyword for finding relevant items

customer_id
string
Required
A unique user identifier in your system. Please make sure that the value remains consistent for the same user.

locale
string
Country code / language of the customer ISO 3166 (ge; us; uk; ru etc) (Alpha-2) (https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2#Officially_assigned_code_elements)

content_filter
string
Specify the content safety filter level. The accepted values are off, low, medium, and high.

format_filter
string
Comma-separated list of desired formats. Results will include only these formats, even if other formats exist. Possible values: gif, webp, jpg, mp4, webm.

Path Parameters
app_key
string
Required
The unique app key issued by KLIPY for your system

ResponseExpand all
200
Object
Response Attributes
result
boolean
data
object

Query Parameters
locale
string
Language of the user in xx_YY format, where: xx is the ISO 639-1 (https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes#Table) two-letter language code and YY is the ISO 3166-1 (https://en.wikipedia.org/wiki/ISO_3166-1#Codes) alpha-2 two-letter country code

Path Parameters
app_key
string
Required
The unique app key issued by KLIPY for your system

ResponseExpand all
200
Object
Response Attributes
result
boolean
data
object

import requests
import json

url = "https://api.klipy.com/api/v1/{app_key}/gifs/categories?locale={country_code}"

payload = {}
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)

GIF - Categories API
Use this endpoint to retrieve a list of curated categories that group KLIPY GIFs by common themes, moods, and reactions.

Categories can be shown as buttons, filters, or tabs in your UI, and are fully compatible with the Search API to help users discover content faster.

See our Demo App Source Code for an example of category-based integration.

Query Parameters
locale
string
Language of the user in xx_YY format, where: xx is the ISO 639-1 (https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes#Table) two-letter language code and YY is the ISO 3166-1 (https://en.wikipedia.org/wiki/ISO_3166-1#Codes) alpha-2 two-letter country code

Path Parameters
app_key
string
Required
The unique app key issued by KLIPY for your system

ResponseExpand all
200
Object
Response Attributes
result
boolean
data
object
Show child attributes

| Size | File format | Mean file size (KB) | Median file size (KB) |
| ---- | ----------- | ------------------- | --------------------- |
| hd   | gif         | 3874                | 2578                  |
| hd   | webp        | 755                 | 288                   |
| hd   | webm        | 136                 | 94                    |
| hd   | mp4         | 492                 | 295                   |
| hd   | jpg         | 19                  | 16                    |
| xs   | gif         | 101                 | 64                    |
| xs   | webp        | 51                  | 35                    |
| xs   | webm        | 45                  | 37                    |
| xs   | mp4         | 37                  | 31                    |
| xs   | jpg         | 2                   | 2                     |
| sm   | gif         | 330                 | 206                   |
| sm   | webp        | 178                 | 117                   |
| sm   | webm        | 74                  | 60                    |
| sm   | mp4         | 98                  | 85                    |
| sm   | jpg         | 7                   | 6                     |
| md   | gif         | 2263                | 1405                  |
| md   | webp        | 988                 | 636                   |
| md   | webm        | 136                 | 94                    |
| md   | mp4         | 444                 | 257                   |
| md   | jpg         | 20                  | 19                    |
