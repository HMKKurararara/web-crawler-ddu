# How to Use the Dynamic Scraper Pro

This tool allows you to scrape data from websites, even complex ones with dynamic content. To make it "idiot-proof," you can use ChatGPT (or any LLM) to help you find the right settings.

## 🚀 Quick Start Workflow

### Step 1: Open Developer Tools
1.  Go to the website you want to scrape.
2.  Right-click on the **first item** (e.g., the first company card) and select **Inspect**.
3.  This opens the "Developer Tools" panel showing the HTML code.

### Step 2: Take a Screenshot
1.  Take a screenshot of the **HTML code** in the Developer Tools panel.
    *   *Make sure the screenshot shows the container of the item (like `<div class="card">`) and the fields you want (like Name, Date, etc.).*
2.  (Optional) Take a screenshot of the **actual website** visual as well, so the AI understands what you are looking at.

### Step 3: Ask ChatGPT
Upload your screenshot(s) to ChatGPT and paste this prompt:

> "I am using a web scraper. I need to extract data from this HTML structure.
>
> 1. **Container Selector**: What is the CSS class for the main card/container that holds one item?
> 2. **Relative Selectors**: I need a JSON map for these fields: [List fields here, e.g., Name, Description, Incorporated Date].
>    - If a field has a unique class, give me the class (e.g., `.name`).
>    - If a field is just a label and value (like 'Incorporated: 2020'), use this format: `TEXT_MATCH:Label Text|Value Tag`.
>
> Please provide the JSON output ready to copy."

### Step 4: Configure the Scraper
1.  **Target URL**: Paste the website URL.
2.  **Crawl Mode**:
    *   **Single Page**: Just scrape the current page.
    *   **Pagination**: If there is a "Next" button. (Ask ChatGPT for the "Next Button Selector" if needed).
    *   **List-Detail**: If you need to click into each item.
3.  **Custom Extraction**:
    *   **Parent Container Selector**: Paste the class ChatGPT gave you (e.g., `.card` or `.entity-item`).
    *   **Relative Selectors**: Paste the JSON ChatGPT gave you.

---

## 💡 Example Scenarios

### Scenario A: Simple List (Unique Classes)
*The HTML looks like:*
```html
<div class="company-card">
  <h2 class="name">Google</h2>
  <p class="desc">Tech giant...</p>
</div>
```
*   **Container**: `.company-card`
*   **JSON**:
    ```json
    {
      "Name": ".name",
      "Description": ".desc"
    }
    ```

### Scenario B: Labeled Data (No Unique Classes)
*The HTML looks like:*
```html
<div class="info-box">
  <div><strong>Founded:</strong> <span>1998</span></div>
  <div><strong>CEO:</strong> <span>Sundar Pichai</span></div>
</div>
```
*   **Container**: `.info-box`
*   **JSON**:
    ```json
    {
      "Founded": "TEXT_MATCH:Founded:|span",
      "CEO": "TEXT_MATCH:CEO:|span"
    }
    ```
    *(This tells the scraper: Find "Founded:", look at the parent, then grab the next `<span>`)*

## ⚠️ Troubleshooting
*   **No Data Found?**
    *   Check if the **Parent Container Selector** is correct. It must match the *outer box* of each item.
    *   Try enabling **Force Dynamic Fetch (Playwright)** in the sidebar. The site might be loading data with JavaScript.
*   **Wrong Data?**
    *   Check your JSON selectors. If `TEXT_MATCH` isn't working, ensure the Label Text is *exactly* as it appears on the screen (case-sensitive).
