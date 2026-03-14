"""
AI-powered web scraping agent for PropertyMonitor.ae
Uses Claude to intelligently navigate and extract property data.
"""

import asyncio
import random
import re
from playwright.async_api import async_playwright, Page
from anthropic import Anthropic
import config


class PropertyMonitorAgent:
    """AI-powered web scraping agent for PropertyMonitor.ae with anti-bot evasion."""
    
    def __init__(self):
        config.validate_config()
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.browser = None
        self.page = None
        self.context = None
        self.playwright = None
        
    async def initialize(self):
        """Launch browser with stealth settings."""
        self.playwright = await async_playwright().start()
        
        # Launch browser with anti-detection settings
        self.browser = await self.playwright.chromium.launch(
            headless=False,  # Visible browser for debugging
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        
        # Create context with realistic settings
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='Asia/Dubai',
        )
        
        # Disable webdriver flag to avoid detection
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        self.page = await self.context.new_page()
        
        # Set realistic timeout
        self.page.set_default_timeout(config.HUMAN_DELAYS['page_load_timeout'])
        
        print("✅ Browser initialized with anti-bot settings")
    
    async def human_delay(self, min_delay=None, max_delay=None):
        """Add random human-like delay between actions."""
        if min_delay is None:
            min_delay = config.HUMAN_DELAYS['min_action_delay']
        if max_delay is None:
            max_delay = config.HUMAN_DELAYS['max_action_delay']
        
        delay = random.uniform(min_delay, max_delay)
        await asyncio.sleep(delay)
    
    async def human_type(self, selector: str, text: str):
        """Type text with human-like delays between keystrokes."""
        element = await self.page.wait_for_selector(selector)
        await element.click()
        await self.human_delay(0.2, 0.5)
        
        for char in text:
            await element.type(char, delay=random.randint(50, 150))
        
        await self.human_delay(0.3, 0.7)
    
    async def login(self):
        """Log into PropertyMonitor.ae."""
        try:
            print("🔐 Navigating to PropertyMonitor.ae...")
            await self.page.goto('https://www.propertymonitor.ae/', wait_until='networkidle')
            await self.human_delay(2, 4)
            
            # Look for login button/link
            print("🔍 Looking for login option...")
            page_content = await self.page.content()
            
            # Use Claude to find login element
            login_selector = await self.ask_claude_for_selector(
                page_content,
                "Find the CSS selector for the login button or link. Return ONLY the selector, nothing else."
            )
            
            if login_selector:
                print(f"📍 Found login element: {login_selector}")
                await self.page.click(login_selector)
                await self.human_delay(1, 2)
            
            # Enter credentials
            print("✍️ Entering credentials...")
            
            # Find email field
            email_selector = await self.ask_claude_for_selector(
                await self.page.content(),
                "Find the CSS selector for the email/username input field. Return ONLY the selector."
            )
            
            if email_selector:
                await self.human_type(email_selector, config.PROPERTYMONITOR_EMAIL)
            
            # Find password field
            password_selector = await self.ask_claude_for_selector(
                await self.page.content(),
                "Find the CSS selector for the password input field. Return ONLY the selector."
            )
            
            if password_selector:
                await self.human_type(password_selector, config.PROPERTYMONITOR_PASSWORD)
            
            # Find submit button
            submit_selector = await self.ask_claude_for_selector(
                await self.page.content(),
                "Find the CSS selector for the login submit button. Return ONLY the selector."
            )
            
            if submit_selector:
                await self.page.click(submit_selector)
                await self.human_delay(3, 5)
            
            # Check if login successful
            await self.page.wait_for_load_state('networkidle')
            
            if 'login' not in self.page.url.lower():
                print("✅ Login successful!")
                return True
            else:
                print("❌ Login may have failed - still on login page")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False
    
    async def ask_claude_for_selector(self, html_content: str, question: str) -> str:
        """Use Claude to analyze HTML and return CSS selector."""
        try:
            # Truncate HTML if too large (keep first 50k chars)
            html_sample = html_content[:50000] if len(html_content) > 50000 else html_content
            
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": f"{question}\n\nHTML:\n{html_sample}"
                }]
            )
            
            selector = response.content[0].text.strip()
            # Remove any markdown code blocks
            selector = re.sub(r'```[\w]*\n?|```', '', selector).strip()
            return selector
            
        except Exception as e:
            print(f"⚠️ Claude selector error: {str(e)}")
            return None
    
    async def search_property(self, building_name: str):
        """Search for a property/building on the site."""
        try:
            print(f"🔍 Searching for: {building_name}")
            
            # Find search input
            search_selector = await self.ask_claude_for_selector(
                await self.page.content(),
                "Find the CSS selector for the main search input field. Return ONLY the selector."
            )
            
            if search_selector:
                await self.human_type(search_selector, building_name)
                await self.human_delay(1, 2)
                
                # Press Enter or click search button
                await self.page.keyboard.press('Enter')
                await self.human_delay(2, 4)
                
                await self.page.wait_for_load_state('networkidle')
                print("✅ Search completed")
                return True
            else:
                print("❌ Could not find search field")
                return False
                
        except Exception as e:
            print(f"❌ Search error: {str(e)}")
            return False
    
    async def navigate_to_section(self, section_name: str):
        """Navigate to a specific section (e.g., Service Charges, Transactions)."""
        try:
            print(f"🧭 Navigating to: {section_name}")
            
            nav_selector = await self.ask_claude_for_selector(
                await self.page.content(),
                f"Find the CSS selector for a navigation link or button related to '{section_name}'. Return ONLY the selector."
            )
            
            if nav_selector:
                await self.page.click(nav_selector)
                await self.human_delay(2, 3)
                await self.page.wait_for_load_state('networkidle')
                print(f"✅ Navigated to {section_name}")
                return True
            else:
                print(f"⚠️ Could not find navigation for: {section_name}")
                return False
                
        except Exception as e:
            print(f"❌ Navigation error: {str(e)}")
            return False
    
    async def extract_data(self, query: str):
        """Use Claude to extract specific data from current page."""
        try:
            page_content = await self.page.content()
            page_text = await self.page.inner_text('body')
            
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": f"""You are analyzing a PropertyMonitor.ae page about Dubai real estate.

User Question: {query}

Page Content (text only):
{page_text[:15000]}

Instructions:
1. Extract the answer to the user's question from this page content
2. If the information is not available, say "Information not found on current page"
3. Be specific and include numbers/values if present
4. Format monetary values with AED currency
5. Include dates if relevant to the query"""
                }]
            )
            
            answer = response.content[0].text.strip()
            return answer
            
        except Exception as e:
            print(f"❌ Extraction error: {str(e)}")
            return f"Error extracting data: {str(e)}"
    
    async def take_screenshot(self, filename: str = "screenshot.png"):
        """Take screenshot of current page for debugging."""
        try:
            await self.page.screenshot(path=filename)
            print(f"📸 Screenshot saved: {filename}")
            return filename
        except Exception as e:
            print(f"⚠️ Screenshot error: {str(e)}")
            return None
    
    async def research_query(self, query: str):
        """Process a natural language query about properties."""
        steps = []
        
        try:
            # Initialize browser
            await self.initialize()
            steps.append("✅ Browser launched")
            
            # Login
            login_success = await self.login()
            if not login_success:
                return {
                    'success': False,
                    'answer': 'Failed to log in to PropertyMonitor.ae. Please check credentials.',
                    'steps': steps
                }
            steps.append("✅ Logged in successfully")
            
            # Extract building name from query using Claude
            building_response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                messages=[{
                    "role": "user",
                    "content": f"""Extract the building/property name from this query: "{query}"

Return ONLY the building name, nothing else. 
Examples:
- "What's the service charge for Tiara?" -> Tiara
- "Show sales in Shoreline 10" -> Shoreline 10
- "Oceana rental transactions" -> Oceana

If no building name found, return "UNKNOWN"."""
                }]
            )
            
            building_name = building_response.content[0].text.strip()
            steps.append(f"📍 Identified building: {building_name}")
            
            if building_name != "UNKNOWN":
                # Search for building
                search_success = await self.search_property(building_name)
                if search_success:
                    steps.append(f"✅ Searched for: {building_name}")
                else:
                    steps.append(f"⚠️ Search may have failed for: {building_name}")
            
            # Determine if we need to navigate to a specific section
            section_response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=50,
                messages=[{
                    "role": "user",
                    "content": f"""What section of a real estate portal would have this info: "{query}"

Options: service charges, transactions, sales, rentals, overview, none
Return ONLY one option."""
                }]
            )
            
            section = section_response.content[0].text.strip().lower()
            
            if section != "none" and section != "overview":
                nav_success = await self.navigate_to_section(section)
                if nav_success:
                    steps.append(f"✅ Navigated to: {section}")
            
            # Extract answer
            await self.human_delay(2, 3)
            answer = await self.extract_data(query)
            steps.append("✅ Data extracted from page")
            
            return {
                'success': True,
                'answer': answer,
                'steps': steps,
                'building': building_name,
                'section': section
            }
            
        except Exception as e:
            steps.append(f"❌ Error: {str(e)}")
            return {
                'success': False,
                'answer': f'Error during research: {str(e)}',
                'steps': steps
            }
        
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Close browser and cleanup resources."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            print("🧹 Browser closed")
        except Exception as e:
            print(f"⚠️ Cleanup error: {str(e)}")


# Standalone test
if __name__ == "__main__":
    async def test():
        agent = PropertyMonitorAgent()
        result = await agent.research_query("What's the service charge for Tiara Residences?")
        print("\n" + "="*50)
        print("RESULT:", result)
    
    asyncio.run(test())
