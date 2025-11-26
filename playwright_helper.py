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
        
        wait_time = automation_config.get("wait_time", 3)
        automation_type = automation_config.get("type", "single")
        
        if automation_type == "single":
            time.sleep(wait_time)
            html_pages.append(page.content())
            
        elif automation_type == "pagination":
            max_pages = automation_config.get("max_pages", 5)
            next_sel = automation_config.get("next_selector")
            
            for i in range(max_pages):
                html_pages.append(page.content())
                if page.locator(next_sel).count() > 0 and page.locator(next_sel).is_visible():
                    try:
                        with page.expect_navigation(timeout=5000):
                            page.click(next_sel)
                        time.sleep(wait_time)
                    except:
                        break
                else:
                    break
                    
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
