<div align="center" dir="rtl">

# PAMP
### پنل مدیریت ادمین‌های پاسارگاد

پنل وب زیبا برای مدیریت ادمین‌های پنل VPN پاسارگاد/سیگما

</div>

---

<div dir="rtl">

## ویژگی‌ها

- **داشبورد ادمین** — مشاهده همه ادمین‌ها با مصرف، لیمیت و پروگرس‌بار
- **پورتال شخصی** — هر ادمین فقط اطلاعات خودش را می‌بیند
- **لیمیت PAMP** — تعیین لیمیت مستقل از پنل سیگما
- **اجرای خودکار** — غیرفعال‌سازی خودکار کاربران هنگام رسیدن به لیمیت
- **ترافیک مخفی** — محاسبه: `لیمیت کل یوزرها − مصرف یوزرها − مانده ادمین`
- **غیرفعال/فعال‌سازی** — کنترل دسترسی ادمین و کاربرانش از پنل
- **سینک خودکار** — دریافت داده هر N دقیقه (قابل تنظیم)
- **phpMyAdmin** — مدیریت دیتابیس از طریق وب در `/phpmyadmin/`
- **رابط شیشه‌ای** — طراحی تاریک و زیبا با گرادیانت

## نصب سریع

```bash
bash <(curl -Ls https://raw.githubusercontent.com/santiyagoburcart/PAMP/main/install.sh)
```

## نصب دستی

```bash
git clone https://github.com/santiyagoburcart/PAMP.git /opt/pamp
cd /opt/pamp
cp .env.example .env
nano .env  # مقادیر را وارد کنید
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

## دسترسی

| سرویس | آدرس |
|-------|------|
| پنل | `http://your-domain/` |
| phpMyAdmin | `http://your-domain/phpmyadmin/` |
| پنل جنگو | `http://your-domain/admin/` (فقط سوپریوزر) |

## نکات امنیتی

- فایل `.env` را **هرگز** در گیت‌هاب آپلود نکنید
- رمز عبور قوی برای دیتابیس انتخاب کنید
- دسترسی به phpMyAdmin از طریق nginx محدود شده است

</div>
