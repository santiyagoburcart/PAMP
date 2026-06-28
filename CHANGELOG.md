# Changelog

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
