import re
import time
import random
from urllib.parse import urljoin, urlparse
from collections import Counter
import io
import json # Explicitly import json for the new extraction logic

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import streamlit as st
from bs4 import BeautifulSoup
from lxml import html as lxml_html # For XPath support

# ========== CONFIG & UTILS ==========

# A list of agents to rotate through to avoid basic bot detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
]

def get_random_header():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/"
    }

def clean_text(text: str) -> str:
    """Standardizes text cleaning."""
    if not text:
        return ""
    # Remove excessive whitespace
    return re.sub(r"\s+", " ", text).strip()

# ========== PLAYWRIGHT FETCH ENGINE ==========

def fetch_dynamic_content(url: str, automation: dict = None) -> list[str]:
    """
    Fetches content using Playwright via subprocess.
    This avoids threading conflicts with Streamlit.
    Returns a LIST of HTML strings.
    """
    import subprocess
    import os
    import sys
    
    # Get path to helper script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    helper_path = os.path.join(script_dir, "playwright_helper.py")
    
    # Prepare automation config
    if automation is None:
        automation = {"type": "single", "wait_time": 10}
    
    automation_json = json.dumps(automation)
    
    try:
        # Run Playwright in subprocess using the SAME Python interpreter
        result = subprocess.run(
            [sys.executable, helper_path, url, automation_json],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        
        if result.returncode != 0:
            raise Exception(f"Subprocess failed: {result.stderr}")
        
        # Parse JSON output
        output = json.loads(result.stdout)
        
        if not output.get("success"):
            raise Exception(output.get("error", "Unknown error"))
        
        return output.get("html_pages", [])
        
    except subprocess.TimeoutExpired:
        raise Exception("Playwright fetch timed out after 2 minutes")
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse Playwright output: {str(e)}")
    except Exception as e:
        raise e

# ========== FETCH ENGINE (CACHED) ==========

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_url_content(url: str, use_proxy: str = None, force_dynamic: bool = False, automation: dict = None):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    
    proxies = {"http": use_proxy, "https": use_proxy} if use_proxy else None
    
    # Force dynamic if automation is requested
    if force_dynamic or automation:
        if use_proxy:
             st.warning("Proxies are ignored for Playwright fetching in this basic setup.")
        
        try:
            start_time = time.time()
            # Returns LIST of htmls
            htmls = fetch_dynamic_content(url, automation) 
            elapsed = round(time.time() - start_time, 2)
            return htmls, url, elapsed
        except Exception as e:
            return None, f"Playwright Fetch Failed: {str(e)}", 0
            
    # --- Original requests logic (for static sites) ---
    try:
        start_time = time.time()
        resp = session.get(
            url, 
            headers=get_random_header(), 
            timeout=15, 
            proxies=proxies
        )
        resp.raise_for_status()
        
        # Check content type
        ctype = resp.headers.get("Content-Type", "").lower()
        if "text/html" not in ctype:
            return None, f"Skipped: Content-Type is {ctype}, not HTML.", 0
            
        elapsed = round(time.time() - start_time, 2)
        return [resp.text], resp.url, elapsed # Return list for consistency
        
    except requests.exceptions.RequestException as e:
        return None, str(e), 0

# ========== EXTRACTORS ==========

class Extractor:
    def __init__(self, html: str, base_url: str):
        self.soup = BeautifulSoup(html, "html.parser")
        self.base_url = base_url
        self.base_domain = urlparse(base_url).netloc.lower()
        
        # Parse for XPath
        try:
            self.tree = lxml_html.fromstring(html)
        except:
            self.tree = None
        
        # Pre-clean script/style tags for text extraction
        self.clean_soup = BeautifulSoup(html, "html.parser")
        for tag in self.clean_soup(["script", "style", "noscript", "svg", "meta", "link"]):
            tag.decompose()
        self.visible_text = clean_text(self.clean_soup.get_text(" "))

    def get_metadata(self):
        """Extract SEO metadata."""
        return [{
            "Title": self.soup.title.string.strip() if self.soup.title else "",
            "Description": (self.soup.find("meta", attrs={"name": "description"}) or {}).get("content", ""),
            "Keywords": (self.soup.find("meta", attrs={"name": "keywords"}) or {}).get("content", ""),
            "Generator": (self.soup.find("meta", attrs={"name": "generator"}) or {}).get("content", ""),
        }]

    def get_phones(self):
        """Optimized Phone Extraction."""
        candidates = set()
        
        # 1. Regex for labeled numbers (High Confidence)
        label_pattern = re.compile(
            r"(?i)(tel|phone|mobile|call|contact|fax)\s*[:\.]?\s*(\+?[\d\(\)\-\s]{8,})"
        )
        for m in label_pattern.finditer(self.visible_text):
            raw = m.group(2).strip()
            if len(re.sub(r"\D", "", raw)) >= 8:
                candidates.add(raw)

        # 2. Href tel: links (High Confidence)
        for a in self.soup.find_all("a", href=True):
            if a["href"].startswith("tel:"):
                candidates.add(a["href"].replace("tel:", ""))

        # 3. Generic fallback (Lower Confidence - Filtered)
        generic_pattern = re.compile(r"\+?\d[\d\s\-\(\)]{9,}\d")
        for m in generic_pattern.finditer(self.visible_text):
            raw = m.group(0).strip()
            digits = re.sub(r"\D", "", raw)
            # Filter out years (2020-2025) and short nums
            if len(digits) > 7 and not re.match(r"^(19|20)\d{2}$", digits):
                candidates.add(raw)

        return [{"Phone": p} for p in sorted(candidates)]

    def get_emails(self):
        """Extract emails via regex and mailto links."""
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        text_emails = set(re.findall(pattern, self.visible_text))
        
        # Add mailto links (sometimes obfuscated in text but clear in link)
        for a in self.soup.find_all("a", href=True):
            if a["href"].startswith("mailto:"):
                email = a["href"].replace("mailto:", "").split("?")[0]
                text_emails.add(email)
                
        return [{"Email": e} for e in sorted(text_emails)]

    def get_socials(self):
        """Extract social media profiles."""
        SOCIAL_DOMAINS = [
            "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
            "tiktok.com", "youtube.com", "t.me", "wa.me", "github.com", "medium.com"
        ]
        found = []
        seen = set()
        
        for a in self.soup.find_all("a", href=True):
            href = a["href"]
            abs_url = urljoin(self.base_url, href)
            for domain in SOCIAL_DOMAINS:
                if domain in abs_url:
                    if abs_url not in seen:
                        seen.add(abs_url)
                        found.append({
                            "Platform": domain.split('.')[0].capitalize(), 
                            "URL": abs_url
                        })
                    break
        return found

    def get_links(self):
        """Extract all internal/external links."""
        links = []
        seen = set()
        for a in self.soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "javascript:")): 
                continue
            abs_url = urljoin(self.base_url, href)
            if abs_url in seen: continue
            seen.add(abs_url)
            
            is_internal = self.base_domain in urlparse(abs_url).netloc.lower()
            links.append({
                "Text": clean_text(a.get_text()),
                "URL": abs_url,
                "Type": "Internal" if is_internal else "External"
            })
        return links

    def get_images(self):
        """Extract images with alt text."""
        images = []
        seen = set()
        for img in self.soup.find_all("img", src=True):
            src = urljoin(self.base_url, img["src"])
            if src in seen: continue
            seen.add(src)
            images.append({
                "Source": src,
                "Alt Text": clean_text(img.get("alt") or ""),
            })
        return images

    def get_addresses(self):
        """Heuristic address extraction focusing on Zip/Postal codes."""
        candidates = []
        # Look for patterns like "Singapore 123456" or "NY 10001" or "London SW1A"
        # This is a general regex for common address endings
        postal_patterns = [
            r"(?i)Singapore\s+(\d{6})",
            r"\b[A-Z]{2}\s+\d{5}(-\d{4})?\b", # US Zip
            r"\b(Street|St\.|Road|Rd\.|Avenue|Ave\.|Lane|Ln\.|Boulevard|Blvd\.|Drive|Dr\.)" 
        ]
        
        lines = self.visible_text.split('\n')
        for line in lines:
            line = line.strip()
            if len(line) > 100 or len(line) < 10: continue
            
            # If line matches a postal code pattern OR contains explicit address keywords
            if any(re.search(p, line) for p in postal_patterns):
                candidates.append({"Address Candidate": line})
                
        return candidates

    def get_company_names(self):
        """
        Improved heuristic for company names, looking for suffixes common 
        to various business structures globally.
        """
        ignore_list = {"home", "about", "contact", "services", "blog", "news", "careers", "privacy", "terms", "login", "sign up", "read more"}
        
        # --- ENHANCED SUFFIX LIST ---
        suffixes = [
            # Common Global/US
            "inc", "corp", "group", "holdings", "ventures", "capital", "labs", 
            "partners", "company", "co", 
            
            # Limited/Private/Public Companies
            "limited", "ltd", "private", "public", "plc", "p.l.c.", "pty", 
            "pte ltd", # Singapore specific
            
            # LLCs and equivalent
            "llc", "l.l.c.", "l.p.", "l.p", "llp", "l.l.p.",
            
            # Partnerships/Sole Proprietorships
            "partnership", "associates", "sarl", "sa", "ag", "gmbh",
            
            # Other common identifiers (often used at the end of a name)
            "consulting", "solutions", "technology", "digital" 
        ]
        
        # Create a variant list that includes suffixes with and without periods
        search_suffixes = set(suffixes)
        for s in suffixes:
            if "." in s:
                search_suffixes.add(s.replace('.', ''))
        
        potential_names = set()
        
        # 1. Check Meta Site Name
        og_name = self.soup.find("meta", property="og:site_name")
        if og_name and og_name.get("content"):
            potential_names.add(og_name["content"].strip())

        # 2. Check text for Suffixes
        for text in self.soup.stripped_strings:
            clean = clean_text(text)
            if 3 < len(clean) < 80: # Increased max length slightly for long names
                lower = clean.lower()
                if lower in ignore_list: continue
                
                # Check if it ends with a company suffix, ensuring it's a word boundary
                if any(re.search(r'\s' + re.escape(s) + r'[.\s]?$', lower) for s in search_suffixes):
                    potential_names.add(clean)

        return [{"Company Name": name} for name in sorted(potential_names)]

    def get_tables(self):
        """Extracts HTML tables into list of DataFrames."""
        try:
            return pd.read_html(str(self.soup))
        except:
            return []

    def get_portfolio_blocks(self):
        """
        Specific logic for 'Award/Portfolio' style blocks. 
        Looks for patterns: Heading (Award) -> Link (Company) -> Text (Country/Desc)
        """
        results = []
        # Find all external links that might be companies
        for a in self.soup.find_all("a", href=True):
            url = urljoin(self.base_url, a['href'])
            if self.base_domain in url: continue # Skip internal
            
            # We look at siblings/parents to find context
            parent = a.parent
            container_text = clean_text(parent.get_text(" "))
            
            # If the link text is short and capitalized, it might be a company name
            name = clean_text(a.get_text())
            if not name or len(name) > 50: continue
            
            # Heuristic: Grab the paragraph following the link
            desc = ""
            next_p = a.find_next("p")
            if next_p:
                desc = clean_text(next_p.get_text())

            if len(desc) > 10: # Only if meaningful description exists
                results.append({
                    "Company Name": name,
                    "URL": url,
                    "Description Snippet": desc[:200] + "..."
                })
        return results
    
    # --- CUSTOM EXTRACTION METHODS ---

    def _get_element_value(self, el, attr, base_url):
        """Helper to safely retrieve the attribute or text value."""
        if attr == "text":
            return clean_text(el.get_text())
        elif attr == "href":
            return urljoin(base_url, el.get("href", ""))
        elif attr == "src":
            return urljoin(base_url, el.get("src", ""))
        else:
            return el.get(attr, "")

    def extract_custom_data_blocks(self, container_selector, relative_map_json, attr="text", selector_type="CSS"):
            """
            Extracts structured data blocks using standard selectors or 
            robust Python logic for header-based lookups.
            """
            results = []
            try:
                import json
                try:
                    relative_map = json.loads(relative_map_json)
                except json.JSONDecodeError:
                    return [{"Error": "Invalid JSON format in Relative Selectors."}]

                # --- CONTAINER SELECTION ---
                if selector_type == "XPath":
                    if self.tree is None:
                        return [{"Error": "XPath not supported (lxml failed to load)."}]
                    try:
                        container_elements = self.tree.xpath(container_selector)
                    except Exception as e:
                        return [{"Error": f"Invalid XPath: {str(e)}"}]
                else:
                    container_elements = self.soup.select(container_selector)
                
                if not container_elements:
                    return [{"Error": f"No container elements matched: {container_selector}"}]

                st.info(f"Found **{len(container_elements)}** container blocks. Extracting {len(relative_map)} fields per block.")

                for i, container in enumerate(container_elements):
                    row_data = {"Block Index": i + 1}
                    
                    for col_name, rel_selector in relative_map.items():
                        value = None
                        
                        # --- 1. HEADER LOOKUP (Existing) ---
                        if rel_selector.startswith("HEADER:"):
                            # Format: "HEADER:Header Text|Value Class"
                            # Note: Only works with BeautifulSoup containers for now
                            if selector_type == "XPath":
                                row_data[col_name] = "HEADER: not supported with XPath containers yet"
                                continue
                                
                            try:
                                _, definition = rel_selector.split(":", 1)
                                header_text, value_class = definition.split("|")
                                value = self._get_sibling_value_by_header(container, header_text.strip(), value_class.strip())
                            except ValueError:
                                row_data[col_name] = f"ERROR: Malformed HEADER selector"
                                continue
                        
                        # --- 2. TEXT MATCH LOOKUP (New) ---
                        elif rel_selector.startswith("TEXT_MATCH:"):
                            # Format: "TEXT_MATCH:Label Text|Sibling Tag"
                            # Example: "TEXT_MATCH:Date Incorporated:|span"
                            if selector_type == "XPath":
                                # XPath implementation of text match
                                try:
                                    _, definition = rel_selector.split(":", 1)
                                    label_text, sibling_tag = definition.split("|")
                                    # XPath to find element containing text, then following sibling
                                    # .//*[contains(text(), 'Label')]/following-sibling::tag[1]
                                    xpath_query = f".//*[contains(text(), '{label_text.strip()}')]/following-sibling::{sibling_tag.strip()}[1]"
                                    sub_el = container.xpath(xpath_query)
                                    if sub_el:
                                        value = sub_el[0].text_content().strip()
                                except Exception as e:
                                    row_data[col_name] = f"XPath Error: {str(e)}"
                                    continue
                            else:
                                # BS4 implementation
                                try:
                                    _, definition = rel_selector.split(":", 1)
                                    label_text, sibling_tag = definition.split("|")
                                    value = self._get_sibling_value_by_text_match(container, label_text.strip(), sibling_tag.strip())
                                except ValueError:
                                    row_data[col_name] = f"ERROR: Malformed TEXT_MATCH selector"
                                    continue

                        # --- 3. STANDARD SELECTOR (CSS or XPath) ---
                        else:
                            if selector_type == "XPath":
                                # Relative XPath starts with .
                                if not rel_selector.startswith("."):
                                    rel_selector = "." + rel_selector
                                try:
                                    sub_el = container.xpath(rel_selector)
                                    if sub_el:
                                        # Handle if result is string (attribute) or element
                                        item = sub_el[0]
                                        if isinstance(item, str):
                                            value = item.strip()
                                        else:
                                            value = item.text_content().strip()
                                except Exception as e:
                                    row_data[col_name] = f"XPath Error: {str(e)}"
                            else:
                                field_element = container.select_one(rel_selector)
                                if field_element:
                                    value = self._get_element_value(field_element, attr, self.base_url)

                        # --- FINAL VALUE ASSIGNMENT ---
                        if value is not None:
                            row_data[col_name] = value
                        else:
                            row_data[col_name] = f"MISSING"
                    
                    results.append(row_data)

                return results
                
            except Exception as e:
                return [{"Error": f"Extraction failed: {str(e)}"}]

    def _get_sibling_value_by_header(self, container, header_text, value_class):
        """
        Finds a header element by its text content and returns the text 
        of its adjacent sibling with a specific class.
        """
        # Find the header element containing the specific text
        header_el = container.find('div', class_=lambda c: c and 'entity__field_header' in c and header_text in c.text)
        
        if header_el:
            # The value is the next sibling that has the specified class
            value_el = header_el.find_next_sibling('div', class_=lambda c: c and value_class in c)
            if value_el:
                return clean_text(value_el.get_text())
        
        return None

    def _get_sibling_value_by_text_match(self, container, label_text, sibling_tag):
        """
        Finds an element containing specific text, then finds its next sibling of a certain tag.
        """
        # Find the string node containing the text
        # This is more precise than searching for tags containing the text
        target_string = container.find(string=lambda text: text and label_text in text)
        
        if target_string:
            target_tag = target_string.parent
            # Try to find next sibling of the tag containing the text
            sibling = target_tag.find_next_sibling(sibling_tag)
            if sibling:
                return clean_text(sibling.get_text())
        return None


# ========== UI LOGIC ==========

def to_excel(dfs):
    """Converts a dictionary of DataFrames to a single Excel file bytes."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in dfs.items():
            # Excel sheet names strictly max 31 chars
            safe_name = sheet_name[:31].replace(":", "").replace("/", "")
            df.to_excel(writer, index=False, sheet_name=safe_name)
    return output.getvalue()

def main():
    st.set_page_config(page_title="Dynamic Scraper Pro", page_icon="🕷️", layout="wide")
    
    st.title("KOKO'S CRAWLER FOR DDU")
    st.markdown("""
    **Optimized Pipeline:** Caching enabled • Session Retries • User-Agent Rotation • **Dynamic Content Fetching (Selenium)** **Capabilities:** Extract Metadata, Contacts, Structure Data, and **Contextual Custom Selectors**.
    """)

    # --- Sidebar ---
    with st.sidebar:
        st.header("⚙️ Configuration")
        url = st.text_input("Target URL", placeholder="https://example.com", key="target_url")
        use_proxy = st.text_input("Proxy (Optional)", placeholder="http://user:pass@host:port", key="proxy_input")
        force_dynamic = st.checkbox("Force Dynamic Fetch (Playwright)", value=False, help="Use headless browser for all requests.")
        
        st.markdown("---")
        st.subheader("🤖 Automation")
        crawl_mode = st.selectbox("Crawl Mode", ["Single Page", "Pagination", "List-Detail"], help="Choose how to navigate the site.")
        wait_time = st.slider("Page Load Delay (s)", min_value=1, max_value=20, value=12, help="Increase this if the site is slow or content is missing.")
        
        automation_config = {"type": "single", "wait_time": wait_time}
        if crawl_mode == "Pagination":
            automation_config["type"] = "pagination"
            automation_config["next_selector"] = st.text_input("Next Button Selector", placeholder=".next-page-btn")
            automation_config["max_pages"] = st.number_input("Max Pages", min_value=1, max_value=20, value=3)
        elif crawl_mode == "List-Detail":
            automation_config["type"] = "list_detail"
            automation_config["detail_selector"] = st.text_input("Detail Link Selector", placeholder=".item-link")
            automation_config["max_items"] = st.number_input("Max Items", min_value=1, max_value=20, value=5)

        st.markdown("---")
        st.subheader("🧩 Custom Extraction")
        
        selector_type = st.radio("Selector Type", ["CSS", "XPath"], horizontal=True, help="Choose CSS for standard scraping, XPath for complex structure.")

        # --- FIXED INPUTS: Removed Duplicates, Added Unique Keys ---
        custom_sel = st.text_input(
            "1. Parent Container Selector", 
            placeholder=".startup-directory-card" if selector_type == "CSS" else "//div[@class='card']", 
            key="custom_sel_container" # UNIQUE KEY
        )
        custom_attr = st.selectbox(
            "Attribute", 
            ["text", "href", "src", "class"], 
            key="custom_attr_select" # UNIQUE KEY
        )

        st.markdown("---")
        st.subheader("✨ Relative Data Mapping")
        
        default_json = '{"Name": ".company-name", "Description": ".company-description"}'
        if selector_type == "XPath":
            default_json = '{"Name": ".//h3", "Link": ".//a/@href"}'

        relative_selectors = st.text_area(
            "2. Relative Selectors (JSON format)", 
            value=default_json,
            help="""
            **CSS Mode:** Key: ".css-selector"
            **XPath Mode:** Key: ".//xpath/expression"
            **Advanced:**
            - `HEADER:Label Text|Value Class` (CSS only)
            - `TEXT_MATCH:Label Text|Sibling Tag` (Finds text, gets next sibling)
            """,
            key="relative_selectors_json" # UNIQUE KEY
        )

    # --- Main Execution ---
    if not url:
        st.info("👈 Enter a URL in the sidebar to begin.")
        return

    # Add a START button to prevent auto-execution
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        start_button = st.button("🚀 Start Scraping", type="primary", use_container_width=True)
    with col2:
        if st.button("🔄 Clear Cache", use_container_width=True):
            st.cache_data.clear()
            st.success("Cache cleared!")
    
    if not start_button:
        st.info("👆 Click 'Start Scraping' when you're ready. Make sure to configure all settings first!")
        st.markdown("**Current Configuration:**")
        st.write(f"- **URL:** {url}")
        st.write(f"- **Crawl Mode:** {crawl_mode}")
        st.write(f"- **Page Load Delay:** {wait_time}s")
        st.write(f"- **Force Dynamic:** {'Yes' if force_dynamic else 'No'}")
        if crawl_mode == "Pagination":
            st.write(f"- **Next Button:** `{automation_config.get('next_selector')}`")
            st.write(f"- **Max Pages:** {automation_config.get('max_pages')}")
        return

    # Trigger Fetch
    with st.status("🚀 Fetching & Analyzing...", expanded=True) as status:
        # Fetch returns a LIST of html strings now
        htmls, final_url, elapsed = fetch_url_content(url, use_proxy, force_dynamic, automation_config)
        
        if htmls is None:
            status.update(label="❌ Failed", state="error")
            st.error(final_url) # Contains error message in this case
            return

        status.write(f"Fetched {len(htmls)} page(s) in {elapsed}s")
        status.write("Parsing DOM & Aggregating Data...")
        
        # --- AGGREGATION LOGIC ---
        all_extractors = [Extractor(h, final_url) for h in htmls]
        status.update(label="✅ Scrape Complete!", state="complete", expanded=False)

    # --- Tabs View ---
    tabs = st.tabs([
        "📊 Overview", "📞 Contacts", "🔗 Links", "🏢 Companies", 
        "🖼️ Media", "📋 Tables", "🧩 Custom"
    ])

    data_exports = {} # Store DFs for Excel export

    def aggregate_data(extractors, method_name, *args, **kwargs):
        """Helper to run a method on all extractors and combine results."""
        all_data = []
        for ext in extractors:
            method = getattr(ext, method_name)
            data = method(*args, **kwargs)
            if data:
                all_data.extend(data)
        return pd.DataFrame(all_data).drop_duplicates() if all_data else pd.DataFrame()

    # ... (Tabs Logic Updated for Aggregation) ...
    with tabs[0]: # Overview
        # Just show metadata from the first page
        if all_extractors:
            meta = all_extractors[0].get_metadata()
            st.dataframe(pd.DataFrame(meta), hide_index=True)
        col1, col2 = st.columns(2)
        with col1: st.info(f"Final URL: {final_url}")
        with col2: st.success(f"Total Pages Scraped: {len(htmls)}")
    
    with tabs[1]: # Contacts
        df_emails = aggregate_data(all_extractors, "get_emails")
        df_phones = aggregate_data(all_extractors, "get_phones")
        df_addresses = aggregate_data(all_extractors, "get_addresses")
        
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(f"**Emails ({len(df_emails)})**"); st.dataframe(df_emails, hide_index=True, use_container_width=True)
        with c2: st.markdown(f"**Phones ({len(df_phones)})**"); st.dataframe(df_phones, hide_index=True, use_container_width=True)
        with c3: st.markdown(f"**Addresses ({len(df_addresses)})**"); st.dataframe(df_addresses, hide_index=True, use_container_width=True)
        
        # Combine for export
        contact_frames = [df for df in [df_emails, df_phones, df_addresses] if not df.empty]
        if contact_frames:
            data_exports["Contacts"] = pd.concat(contact_frames, axis=1) # Concatenate loosely
        
    with tabs[2]: # Links & Social
        df_socials = aggregate_data(all_extractors, "get_socials")
        st.markdown(f"**Social Media ({len(df_socials)})**")
        if not df_socials.empty: 
            data_exports["Socials"] = df_socials
            st.dataframe(df_socials, hide_index=True)
            
        df_links = aggregate_data(all_extractors, "get_links")
        st.markdown(f"**All Links ({len(df_links)})**")
        if not df_links.empty:
            data_exports["All_Links"] = df_links
            search = st.text_input("🔍 Filter Links", "", key="link_filter")
            if search: df_links = df_links[df_links["Text"].str.contains(search, case=False, na=False)]
            st.dataframe(df_links, use_container_width=True)
            
    with tabs[3]: # Companies & Portfolios
        df_companies = aggregate_data(all_extractors, "get_company_names")
        df_portfolios = aggregate_data(all_extractors, "get_portfolio_blocks")
        
        col1, col2 = st.columns(2)
        with col1: st.markdown("### 🏢 Company Names Detected")
        if not df_companies.empty: 
            data_exports["Companies"] = df_companies
            st.dataframe(df_companies, hide_index=True, use_container_width=True)
            
        with col2: st.markdown("### 🏆 Portfolio/Awards Logic")
        if not df_portfolios.empty: 
            data_exports["Portfolio_Blocks"] = df_portfolios
            st.dataframe(df_portfolios, hide_index=True, use_container_width=True)
        else: st.caption("No portfolio/award blocks detected.")
    
    with tabs[4]: # Media
        df_images = aggregate_data(all_extractors, "get_images")
        if not df_images.empty: 
            data_exports["Images"] = df_images
            st.dataframe(df_images, use_container_width=True)
        
    with tabs[5]: # Tables
        # Tables are tricky to aggregate blindly. We'll just show tables from the first page for now, 
        # or maybe list them all. Let's list count.
        total_tables = sum(len(ext.get_tables()) for ext in all_extractors)
        if total_tables > 0:
            st.info(f"Found {total_tables} HTML tables across all pages.")
            # Just show first page tables to avoid UI clutter
            tables = all_extractors[0].get_tables()
            for i, df in enumerate(tables):
                st.markdown(f"**Page 1 - Table {i+1}**"); st.dataframe(df); data_exports[f"P1_Table_{i+1}"] = df
        else: st.write("No HTML tables found.")

    with tabs[6]: # Custom (Using the new structured extraction)
        # Use the values retrieved from the sidebar inputs
        if custom_sel and relative_selectors:
            st.markdown(f"**Targeting Container: `{custom_sel}` ({selector_type})**")
            
            # Aggregate custom data
            all_custom_data = []
            for i, ext in enumerate(all_extractors):
                custom_data = ext.extract_custom_data_blocks(
                    container_selector=custom_sel, 
                    relative_map_json=relative_selectors,
                    attr=custom_attr,
                    selector_type=selector_type
                )
                if custom_data and "Error" not in custom_data[0]:
                    # Add a page source column
                    for row in custom_data:
                        row["Source Page"] = i + 1
                    all_custom_data.extend(custom_data)
                elif "Error" in custom_data[0] and len(all_extractors) == 1:
                     # Only show error if single page, otherwise might be noisy
                     st.error(f"Page {i+1}: {custom_data[0]['Error']}")

            if all_custom_data:
                df_custom = pd.DataFrame(all_custom_data)
                
                # Drop helper columns
                if "Block Index" in df_custom.columns:
                    df_custom = df_custom.drop(columns=["Block Index"])
                if "Container Selector Used" in df_custom.columns:
                    df_custom = df_custom.drop(columns=["Container Selector Used"])
                
                st.dataframe(df_custom, use_container_width=True)
                data_exports["Custom_Extraction"] = df_custom
            else:
                st.warning("No custom data found matching selectors.")
        else:
            st.info("Enter both the Parent Container Selector and the Relative Data Mapping in the sidebar to extract structured data.")


    # --- Global Export ---
    st.divider()
    if data_exports:
        st.write("### 📥 Export Data")
        excel_data = to_excel(data_exports)
        st.download_button(
            label="Download Everything (Excel)",
            data=excel_data,
            file_name="scraped_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

if __name__ == "__main__":
    main()