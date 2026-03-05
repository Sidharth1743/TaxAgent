from scrapling import Fetcher

Fetcher.configure(adaptive=True)

url = "https://www.taxtmi.com/article/detailed?id=11385&allSearchQueries=tax%20for%20freelancers"

fetcher = Fetcher()
response = fetcher.get(url)

title = response.css(".ques .title::text").get()
author = response.css(".ques .user-info .name::text").get()
date = response.css(".ques .date::text").get()

summary = response.css(".summary::text").get()

article = " ".join(response.css(".desc .text p::text").getall())

answers = []
for ans in response.css(".answer .text"):
    answers.append(" ".join(ans.css("p::text").getall()))

print("TITLE:", title)
print("AUTHOR:", author)
print("DATE:", date)

print("\nSUMMARY:")
print(summary)

print("\nARTICLE:")
print(article[:500])

print("\nANSWERS:")
print(answers)