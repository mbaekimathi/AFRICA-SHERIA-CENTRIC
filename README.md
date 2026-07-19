# Sheria-Centric

Professional practice management web app for advocates.

## Stack

- **Backend:** Django 5.0
- **Database:** MySQL / MariaDB via PyMySQL
- **Auth user model:** `accounts.Employee`
- **Frontend:** HTML5, modern CSS, vanilla JavaScript
- **Theme:** Professional purple with justice iconography

## Roles

Firm Administrator · Managing Partner · Advocate · Intern · IT Support · Employee

## Status flow

| Status | After login |
| --- | --- |
| Pending Approval | About Work page |
| Active | Role dashboard |
| Suspended | Warning popup (no access) |

New signups start as **Employee** + **Pending Approval**.

## Database

MySQL only. Default name: **`v.2-sheria-centric-db`**

On start, missing database/tables are created automatically (once per process).

> Local MariaDB 10.4 works with **Django 5.0**. Django 6 needs MariaDB 10.6+.

## Quick start

```bash
py -m pip install -r requirements.txt
copy .env.example .env
py manage.py migrate
py manage.py runserver
```

- Home: http://127.0.0.1:8000/
- Employee login: http://127.0.0.1:8000/employee/login/
- Client login: http://127.0.0.1:8000/client/login/
- Client signup: http://127.0.0.1:8000/client/signup/
- Employee signup: http://127.0.0.1:8000/signup/
- Approve employees in Django admin: set `status` to Active and assign `role`
- Manage clients in Django admin: status starts as **Pending Onboarding**

### View on another device (same Wi‑Fi)

`runserver` binds to **all interfaces** and prints a **Network** link in the terminal, for example:

`http://192.168.x.x:8000/`

Open that URL on your phone or tablet. Both devices must be on the same network. If the page does not load, allow Python through Windows Firewall when prompted (or add an inbound rule for port 8000).

Optional Google client sign-in: set `GOOGLE_CLIENT_ID` in `.env` (Google Cloud OAuth Web client ID).

## `.env` (keep it short)

Copy `.env.example` → `.env`. **Domain auto-picks** from the URL visitors use (no `SITE_URL` / `ALLOWED_HOSTS` needed).

**Local:**

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
DB_PASSWORD=
```

**Production (cPanel)** — use the DB name/user from **MySQL Databases** (not `root`):

```env
DB_NAME=baunilaw_yourdb
DB_USER=baunilaw_youruser
DB_PASSWORD=your_db_password
DB_HOST=localhost
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

Auto-picked: `SECRET_KEY`, `DEBUG` (off under Passenger), any domain/host, CSRF origins, OAuth callback, MySQL defaults, firm/Drive names.

## GitHub + cPanel deploy

Remote: https://github.com/mbaekimathi/AFRICA-SHERIA-CENTRIC.git

### Push from this machine

```bash
git push -u origin main
```

`.env` and `.secret_key` are gitignored — never commit secrets.

### First deploy on cPanel

1. **Create a MySQL database** in cPanel and note name, user, password, host.
2. **Setup Python App** (cPanel → Software → Setup Python App):
   - Application root = folder that contains `manage.py`
   - Startup file = `passenger_wsgi.py`
   - Entry point = `application`
   - Create / attach a virtualenv, then install deps:
     ```bash
     pip install -r requirements.txt
     ```
3. **Clone** into that app folder (or pull if already cloned):
   ```bash
   git clone https://github.com/mbaekimathi/AFRICA-SHERIA-CENTRIC.git .
   ```
4. **Create `.env` on the server** with DB (+ Google) only — domain auto-picks.
5. Collect static files and migrate:
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```
6. Restart the Python app (`touch tmp/restart.txt` or use the cPanel restart button).

### Later updates on cPanel

```bash
git pull origin main
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
touch tmp/restart.txt
```
