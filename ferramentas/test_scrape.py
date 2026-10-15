import hardware_control as hc
import urllib.request, re

news = hc.search_realtime_news("Catanduva SP")
print(f"Total news found: {len(news)}")
if news:
    first = news[0]
    print("Title:", first["title"])
    print("URL:", first["url"])
    det = hc.fetch_article_details(first["url"])
    print("Scraped Image:", det.get("image_url"))
    print("Scraped Source:", det.get("source"))
    print("Scraped Paragraphs count:", len(det.get("paragraphs", [])))
    if det.get("paragraphs"):
        print("First paragraph:", det["paragraphs"][0][:150])
