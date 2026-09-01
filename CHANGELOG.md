## v1.4.5 — Session timeout & expiry handling

### Fixes
- **Session duration extended to 10 days** — `SESSION_COOKIE_AGE = 864000` (was Django default 2 weeks but closed-browser behavior varied)
- **Session persists across browser close** — `SESSION_EXPIRE_AT_BROWSER_CLOSE = False`
- **Session refreshed on every request** — `SESSION_SAVE_EVERY_REQUEST = True` keeps the 10-day window rolling
- **On session expiry during htmx action** — confirm dialog → redirect to `/login/?next=<current page>` so user returns to same page after re-login
- **On session expiry during fetch action** — `saveGroup`, `deleteGroup`, `doImport` redirect to login with return URL (instead of showing inline error)
- **CSRF-missing guard** — if CSRF token is absent from DOM, immediately redirects to login rather than sending a broken request

---

## نسخه ۱.۴.۵ — مدیریت session و انقضا

### رفع
- **مدت session به ۱۰ روز افزایش یافت** — هر ۱۰ روز یک بار نیاز به لاگین مجدد
- **session بعد از بستن مرورگر منقضی نمی‌شود**
- **session در هر درخواست تمدید می‌شود** — ۱۰ روز از آخرین فعالیت
- **انقضای session حین action** — پیام تأیید + redirect به لاگین با بازگشت به همان صفحه
- **محافظت از CSRF غایب** — اگر توکن نباشد مستقیم به لاگین می‌رود

---

## v1.4.4 — Session expiry fix across all AJAX views

### Fixes
- **Login page appearing in popups** — all AJAX/htmx views now return a 401 error fragment on expired session instead of redirecting to /login/ (which caused full login page HTML to inject into result popups and target divs)
- **New `ajax_login_required` decorator** — replaces `@login_required` on 14 AJAX views: `trigger_sync`, `set_limit`, `remove_limit`, `update_sync_interval`, `panel_config`, `reset_deleted_traffic`, `reset_admin_usage`, `telegram_config`, `telegram_backup_now`, `admin_action`, `sync_status`, `import_database`, `server_stats`, `set_ui_theme`
- **htmx afterRequest hook** — detects full HTML page responses (`<!doctype`, `<html`) and shows a friendly "Session Expired" popup instead of parsing login page text
- **fetch()-based calls** — `saveGroup`, `deleteGroup`, and `doImport` now check `r.status === 401 || r.redirected` before processing response HTML

### How it works
Full-page views (`dashboard`, `portal`, `settings`, etc.) keep `@login_required` so unauthenticated browser navigation still redirects to login. AJAX views use the new decorator to return `HTTP 401` with an error fragment, which the UI surfaces as a clear "Session expired — please refresh" message.

---

## نسخه ۱.۴.۴ — رفع باگ session expiry در تمام ویوهای AJAX

### رفع باگ
- **ظاهر شدن فرم لاگین در پاپ‌آپ** — همه ویوهای AJAX حالا روی session منقضی، fragment خطا با status 401 برمی‌گردانند
- **دکوراتور `ajax_login_required`** — جایگزین `@login_required` روی ۱۴ ویوی AJAX
- **htmx afterRequest hook** — پاسخ‌های HTML کامل را تشخیص می‌دهد و پیام "Session Expired" نمایش می‌دهد
- **fetch()-based calls** — بررسی `r.status === 401 || r.redirected` قبل از استفاده از HTML پاسخ

---

## v1.4.3 — Account Groups bug fixes & UI redesign

### Fixes
- **Login form appearing inside page** — AJAX views now return 401 fragment on expired session instead of redirecting to /login/ (which caused the login HTML to inject into the page)
- **Logout on Save** — fetch() now uses explicit csrfmiddlewaretoken from DOM, no redirect side effects
- **Owner excluded from members** — selected owner is hidden from the member chip list automatically

### Improvements
- **Account Groups redesign** — mobile-first responsive (single column ≤900px, sticky form on desktop), member filter input to search chips, onmousedown dropdown to avoid blur conflicts, group cards clickable to load into edit form

---

## نسخه ۱.۴.۳ — رفع باگ و بازطراحی گروه‌بندی

### رفع باگ
- **فرم لاگین داخل صفحه** — views های AJAX حالا روی session منقضی، fragment خطا برمی‌گردانند (نه redirect)
- **logout هنگام Save** — fetch از csrfmiddlewaretoken مستقیم DOM استفاده می‌کند
- **Owner از لیست members حذف** — owner انتخاب‌شده از chip های members مخفی می‌شود

### بهبودها
- **بازطراحی گروه‌بندی** — mobile-first ریسپانسیو، فیلتر جستجو برای chip ها، کلیک روی کارت گروه برای ویرایش

---

## v1.4.2 — UI Polish

### Fixes & Improvements
- **Account Groups**: custom dark-themed searchable dropdown for Owner field (replaces native browser datalist)
- **Account Groups**: generic placeholder text (no personal names)
- **Database Import**: dropzone hidden by default behind "Import Database" button; Cancel button collapses it; auto-resets after successful import

---

## نسخه ۱.۴.۲ — بهبود رابط کاربری

### رفع و بهبود
- **گروه‌بندی**: dropdown سفارشی تیره و قابل جستجو برای فیلد Owner
- **گروه‌بندی**: متن placeholder عمومی شد
- **ایمپورت دیتابیس**: ناحیه آپلود پشت دکمه مخفی است؛ دکمه Cancel اضافه شد

---

# Changelog

## v1.4.1 — UI Improvements

### Improvements
- **Account Groups** — clickable chip selector for members (no more comma typing), two-column layout, click a group card to pre-fill the edit form, mobile responsive
- **Database Import** — drag & drop upload zone with file preview, filename and size shown, import button only appears after file selected, dropzone resets after import

---

## نسخه ۱.۴.۱ — بهبود رابط کاربری

### بهبودها
- **گروه‌بندی اکانت‌ها** — انتخاب کلیکی اعضا (بدون تایپ کردن)، چیدمان دو ستونه، کلیک روی کارت گروه برای ویرایش، ریسپانسیو موبایل
- **ایمپورت دیتابیس** — ناحیه درگ‌اند‌دراپ با پیش‌نمایش فایل، دکمه ایمپورت فقط بعد از انتخاب فایل ظاهر می‌شود

---


## v1.4.0 — Account Groups, Login UI, API v5.2.1, Telegram Backup, DB Import, Smart Update

### New Features
- **Account Groups** — Superuser can group multiple Pasargad admin accounts under one owner. When the owner logs in, My Panel shows all their accounts (owner + members) separately with full traffic and user stats
- **Telegram Backup** — Automated scheduled database backup sent to a Telegram bot; configurable interval; manual send button; last backup status in Settings
- **Database Import** — Upload a .sql file from Settings to restore the database (confirmation dialog, 100 MB limit, utf8mb4 charset)
- **Smart Update** — Installer compares installed version with GitHub, shows changelog, auto-rollback on failure
- **New Login Page** — Clean minimal glassmorphism design
- **API Client v5.2.1** — get_admins_simple, get_admin_usage, reset_admin_usage, bulk disable/enable admins and users, get_system_resources, get_nodes
- **Reset Usage button** — Superuser can reset an admin's usage counter from the detail page
- **Overview server info** — Public IPv4/IPv6, kernel version, hostname, process count, Docker IPs

### Fixes
- CSRF_TRUSTED_ORIGINS written to .env on fresh install (fixes 403 on first login)
- nginx.conf always written as file before Docker starts (fixes mount error)
- Two-phase SSL: HTTP-only on first boot, SSL after certbot
- Telegram chat_id leading-digit bug fixed
- Database import charset (utf8mb4) and max_allowed_packet fixed
- nginx.conf preserved across git reset during update

---

## نسخه ۱.۴.۰ — گروه‌بندی اکانت‌ها، رابط لاگین، API، بک‌آپ تلگرام، ایمپورت دیتابیس، آپدیت هوشمند

### امکانات جدید
- **گروه‌بندی اکانت‌ها** — سوپریوزر می‌تواند چند اکانت ادمین پاسارگاد را زیرمجموعه یک مالک تعریف کند. هنگام لاگین مالک، همه اکانت‌ها در My Panel جداگانه نمایش داده می‌شوند
- **بک‌آپ تلگرام** — ارسال خودکار بک‌آپ دیتابیس به ربات تلگرام با بازه زمانی قابل تنظیم
- **ایمپورت دیتابیس** — آپلود فایل SQL از صفحه تنظیمات برای بازیابی دیتابیس
- **آپدیت هوشمند** — نصاب نسخه GitHub را مقایسه می‌کند، changelog نشون می‌دهد، rollback خودکار
- **صفحه لاگین جدید** — طراحی مینیمال glassmorphism
- **API Client نسخه ۵.۲.۱** — endpoint های جدید پاسارگاد
- **کارت اطلاعات سرور** در Overview — IPv4/IPv6، کرنل، hostname، پروسس‌ها، IP های Docker

### رفع باگ
- رفع CSRF 403 در نصب جدید
- رفع خطای mount nginx.conf
- SSL دومرحله‌ای پایدار
- رفع باگ Chat ID تلگرام
- رفع charset ایمپورت دیتابیس
- حفظ nginx.conf در آپدیت

---


## v1.3.2 — Installer Reliability

### Fixes
- nginx.conf is always written as a file (HTTP-only) before `docker compose up` — fixes "is a directory" mount error on fresh installs
- Two-phase SSL: HTTP-only config on first boot, SSL config applied only after certbot successfully issues the cert
- Update flow backs up nginx.conf before `git reset --hard` and restores it after; regenerates from template if backup is missing (HTTP-only if no cert, SSL if cert exists)
- Certbot failure no longer aborts the entire install — site stays running on HTTP, SSL can be added later
- Volume cleanup before `docker compose up` prevents "Table already exists" errors on re-installs
- `git pull` on existing installs replaced with `git fetch + reset --hard` to avoid failures on local changes
- Non-git directory at `/opt/pamp` is removed and recloned instead of aborting
- nginx container name detection fixed: tries `pamp-nginx-1` then `pamp_nginx_1`
- `collectstatic` failure in update no longer aborts the update process

---

## نسخه ۱.۳.۲ — پایداری نصاب

### رفع باگ
- `nginx.conf` همیشه قبل از `docker compose up` به‌صورت فایل HTTP نوشته می‌شود — رفع خطای mount روی سرورهای جدید
- SSL دومرحله‌ای: ابتدا HTTP راه‌اندازی می‌شود، پس از صدور گواهی توسط certbot به SSL سوییچ می‌کند
- جریان آپدیت: nginx.conf را قبل از `git reset` بکاپ می‌گیرد و بعد بازیابی می‌کند؛ در صورت از دست رفتن، از template بازسازی می‌شود
- شکست certbot دیگر کل نصب را متوقف نمی‌کند — سایت روی HTTP ادامه می‌دهد
- پاکسازی volume قبل از نصب برای جلوگیری از خطای "Table already exists"
- تشخیص نام کانتینر nginx اصلاح شد

---


## v1.3.1 — Login UI, API updates, installer fixes

### New Features
- **New login page** — Clean minimal design, glassmorphism theme matching v2 UI
- **API Client v5.2.1** — New endpoints: get_admins_simple, get_admin_usage, reset_admin_usage, bulk disable/enable admins and their users, get_system_resources, get_nodes
- **Reset Usage button** — Superuser can reset an admin's usage counter directly from the admin detail page

### Fixes
- **CSRF fix in installer** — fresh installs now write CSRF_TRUSTED_ORIGINS to .env automatically (prevents 403 on first login)
- **Update flow** — adds CSRF_TRUSTED_ORIGINS to .env of older installs automatically
- **Database import** — added utf8mb4 charset and max_allowed_packet=256M to fix truncated INSERT errors
- **nginx.conf** — untracked from git; nginx.conf.template with PAMP_DOMAIN placeholder committed instead; update preserves server-specific config

---

## نسخه ۱.۳.۱ — UI لاگین، آپدیت API، رفع باگ نصاب

### امکانات جدید
- **صفحه لاگین جدید** — طراحی مینیمال و تمیز با تم glassmorphism نسخه v2
- **API Client نسخه ۵.۲.۱** — endpoint های جدید: لیست ساده ادمین‌ها، مصرف مستقیم، ریست مصرف، عملیات دسته‌جمعی، منابع سیستم، نودها
- **دکمه ریست مصرف** — سوپریوزر می‌تواند شمارنده مصرف هر ادمین را از صفحه جزئیات ریست کند

### رفع باگ
- **رفع CSRF در نصاب** — نصب‌های تازه CSRF_TRUSTED_ORIGINS را به .env می‌نویسند (جلوگیری از خطای 403)
- **آپدیت** — CSRF_TRUSTED_ORIGINS را به .env نصب‌های قدیمی‌تر اضافه می‌کند
- **ایمپورت دیتابیس** — اضافه شدن utf8mb4 و max_allowed_packet=256M برای رفع خطای INSERT
- **nginx.conf** — از git حذف شد؛ nginx.conf.template با placeholder ثبت شد؛ آپدیت config مخصوص سرور را حفظ می‌کند

---

## v1.3.0 — Server monitoring, Telegram backup, DB import, smart update

### New Features
- **Overview — Server Information card**: public IPv4/IPv6, kernel version, hostname, process count, Docker internal IPs
- **Telegram Backup**: automated scheduled database backup sent to a Telegram bot; configurable interval (hours); manual "Send Now" button with immediate result feedback
- **Database Import**: upload a .sql file from Settings to restore the database (confirmation dialog, 100 MB limit, both v1 and v2 UI)
- **Smart Update**: the installer's Update option now fetches the latest version from GitHub, shows the relevant changelog section, and only updates if a newer version exists; includes auto-rollback if the web container fails to start after update

### Fixes
- Telegram chat_id leading-digit bug fixed ("chat not found" error resolved)
- Backup task runs synchronously in the view so the result is shown immediately in the UI
- Improved Telegram API error reporting — shows Telegram's actual description, not raw HTTP status

---

## نسخه ۱.۳.۰ — مانیتورینگ سرور، بک‌آپ تلگرام، ایمپورت دیتابیس، آپدیت هوشمند

### امکانات جدید
- **Overview — کارت اطلاعات سرور**: IPv4/IPv6 عمومی، نسخه کرنل، hostname، تعداد پروسس، IP‌های داخلی Docker
- **بک‌آپ تلگرام**: ارسال خودکار بک‌آپ دیتابیس به ربات تلگرام با بازه زمانی قابل تنظیم (بر حسب ساعت)؛ دکمه ارسال دستی با نمایش فوری نتیجه
- **ایمپورت دیتابیس**: آپلود فایل SQL از صفحه تنظیمات برای بازیابی دیتابیس (تأییدیه، محدودیت ۱۰۰ مگابایت، هر دو تم v1 و v2)
- **آپدیت هوشمند**: گزینه Update در نصاب نسخه GitHub را با نسخه نصب‌شده مقایسه می‌کند، بخش changelog مربوط را نشان می‌دهد، و فقط در صورت وجود نسخه جدید آپدیت می‌کند؛ شامل rollback خودکار در صورت شکست وب‌کانتینر

### رفع باگ
- رفع باگ Chat ID تلگرام (رقم ۱ ابتدایی جا افتاده بود)
- اجرای synchronous بک‌آپ در view برای نمایش فوری نتیجه
- بهبود گزارش خطای Telegram API — نمایش توضیح واقعی به جای کد HTTP خام

---

## v1.2.1 — Installer fixes

### Fixes
- **install.sh now works on any domain** — the chosen domain is written into nginx.conf and docker-compose.yml instead of a hardcoded value (fixes ERR_EMPTY_RESPONSE on fresh installs)
- **Two-phase SSL setup** — nginx starts HTTP-only first so the app is reachable and Let's Encrypt can validate, then switches to HTTPS automatically
- **Docker Compose v2 support** — the installer detects and uses `docker compose` (v2) or `docker-compose` (v1)
- **certbot webroot volume** added automatically; SSL step skips gracefully if DNS isn't ready yet
- **phpMyAdmin** uses a relative URI to avoid domain/scheme mismatch

---

## نسخه ۱.۲.۱ — رفع مشکلات نصب

### رفع باگ‌ها
- **install.sh حالا با هر دامنه‌ای کار می‌کند** — دامنه انتخابی در nginx.conf و docker-compose.yml نوشته می‌شود به‌جای مقدار ثابت (رفع خطای ERR_EMPTY_RESPONSE در نصب تازه)
- **راه‌اندازی SSL دومرحله‌ای** — nginx ابتدا فقط HTTP بالا می‌آید تا سایت در دسترس باشد و Let's Encrypt اعتبارسنجی کند، سپس خودکار به HTTPS سوییچ می‌کند
- **پشتیبانی از Docker Compose v2** — نصاب `docker compose` یا `docker-compose` را تشخیص می‌دهد
- **volume مربوط به certbot** خودکار اضافه می‌شود؛ اگر DNS آماده نباشد مرحله SSL به‌آرامی رد می‌شود
- **phpMyAdmin** از URI نسبی استفاده می‌کند

---

## v1.2.0 — New UI (v2) with theme switcher

### New Features
- **Redesigned modern UI (v2)** — A new navy/purple glassmorphism interface with:
  - Overview page: live server resources (CPU, Memory, Disk, Bandwidth) with circular gauges, updating every 2 seconds
  - Redesigned Dashboard, My Panel, Admin Detail, Sync Logs, and Settings pages
  - Self-hosted Vazirmatn font (no CDN dependency — reliable inside Iran)
  - Fully responsive with a mobile hamburger drawer menu
  - Left sidebar, English menu, LTR layout
- **Theme switcher** — A global UI theme setting (Classic v1 / Modern v2), changeable by the superuser from Settings. Defaults to Modern (v2). Both themes are kept; main routes render whichever is active.
- **Bandwidth card** — Live upload/download speed on the Overview page
- **Color-coded action buttons** — On the admin detail page, buttons are semantically colored (Set = green, Add = blue, Reduce = orange, Remove/Disable = red, Enable = green)
- **Sync + Logout on every page** — The Sync button (top-right) and Logout (sidebar) are available across the new UI

### Notes
- The classic v1 interface remains fully available and can be re-selected any time from Settings → UI Theme.

---

## نسخه ۱.۲.۰ — رابط کاربری جدید با قابلیت تعویض تم

### امکانات جدید
- **رابط مدرن بازطراحی‌شده (v2)** — رابط شیشه‌ای navy/purple جدید شامل:
  - صفحه Overview: منابع زنده سرور (CPU، حافظه، دیسک، پهنای باند) با گیج دایره‌ای، آپدیت هر ۲ ثانیه
  - بازطراحی صفحات داشبورد، پنل من، جزئیات ادمین، لاگ سینک و تنظیمات
  - فونت Vazirmatn خودمیزبان (بدون وابستگی به CDN — پایدار در ایران)
  - کاملاً ریسپانسیو با منوی همبرگری موبایل
- **تعویض تم** — تنظیم کلی تم (کلاسیک v1 / مدرن v2) که سوپریوزر از تنظیمات عوض می‌کند. پیش‌فرض مدرن (v2). هر دو تم حفظ می‌شوند
- **کارت پهنای باند** — سرعت لحظه‌ای دانلود/آپلود در صفحه Overview
- **دکمه‌های رنگی معنادار** — در صفحه جزئیات ادمین (تنظیم=سبز، افزودن=آبی، کاهش=نارنجی، حذف/غیرفعال=قرمز، فعال=سبز)
- **دکمه Sync و Logout در همه صفحات**

### نکته
- رابط کلاسیک v1 کاملاً در دسترس می‌ماند و هر زمان از تنظیمات → UI Theme قابل انتخاب است.

---

## v1.1.0 — Sold Limit Accounting, Deleted-User Traffic Preservation & Mobile Responsiveness

### Features
- **Deleted-user traffic preservation** — When a user is deleted from the panel, their used traffic is accumulated into the admin's sold-volume counter (`deleted_users_used_bytes`). The Sold Limit stays accurate across user deletions without double-counting anything in live usage metrics.
- **Per-user traffic snapshots** — New `UserTrafficSnapshot` model records each user's last-seen `used_traffic` every sync cycle. Deletions are detected by diffing the snapshot against the live user list — no extra API call needed.
- **Reset deleted-traffic counter** — Superusers can reset the preserved deleted-users counter to zero from the admin detail page, with a confirmation modal and full audit trail (`deleted_traffic_reset_at` timestamp).
- **Corrected Sold Limit formula** — Fixed sign error in the Sold Limit calculation: `Sold Limit = Remaining − Total User Limit + Total User Used` (was subtracting used instead of adding).
- **Full mobile responsiveness** — All pages (dashboard, admin detail, settings, sync logs, portal) are now fully responsive with a hamburger off-canvas sidebar, scrollable tables, and stacking grids at 1024 / 768 / 480 px breakpoints.
- **Sync Logs stats bar** — Dedicated Sync Logs page now shows Total Syncs, Successful, and Failed counts in a summary bar at the top.

### Bug Fixes
- Fixed double-API-call in sync loop — user list fetched by `get_admin_user_stats` is now passed directly to the snapshot tracker via `users` key in the result dict.
- Fixed CSS attribute selector unreliability for inline `grid-template-columns` — action grids now use explicit `action-grid` class for reliable mobile stacking.

### Database Migrations
- `0006_paneladmin_deleted_traffic_reset_at_and_more` — adds `deleted_users_used_bytes`, `deleted_traffic_reset_at` to `PanelAdmin`, and creates the `UserTrafficSnapshot` table.

---

## نسخه ۱.۱.۰ — حسابداری حجم فروخته‌شده، نگهداری ترافیک کاربران حذف‌شده و ریسپانسیو موبایل

### امکانات
- **نگهداری ترافیک کاربران حذف‌شده** — وقتی کاربری از پنل حذف می‌شود، ترافیک مصرف‌شده‌اش در یک شمارنده (`deleted_users_used_bytes`) ذخیره می‌شود تا Sold Limit بعد از حذف کاربران دقیق بماند.
- **اسنپ‌شات ترافیک کاربران** — مدل `UserTrafficSnapshot` در هر سینک، آخرین `used_traffic` هر کاربر را ذخیره می‌کند. حذف‌ها با مقایسه اسنپ‌شات با لیست زنده شناسایی می‌شوند — بدون فراخوانی API اضافه.
- **ریست شمارنده حجم حذف‌شده** — سوپریوزرها می‌توانند از صفحه جزئیات ادمین، شمارنده کاربران حذف‌شده را با تأیید و ثبت زمان ریست کنند.
- **اصلاح فرمول Sold Limit** — خطای علامت در فرمول Sold Limit برطرف شد: `Sold Limit = Remaining − Total User Limit + Total User Used`.
- **ریسپانسیو کامل موبایل** — همه صفحات (داشبورد، جزئیات ادمین، تنظیمات، لاگ سینک، پورتال) با منوی همبرگری، جداول قابل اسکرول و چیدمان انعطاف‌پذیر در ۱۰۲۴/۷۶۸/۴۸۰ پیکسل کاملاً ریسپانسیو شدند.
- **نوار آمار سینک** — صفحه لاگ سینک حالا تعداد کل سینک‌ها، موفق و ناموفق را در بالا نمایش می‌دهد.

### رفع باگ
- رفع فراخوانی دوبله API در حلقه سینک — لیست کاربران حالا مستقیماً از `get_admin_user_stats` به ردیاب اسنپ‌شات پاس می‌شود.
- رفع مشکل انتخابگر CSS برای `grid-template-columns` اینلاین — گریدهای اکشن حالا کلاس `action-grid` دارند.

### مایگریشن دیتابیس
- `0006_paneladmin_deleted_traffic_reset_at_and_more` — فیلدهای `deleted_users_used_bytes` و `deleted_traffic_reset_at` به `PanelAdmin` اضافه شد و جدول `UserTrafficSnapshot` ایجاد شد.

---

## v1.0.0 — First stable release

### Features
- **Admin dashboard** — Monitor all panel admins: traffic usage, limits, status, progress bars
- **Per-admin portal** — Each admin logs in with panel credentials and sees only their own data
- **Unified limit management** — Set / Add / Reduce / Remove admin data limits directly on the Pasargad panel, fully synced
- **Auto-enforcement** — Automatically disable an admin and their users when usage reaches the limit
- **Admin actions** — Disable/Enable admin access and disable/enable all their users, with confirmation modals and clear success/error feedback
- **Sold Limit calculation** — Per-admin signed traffic calculation with color coding
- **Live server monitoring** — Real-time CPU, RAM, Disk, and Bandwidth of the host server
- **Auto-sync** — Configurable interval (Celery Beat) plus manual sync, with full sync log history
- **Database backup** — One-click SQL dump download
- **Dedicated pages** — Separate Settings and Sync Logs pages with polished UX
- **Glassmorphism UI** — Fully responsive (desktop + mobile) with gradient glass design and SVG icons

### Security
- Panel credentials stored in the database and editable via the Settings UI (not in env files)
- Django admin restricted to superusers only
- No sensitive data (panel name/URL) in any committed files
- HTTPS with auto-renewing SSL

### Infrastructure
- Django 5 + MySQL + Redis + Celery + Nginx + phpMyAdmin via Docker Compose
- One-line installer script
- Auto git push on file changes

---

## نسخه ۱.۰.۰ — اولین نسخه پایدار

### امکانات
- **داشبورد ادمین** — نظارت بر همه ادمین‌ها: مصرف، لیمیت، وضعیت
- **پورتال شخصی** — هر ادمین با اطلاعات پنل وارد می‌شود و فقط داده خود را می‌بیند
- **مدیریت یکپارچه لیمیت** — تنظیم / افزودن / کاهش / حذف لیمیت مستقیماً روی پنل پاسارگاد
- **اجرای خودکار** — غیرفعال‌سازی خودکار ادمین و کاربرانش هنگام رسیدن به لیمیت
- **عملیات ادمین** — فعال/غیرفعال‌سازی دسترسی ادمین و کاربرانش با تأیید و پیام نتیجه
- **مانیتورینگ زنده سرور** — نمایش لحظه‌ای CPU، RAM، دیسک و پهنای باند
- **سینک خودکار** — بازه قابل تنظیم به‌همراه سینک دستی و تاریخچه کامل
- **بک‌آپ دیتابیس** — دانلود SQL با یک کلیک
- **صفحات مجزا** — تنظیمات و لاگ سینک جداگانه
- **رابط شیشه‌ای** — کاملاً ریسپانسیو (دسکتاپ و موبایل)

### امنیت
- اطلاعات پنل در دیتابیس و قابل ویرایش از UI (نه در فایل env)
- دسترسی پنل جنگو فقط برای سوپریوزر
- بدون اطلاعات حساس در فایل‌های گیت
- HTTPS با SSL خودکار
