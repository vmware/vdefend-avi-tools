FROM python:3.13-slim

# Run as an unprivileged user.
RUN useradd --create-home --uid 1000 site
WORKDIR /app
COPY --chown=site:site . /app
USER site

EXPOSE 8000

# Rebuild site/data/index.json on every start (so restarting picks up edited tool
# files), then serve the site on port 8000.
CMD ["sh", "-c", "python3 build/build.py && exec python3 -m http.server 8000 --bind 0.0.0.0 --directory site"]
