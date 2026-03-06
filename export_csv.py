import argparse
import sys
import os
import re
import csv

def parse_enriched_file(filepath):
    leads = []
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return leads
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    blocks = content.split('-'*40)
    
    for block in blocks:
        block = block.strip()
        if not block or block.startswith("Enriched Leads"):
            continue
            
        lead = {
            "name": "", "rating": "", "phone": "", 
            "website": "", "address": "", "emails": "",
            "social_media": "", "score": "", "gmb": ""
        }
        
        for line in block.split('\n'):
            line = line.strip()
            if line.startswith("Name:"): lead["name"] = line.replace("Name:", "").strip()
            elif line.startswith("Rating/Reviews:"): lead["rating"] = line.replace("Rating/Reviews:", "").strip()
            elif line.startswith("Phone:"): lead["phone"] = line.replace("Phone:", "").strip()
            elif line.startswith("Website:"): lead["website"] = line.replace("Website:", "").strip()
            elif line.startswith("Address:"): lead["address"] = line.replace("Address:", "").strip()
            elif line.startswith("Emails:"): lead["emails"] = line.replace("Emails:", "").strip()
            elif line.startswith("Social Media:"): lead["social_media"] = line.replace("Social Media:", "").strip()
            elif line.startswith("Lead Score"): lead["score"] = line.split(":", 1)[1].strip() if ":" in line else line
            elif line.startswith("GMB URL:"): lead["gmb"] = line.replace("GMB URL:", "").strip()
            
        leads.append(lead)
        
    return leads

def categorize_socials(social_str):
    socials = {
        "facebook": "",
        "instagram": "",
        "tiktok": "",
        "linkedin": "",
        "twitter_x": "",
        "youtube": ""
    }
    
    if not social_str or social_str == "None found":
        return socials
        
    links = [link.strip() for link in social_str.split(',')]
    
    for link in links:
        link_lower = link.lower()
        if "facebook.com" in link_lower:
            socials["facebook"] = link
        elif "instagram.com" in link_lower:
            socials["instagram"] = link
        elif "tiktok.com" in link_lower:
            socials["tiktok"] = link
        elif "linkedin.com" in link_lower:
            socials["linkedin"] = link
        elif "twitter.com" in link_lower or "x.com" in link_lower:
            socials["twitter_x"] = link
        elif "youtube.com" in link_lower:
            socials["youtube"] = link
            
    return socials

def export_to_csv(input_path, output_path):
    print(f"Reading enriched leads from {input_path}...")
    leads = parse_enriched_file(input_path)
    
    if not leads:
        print("No leads found or file does not exist. Aborting export.")
        return
        
    print(f"Parsed {len(leads)} leads. Formatting for CSV...")
    
    headers = [
        "Name", "Website", "Phone", "Email", "Score", "Rating/Reviews",
        "Facebook", "Instagram", "TikTok", "X (Twitter)", "LinkedIn", "YouTube",
        "Address", "GMB URL"
    ]
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        
        for lead in leads:
            socials = categorize_socials(lead["social_media"])
            row = [
                lead["name"],
                lead["website"] if lead["website"] != "N/A" else "",
                lead["phone"] if lead["phone"] != "N/A" else "",
                lead["emails"] if lead["emails"] != "None found" else "",
                lead["score"] if lead["score"] else "1/5",
                lead["rating"] if lead["rating"] != "N/A" else "",
                socials["facebook"],
                socials["instagram"],
                socials["tiktok"],
                socials["twitter_x"],
                socials["linkedin"],
                socials["youtube"],
                lead["address"] if lead["address"] != "N/A" else "",
                lead["gmb"] if lead["gmb"] != "N/A" else ""
            ]
            writer.writerow(row)
            
    print(f"Successfully exported {len(leads)} leads to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export enriched text leads to CSV format.")
    parser.add_argument("--input", type=str, default=".tmp/enriched_leads.txt", help="Input file path")
    parser.add_argument("--output", type=str, default=".tmp/leads_export.csv", help="Output CSV path")
    args = parser.parse_args()
    
    export_to_csv(args.input, args.output)
