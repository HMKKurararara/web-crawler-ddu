#!/usr/bin/env python3
"""
Playwright Helper Script - Runs in subprocess to avoid threading conflicts.
Usage: python playwright_helper.py <url> <automation_json>
"""
import sys
import json
import time
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin

def fetch_with_playwright(url, automation_config):
    """Fetch content using Playwright."""
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    context = browser.new_context()
    page = context.new_page()
    html_pages = []
    
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("body", state="visible", timeout=10000)
        
        wait_time = automation_config.get("wait_time", 10)
        automation_type = automation_config.get("type", "single")
        
        if automation_type == "single":
            time.sleep(wait_time)
            html_pages.append(page.content())
            
        elif automation_type == "pagination":
            max_pages = automation_config.get("max_pages", 5)
            debug_log = []
            
            debug_log.append(f"Starting NUMBERED BUTTON pagination, max_pages: {max_pages}")
            
            # Wait for pagination controls to load first!
            debug_log.append(f"Waiting for pagination controls to appear...")
            try:
                page.wait_for_selector(".v-pagination__item", state="visible", timeout=20000)
                debug_log.append(f"✓ Pagination controls loaded")
            except:
                debug_log.append(f"✗ Pagination controls did not appear within 20s")
                html_pages.append(page.content())
                return {"success": True, "html_pages": html_pages, "debug_log": debug_log}
            
            for page_num in range(1, max_pages + 1):
                debug_log.append(f"=== Page {page_num}/{max_pages} ===")
                
                # Capture current page
                current_url = page.url
                current_html = page.content()
                html_pages.append(current_html)
                debug_log.append(f"Captured page {page_num}, HTML length: {len(current_html)}")
                
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
                
                # Check if this is the last page
                if page_num == max_pages:
                    debug_log.append(f"Reached max_pages limit")
                    break
                
                # Click the NEXT numbered page button (page_num + 1)
                next_page_num = page_num + 1
                debug_log.append(f"Looking for page {next_page_num} button...")
                
                try:
                    # Find button by text content  
                    button_selector = f"button.v-pagination__item:has-text('{next_page_num}')"
                    button = page.locator(button_selector)
                    
                    if button.count() > 0:
                        debug_log.append(f"✓ Found page {next_page_num} button")
                        button.first.click(timeout=5000)
                        debug_log.append(f"✓ Clicked page {next_page_num}")
                        page_button_clicked = True
                    else:
                        # Fallback: JavaScript
                        debug_log.append(f"Trying JavaScript...")
                        js_script = f"""
                        const buttons = document.querySelectorAll('.v-pagination__item');
                        for (let btn of buttons) {{
                            if (btn.textContent.trim() === '{next_page_num}') {{
                                btn.click();
                                return true;
                            }}
                        }}
                        return false;
                        """
                        clicked = page.evaluate(js_script)
                        if clicked:
                            debug_log.append(f"✓ JS clicked page {next_page_num}")
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
                                debug_log.append(f"Was: {first_card_text[:35]}...")
                                debug_log.append(f"Now: {new_cards[0][:35]}...")
                                cards_updated = True
                                break
                        except:
                            pass
                    
                    if not cards_updated:
                        debug_log.append(f"✗ Cards did not update")
                        break
                    
                    # Wait for rendering
                    time.sleep(wait_time)
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
