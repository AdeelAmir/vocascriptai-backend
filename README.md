# BriefRoom Backend

FastAPI backend managed with `uv`, PostgreSQL, and Alembic. Python 3.11 is
pinned in `.python-version`, while `uv.lock` contains the reproducible dependency
resolution.

## Recommended: run locally without Docker

Prerequisites: Git and access to a PostgreSQL database such as Neon.

1. Install `uv` on Windows:

   ```powershell
   winget install --id=astral-sh.uv -e
   ```

2. Create `.env` from the safe template and replace its placeholders:

   ```powershell
   Copy-Item .env.example .env
   ```

   For an existing deployment, securely copy its `.env` instead. Keep the same
   `ENCRYPTION_KEY` when moving an existing database because encrypted values
   depend on it. Never commit `.env`.

3. Install the pinned Python version and exact locked dependencies:

   ```powershell
   uv python install
   uv sync --frozen
   ```

4. Apply migrations and start the API:

   ```powershell
   uv run --frozen alembic upgrade head
   uv run --frozen uvicorn app.main:app --reload --port 7860
   ```

The API is available at `http://localhost:7860`, interactive documentation at
`http://localhost:7860/docs`, and health status at
`http://localhost:7860/health`.

Do not copy `.venv` between machines. `uv sync --frozen` recreates it from the
committed project and lock files.

## Generate local security values

After `uv sync`, generate values for a new local environment with:

```powershell
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Use the first output as `JWT_SECRET_KEY` and the second as `ENCRYPTION_KEY`.

## Optional local PostgreSQL

The simplest no-Docker setup is a managed development database such as a
separate Neon branch. Native PostgreSQL also works; set `DATABASE_URL` to an
asyncpg URL such as:

```text
postgresql+asyncpg://user:password@localhost:5432/database
```

Docker Compose remains available as an optional isolated stack:

```powershell
docker compose up --build -d
docker compose logs -f backend
```

Compose persists PostgreSQL and uploaded files in named volumes. Do not run
`docker compose down -v` unless you intentionally want to delete that local
data.

## Database migrations

Development startup applies pending migrations automatically. They can also be
managed explicitly:

```powershell
uv run --frozen alembic upgrade head
uv run alembic revision --autogenerate -m "describe_change"
```

Apply and review migrations separately during production deployment. Always
back up production data before a schema migration.

## Create the initial admin

The seeder contains no default credentials. Run it interactively:

```powershell
uv run --frozen python scripts/seed_admin.py
```

For non-interactive use, set `INITIAL_ADMIN_EMAIL` and
`INITIAL_ADMIN_PASSWORD` in the process environment. The password must contain
at least 12 characters.

## Tests

```powershell
uv run --frozen python -m unittest discover -s tests -v
```

## Important files

- `app/main.py`: FastAPI entry point and lifespan.
- `app/core/config.py`: environment variable schema.
- `app/core/database.py`: SQLAlchemy engine and Alembic startup helper.
- `migrations/`: database migrations.
- `.env.example`: safe configuration template; `.env` stays untracked.
- `docker-compose.yaml`: optional isolated API/database stack.
