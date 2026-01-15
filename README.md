# Bank Chatbot

Simple Django app to find and compare bank loans using CSV data and an Ollama model fallback.

## Quick local setup ✅

1. Create & activate a virtualenv:
   - python -m venv .venv
   - On PowerShell: .venv\Scripts\Activate.ps1
2. Install dependencies:
   - pip install -r requirements.txt
3. Create a `.env` from `.env.example` and set `SECRET_KEY` and `DEBUG=False` for production.
4. Run migrations & collect static files:
   - python manage.py migrate
   - python manage.py collectstatic --noinput
5. Run the dev server:
   - python manage.py runserver

## Deployment (example: Heroku / any WSGI host) 🚀

- `requirements.txt`, `Procfile`, and `runtime.txt` are included for easy deployment to Heroku or similar providers.
- Ensure `SECRET_KEY` is set in environment, `DEBUG=False`, and `ALLOWED_HOSTS` set to your domain.
- Run `python manage.py migrate` and `python manage.py collectstatic --noinput` during deploy.

## Notes & Next steps 💡

- This project uses WhiteNoise to serve static files in production.
- CSV data is bundled in `chat/bank_loans.csv` — ensure the file has expected columns.
- Before deploying, set the following environment variables securely:
  - `SECRET_KEY` (use a long random string, **not** the default)
  - `DEBUG=False`
  - `ALLOWED_HOSTS` (comma-separated domains)
  - Optional: `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, etc.
- If you want, I can create a `docker-compose` file, CI workflow (GitHub Actions), or set up automated deployment.
