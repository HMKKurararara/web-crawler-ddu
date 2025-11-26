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
                    
                    # Get reference to first card element
                    first_card_text = current_cards[0] if len(current_cards) > 0 else ""
                    debug_log.append(f"Attempting to click Next button...")
                    
                    # Try multiple click strategies
                    next_button = page.locator(next_sel).first
                    
                    # Strategy 1: Scroll into view
                    try:
                        next_button.scroll_into_view_if_needed()
                        debug_log.append(f"✓ Scrolled button into view")
                        time.sleep(0.5)
                    except:
                        pass
                    
                    # Strategy 2: Try normal click first
                    try:
                        next_button.click(timeout=5000)
                        debug_log.append(f"✓ Normal click succeeded")
                    except:
                        # Strategy 3: Force click
                        try:
                            next_button.click(force=True, timeout=5000)
                            debug_log.append(f"✓ Force click succeeded")
                        except:
                            # Strategy 4: JavaScript click
                            page.evaluate(f"document.querySelector('{next_sel}').click()")
                            debug_log.append(f"✓ JavaScript click executed")
                    
                    # Check for loading indicator
                    debug_log.append(f"Checking for loading indicators...")
                    time.sleep(1)
                    
                    # Wait for cards to update
                    debug_log.append(f"Waiting for cards to update...")
                    cards_updated = False
                    
                    for attempt in range(35):  # 35 second timeout
                        time.sleep(1)
                        try:
                            # Check if cards changed
                            new_cards = page.locator('.card.entity').all_inner_texts()
                            
                            if len(new_cards) > 0:
                                # Check if ANY card is different
                                if new_cards[0] != first_card_text:
                                    debug_log.append(f"✓ First card changed after {attempt+1}s!")
                                    debug_log.append(f"Was: {first_card_text[:40]}...")
                                    debug_log.append(f"Now: {new_cards[0][:40]}...")
                                    cards_updated = True
                                    break
                                # Also check if the entire list is different
                                elif new_cards != current_cards:
                                    debug_log.append(f"✓ Card list changed after {attempt+1}s (different order/content)")
                                    cards_updated = True
                                    break
                        except Exception as e:
                            debug_log.append(f"Error checking cards at {attempt}s: {str(e)}")
                    
                    if not cards_updated:
                        debug_log.append(f"✗ Cards did NOT update after 35s")
                        debug_log.append(f"First card still shows: {first_card_text[:40] if first_card_text else 'N/A'}...")
                        
                        # One last check - maybe it's a timing issue
                        try:
                            final_cards = page.locator('.card.entity').all_inner_texts()
                            debug_log.append(f"Final check: {len(final_cards)} cards found")
                            if len(final_cards) > 0:
                                debug_log.append(f"Final first card: {final_cards[0][:40]}...")
                        except:
                            pass
                        
                        debug_log.append(f"Stopping pagination - likely last page or Vue.js click handler not working")
                        break
                    
                    # Wait for full rendering
                    time.sleep(wait_time)
                    debug_log.append(f"✓ Page {i+2} ready")
                    
                except Exception as e:
                    debug_log.append(f"✗ Error: {str(e)}")
                    import traceback
                    debug_log.append(f"Traceback: {traceback.format_exc()}")
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
