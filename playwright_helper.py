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
            next_sel = automation_config.get("next_selector")
            debug_log = []
            
            debug_log.append(f"Starting pagination: {next_sel}, max_pages: {max_pages}")
            
            # CRITICAL: Wait for pagination controls to load first!
            debug_log.append(f"Waiting for pagination controls to appear...")
            try:
                page.wait_for_selector(next_sel, state="visible", timeout=20000)
                debug_log.append(f"✓ Pagination controls loaded")
            except:
                debug_log.append(f"✗ Pagination controls did not appear within 20s")
                debug_log.append(f"This might mean the page has only 1 page, or wait_time needs to be longer")
                # Still try to scrape the current page
                html_pages.append(page.content())
                return {"success": True, "html_pages": html_pages, "debug_log": debug_log}
            
            for i in range(max_pages):
                debug_log.append(f"=== Page {i+1}/{max_pages} ===")
                
                # Capture current page content and URL
                current_url = page.url
                
                # Get current data cards to compare (more reliable than full HTML)
                try:
                    current_cards = page.locator('.card.entity').all_inner_texts()
                    debug_log.append(f"Found {len(current_cards)} data cards on page {i+1}")
                    if len(current_cards) > 0:
                        debug_log.append(f"First card text preview: {current_cards[0][:50]}...")
                except:
                    current_cards = []
                
                # Capture full HTML
                current_html = page.content()
                html_pages.append(current_html)
                debug_log.append(f"Captured page {i+1}, HTML length: {len(current_html)}")
                debug_log.append(f"Current URL: {current_url}")
                
                # Check if this is the last page
                if i == max_pages - 1:
                    debug_log.append(f"Reached max_pages limit")
                    break
                
                # Try to find and click next button using JavaScript
                try:
                    # Check if button exists
                    button_count = page.locator(next_sel).count()
                    debug_log.append(f"Found {button_count} buttons matching '{next_sel}'")
                    
                    if button_count == 0:
                        debug_log.append(f"No next button found, stopping")
                        break
                    
                    # Check if button is disabled
                    is_disabled = page.locator(next_sel).first.get_attribute("disabled")
                    if is_disabled:
                        debug_log.append(f"Next button is disabled, we've reached the last page")
                        break
                    
                    # Use JavaScript click
                    js_click_script = f"""
                    const button = document.querySelector('{next_sel}');
                    if (button && !button.disabled) {{
                        button.click();
                        true;
                    }} else {{
                        false;
                    }}
                    """
                    
                    clicked = page.evaluate(js_click_script)
                    debug_log.append(f"JavaScript click result: {clicked}")
                    
                    if not clicked:
                        debug_log.append(f"Click failed, stopping")
                        break
                    
                    # Wait for DATA to change (not just HTML)
                    debug_log.append(f"Waiting for data cards to change...")
                    data_changed = False
                    
                    for wait_attempt in range(40):  # 40 seconds max
                        time.sleep(1)
                        try:
                            new_cards = page.locator('.card.entity').all_inner_texts()
                            # Compare the actual card data
                            if new_cards != current_cards and len(new_cards) > 0:
                                debug_log.append(f"✓ Data cards changed after {wait_attempt+1}s (was {len(current_cards)}, now {len(new_cards)} cards)")
                                if len(new_cards) > 0:
                                    debug_log.append(f"New first card preview: {new_cards[0][:50]}...")
                                data_changed = True
                                break
                        except:
                            pass  # Keep waiting
                    
                    if not data_changed:
                        debug_log.append(f"✗ WARNING: Data did NOT change after 40s!")
                        debug_log.append(f"Retrying with longer wait...")
                        time.sleep(10)  # Extra 10s wait
                        try:
                            final_cards = page.locator('.card.entity').all_inner_texts()
                            if final_cards != current_cards:
                                debug_log.append(f"✓ Data changed after extended wait")
                                data_changed = True
                        except:
                            pass
                        
                        if not data_changed:
                            debug_log.append(f"Click likely failed or no more pages. Stopping.")
                            break
                    
                    # Additional wait for full rendering
                    debug_log.append(f"Waiting {wait_time}s for full rendering...")
                    time.sleep(wait_time)
                    debug_log.append(f"✓ Page {i+2} ready")
                    
                except Exception as e:
                    debug_log.append(f"✗ Error: {str(e)}")
                    break
            
            debug_log.append(f"=== Pagination complete: {len(html_pages)} pages scraped ===")
            
            # Return debug log in the result
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
