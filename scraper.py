import requests
from dotenv import load_dotenv
import os
from config import PROGRESS_FILE, OUTPUT_DIR, OUTPUT_FILE, MAX_RETRIES, RETRY_DELAY, BASE_URL, LISTING_PATH, TOTAL_PAGES, BATCH_SIZE, CONCURRENCY
import json
import csv
import asyncio
from playwright.async_api import async_playwright
import time

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BROWSERLESS_API_KEY = os.getenv("BROWSERLESS_API_KEY")


async def get_browser_instance(p):
    """Factory to get either a local browser or a remote browserless instance."""
    if BROWSERLESS_API_KEY:
        # Re-enabling stealth=true to bypass Cloudflare and Bot Detection!
        ws_url = f"wss://chrome.browserless.io?token={BROWSERLESS_API_KEY}&stealth=true"
        print("Connecting to Browserless.io (Stealth Anti-Bot Mode)...")
        return await p.chromium.connect_over_cdp(ws_url)
    
    # Fallback to local chromium if no API key is set
    return await p.chromium.launch(headless=True)



def send_telegram_message(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram error:", e)


def send_telegram_file(file_path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            requests.post(url, data={"chat_id": CHAT_ID}, files={"document": f})
    except Exception as e:
        print("Telegram file error:", e)

#--------

def load_progress():
    """Load last-saved progress so we can resume after a crash."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_page": 0, "last_link_index": -1, "batch_count": 0}


def save_progress(page_num, link_index, batch_count):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "last_page": page_num,
                "last_link_index": link_index,
                "batch_count": batch_count,
            },
            f,
        )

def clear_progress():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)   


#----------------             

def flatten_car(car: dict) -> dict:
    """Flatten nested details/features into a single-level dict for CSV."""
    flat = {
        "title": car.get("title"),
        "year": car.get("year"),
        "km": car.get("km"),
        "transmission": car.get("transmission"),
        "fuel": car.get("fuel"),
        "price": car.get("price"),
        "description": car.get("description"),
        "url": car.get("url"),
    }

    # Flatten details dict → one column per key
    for key, value in car.get("details", {}).items():
        flat[f"detail_{key}"] = value

    # Flatten features dict → semicolon-separated string per category
    for category, items in car.get("features", {}).items():
        flat[f"feature_{category}"] = "; ".join(items)

    return flat

def write_csv_batch(batch_data: list[dict], batch_num: int) -> str:
    """Write a batch to its own CSV file and return the file path."""
    flat_rows = [flatten_car(car) for car in batch_data]

    # Collect all possible columns across every row in this batch
    all_columns = list(dict.fromkeys(col for row in flat_rows for col in row.keys()))

    file_path = os.path.join(OUTPUT_DIR, f"batch_{batch_num}.csv")
    with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_rows)

    return file_path

def merge_batches_to_final():
    """Merge all batch CSVs into one final clean CSV, then clean up batches."""
    batch_files = sorted(
        [
            os.path.join(OUTPUT_DIR, f)
            for f in os.listdir(OUTPUT_DIR)
            if f.startswith("batch_") and f.endswith(".csv")
        ]
    )

    if not batch_files:
        return

    # Collect all column names across all batches
    all_columns = []
    for bf in batch_files:
        with open(bf, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for col in reader.fieldnames or []:
                if col not in all_columns:
                    all_columns.append(col)

    final_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    with open(final_path, "w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=all_columns, extrasaction="ignore")
        writer.writeheader()
        for bf in batch_files:
            with open(bf, "r", encoding="utf-8-sig") as inp:
                reader = csv.DictReader(inp)
                for row in reader:
                    writer.writerow(row)

    # Clean up individual batch files
    for bf in batch_files:
        os.remove(bf)

    print(f"Final CSV saved → {final_path}")


#----------------          

async def scrape_page_links(page, page_num):
    """Scrape car listing links from a single page. Reuses existing browser page."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            await page.goto(
                f"{BASE_URL}{LISTING_PATH.format(page_num=page_num)}",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await page.wait_for_timeout(5000)

            links = await page.locator("a.no-underline").evaluate_all(
                "elements => elements.map(el => el.getAttribute('href'))"
            )
            
            # Filter valid car links and explicitly remove duplicates while preserving order
            valid_links = list(dict.fromkeys([
                l for l in links if l and "/showroom/" not in l
            ]))
            return valid_links
            
        except Exception as e:
            print(f"Page {page_num} attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"Skipping page {page_num} after {MAX_RETRIES} retries")
                return []


async def scrape_car_details(context, url, semaphore):
    """Scrape details of a single car concurrently within a semaphore limit."""
    async with semaphore:
        # Each concurrent job gets its own isolated page tab
        page = await context.new_page()
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await page.goto(
                    f"{BASE_URL}{url}",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await page.wait_for_timeout(5000)

                overview = page.locator("#listing-overview")
                title = (await overview.locator("h1").inner_text()).strip()

                specs = await overview.locator("span.font-medium").all_inner_texts()
                year = specs[0] if len(specs) > 0 else None
                km = specs[1] if len(specs) > 1 else None
                transmission = specs[2] if len(specs) > 2 else None
                fuel = specs[3] if len(specs) > 3 else None

                # Safely parse price
                try:
                    price_text = await overview.locator("span.text-primary-800").first.inner_text()
                    price = int(price_text.replace(",", "").replace("EGP", "").strip())
                except (ValueError, Exception):
                    price = None

                description_el = page.locator("#description")
                description = None
                if await description_el.count() > 0:
                    description = (await description_el.inner_text()).strip()

                # Car details table
                details_elements = page.locator("#car-details .flex")
                data = {}
                for item in await details_elements.all():
                    cols = item.locator("div")
                    if await cols.count() == 2:
                        key = (await cols.nth(0).inner_text()).strip()
                        value = (await cols.nth(1).inner_text()).strip()
                        data[key] = value

                # Features
                features = {}
                feature_container = page.locator("h2#features + div")
                if await feature_container.count() > 0:
                    sections = feature_container.locator(
                        ".grid > div > .flex.flex-col.gap-2"
                    )
                    for section in await sections.all():
                        section_title = (
                            await section.locator("span.font-bold").first.inner_text()
                        ).strip()
                        items = await section.locator(
                            "span.text-sm:not(.font-bold)"
                        ).all_inner_texts()
                        features[section_title] = [item.strip() for item in items]

                return {
                    "title": title,
                    "year": year,
                    "km": km,
                    "transmission": transmission,
                    "fuel": fuel,
                    "price": price,
                    "description": description,
                    "url": url,
                    "details": data,
                    "features": features,
                }

            except Exception as e:
                print(f"Car {url} attempt {attempt}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    print(f"Skipping car {url} after {MAX_RETRIES} retries")
                    return None
            
            finally:
                pass
                
        await page.close()


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    start_time = time.time()

    # Load resume state
    progress = load_progress()
    start_page = progress["last_page"] if progress["last_page"] > 0 else 1
    skip_links_before = progress["last_link_index"] + 1
    batch_count = progress["batch_count"]

    batch_data = []
    car_counter = 0
    current_page = start_page
    current_chunk_idx = 0

    is_resuming = progress["last_page"] > 0
    if is_resuming:
        send_telegram_message(
            f"Resuming scraping from page {start_page}, "
            f"link index {skip_links_before}, batch #{batch_count + 1}"
        )
    else:
        send_telegram_message("Scraping started")

    # Reuse a single browser instance for ALL pages & cars
    async with async_playwright() as p:
        
        try:
            for page_num in range(start_page, TOTAL_PAGES + 1):
                current_page = page_num
                print(f"Scraping page {page_num}/{TOTAL_PAGES}")
                
                # Open browser temporarily just to get links for this page
                list_browser = await get_browser_instance(p)
                list_context = await list_browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                list_page = await list_context.new_page()
                links = await scrape_page_links(list_page, page_num)
                await list_browser.close()

                # Process links in chunks based on BATCH_SIZE
                for i in range(0, len(links), BATCH_SIZE):
                    current_chunk_idx = i
                    
                    # Skip chunks we already scraped (resume case)
                    if page_num == start_page and i < skip_links_before:
                        continue

                    chunk_links = links[i:i + BATCH_SIZE]
                    print(f"Processing batch of {len(chunk_links)} links concurrently...")
                    

                    chunk_browser = await get_browser_instance(p)
                    chunk_context = await chunk_browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 720}
                    )
                    semaphore = asyncio.Semaphore(CONCURRENCY)
                    
                    # Create tasks for this chunk
                    tasks = [
                        scrape_car_details(chunk_context, link, semaphore) 
                        for link in chunk_links
                    ]
                    
                    # Run them concurrently
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Close the batch browser IMMEDIATELY to free ALL RAM
                    await chunk_browser.close()
                    
                    for res in results:
                        if isinstance(res, dict) and res is not None:
                            batch_data.append(res)
                            car_counter += 1
                        elif isinstance(res, Exception):
                            print(f"Exception during gathering: {res}")
                    
                    if batch_data:
                        batch_count += 1
                        file_path = write_csv_batch(batch_data, batch_count)
                        send_telegram_file(file_path)
                        print(f"Batch {batch_count} sent ({len(batch_data)} cars)")


                        save_progress(page_num, i + len(chunk_links) - 1, batch_count)
                        batch_data = []

            # Final remaining batch
            if batch_data:
                batch_count += 1
                file_path = write_csv_batch(batch_data, batch_count)
                send_telegram_file(file_path)
                print(f"Batch {batch_count} sent ({len(batch_data)} cars)")

            # Merge all batch CSVs into one final file
            merge_batches_to_final()

            # All done — clear progress file
            clear_progress()

            end_time = time.time()
            duration = end_time - start_time
            send_telegram_message(
                f"Scraping completed!\n"
                f"Cars scraped: {car_counter}\n"
                f"Batches sent: {batch_count}\n"
                f"Duration: {duration:.2f}s\n"
                f"Final file: {OUTPUT_FILE}"
            )

        except Exception as e:
            # Save progress so next run resumes from here
            if batch_data:
                batch_count += 1
                file_path = write_csv_batch(batch_data, batch_count)
                send_telegram_file(file_path)

            save_progress(current_page, current_chunk_idx, batch_count)
            print(f"Saved progress at page {current_page}, chunk offset {current_chunk_idx} before exit")

            send_telegram_message(
                f"Scraping crashed: {e}\nRun again to resume."
            )
            # Make sure we don't accidentally leave browsers running on unhandled crash exceptions
            try:
                if 'chunk_browser' in locals() and chunk_browser:
                    await chunk_browser.close()
                if 'list_browser' in locals() and list_browser:
                    await list_browser.close()
            except Exception:
                pass
            raise            

if __name__ == "__main__":
    asyncio.run(main())