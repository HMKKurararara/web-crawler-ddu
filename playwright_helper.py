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
            
            # Wait for pagination controls to load first!
            debug_log.append(f"Waiting for pagination controls to appear...")
            try:
                page.wait_for_selector(next_sel, state="visible", timeout=20000)
                debug_log.append(f"✓ Pagination controls loaded")
            except:
                debug_log.append(f"✗ Pagination controls did not appear within 20s")
                html_pages.append(page.content())
                return {"success": True, "html_pages": html_pages, "debug_log": debug_log}
            
            for i in range(max_pages):
                debug_log.append(f"=== Page {i+1}/{max_pages} ===")
                
                # Capture current page
                current_url = page.url
                current_html = page.content()
                html_pages.append(current_html)
                debug_log.append(f"Captured page {i+1}, HTML length: {len(current_html)}")
                debug_log.append(f"Current URL: {current_url}")
                
                # Get current data for comparison
                try:
                    current_cards = page.locator('.card.entity').all_inner_texts()
                    debug_log.append(f"Found {len(current_cards)} data cards")
                    if len(current_cards) > 0:
                        debug_log.append(f"First card: {current_cards[0][:60]}...")
                except:
                    current_cards = []
                
                # Check if last page
                if i == max_pages - 1:
                    debug_log.append(f"Reached max_pages limit")
                    break
                
                # Check if button exists and is enabled
                try:
                    button_count = page.locator(next_sel).count()
                    if button_count == 0:
                        debug_log.append(f"No next button found, stopping")
                        break
                    
                    is_disabled = page.locator(next_sel).first.get_attribute("disabled")
                    if is_disabled:
                        debug_log.append(f"Next button disabled, last page reached")
                        break
                    
                    # THE KEY FIX: Wait for network response
                    debug_log.append(f"Clicking next and waiting for network response...")
                    
                    # Set up response listener BEFORE clicking
                    with page.expect_response(lambda response: response.status == 200 and ("/api/" in response.url or "/directory/" in response.url), timeout=30000) as response_info:
                        # Click the button
                        page.click(next_sel, force=True)
                        debug_log.append(f"✓ Clicked next button")
                    
                    # Response received
                    response = response_info.value
                    debug_log.append(f"✓ Got response from: {response.url}")
                    
                    # Wait for Vue to process the response and re-render
                    debug_log.append(f"Waiting for Vue.js to re-render...")
                    time.sleep(3)  # Give Vue time to process
                    
                    # Verify data actually changed
                    try:
                        new_cards = page.locator('.card.entity').all_inner_texts()
                        if new_cards != current_cards and len(new_cards) > 0:
                            debug_log.append(f"✓ Data changed! Now have {len(new_cards)} cards")
                            if len(new_cards) > 0:
                                debug_log.append(f"New first card: {new_cards[0][:60]}...")
                        else:
                            debug_log.append(f"⚠ Warning: Response received but data looks same")
                            debug_log.append(f"This might be a duplicate or cache issue")
                    except Exception as e:
                        debug_log.append(f"Could not verify data change: {str(e)}")
                    
                    # Additional wait for full rendering
                    time.sleep(wait_time)
                    debug_log.append(f"✓ Page {i+2} ready")
                    
                except Exception as e:
                    debug_log.append(f"✗ Error during navigation: {str(e)}")
                    debug_log.append(f"This usually means no network response was received")
                    debug_log.append(f"Possible reasons: no more pages, or response timeout")
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
