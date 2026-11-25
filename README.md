# Country Park Visitor Centre Assistant

A visitor can ask what to borrow at Shing Mun, check Sai Kung’s holiday hours or look up Tai Mo Shan’s renovation closure. Factual answers cite their sources. A staff follow-up stays in the local database and needs a reviewer’s approval.

**Snapshot** 26 November 2026, Asia/Hong_Kong. **Supported visit dates** 1 January 2026 through 31 December 2027. Published hours describe the timetable. The service cannot confirm that a centre opened on a particular day. [Sources and calendar rules](docs/sources.md)

## Run the local demo

Start the demo from a clean checkout with Git, Python 3 and Docker Compose.

```sh
git clone https://github.com/RoLBester/country-park-visitor-assistant.git
cd country-park-visitor-assistant
python3 scripts/setup_env.py
docker compose up --build -d --wait
python3 scripts/demo.py
```

Setup generates private database and access credentials in `.env`. Startup creates the PostgreSQL schema, enables pgvector and seeds the verified passages. The default demo uses a deterministic adapter and works without a model download. For another port, set `APP_PORT` in `.env` before starting Compose. Stop the services with `docker compose down`. The named volume retains the records.

Open the [interactive API](http://127.0.0.1:8765/docs). The walkthrough above produced these results. [Full demo response and audit](docs/demo.json)

| Step | Observed result |
| --- | --- |
| Ask what Shing Mun lends | A map, hiking poles and a power bank. The citation points to *Hiking Equipment Loan Service* on the centre’s page. |
| Ask for Sai Kung’s hours on 7 February | The assistant asks which year. With 2027 supplied, it looks up the date and reports the Lunar New Year day two closure. An ambiguous date such as `02/07/2027` prompts for `YYYY-MM-DD`. |
| Check Tai Mo Shan on 26 November 2026 | `notice_closed`. The whole centre was under renovation. Its ordinary Thursday timetable was 09:30–16:30. |
| Check Tai Mo Shan on 7 February 2027 | `scheduled_closed` under the Lunar New Year rule. The reply also identifies the renovation recorded on 26 November and says reopening is unconfirmed. |
| Ask about the accessible toilet at Tai Mo Shan | The centre page locates the toilet indoors. The cited notice says the entire centre closed for renovation on 1 July 2026. |
| Ask whether Sai Kung has free Wi-Fi | `unknown`, with no citation or draft. A question about the admission fee gets the cited free-entry policy. |
| Ask staff to check a visit on 2 January 2027 | The future status was unknown. The service returned a visible `pending` proposal with a centre, reason and sources. |
| Approve the proposal twice | Both responses contained the same follow-up ID. The audit contained one reviewer decision and one final creation. |

## Try a visitor or reviewer request

Use **Try it out** on `POST /ask`. For example, send `{"question":"Is Shing Mun open on 2027-02-09?"}`. Use `GET /status` for a read-only lookup with a centre, local date and optional area. The area `photo-exhibition` selects the Hiking Etiquette programme. `GET /snapshot` shows calendar coverage and notices. Each citation identifies a source, its URL, a section or date and the retrieval time.

To review a draft in the browser, follow these steps.

1. Send `{"question":"Please ask staff at Shing Mun to check the hiking pole loan service."}` to `POST /ask`. Copy the proposal and request IDs from the response.
2. In **Authorize**, paste `REVIEWER_TOKEN` from your local `.env`. The server maps it to `REVIEWER_ID`. Open `GET /review/proposals` to see the pending draft.
3. Use `POST /review/proposals/{proposal_id}/decision` with `{"decision":"approve"}` or `{"decision":"reject"}`. Read the events at `GET /review/requests/{request_id}/audit`. The visitor token receives HTTP 403 on reviewer routes.

Approval locks the proposal row and writes the review, state change, follow-up and audit events in one transaction. A repeated approval returns the original record. A rejected proposal retains its decision and history with zero follow-up rows.

## Use the local model

The tested provider was Ollama 0.40.18 with `gpt-oss:20b`. Start Ollama on the host and run `ollama pull gpt-oss:20b`. In `.env`, set `MODEL_PROVIDER=ollama`, then run `docker compose up -d --wait api`. Docker Desktop uses the example `OLLAMA_HOST=http://host.docker.internal:11434`. On Linux, bind Ollama to a Docker-reachable host address and set `OLLAMA_HOST` accordingly. The reviewer credentials are used only by the API. [Tested versions and model settings](docs/runtime.md)

For each question the service retrieves six pgvector neighbours using a 384-dimensional lexical vector. For Tai Mo Shan it also retrieves the renovation notice. The model selects passages or calls a typed tool. The API checks the arguments and evidence IDs. For a question covered by the indoor toilet or ramp listing, the API pairs the listing with the notice and records the model’s original selection in the audit. The car park has its own passage. A question can produce at most one draft. Only the review endpoint can create a final record.

## Repeat the checks

Run the checks while the database and API are up.

```sh
docker compose exec -T api python -m pytest -q -p no:cacheprovider
docker compose exec -T api python -m evaluation.run --adapter fixture
docker compose exec -T api python -m evaluation.run --adapter ollama
```

The last command requires the local model. Each run gets an isolated PostgreSQL schema. The evaluators write JSON to standard output, progress to standard error and exit with code 1 if a label is missed. Pytest passed 102/102. The deterministic evaluation passed 52/52, and the Ollama-backed API passed 51/52. The model missed the printed-leaflet question. [Results by category](docs/results.md) · [Labelled cases](evaluation/cases.json)
