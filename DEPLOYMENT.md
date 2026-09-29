# Deploying the FC Middleware with Docker

One image runs every part of the middleware. Docker Compose starts it as separate services behind NGINX:

| Service | What it does | Started by `up` |
|---|---|---|
| `nginx` | Public entry point on ports 80 (and 443 once TLS is enabled). Serves `/static/` and `/media/`, proxies everything else to `web` | yes |
| `web` | Django API and admin under Gunicorn. Runs migrations and `collectstatic` on start | yes |
| `worker` | Celery worker: posts POS GRNs, returns and wastage to ByD, and sends invoices to Restroworks | yes |
| `beat` | Celery scheduler: invoice poll and re-queue of stale work. Run exactly one | yes |
| `redis` | Celery broker | yes |
| `sales-sync` | The daily sales posting job (`sales_aggregation.icg_to_byd`), run on demand | no, see below |
| `db` | MySQL 8, for environments without an existing database | only with `--profile local-db` |

Only NGINX publishes ports. Gunicorn, Redis and MySQL are reachable only on the internal Compose network.

## First deployment

1. Install Docker Engine with the Compose plugin on the server.
2. If Apache (or anything else) listens on port 80 or 443, stop it. Alternatively, change the `nginx` port mapping in `docker-compose.yml`.
3. Create the environment file, then fill in every value. The comments in the file explain each one.
   ```bash
   cp .env.example .env
   ```
   - **Existing MySQL on the same server** (the current setup): set `DB_HOST=host.docker.internal`. Make sure MySQL accepts connections from the Docker network: `bind-address` must not be only `127.0.0.1`, and the user needs host `%` or `172.%`.
   - **New, self-contained environment:** set `DB_HOST=db` and start with `--profile local-db`.
4. Build and start:
   ```bash
   docker compose up -d --build                        # existing MySQL
   docker compose --profile local-db up -d --build     # bundled MySQL
   ```
5. Create an admin user the first time:
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```
6. Check:
   ```bash
   curl http://<server>/nginx-health        # ok
   curl -I http://<server>/admin/login/     # 200
   docker compose ps                        # web healthy, worker and beat running
   ```

Then do the one-off admin setup for the POS integration, in the Django admin:

- enter each store's Restroworks `storeId` in **Store → Pos store id**;
- create the groups `restroworks` and `store_requisition`;
- create a service user for Restroworks and one for the Store Requisition Portal, and put each in its group.

The POS settings in `.env` (`POS_*` and `RESTROWORKS_*`) are explained in `.env.example`.

## HTTPS

Restroworks will call the webhooks over the internet, so production must be HTTPS.

1. Put `fullchain.pem` and `privkey.pem` in `nginx/certs/`. This folder is not committed.
2. In `nginx/conf.d/`:
   - rename `middleware-https.conf.example` to `middleware-https.conf`;
   - replace `middleware.example.com` with the real host name;
   - delete `middleware.conf`.
3. In `.env`, set:
   ```
   DJANGO_ALLOWED_HOSTS=<host name>
   DJANGO_CSRF_TRUSTED_ORIGINS=https://<host name>
   ```
4. Restart: `docker compose up -d` and `docker compose restart nginx`.

## Daily sales sync

The job used to run from a scheduled task, and it still does. It reads its settings from `config/sales_aggregation.json`, which is not committed.

1. Create the config file:
   ```bash
   cp config/sales_aggregation.json.example config/sales_aggregation.json
   ```
2. Schedule the job on the host, for example with cron at 06:00 every day:
   ```
   0 6 * * * cd /opt/fc-middleware && docker compose run --rm sales-sync >> /var/log/fc-sales-sync.log 2>&1
   ```

The job's own log files and Excel reports are kept in the `sales_logs` and `sales_reports` volumes.

The optional desktop window for the sync (`"show_ui": true`) is not available in the container. To use it on a workstation, install `requirements-gui.txt` there.

## Everyday operations

| Task | Command |
|---|---|
| Logs | `docker compose logs -f web worker beat nginx` |
| Deploy a new version | `git pull && docker compose up -d --build` (migrations run automatically) |
| Django shell | `docker compose exec web python manage.py shell` |
| Run the POS tests | `docker compose exec -e CELERY_TASK_ALWAYS_EAGER=True -e BYD_POST_DELAY_SECONDS=0 web python manage.py test pos_services` |
| Stop everything | `docker compose down` (volumes and data are kept) |

## Running without Docker

For development on Windows:

1. Create or activate the project venv.
2. Install the requirements:
   ```bash
   uv pip install -r requirements.txt
   ```
   Add `requirements-gui.txt` for the sync window.
3. Start Django as before:
   ```bash
   python manage.py runserver
   ```
4. Start Celery:
   ```bash
   celery -A middleware worker --pool=solo -l info
   celery -A middleware beat -l info
   ```
   Celery needs a Redis you can reach, set in `CELERY_BROKER_URL`.

## What changed in `requirements.txt`

The old file was a full `pip freeze` of a desktop environment: 79 pins, including PyQt5, PyQt6, PySide2, customtkinter, PyAutoGUI, matplotlib, pytesseract and their dependencies. Apart from PySide2, which only the optional sync window uses, the middleware imports none of them.

The file now has 19 pins. Packages that were already there keep the version in use:

- the packages the code imports;
- `gunicorn`, the container's web server;
- three supporting pins, `setuptools`, `numpy` and `tzdata`. The reason for each is noted beside it in the file.

pip resolves their own dependencies at install.

`PySide2` moved to `requirements-gui.txt`, because only the optional sync window uses it.
