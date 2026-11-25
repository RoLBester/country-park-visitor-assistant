# Tested runtime

The project checked the following stable releases on 26 November 2026. The Dockerfile pins the Python and uv multi-platform images by digest. Compose pins the combined database/extension image. The Python lock contains exact resolved versions and distribution hashes. [Dockerfile](../Dockerfile) · [Compose configuration](../compose.yaml) · [Dependency lock](../requirements.lock)

| Component | Tested version | Upstream release or documentation |
| --- | --- | --- |
| CPython | 3.15.2 | [Python release](https://www.python.org/downloads/release/python-3152/) |
| PostgreSQL / pgvector | 19.0 / 0.8.7 | [PostgreSQL release](https://www.postgresql.org/docs/release/19.0/) · [pgvector changes](https://github.com/pgvector/pgvector/blob/v0.8.7/CHANGELOG.md) |
| FastAPI / Starlette | 0.165.0 / 1.10.0 | [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/) · [Starlette release](https://github.com/Kludex/starlette/releases/tag/1.10.0) |
| Uvicorn / Pydantic | 0.54.0 / 2.14.4 | [Uvicorn release](https://github.com/Kludex/uvicorn/releases/tag/0.54.0) · [Pydantic release](https://github.com/pydantic/pydantic/releases/tag/v2.14.4) |
| Psycopg and its binary package | 3.3.9 | [Psycopg releases](https://www.psycopg.org/psycopg3/docs/news.html) |
| Ollama server / Python client | 0.40.18 / 0.6.3 | [Server release](https://github.com/ollama/ollama/releases/tag/v0.40.18) · [Python client](https://pypi.org/project/ollama/0.6.3/) · [Tool calling](https://docs.ollama.com/capabilities/tool-calling) |
| HTTPX / HTTPX2 | 0.28.1 / 2.16.2 | Ollama imports HTTPX. Starlette uses HTTPX2 for its test client. [HTTPX releases](https://github.com/encode/httpx/releases) · [HTTPX2 changelog](https://github.com/pydantic/httpx2/blob/main/src/httpx2/CHANGELOG.md) |
| pytest / uv | 9.2.0 / 0.13.10 | [pytest changes](https://docs.pytest.org/en/stable/changelog.html) · [uv release](https://github.com/astral-sh/uv/releases/tag/0.13.10) |
| Swagger UI | 5.36.0 | The build verifies the distribution checksum and serves the assets locally. [Release](https://github.com/swagger-api/swagger-ui/releases/tag/v5.36.0) |
| Docker Compose | 5.8.0 | [Compose release](https://github.com/docker/compose/releases/tag/v5.8.0) |

The Docker Desktop host supplied Engine 29.9.3. Engine 29.10.1 was available upstream. No application dependency requires the older daemon. The exact host version describes the environment used to run the pinned containers. [Engine releases](https://docs.docker.com/engine/release-notes/29/)

The live evaluation used Ollama’s `gpt-oss:20b` model with temperature 0, seed 17, low reasoning effort and an 8,192-token context. Its manifest digest is recorded with the observations. It runs on the host and requires enough memory for the approximately 13 GB model download. For the default deterministic demo, the API needs only Docker. [Ollama model](https://ollama.com/library/gpt-oss:20b)
