import asyncio
import os
from stagehand import Stagehand, StagehandConfig
from dotenv import load_dotenv

load_dotenv()

# 1. Access keys from Codespaces Secrets
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BROWSERBASE_API_KEY = os.environ.get('BROWSERBASE_API_KEY')
BROWSERBASE_PROJECT_ID = os.environ.get('BROWSERBASE_PROJECT_ID')
MODEL_API_KEY = "B_cieHCZgOhPIH28jNaqYU8baY0rmvMwGySpm6YFqz9W1rnigrtKCTEWwS2ifZIRT7LPC9q3OfT3BlbkFJFL912sn3_CRzaQSlf1OSXWeV66_0UMIJ2bN-V1aRA7byqOLHy6c90-kMIvyB57xbYT2AhBGwQA"
# 1. Force the "Master" key variable that Stagehand looks for internally
# This is the specific fix for the "model_api_key is required" error

async def main():
    config = StagehandConfig(
        env="BROWSERBASE",
        api_key=BROWSERBASE_API_KEY,
        project_id=BROWSERBASE_PROJECT_ID,
        model_name="gpt-4o",
        model_api_key=MODEL_API_KEY
    )
    
    stagehand = Stagehand(config)
    
    try:
        await stagehand.init()
        page = stagehand.page
        
        await page.goto("https://docs.stagehand.dev/")
        await page.act("click the quickstart link")
        
        result = await page.extract("extract the main heading of the page")
        
        print(f"Extracted: {result}")
        
    finally:
        await stagehand.close()

if __name__ == "__main__":
    asyncio.run(main())