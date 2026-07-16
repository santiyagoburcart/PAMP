# Changelog

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
