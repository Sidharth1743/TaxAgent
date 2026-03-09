Sticker - Trending API
import requests
import json

url = "https://api.klipy.com/api/v1/{app_key}/stickers/trending?page={page}&per_page={per_page}&customer_id={customer_id}&locale={locale}"

payload = {}
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)

Use this endpoint to fetch the most popular and high-performing Stickers of the moment, personalized by user language and location.

Trending results are refreshed throughout the day to boost engagement in keyboards, messaging apps, and social features.

Sticker - Search API
import requests
import json

url = "https://api.klipy.com/api/v1/{app_key}/stickers/search?page={page}&per_page={per_page}&q={q}&customer_id={customer_id}&locale={country_code}&content_filter={content_filter}"

payload = {}
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)

Use this endpoint to search KLIPY’s entire sticker library by keyword or phrase. Results are ranked by relevance, popularity, and language to deliver highly engaging and localized stickers.

Supports pagination, content filtering, and region-based boosting.

Looking to monetize search results? See the Advertisements section

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

Sticker - Categories API
import requests
import json

url = "https://api.klipy.com/api/v1/{app_key}/stickers/categories?locale={country_code}"

payload = {}
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)

Use this endpoint to retrieve a list of curated sticker categories, organized by emotion, action, or reaction.

These categories can be paired with the Search API to create filterable sticker experiences in your app.

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

| Size | File format | Mean file size (KB) | Median file size (KB) |
|-----|-------------|---------------------|-----------------------|
| hd  | gif  | 813 | 257 |
| hd  | webp | 247 | 111 |
| hd  | webm | 881 | 348 |
| hd  | png  | 23  | 15  |
| md  | gif  | 795 | 256 |
| md  | webp | 257 | 129 |
| md  | webm | 881 | 348 |
| md  | png  | 23  | 15  |
| sm  | gif  | 159 | 98  |
| sm  | webp | 97  | 58  |
| sm  | webm | 250 | 134 |
| sm  | png  | 6   | 5   |
| xs  | gif  | 41  | 31  |
| xs  | webp | 37  | 25  |
| xs  | webm | 72  | 44  |
| xs  | png  | 2   | 2   |