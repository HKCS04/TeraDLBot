import re
from urllib.parse import parse_qs, urlparse
import requests
from tools import get_formatted_size

# Authentication cookie
COOKIE = {
    "COOKIE": """browserid=ECp8myR7LciVVyrKxhjseu5DsPlsBGfcO2llDtQXqlF9ol1xSxrOyu-zQOo=; __bid_n=18de05eca9a9ef426f4207; _ga=GA1.1.993333438.1714196932; ndus=Ye4ozFx5eHuiHedfAOmdECQ1cUYjXwfZF6VF4QbD; TSID=JmuRgIKcaPqMjlzvZE5wXOJD96SkO594; PANWEB=1; csrfToken=8nN5Q8Y5H71nPyC8NHxBYAcr; lang=en; __bid_n=18de05eca9a9ef426f4207; ndut_fmt=A66A9E7BD20D40C268FB5C44A4E512FB76288B038CE8454BBB5B6BA0DB474814; ab_sr=1.0.1_OWVhNGFjZjk2MTJjMjE4MWViNzJhZDZhYTFmYzc4YmU3YmM4YmE2YzM4OTlkNGFiYTgwMTU5YjExYzVkMmYyOWU3NjQ2MGY4OGU2NWFlN2VhMDVhM2EzMGFlNmVlY2YzODY4YWNlNTdiYzdkODllZGQyNzRmODFiMmYxMTA2NGQyYWM2NGQxN2UxNDA3YzlhMDZkNDJiNWE4YmM5NTkxOA==; ab_ymg_result={"data":"97e606d2561336895e6c204c4cefdda3f92fcb3da76591b45dff12f3686fa1cad214e650165788b6b308134b9d9630b87d3b7b925e4d6eff5c376d2a0616a7d075d125397d73a7d649719f13489133194f2afd96fe712df4def2120f7e123df403d77144b1fb1f7ef9cd2b2c34feda576a824304a7c66bc9bbf9482618a92b59","key_id":"66","sign":"a8e92f31"}; _ga_06ZNKL8C2E=GS1.1.1714281215.2.0.1714281219.56.0.0"""
}

def check_url_patterns(url):
    """
    Check if a given URL matches predefined patterns.
    """
    patterns = [
        r"mirrobox\.com",
        r"nephobox\.com",
        r"freeterabox\.com",
        r"1024tera\.com",
        r"4funbox\.com",
        r"terabox\.app",
        r"terabox\.com",
        r"momerybox\.com",
        r"tibibox\.com",
    ]

    return any(re.search(pattern, url) for pattern in patterns)


def extract_urls(string: str) -> list[str]:
    """
    Extract valid URLs from a given string.
    """
    pattern = r"(https?://\S+)"
    urls = re.findall(pattern, string)
    return [url for url in urls if check_url_patterns(url)]


def find_between(data: str, first: str, last: str) -> str | None:
    """
    Extract text between two substrings.
    """
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None


def extract_surl_from_url(url: str) -> str | None:
    """
    Extract the 'surl' parameter from a URL.
    """
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    return query_params.get("surl", [None])[0]


def fetch_data(url: str):
    """
    Fetch and process data from a Terabox URL.
    """
    session = requests.Session()
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Cookie": COOKIE,
        "DNT": "1",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ),
    }

    # Make initial request
    response = session.get(url, headers=headers)
    if response.status_code != 200:
        return {"error": "Failed to fetch initial URL"}

    # Extract required parameters
    default_thumbnail = find_between(response.text, 'og:image" content="', '"')
    logid = find_between(response.text, "dp-logid=", "&")
    jsToken = find_between(response.text, "fn%28%22", "%22%29")
    bdstoken = find_between(response.text, 'bdstoken":"', '"')
    shorturl = extract_surl_from_url(response.url)

    if not shorturl or not logid or not jsToken:
        return {"error": "Missing required parameters"}

    api_url = (
        f"https://www.terabox.app/share/list?app_id=250528&web=1&channel=0"
        f"&jsToken={jsToken}&dp-logid={logid}&page=1&num=20&by=name&order=asc"
        f"&shorturl={shorturl}&root=1"
    )

    # Fetch file list from API
    response = session.get(api_url, headers=headers)
    if response.status_code != 200:
        return {"error": "Failed to fetch API data"}

    try:
        response_json = response.json()
    except ValueError:
        return {"error": "Invalid JSON response"}

    if response_json.get("errno"):
        return {"error": "API returned an error", "errno": response_json["errno"]}

    file_list = response_json.get("list", [])
    if not file_list:
        return {"error": "No files found"}

    file_info = file_list[0]
    direct_link_response = session.head(file_info["dlink"], headers=headers)

    # Compile result data
    data = {
        "file_name": file_info.get("server_filename"),
        "link": file_info.get("dlink"),
        "direct_link": direct_link_response.headers.get("location"),
        "thumb": file_info.get("thumbs", {}).get("url3", default_thumbnail),
        "size": get_formatted_size(file_info.get("size", 0)),
        "sizebytes": file_info.get("size", 0),
    }

    return data


if __name__ == "__main__":
    test_url = "https://teraboxapp.com/s/1GV28I3ea5rR_oR_f6LZGwQ"
    result = fetch_data(test_url)
    print(result)
