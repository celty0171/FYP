# VizLM shareable deployment image.
#
# Runs the deterministic Step 1->2->3 web front-end (experiments/web_pipeline/server.py)
# against a live PostgreSQL Mondial database (VIZER_DATASOURCE=postgres), with the LLM
# features (natural-language box + LLM Step-2) enabled via env vars set on the host.
#
# The server is std-lib; the pip deps are for the production layer (openai for the LLM;
# SQLAlchemy/psycopg2 for the live PostgreSQL data source — see experiments/requirements.txt).
FROM python:3.12-slim

WORKDIR /app

# Install deps first for better layer caching.
COPY experiments/requirements.txt experiments/requirements.txt
RUN pip install --no-cache-dir -r experiments/requirements.txt

# Bring in the repo. server.py imports the LLM-authored programs at runtime from
# results/prompt_v9_codegen/, results/step2_codegen/ and results/viz_codegen_*/, and reads
# experiments/mondial_database/*.json — all included by this copy (see .dockerignore).
COPY . .

# Data source + LLM config are provided as env vars by the host (see render.yaml); config.py
# reads os.environ with precedence over any .env, and .env is never copied into the image.
# Data source defaults to live PostgreSQL (config.py) unless VIZER_DATASOURCE is set otherwise.
ENV PYTHONUNBUFFERED=1

# Bind all interfaces; take the port from the platform's $PORT (Render/Railway/etc.), else 8090.
CMD ["sh", "-c", "python experiments/web_pipeline/server.py --host 0.0.0.0 --port ${PORT:-8090}"]
