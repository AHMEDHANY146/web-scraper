from playwright.sync_api import sync_playwright
from config import BASE_URL

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    test_page_num = 5
    page.goto(f"{BASE_URL}/en/car/page/{test_page_num}")
    page.wait_for_timeout(5000)

    links = page.locator("a.no-underline").evaluate_all(
        "elements => elements.map(el => el.getAttribute('href'))"
    )
    
    valid_links = list(dict.fromkeys([
        l for l in links if l and "/showroom/" not in l
    ]))

    page.goto(f"{BASE_URL}{valid_links[12]}")
    page.wait_for_timeout(5000)

    overview = page.locator("#listing-overview")
    title = overview.locator("h1").inner_text().strip()

    specs = overview.locator("span.font-medium").all_inner_texts()
    year = specs[0]
    km = specs[1]
    transmission = specs[2]
    fuel = specs[3]

    price = overview.locator("span.text-primary-800").first.inner_text()
    price = int(price.replace(",", "").replace("EGP", "").strip())

    description = page.locator("#description").inner_text().strip()

    details = page.locator("#car-details .flex")

    
    data = {}

    for item in details.all():
        cols = item.locator("div")

        if cols.count() == 2:
            key = cols.nth(0).inner_text().strip()
            value = cols.nth(1).inner_text().strip()

            data[key] = value
    
    
    features = {}

    feature_container = page.locator("h2#features + div")
    sections = feature_container.locator(".grid > div > .flex.flex-col.gap-2")

    for section in sections.all():
        section_title = section.locator("span.font-bold").first.inner_text().strip()
        items = section.locator("span.text-sm:not(.font-bold)").all_inner_texts()
        features[section_title] = [item.strip() for item in items]        

    print({
    "title": title,
    "year": year,
    "km": km,
    "transmission": transmission,
    "fuel": fuel,
    "price": price,
    "description": description,
    "details": data,
    "features": features
})

    browser.close()

