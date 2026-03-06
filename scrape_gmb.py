import argparse
import sys
import os
import time

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("Error: playwright is not installed. Please run `pip install playwright` and `playwright install chromium`.", file=sys.stderr)
    sys.exit(1)

def scrape_gmb_profiles(query: str, limit: int, output_path: str):
    print(f"Starting GMB Scraper for query: '{query}' with limit {limit}")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    leads = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        # Navigate to Google Maps search directly
        search_query = query.replace(" ", "+")
        search_url = f"https://www.google.com/maps/search/{search_query}?hl=en"
        print(f"Navigating to {search_url}...")
        page.goto(search_url, timeout=60000)
        
        # Agree to cookies if prompted
        try:
            agree_button = page.locator('button:has-text("Accept all"), button:has-text("I agree")')
            if agree_button.count() > 0:
                agree_button.first.click()
                time.sleep(2)
        except:
            pass
        
        # Wait for the results pane to load
        try:
            page.wait_for_selector('div[role="feed"]', timeout=15000)
        except PlaywrightTimeoutError:
            print("Could not find the results feed. Possibly no results or a layout change.")
            browser.close()
            return

        print("Results loaded. Scraping...")
        
        # A selector that typically matches individual result links in the side panel
        listing_selector = 'a[class*="hfpxzc"]'
        
        # Scroll and gather listings
        listings_found = set()
        listing_urls = []
        
        feed_element = page.locator('div[role="feed"]')
        
        scroll_attempts = 0
        no_new_results_count = 0
        previous_len = 0
        
        # Google Maps can take many scrolls to load 1000 items. Often it caps at ~120-300 anyway.
        while len(listing_urls) < limit and scroll_attempts < 200:
            current_elements = page.locator(listing_selector).all()
            for el in current_elements:
                try:
                    url = el.get_attribute("href")
                    if url:
                        # Force english URL to make scraping predictable
                        if "hl=" in url:
                            import re
                            url = re.sub(r'hl=[^&]+', 'hl=en', url)
                        else:
                            url += "&hl=en"
                            
                        if url not in listings_found:
                            listings_found.add(url)
                            listing_urls.append(url)
                            if len(listing_urls) >= limit:
                                break
                except:
                    pass
            
            if len(listing_urls) >= limit:
                break
                
            # Check if we didn't find any new items in this scroll
            if len(listing_urls) == previous_len:
                no_new_results_count += 1
            else:
                no_new_results_count = 0
                
            # If we scroll 5 times and get no new items, we are probably at the end of the list.
            if no_new_results_count >= 5:
                print(f"Reached the end of available listings. Found {len(listing_urls)} total.")
                break
                
            previous_len = len(listing_urls)
            
            # Focus on the last element to scroll down
            if current_elements:
                try:
                    current_elements[-1].scroll_into_view_if_needed()
                    time.sleep(2) # Wait for network load
                except:
                    pass
            
            scroll_attempts += 1
            
        print(f"Found {len(listing_urls)} listings. Extracting details...")
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"Scrape Results for '{query}'\n")
            f.write(f"{'-'*40}\n\n")

        for idx, url in enumerate(listing_urls[:limit], 1):
            print(f"Processing {idx}/{len(listing_urls[:limit])}...")
            
            # Open a new page for each detail to keep it clean
            detail_page = context.new_page()
            try:
                detail_page.goto(url, timeout=30000)
                detail_page.wait_for_selector('h1', timeout=10000)
                time.sleep(1) # Extra buffer for elements to render
                
                # Extract details
                name = "N/A"
                if detail_page.locator('h1').count() > 0:
                    name = detail_page.locator('h1').first.inner_text().strip()
                
                rating = "N/A"
                if detail_page.locator('div.F7nice').count() > 0:
                    rating_text = detail_page.locator('div.F7nice').first.inner_text().replace('\n', ' ')
                    rating = rating_text.strip()
                    
                phone = "N/A"
                if detail_page.locator('button[data-tooltip="Copy phone number"]').count() > 0:
                    phone = detail_page.locator('button[data-tooltip="Copy phone number"]').first.inner_text().strip()
                
                website = "N/A"
                if detail_page.locator('a[data-tooltip="Open website"]').count() > 0:
                    website = detail_page.locator('a[data-tooltip="Open website"]').first.get_attribute("href")
                elif detail_page.locator('a[data-item-id="authority"]').count() > 0:
                    website = detail_page.locator('a[data-item-id="authority"]').first.get_attribute("href")
                    
                address = "N/A"
                if detail_page.locator('button[data-tooltip="Copy address"]').count() > 0:
                    address = detail_page.locator('button[data-tooltip="Copy address"]').first.inner_text().strip()
                
                lead_data = (
                    f"Name: {name}\n"
                    f"Rating/Reviews: {rating}\n"
                    f"Phone: {phone}\n"
                    f"Website: {website}\n"
                    f"Address: {address}\n"
                    f"GMB URL: {url}\n"
                    f"{'-'*40}\n"
                )
                
                # Write continuously to save progress
                with open(output_path, "a", encoding="utf-8") as f:
                    f.write(lead_data + "\n")
                    
            except Exception as e:
                print(f"Error scraping a listing: {e}")
                
            finally:
                detail_page.close()
                time.sleep(1) # Small delay to not get blocked
                
        browser.close()
        
    print(f"Scraping completed! Results saved to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape GMB profiles for leads.")
    parser.add_argument("--query", type=str, required=True, help="Search query for Google Maps")
    parser.add_argument("--limit", type=int, default=5, help="Number of listings to extract")
    parser.add_argument("--output", type=str, default=".tmp/gmb_leads.txt", help="Output path for raw leads")
    args = parser.parse_args()
    
    scrape_gmb_profiles(args.query, args.limit, args.output)
