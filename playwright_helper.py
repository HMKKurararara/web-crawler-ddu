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
                
                # Capture current page content
                current_html = page.content()
                html_pages.append(current_html)
                debug_log.append(f"Captured page {i+1}, HTML length: {len(current_html)}")
                
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
                    
                    # Try JavaScript click (more reliable for Vue.js)
                    js_click_script = f"""
                    const button = document.querySelector('{next_sel}');
                    if (button) {{
                        button.click();
                        true;
                    }} else {{
                        false;
                    }}
                    """
                    
                    clicked = page.evaluate(js_click_script)
                    debug_log.append(f"JavaScript click result: {clicked}")
                    
                    if not clicked:
                        debug_log.append(f"JavaScript click failed, trying Playwright click")
                        # Fallback to Playwright click
                        page.locator(next_sel).first.click(force=True)
                        debug_log.append(f"Playwright click executed")
                    
                    # Wait for content to change
                    debug_log.append(f"Waiting for content to change...")
                    content_changed = False
                    
                    for wait_attempt in range(30):  # 30 seconds max
                        time.sleep(1)
                        new_html = page.content()
                        if new_html != current_html:
                            debug_log.append(f"✓ Content changed after {wait_attempt+1}s")
                            content_changed = True
                            break
                    
                    if not content_changed:
                        debug_log.append(f"✗ WARNING: Content did NOT change after 30s!")
                        debug_log.append(f"This usually means the click didn't work or there are no more pages")
                        break
                    
                    # Additional wait for Vue.js rendering
                    debug_log.append(f"Waiting {wait_time}s for rendering...")
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
