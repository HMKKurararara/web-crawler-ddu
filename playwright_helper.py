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
            
            print(f"[PAGINATION] Starting pagination with selector: {next_sel}, max_pages: {max_pages}")
            
            for i in range(max_pages):
                print(f"[PAGINATION] Page {i+1}/{max_pages}")
                
                # Capture current page content
                current_html = page.content()
                html_pages.append(current_html)
                
                # Check for next button
                next_button = page.locator(next_sel)
                button_count = next_button.count()
                
                print(f"[PAGINATION] Found {button_count} next buttons")
                
                if button_count > 0:
                    is_visible = next_button.is_visible()
                    is_enabled = next_button.is_enabled()
                    print(f"[PAGINATION] Button visible: {is_visible}, enabled: {is_enabled}")
                    
                    if is_visible and is_enabled:
                        try:
                            # Scroll button into view first
                            next_button.scroll_into_view_if_needed()
                            time.sleep(0.5)
                            
                            # Try force click (bypasses actionability checks)
                            print(f"[PAGINATION] Clicking next button...")
                            next_button.click(force=True)
                            
                            # Wait for content to change
                            print(f"[PAGINATION] Waiting for content to change...")
                            content_changed = False
                            for wait_attempt in range(25):  # 25 seconds max
                                time.sleep(1)
                                new_html = page.content()
                                if new_html != current_html:
                                    print(f"[PAGINATION] Content changed after {wait_attempt+1}s")
                                    content_changed = True
                                    break
                            
                            if not content_changed:
                                print(f"[PAGINATION] WARNING: Content did not change after clicking!")
                                break
                            
                            # Additional wait for rendering
                            print(f"[PAGINATION] Waiting {wait_time}s for rendering...")
                            time.sleep(wait_time)
                            print(f"[PAGINATION] Page {i+2} ready")
                            
                        except Exception as e:
                            print(f"[PAGINATION] Error clicking next: {str(e)}")
                            break
                    else:
                        print(f"[PAGINATION] Button not clickable, stopping")
                        break
                else:
                    print(f"[PAGINATION] No next button found, stopping")
                    break
            
            print(f"[PAGINATION] Completed. Total pages: {len(html_pages)}")                
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
