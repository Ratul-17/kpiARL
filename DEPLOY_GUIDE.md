# AKIJ Resource KPI Dashboard — Streamlit Deployment Guide

## Files in this package
```
streamlit-kpi/
├── app.py                     ← Main Streamlit application
├── requirements.txt           ← Python dependencies
├── .streamlit/
│   ├── config.toml            ← Dark theme config
│   └── secrets.toml           ← Google Sheets credentials (template)
└── DEPLOY_GUIDE.md            ← This file
```

---

## ✅ STEP 1 — Make Your Google Sheet Public (Simplest Method)

> Skip this if you want to use a Service Account (Step 4B).

1. Open: **https://docs.google.com/spreadsheets/d/1mv4TUi-JPD2AZBKssDoPmGgzUzGIIbTIKRAz0wjqOFY**
2. Click **Share** (top right)
3. Under "General access" → Change to **"Anyone with the link"** → **Viewer**
4. Click **Done**

The app will now pull live data via Google's public CSV export API — **no API key needed**.

---

## ✅ STEP 2 — Install Python & Dependencies (Local Setup)

### Install Python 3.10+
Download from: https://www.python.org/downloads/

### Create a virtual environment
```bash
# Navigate to your project folder
cd path/to/streamlit-kpi

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate
```

### Install dependencies
```bash
pip install -r requirements.txt
```

---

## ✅ STEP 3 — Run Locally to Test

```bash
# Make sure you're in the streamlit-kpi folder with venv activated
streamlit run app.py
```

Your browser opens automatically at: **http://localhost:8501**

Test it:
- Select different SBUs from sidebar
- Change date range
- Check that % values look correct (e.g. 34.3%, 65.5% — not 3430%)
- Verify SBU full names are correct

---

## ✅ STEP 4 — Deploy to Streamlit Cloud (FREE, Recommended)

### 4A. Push code to GitHub

1. Create a free GitHub account: https://github.com
2. Create a new **public** repository named `akij-kpi-dashboard`
3. Upload these files to the repo:
   - `app.py`
   - `requirements.txt`
   - `.streamlit/config.toml`
   - `.streamlit/secrets.toml` ← **DO NOT** push if it has real credentials!

   For secrets on GitHub, use Streamlit Cloud's secrets UI (Step 4C).

```bash
# OR use git from terminal:
git init
git add app.py requirements.txt .streamlit/config.toml
git commit -m "Initial KPI dashboard"
git remote add origin https://github.com/YOUR_USERNAME/akij-kpi-dashboard.git
git push -u origin main
```

### 4B. Deploy on Streamlit Cloud

1. Go to: **https://share.streamlit.io**
2. Sign in with GitHub
3. Click **"New app"**
4. Select your repository: `akij-kpi-dashboard`
5. Branch: `main`
6. Main file path: `app.py`
7. Click **"Deploy!"**

Streamlit builds and deploys automatically. Your dashboard is live at:
```
https://YOUR_USERNAME-akij-kpi-dashboard-app-XXXXX.streamlit.app
```

### 4C. Add Google Credentials (if sheet is NOT public)

In Streamlit Cloud dashboard:
1. Go to your app → **Settings** → **Secrets**
2. Paste the contents of your `secrets.toml` (with real credentials)
3. Click **Save**

---

## ✅ STEP 5 — (Optional) Service Account for Private Sheets

Use this if you do NOT want to make your Google Sheet public.

### A. Create a Google Cloud Project
1. Go to: https://console.cloud.google.com
2. Create a new project (e.g., "akij-kpi-dashboard")
3. Enable **Google Sheets API** and **Google Drive API**:
   - APIs & Services → Library → Search "Google Sheets API" → Enable
   - APIs & Services → Library → Search "Google Drive API" → Enable

### B. Create a Service Account
1. APIs & Services → **Credentials** → Create Credentials → **Service Account**
2. Name it (e.g., "kpi-dashboard-reader")
3. Role: **Editor** or **Viewer**
4. Click Done → Click the service account → **Keys** → Add Key → **JSON**
5. Download the JSON file

### C. Share Sheet with Service Account
1. Open the JSON file — copy the `client_email` value
   (looks like: `kpi-dashboard-reader@your-project.iam.gserviceaccount.com`)
2. Open your Google Sheet → **Share**
3. Paste the service account email → **Viewer** → Share

### D. Add to secrets.toml
Open `.streamlit/secrets.toml` and add:
```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "key-id-from-json"
private_key = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
client_email = "your-sa@your-project.iam.gserviceaccount.com"
client_id = "123456789"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://..."
```

---

## ✅ STEP 6 — Value Formatting Reference

All percentage KPIs in your sheet are stored as **decimals** (0.xx):

| Sheet Value | Dashboard Shows |
|-------------|-----------------|
| 0.3432      | 34.3%           |
| 0.6545      | 65.5%           |
| 1.0         | 100.0%          |
| -0.0485     | -4.9%           |
| 0.8694      | 86.9%           |

BDT values and Hours are shown as-is (no × 100):
| Sheet Value | Dashboard Shows |
|-------------|-----------------|
| 431790.82   | ৳431.8K         |
| 1507935.5   | ৳1.51M          |
| 17.31       | 17.3 hrs        |

---

## 🔁 Updating Data

- Data auto-refreshes from Google Sheets every **5 minutes** (Streamlit cache TTL)
- Click **"Refresh Data"** in sidebar for immediate reload
- Just update your Google Sheet — the dashboard reflects changes automatically

---

## 🛠 Troubleshooting

| Problem | Fix |
|---------|-----|
| "Could not load sheet" error | Make sheet public (Step 1) or add service account (Step 5) |
| Wrong % values | All % KPIs must be stored as decimals (0.87 = 87%) in Google Sheet |
| Sheet name mismatch | In `app.py`, `SBU_CONFIG` → check `"sheet"` value matches exact tab name |
| App crashes locally | Ensure `venv` is activated and `pip install -r requirements.txt` completed |
| Streamlit Cloud not building | Check `requirements.txt` versions are compatible |

---

## 📋 SBU Sheet Name Mapping

| Dashboard Key | Google Sheet Tab Name |
|---------------|-----------------------|
| AIL           | AIL                   |
| AAFL          | AAFL                  |
| ACCL          | ACCL                  |
| AEL (Flour)   | AEL (Flour)           |
| AEL (Rice)    | AEL (Rice)            |
| APFIL         | APFIL                 |
| ABSL          | ABSL                  |
| ARMCL-01      | ARMCL - 01            |

---

*AKIJ Resource — Production Planning KPI Intelligence Dashboard*
*Built for Operations Planning & Management Decision Making*
