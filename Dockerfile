FROM ghcr.io/astral-sh/uv:0.13.10@sha256:a3ea1357342c1a4bf9a0c53a3deb1b55379aefa037338d8113d5771efa01774f AS installer
FROM python:3.15.2-slim-trixie@sha256:63bb298d2b7b88f176f51b5189f54ce6535c997682ea70885d2132f5d473a8a5 AS runtime
COPY --from=installer /uv /usr/local/bin/uv
FROM runtime AS swagger
ADD --checksum=sha256:685a2b38b5d6eab2dbc096a8596db11cc7409cdb671d2e3bec8f9b017d0d566b https://registry.npmjs.org/swagger-ui-dist/-/swagger-ui-dist-5.36.0.tgz /tmp/swagger.tgz
RUN mkdir /ui && tar xzf /tmp/swagger.tgz -C /ui --strip-components=1 \
    package/swagger-ui.css package/swagger-ui-bundle.js package/favicon-32x32.png \
    package/LICENSE package/NOTICE package/swagger-ui-bundle.js.LICENSE.txt
FROM runtime AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Hong_Kong
WORKDIR /service
COPY requirements.lock .
RUN uv pip install --system --no-cache --require-hashes -r requirements.lock
COPY app app
COPY data data
COPY evaluation evaluation
COPY tests tests
COPY pyproject.toml .
COPY --from=swagger /ui /service/ui
USER 65534:65534
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
