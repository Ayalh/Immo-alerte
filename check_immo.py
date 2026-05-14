#!/usr/bin/env python3
import json, base64, urllib.request, urllib.error, gzip, os, traceback

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPOSITORY", "Ayalh/immo-alerte")
STATE_FILE   = "seen_listings.json"

BIENVEO_URL  = "https://www.bienveo.fr/rechercher?distance=0km&maxBudget=250000&nbRooms=2&nbRooms=3&nbRooms=4&nbRooms=5&place=HAUTS-DE-SEINE%3A92&place=SEINE-SAINT-DENIS%3A93&place=VAL-DE-MARNE%3A94&tab=PURCHASE&type=Appartement&type=Maison"
HAVITAT_BASE = "https://www.havitat.fr/api/havitat_search/api/v2?locations=Hauts-de-Seine%2B92%2CSeine-Saint-Denis%2B93%2CVal-de-Marne%2B94&budget_max=250000&type_bien=f-appart%2Cf-maison&rooms=2%2C3%2C4%2C5%2C6&etat_bien=ancien"

def http_get_html(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    req.add_header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
    req.add_header("Accept-Language", "fr-FR,fr;q=0.9")
    req.add_header("Accept-Encoding", "gzip, deflate")
    req.add_header("Referer", "https://www.bienveo.fr/")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8")

def http_get_json(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")

def github_api(path, data=None, method="GET"):
    req = urllib.request.Request(f"https://api.github.com{path}", data=data, method=method)
    req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def get_state():
    data = github_api(f"/repos/{GITHUB_REPO}/contents/{STATE_FILE}")
    state = json.loads(base64.b64decode(data["content"]).decode())
    return state, data["sha"]

def update_state(state, sha):
    content = base64.b64encode(json.dumps(state).encode()).decode()
    github_api(f"/repos/{GITHUB_REPO}/contents/{STATE_FILE}",
               data=json.dumps({"message": "Update seen listings", "content": content, "sha": sha}).encode(),
               method="PUT")

def create_issue(new_bienveo, new_havitat):
    total = len(new_bienveo) + len(new_havitat)
    if total == 0:
        return
    title = f"[Immo Alerte] {total} nouveau(x) bien(s) - 92/93/94"
    lines = []
    if new_bienveo:
        lines.append("## BIENVEO.FR")
        for l in new_bienveo:
            lines.append(f"### {l['title']}")
            lines.append(f"- **Prix :** {l['price']} EUR")
            lines.append(f"- **Type :** {l['type']}")
            lines.append(f"- **Lien :** {l['url']}")
            lines.append("")
    if new_havitat:
        lines.append("## HAVITAT.FR")
        for l in new_havitat:
            lines.append(f"### {l['title']}")
            lines.append(f"- **Prix :** {l['price']} EUR")
            lines.append(f"- **Ville :** {l['ville']}")
            lines.append(f"- **Lien :** {l['url']}")
            lines.append("")
    result = github_api(f"/repos/{GITHUB_REPO}/issues",
                        data=json.dumps({"title": title, "body": "\n".join(lines)}).encode(),
                        method="POST")
    print(f"Issue creee: #{result['number']} - {result['html_url']}")

def fetch_bienveo():
    html = http_get_html(BIENVEO_URL)
    idx = html.find("__NEXT_DATA__")
    if idx < 0:
        return []
    start = html.index("{", idx)
    end = html.index("</script>", start)
    data = json.loads(html[start:end])
    hits = data["props"]["pageProps"]["defaultSearchResponse"]["hits"]["hits"]
    listings = []
    for h in hits:
        src = h["_source"]
        listings.append({
            "id": str(src.get("id", "")),
            "title": src.get("title", "Sans titre"),
            "price": src.get("price", 0),
            "type": src.get("type", ""),
            "url": f"https://www.bienveo.fr/annonce/{src.get('id', '')}"
        })
    return listings

def fetch_havitat():
    listings = []
    page = 1
    while True:
        data = json.loads(http_get_json(f"{HAVITAT_BASE}&page={page}"))
        for item in data.get("data", []):
            listings.append({
                "id": item["node_url"],
                "title": item.get("description", "Sans titre"),
                "price": item.get("price", 0),
                "type": item.get("housing_type", ""),
                "ville": item.get("ville", ""),
                "url": f"https://www.havitat.fr{item['node_url']}"
            })
        if page >= data.get("pagination", {}).get("pages", 1):
            break
        page += 1
    return listings

try:
    state, sha = get_state()
    seen_bienveo = set(state.get("bienveo", []))
    seen_havitat = set(state.get("havitat", []))

    bienveo_all = fetch_bienveo()
    print(f"Bienveo: {len(bienveo_all)} annonces")

    havitat_all = fetch_havitat()
    print(f"Havitat: {len(havitat_all)} annonces")

    new_bienveo = [l for l in bienveo_all if l["id"] not in seen_bienveo]
    new_havitat = [l for l in havitat_all if l["id"] not in seen_havitat]
    print(f"Nouveaux: {len(new_bienveo)} bienveo + {len(new_havitat)} havitat")

    create_issue(new_bienveo, new_havitat)

    state["bienveo"] = list(seen_bienveo | {l["id"] for l in bienveo_all})
    state["havitat"] = list(seen_havitat | {l["id"] for l in havitat_all})
    update_state(state, sha)
    print("Etat mis a jour")

except Exception:
    err = traceback.format_exc()
    print(f"ERREUR:\n{err}")
    try:
        github_api(f"/repos/{GITHUB_REPO}/issues",
                   data=json.dumps({"title": "[Immo Alerte] ERREUR agent", "body": f"```\n{err}\n```"}).encode(),
                   method="POST")
    except Exception:
        pass
    raise
