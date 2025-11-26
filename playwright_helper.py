#!/usr/bin/env python3
"""
Playwright Helper Script - Runs in subprocess to avoid threading conflicts.
Usage: python playwright_helper.py <url> <automation_json>
"""
import sys
import json
import time
import random # Added for stealth mode
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin

def human_scroll(page):
    """Scrolls the page like a human."""
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(random.uniform(0.5, 1.5))
    
    total_height = page.evaluate("document.body.scrollHeight")
    viewport_height = page.evaluate("window.innerHeight")
    current_scroll = 0
    
    while current_scroll < total_height:
        # Random scroll amount
        scroll_amount = random.randint(300, 700)
        current_scroll += scroll_amount
        page.evaluate(f"window.scrollTo(0, {current_scroll})")
        
        # Random pause
        time.sleep(random.uniform(0.2, 0.8))
        
        # Occasionally scroll up a bit
        if random.random() < 0.2:
            page.evaluate(f"window.scrollTo(0, {current_scroll - 100})")
            time.sleep(random.uniform(0.3, 0.7))

def human_mouse_move(page, start_x, start_y, end_x, end_y, steps=25):
    """Moves mouse in a curve (Bezier-like) to simulate human movement."""
    # Simple linear interpolation with noise for now
    for i in range(steps):
        t = i / steps
        # Add random noise
        noise_x = random.uniform(-5, 5)
        noise_y = random.uniform(-5, 5)
        
        x = start_x + (end_x - start_x) * t + noise_x
        y = start_y + (end_y - start_y) * t + noise_y
        
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.01, 0.03))
    
    # Final move to exact target
    page.mouse.move(end_x, end_y)

def run_playwright_automation(url, use_proxy=None, automation_config=None):
    debug_log = []
    html_pages = []
    
    playwright = sync_playwright().start()
    
    # Stealth args
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-infobars",
        "--start-maximized"
    ]
    if use_proxy:
        args.append(f"--proxy-server={use_proxy}")

    browser = playwright.chromium.launch(
        headless=True,  # Set to False if you want to see it (helps debugging)
        args=args
    )
    
    # Create context with stealth headers
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        locale="en-US",
        timezone_id="Asia/Singapore"
    )
    
    # Add stealth scripts
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)
    
    page = context.new_page()
    
    try:
        debug_log.append(f"Navigating to {url}...")
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        
        # Random initial wait
        time.sleep(random.uniform(2, 4))
        
        # Human scroll to trigger lazy loading
        human_scroll(page)
        
        # Wait for content
        wait_time = automation_config.get("wait_time", 10)
        time.sleep(wait_time)
        
        automation_type = automation_config.get("type", "single")
        
        if automation_type == "single":
            html_pages.append(page.content())
            
        elif automation_type == "pagination":
            max_pages = automation_config.get("max_pages", 5)
            
            debug_log.append(f"Starting STEALTH pagination, max_pages: {max_pages}")
            
            # Wait for pagination controls
            debug_log.append(f"Waiting for pagination controls...")
            try:
                page.wait_for_selector(".v-pagination__item", state="visible", timeout=20000)
                debug_log.append(f"✓ Pagination controls loaded")
            except:
                debug_log.append(f"✗ Pagination controls did not appear")
                html_pages.append(page.content())
                return {"success": True, "html_pages": html_pages, "debug_log": debug_log}
            
            for page_num in range(1, max_pages + 1):
                debug_log.append(f"=== Page {page_num}/{max_pages} ===")
                
                # Capture current page
                current_html = page.content()
                html_pages.append(current_html)
                debug_log.append(f"Captured page {page_num}, HTML length: {len(current_html)}")
                
                # Check for Incapsula block
                if "Incapsula" in current_html or "Request unsuccessful" in current_html:
                    debug_log.append(f"⚠ DETECTED INCAPSULA BLOCK! Stopping.")
                    break
                
                # Get current cards
                try:
                    current_cards = page.locator('.card.entity').all_inner_texts()
                    debug_log.append(f"Found {len(current_cards)} data cards")
                    if len(current_cards) > 0:
                        debug_log.append(f"First card: {current_cards[0][:50]}...")
                    first_card_text = current_cards[0] if len(current_cards) > 0 else ""
                except:
                    current_cards = []
                    first_card_text = ""
                
                if page_num == max_pages:
                    debug_log.append(f"Reached max_pages limit")
                    break
                
                # Click the NEXT numbered page button (page_num + 1)
                next_page_num = page_num + 1
                debug_log.append(f"Looking for page {next_page_num} button...")
                
                # Scroll to bottom human-like
                debug_log.append(f"Scrolling to bottom...")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(random.uniform(1, 2))
                
                try:
                    # Find button robustly
                    pagination_items = page.locator('.v-pagination__item').all()
                    target_button = None
                    
                    for item in pagination_items:
                        text = item.inner_text().strip()
                        if text == str(next_page_num):
                            if item.get_attribute("type") == "button" or item.get_attribute("role") == "button":
                                target_button = item
                                break
                            btn = item.locator("button")
                            if btn.count() > 0:
                                target_button = btn.first
                                break
                            target_button = item
                            break
                    
                    if target_button:
                        debug_log.append(f"✓ Found target button for page {next_page_num}")
                        
                        try:
                            target_button.scroll_into_view_if_needed()
                            time.sleep(random.uniform(0.5, 1.0))
                            
                            box = target_button.bounding_box()
                            if box:
                                x = box["x"] + box["width"] / 2
                                y = box["y"] + box["height"] / 2
                                
                                # Add randomness to click target
                                x += random.uniform(-5, 5)
                                y += random.uniform(-5, 5)
                                
                                # Get current mouse position (approximate)
                                start_x = random.randint(0, 1920)
                                start_y = random.randint(0, 1080)
                                
                                debug_log.append(f"Human mouse move to {int(x)},{int(y)}...")
                                human_mouse_move(page, start_x, start_y, x, y)
                                
                                time.sleep(random.uniform(0.1, 0.3))
                                page.mouse.down()
                                time.sleep(random.uniform(0.05, 0.15))
                                page.mouse.up()
                                debug_log.append(f"✓ Performed human click")
                                page_button_clicked = True
                            else:
                                target_button.click(force=True)
                                page_button_clicked = True
                        except Exception as e:
                            debug_log.append(f"Click failed: {str(e)}")
                            target_button.click(force=True)
                            page_button_clicked = True
                    else:
                        debug_log.append(f"✗ Could not find page {next_page_num}")
                        break
                    
                    # Wait for cards to update
                    debug_log.append(f"Waiting for cards to update...")
                    cards_updated = False
                    
                    for attempt in range(30):
                        time.sleep(1)
                        try:
                            new_cards = page.locator('.card.entity').all_inner_texts()
                            if len(new_cards) > 0 and new_cards[0] != first_card_text:
                                debug_log.append(f"✓ Cards updated after {attempt+1}s!")
                                cards_updated = True
                                break
                        except:
                            pass
                    
                    if not cards_updated:
                        debug_log.append(f"✗ Cards did not update")
                        break
                    
                    # Random wait for rendering
                    time.sleep(wait_time + random.uniform(0, 2))
                    debug_log.append(f"✓ Page {next_page_num} ready")
                    
                except Exception as e:
                    debug_log.append(f"✗ Error: {str(e)}")
                    break
            
            debug_log.append(f"=== Pagination complete: {len(html_pages)} pages scraped ===")
            return {"success": True, "html_pages": html_pages, "debug_log": debug_log}
            
        elif automation_type == "list_detail":
            html_pages.append(page.content())
            detail_sel = automation_config.get("detail_selector")
            max_items = automation_config.get("max_items", 5)
            
            links = page.locator(detail_sel).all()
            urls_to_visit = []
            for link in links[:max_items]:
                href = link.get_attribute("href")
                if href:
                    urls_to_visit.append(href)
            
            for item_url in urls_to_visit:
                try:
                    if not item_url.startswith(("http", "https")):
                        item_url = urljoin(page.url, item_url)
                    page.goto(item_url, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(wait_time)
                    html_pages.append(page.content())
                except:
                    continue
        
        return {"success": True, "html_pages": html_pages}
        
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        context.close()
        browser.close()
        p.stop()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "Missing arguments"}))
        sys.exit(1)
    
    url = sys.argv[1]
    automation_json = sys.argv[2]
    
    try:
        automation_config = json.loads(automation_json)
    except:
        automation_config = {"type": "single"}
    
    result = fetch_with_playwright(url, automation_config)
    print(json.dumps(result))
