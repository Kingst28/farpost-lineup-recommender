#!/usr/bin/env python3
"""
Premier League Attacking Stats Scraper
Extracts all attacking statistics from theanalyst.com and saves to CSV
Compatible with GitHub CodeSpaces
"""

import csv
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import os
import sys

def setup_driver():
    """Setup Chrome WebDriver with headless options for CodeSpaces"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def close_privacy_dialog(driver):
    """Close the privacy consent dialog if present"""
    try:
        deny_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Deny all')]"))
        )
        deny_button.click()
        time.sleep(1)
        print("✓ Privacy dialog closed")
    except Exception as e:
        print(f"⚠ Privacy dialog not found or already closed: {e}")

def extract_player_stats(driver):
    """Extract all player stats from the current page"""
    players_data = []
    
    try:
        # Wait for table to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//table//tbody//tr"))
        )
        
        # Get all rows from the table
        rows = driver.find_elements(By.XPATH, "//table//tbody//tr")
        
        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                
                if len(cells) >= 10:
                    # Extract player name from the first cell
                    name_element = cells[0].find_element(By.TAG_NAME, "a")
                    player_name = name_element.text.strip()
                    
                    # Extract all stats
                    stats = {
                        'Player Name': player_name,
                        'Apps': cells[1].text.strip(),
                        'Mins': cells[2].text.strip(),
                        'Goals': cells[3].text.strip(),
                        'xG': cells[4].text.strip(),
                        'Goals vs xG': cells[5].text.strip(),
                        'Shots': cells[6].text.strip(),
                        'SOT': cells[7].text.strip(),
                        'Conv %': cells[8].text.strip(),
                        'xG per Shot': cells[9].text.strip(),
                    }
                    
                    players_data.append(stats)
                    print(f"  ✓ {player_name}")
                    
            except Exception as e:
                print(f"  ⚠ Error extracting row: {e}")
                continue
        
        return players_data
    
    except Exception as e:
        print(f"✗ Error extracting stats: {e}")
        return []

def get_total_pages(driver):
    """Get the total number of pages"""
    try:
        pagination_text = driver.find_element(By.XPATH, "//span[contains(text(), 'of')]").text
        total_pages = int(pagination_text.split('of')[1].strip())
        return total_pages
    except Exception as e:
        print(f"⚠ Could not determine total pages: {e}")
        return 1

def go_to_next_page(driver):
    """Click the next page button"""
    try:
        next_button = driver.find_element(By.XPATH, "//button[contains(text(), '>')]")
        next_button.click()
        time.sleep(2)  # Wait for page to load
        return True
    except Exception as e:
        print(f"⚠ Could not navigate to next page: {e}")
        return False

def scrape_all_pages(driver, url):
    """Scrape all pages of attacking stats"""
    all_players = []
    
    # Navigate to the URL
    print(f"🔗 Navigating to {url}...")
    driver.get(url)
    time.sleep(3)
    
    # Close privacy dialog
    close_privacy_dialog(driver)
    
    # Get total pages
    total_pages = get_total_pages(driver)
    print(f"📊 Found {total_pages} pages of data\n")
    
    # Scrape each page
    for page_num in range(1, total_pages + 1):
        print(f"📄 Scraping page {page_num}/{total_pages}...")
        
        # Extract stats from current page
        page_data = extract_player_stats(driver)
        all_players.extend(page_data)
        
        print(f"  ✓ Extracted {len(page_data)} players from page {page_num}\n")
        
        # Go to next page if not the last page
        if page_num < total_pages:
            if not go_to_next_page(driver):
                print(f"⚠ Could not navigate to page {page_num + 1}, stopping scrape")
                break
    
    return all_players

def save_to_csv(data, filename='premier_league_attacking_stats.csv'):
    """Save player data to CSV file"""
    if not data:
        print("✗ No data to save")
        return False
    
    try:
        # Define CSV columns
        fieldnames = [
            'Player Name', 'Apps', 'Mins', 'Goals', 'xG', 'Goals vs xG',
            'Shots', 'SOT', 'Conv %', 'xG per Shot'
        ]
        
        # Write to CSV
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        print(f"\n✓ Successfully saved {len(data)} players to {filename}")
        return True
    
    except Exception as e:
        print(f"✗ Error saving to CSV: {e}")
        return False

def main():
    """Main execution function"""
    url = "https://theanalyst.com/competition/premier-league/stats"
    output_file = "premier_league_attacking_stats.csv"
    
    driver = None
    
    try:
        print("=" * 60)
        print("Premier League Attacking Stats Scraper")
        print("=" * 60 + "\n")
        
        # Setup driver
        print("🚀 Starting Chrome WebDriver...")
        driver = setup_driver()
        
        # Scrape all pages
        all_players = scrape_all_pages(driver, url)
        
        # Save to CSV
        if all_players:
            save_to_csv(all_players, output_file)
            print(f"\n📁 Output file: {os.path.abspath(output_file)}")
            print(f"📈 Total players scraped: {len(all_players)}")
        else:
            print("\n✗ No data was scraped")
            return 1
        
        print("\n" + "=" * 60)
        print("✓ Scraping completed successfully!")
        print("=" * 60)
        return 0
    
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        return 1
    
    finally:
        if driver:
            print("\n🔌 Closing WebDriver...")
            driver.quit()

if __name__ == "__main__":
    sys.exit(main())