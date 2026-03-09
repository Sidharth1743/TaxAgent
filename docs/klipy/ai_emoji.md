AI Emoji - Trending API
import requests
import json

url = "https://api.klipy.com/api/v1/{app_key}/emojis/trending?page={page}&per_page={per_page}&customer_id={customer_id}&locale={locale}"

payload = {}
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)

Use this endpoint to retrieve trending AI Emojis tailored to the user's language and time of day. This helps surface relevant, high-engagement content. Include a customer_id to improve personalization and pass locale for language-aware ranking.

To request an Ad alongside the results, refer to the Advertisements section

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

AI Emoji - Search API
import requests
import json

url = "https://api.klipy.com/api/v1/{app_key}/emojis/search?page={page}&per_page={per_page}&q={q}&customer_id={customer_id}&locale={country_code}&content_filter={content_filter}"

payload = {}
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)

Use this endpoint to search for AI Emojis in KLIPY's database based on a keyword query. You can personalize results by passing a stable customer_id, localize them with the locale parameter, and apply content filters for safe browsing.

To display an ad with search results, refer to the Advertisements section

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
The search keyword for finding relevant Memes

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


AI Emoji - Categories API
import requests
import json

url = "https://api.klipy.com/api/v1/{app_key}/emojis/categories?locale={country_code}"

payload = {}
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)

Use this endpoint to fetch all available AI Emoji categories from KLIPY. These categories can be used to power UI filters, improve discovery, or be paired with the AI Emoji Search API for contextual queries.

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
| hd   | webp        | 29                  | 24                    |
| hd   | png         | 76                  | 69                    |
| sm   | webp        | 10                  | 9                     |
| sm   | png         | 27                  | 25                    |
| md   | webp        | 30                  | 26                    |
| md   | png         | 90                  | 89                    |
| xs   | webp        | 3                   | 2                     |
| xs   | png         | 6                   | 6                     |
