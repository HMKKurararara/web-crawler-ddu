# How to Deploy for Free (Streamlit Cloud)

The fastest and easiest way to host this for your colleagues is **Streamlit Community Cloud**. It is free and connects directly to GitHub.

## Step 1: Push to GitHub
1.  Create a new repository on GitHub (e.g., `my-crawler`).
2.  Upload the following files to it:
    *   `crawler.py`
    *   `requirements.txt`
    *   `packages.txt`
    *   `HOW_TO_USE.md` (Optional, for reference)

## Step 2: Deploy on Streamlit Cloud
1.  Go to [share.streamlit.io](https://share.streamlit.io/).
2.  Sign in with GitHub.
3.  Click **"New app"**.
4.  Select your repository (`my-crawler`), branch (`main`), and file (`crawler.py`).
5.  Click **"Deploy!"**.

## Step 3: Share
*   Once deployed, you will get a URL (e.g., `https://my-crawler.streamlit.app`).
*   Send this URL to your colleagues. They can use it on their phones or laptops without installing anything!

## Notes
*   **Startup Time**: The first time the app loads, it might take a minute to install the browser. Subsequent loads will be faster.
*   **Privacy**: Streamlit Community Cloud apps are public by default unless you have a private repo and a paid plan (or use the limited private app allowance).
