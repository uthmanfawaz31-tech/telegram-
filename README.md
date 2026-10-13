# TelePro — Modern Telegram Broadcasting Platform

TelePro is an upgraded, high-capacity Telegram broadcast platform engineered to manage, auto-sync, and broadcast to **300+ groups** with anti-spam protections.

---

## 🚀 Key Features

### 1. Telegram Account Connection & Group Detection
- **Interactive MTProto Login**: Connect your Telegram account via Phone + OTP with full support for **Two-Step Verification (2FA)**.
- **Custom API Credentials**: Configure your own `API_ID` & `API_HASH` from [my.telegram.org](https://my.telegram.org) directly in the app.
- **Auto-Sync Groups**: Automatically detects and catalogs all Groups, Supergroups, and Channels on your account.
- **Instant Dynamic Updates**: Click **"Sync Groups"** anytime to refresh and detect newly joined groups.
- **Join by Link**: Built-in modal to join groups by invite link (`t.me/+...`) or public `@username` and instantly add them to your directory.

### 2. Anti-Spam & 1-Minute Timing
- **1-Minute Difference Between Groups**: Default broadcast interval is 60 seconds (customizable).
- **Human Jitter Randomization**: Adds natural variation (55s–68s) so message timing is not robotic.
- **Typing Simulation**: Sends realistic Telegram `typing...` status for 3–4 seconds before each post.
- **Spintax Engine**: Supports nested spintax like `{Hello|Hi|Greetings} {everyone|friends}! {Check out|Explore} our updates.`
- **Dynamic Placeholders**:
  - `{group_name}` — Replaced with target group's title
  - `{random_emoji}` — Distinct random emoji per group
  - `{greeting}` — Contextual greeting ("Good morning", "Good afternoon", etc.)
  - `{date}` and `{time}` — Real-time timestamps
- **FloodWait & Error Handling**: If Telegram returns a rate limit (`FloodWaitError`), the worker cools down for the requested seconds and automatically resumes without aborting the campaign.

### 3. Scalable for 300+ Groups
- **High-Capacity Directory**: Filter and search through hundreds of groups in milliseconds.
- **Quick Batch Selection**: Select All, Select First 100, Select First 300 (leaving space if you have more than 300 groups!), or filter by Writable only.
- **Live Campaign Monitor**: Track active broadcasts in real-time with an animated progress bar, next group countdown, ETA, and Pause / Resume / Stop controls.
- **Audit Logs**: Inspect per-group delivery logs with timestamps and exact spintax message variations sent.

### 4. Template Message System
- **Template Manager**: Create, save, edit, and organize broadcast templates.
- **Live Spintax Tester**: Click **"Generate 3 Test Spins"** inside the editor to preview sample variations before broadcasting.

---

## ⚡ How to Start

### Option A: One-Click Launcher (Windows)
Double-click `start.bat` or run in PowerShell:
```powershell
.\start.ps1
```
This automatically launches both the FastAPI backend and Next.js frontend, and opens `http://localhost:3000` in your browser.

### Option B: Manual Start
**1. Start Backend:**
```powershell
cd telegram-scout-main\backend
& "C:\Users\OFFICE\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn app.main:app --port 8000 --reload
```

**2. Start Frontend:**
```powershell
cd telegram-scout-main\frontend
npm.cmd run dev
```
Open **http://localhost:3000** in your browser.
