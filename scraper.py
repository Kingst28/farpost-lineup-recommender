#!/usr/bin/env python3
"""
Script to scrape Premier League attacking stats from The Analyst using Browserbase
Works on GitHub Codespaces
"""

import asyncio
import csv
import os
from datetime import datetime
from browserbase import Browserbase

# Initialize Browserbase client
client = Browserbase(api_key=os.environ.get('BROWSERBASE_API_KEY'))

async def scrape_attacking_stats():
    """
    Scrape all attacking stats from The Analyst Premier League stats page
    across all available pages and save to CSV
    """
    
    all_stats = []
    base_url = "https://theanalyst.com/competition/premier-league/stats"
    
    async with client.session() as session:
        # Navigate to the page
        print("🌐 Navigating to The Analyst Premier League stats page...")
        await session.goto(base_url)
        
        # Wait for page to load
        await session.wait_for_timeout(3000)
        
        # Close privacy consent dialog if present
        try:
            print("🔒 Closing privacy consent dialog...")
            await session.evaluate("""
                const buttons = document.querySelectorAll('button');
                for (let btn of buttons) {
                    if (btn.textContent.includes('Deny all')) {
                        btn.click();
                        break;
                    }
                }
            """)
            await session.wait_for_timeout(2000)
        except Exception as e:
            print(f"⚠️  Could not close privacy dialog: {e}")
        
        # Get total number of pages
        print("📊 Determining total number of pages...")
        page_info = await session.evaluate("""
            const pageText = document.querySelector('[role="status"]')?.textContent || '';
            const match = pageText.match(/of (\\d+)/);
            return match ? parseInt(match[1]) : 1;
        """)
        
        total_pages = page_info if isinstance(page_info, int) else 1
        print(f"📄 Found {total_pages} pages of attacking stats")
        
        # Extract data from each page
        for page_num in range(1, total_pages + 1):
            print(f"\n📖 Extracting page {page_num} of {total_pages}...")
            
            # Wait for table to load
            await session.wait_for_timeout(2000)
            
            # Extract table data
            page_data = await session.evaluate("""
                const rows = document.querySelectorAll('table tbody tr');
                const data = [];
                
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length > 0) {
                        // Extract player name from the first cell
                        const nameCell = cells[0];
                        const playerName = nameCell.textContent.trim();
                        
                        // Extract all stat values
                        const stats = {
                            'Player': playerName,
                            'Apps': cells[1]?.textContent.trim() || '',
                            'Mins': cells[2]?.textContent.trim() || '',
                            'Goals': cells[3]?.textContent.trim() || '',
                            'xG': cells[4]?.textContent.trim() || '',
                            'Goals vs xG': cells[5]?.textContent.trim() || '',
                            'Shots': cells[6]?.textContent.trim() || '',
                            'SOT': cells[7]?.textContent.trim() || '',
                            'Conv %': cells[8]?.textContent.trim() || '',
                            'xG per Shot': cells[9]?.textContent.trim() || ''
                        };
                        data.push(stats);
                    }
                });
                
                return data;
            """)
            
            all_stats.extend(page_data)
            print(f"✅ Extracted {len(page_data)} players from page {page_num}")
            
            # Navigate to next page if not on last page
            if page_num < total_pages:
                print(f"➡️  Moving to next page...")
                try:
                    await session.evaluate("""
                        const nextButton = document.querySelector('button[aria-label*=">"]') || 
                                         Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('>'));
                        if (nextButton) {
                            nextButton.click();
                        }
                    """)
                    await session.wait_for_timeout(2000)
                except Exception as e:
                    print(f"⚠️  Could not navigate to next page: {e}")
                    break
    
    return all_stats

async def save_to_csv(data, filename="premier_league_attacking_stats.csv"):
    """
    Save extracted stats to CSV file
    """
    if not data:
        print("❌ No data to save")
        return
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'Player', 'Apps', 'Mins', 'Goals', 'xG', 'Goals vs xG',
                'Shots', 'SOT', 'Conv %', 'xG per Shot'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            writer.writerows(data)
        
        print(f"\n✅ Successfully saved {len(data)} players to {filename}")
        print(f"📁 File location: {os.path.abspath(filename)}")
        
    except Exception as e:
        print(f"❌ Error saving to CSV: {e}")

async def main():
    """
    Main function to orchestrate the scraping process
    """
    print("=" * 60)
    print("🏆 Premier League Attacking Stats Scraper")
    print("=" * 60)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        # Scrape the data
        stats_data = await scrape_attacking_stats()
        
        # Save to CSV
        await save_to_csv(stats_data)
        
        print("\n" + "=" * 60)
        print("✨ Scraping completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error during scraping: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())