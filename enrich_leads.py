import argparse
import sys
import os
import re
import time

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("Error: playwright is not installed.", file=sys.stderr)
    sys.exit(1)

def is_valid_email(email):
    invalid_domains = ['example.com', 'sentry.io', 'wix.com', 'domain.com']
    invalid_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']
    domain = email.split('@')[-1].lower()
    
    if domain in invalid_domains:
        return False
    
    for ext in invalid_extensions:
        if email.lower().endswith(ext):
            return False
            
    # Basic structural check
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return False
        
    return True

def extract_social_links(html):
    socials = set()
    
    # Common regex patterns to scrape href links pointing to social platforms
    facebook_pattern = re.compile(r'href=["\'](?:https?://)?(?:www\.)?(facebook\.com/[^"\']+)["\']', re.IGNORECASE)
    instagram_pattern = re.compile(r'href=["\'](?:https?://)?(?:www\.)?(instagram\.com/[^"\']+)["\']', re.IGNORECASE)
    tiktok_pattern = re.compile(r'href=["\'](?:https?://)?(?:www\.)?(tiktok\.com/@[^"\']+)["\']', re.IGNORECASE)
    linkedin_pattern = re.compile(r'href=["\'](?:https?://)?(?:www\.)?(linkedin\.com/(?:company|in)/[^"\']+)["\']', re.IGNORECASE)
    twitter_pattern = re.compile(r'href=["\'](?:https?://)?(?:www\.)?((?:twitter\.com|x\.com)/[^"\']+)["\']', re.IGNORECASE)
    youtube_pattern = re.compile(r'href=["\'](?:https?://)?(?:www\.)?(youtube\.com/channel/[^"\']+|youtube\.com/c/[^"\']+|youtube\.com/@[^"\']+)["\']', re.IGNORECASE)
    
    for match in facebook_pattern.findall(html): socials.add("https://" + match)
    for match in instagram_pattern.findall(html): socials.add("https://" + match)
    for match in tiktok_pattern.findall(html): socials.add("https://" + match)
    for match in linkedin_pattern.findall(html): socials.add("https://" + match)
    for match in twitter_pattern.findall(html): socials.add("https://" + match)
    for match in youtube_pattern.findall(html): socials.add("https://" + match)
        
    return list(socials)

def parse_leads_file(filepath):
    leads = []
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return leads
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    blocks = content.split('-'*40)
    
    for block in blocks:
        block = block.strip()
        if not block or block.startswith("Scrape Results for"):
            continue
            
        lead = {
            "name": "N/A", "rating": "N/A", "phone": "N/A", 
            "website": "N/A", "address": "N/A", "gmb": "N/A",
            "raw": block
        }
        
        for line in block.split('\n'):
            line = line.strip()
            if line.startswith("Name:"): lead["name"] = line.replace("Name:", "").strip()
            elif line.startswith("Rating/Reviews:"): lead["rating"] = line.replace("Rating/Reviews:", "").strip()
            elif line.startswith("Phone:"): lead["phone"] = line.replace("Phone:", "").strip()
            elif line.startswith("Website:"): lead["website"] = line.replace("Website:", "").strip()
            elif line.startswith("Address:"): lead["address"] = line.replace("Address:", "").strip()
            elif line.startswith("GMB URL:"): lead["gmb"] = line.replace("GMB URL:", "").strip()
            elif lead["phone"] == "" and line.startswith("+"): lead["phone"] = line.strip()
            elif lead["address"] == "" and line: lead["address"] = line.strip()
            
        leads.append(lead)
        
    return leads

def enrich_leads(input_path: str, output_path: str):
    print(f"Starting enrichment from {input_path}...")
    
    leads = parse_leads_file(input_path)
    
    if not leads:
        print("No leads found to enrich.")
        return
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
        )
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"Enriched Leads\n")
            f.write(f"{'-'*40}\n\n")
            
        for idx, lead in enumerate(leads, 1):
            name = lead["name"]
            website = lead["website"]
            print(f"[{idx}/{len(leads)}] Enriching: {name} ({website})")
            
            emails = set()
            socials = []
            
            # Baseline score: 1 if it's considered a service business 
            # (Assuming leads from the file are valid service businesses)
            score = 1
            
            if website != "N/A" and website.startswith("http"):
                page = context.new_page()
                try:
                    # Timeout after 20 secs
                    page.goto(website, timeout=20000)
                    time.sleep(2) # Give a short delay for JS execution
                    
                    html_content = page.content()
                    
                    # 1. Look for emails using regex across the source code
                    #    Also check mailto: links specifically
                    email_pattern = re.compile(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')
                    for match in email_pattern.findall(html_content):
                        if is_valid_email(match): emails.add(match)
                        
                    # Broad fallback email regex
                    broad_email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')
                    for match in broad_email_pattern.findall(html_content):
                        if is_valid_email(match): emails.add(match.lower())
                        
                    # 2. Extract social links
                    socials = extract_social_links(html_content)
                    
                except Exception as e:
                    print(f"  -> Error fetching {website}: {type(e).__name__} - {e}")
                finally:
                    page.close()
                    
            if emails:
                score += 3
            if socials:
                score += 1
                
            email_str = ", ".join(emails) if emails else "None found"
            socials_str = ", ".join(socials) if socials else "None found"
            
            enriched_data = (
                f"Name: {lead['name']}\n"
                f"Rating/Reviews: {lead['rating']}\n"
                f"Phone: {lead['phone']}\n"
                f"Website: {lead['website']}\n"
                f"Address: {lead['address']}\n"
                f"Emails: {email_str}\n"
                f"Social Media: {socials_str}\n"
                f"Lead Score (1-5): {score}/5\n"
                f"GMB URL: {lead['gmb']}\n"
                f"{'-'*40}\n"
            )
            
            with open(output_path, "a", encoding="utf-8") as f:
                f.write(enriched_data + "\n")
                
            time.sleep(1) # Be nice
            
        browser.close()
        
    print(f"Enrichment completed! Saved to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich GMB leads with emails and socials.")
    parser.add_argument("--input", type=str, default=".tmp/gmb_leads.txt", help="Input file path")
    parser.add_argument("--output", type=str, default=".tmp/enriched_leads.txt", help="Output file path")
    args = parser.parse_args()
    
    enrich_leads(args.input, args.output)
