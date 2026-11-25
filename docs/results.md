# Evaluation results

On 26 November 2026 the deterministic API passed all 52 labelled cases. The Ollama-backed API passed 51. Both ran from a clean checkout against PostgreSQL 19.0 and pgvector 0.8.7, using separate schemas. The questions and reviewer actions were synthetic. The visitor facts came from the published snapshot. [Labels](../evaluation/cases.json) · [Scoring code](../evaluation/run.py) · [Tested runtime](runtime.md)

| Cases | Deterministic | Ollama with gpt-oss:20b |
| --- | ---: | ---: |
| Guidance with the expected content, passages and citations | 15/15 | 14/15 |
| Date lookup with the expected call, arguments, status, rule and sources | 18/18 | 18/18 |
| Unknown or clarification with no selection, citation, tool or draft | 10/10 | 10/10 |
| Draft, reviewer decision, final records and audit | 9/9 | 9/9 |
| **All API cases** | **52/52** | **51/52** |

The scores describe the complete API. They include date clarifications made before inference and the shared rule for indoor facilities. The observation files record the answers, selected and retrieved passages, citations, tools and draft states. For the indoor facility they also record the adapter’s original decision. [Deterministic observations](../evaluation/observed-fixture.json) · [Ollama observations](../evaluation/observed-ollama.json)

## Visitor regressions

The expanded suite had 25 failures and 77 passes against the application at `78a24c8`. The deterministic adapter gave weekly hours for the missing year and cited free admission for both Wi-Fi questions. Both adapters omitted the renovation from the toilet answer. The February holiday returned unknown on both status routes, and the conversational route staged a draft.

| Question or visit | Final result |
| --- | --- |
| Sai Kung hours on 7 February, then on 7 February 2027 | Both adapters asked for the year first, then called `lookup_status` and returned the scheduled lunar day two closure. The ambiguous numeric date prompted for `YYYY-MM-DD`. Neither clarification staged a draft. The weekly-hours question still returned the timetable. |
| Tai Mo Shan on 7 February 2027 | Both routes returned `scheduled_closed`, citing the centre rule and the HKO calendar. The renovation appeared separately with its observation date and unconfirmed reopening. The same routes returned `notice_closed` on 26 November 2026 and `unknown` on 2 January 2027. |
| Accessible toilet at Tai Mo Shan | Both APIs cited the indoor listing and the notice closing the entire centre from 1 July 2026. The fixture selected the listing. Ollama supplied both passage IDs but marked its decision `unknown`. The API verified that the question matched the indoor listing and returned the pair. The separate car park question cited only the parking listing. |
| Free Wi-Fi at Sai Kung | Both phrasings returned `unknown` with empty selections, citations and tools, and no draft. Asking whether admission is free returned the cited AFCD policy. |

AFCD lists the toilet and car park in separate entries and gives the first two lunar days as closures. HKO places day two on 7 February 2027. The dated renovation notice gives no reopening date. [Tai Mo Shan centre](https://www.afcd.gov.hk/english/country/cou_lea/cou_lea_ven/taimoshan.html) · [Closure notice](https://www.hiking.gov.hk/console/public/uploads/news/fd2be37e754a5b6f18f13b50323e587846fcf797.pdf) · [HKO calendar](https://www.hko.gov.hk/en/gts/time/calendar/text/files/T2027e.txt)

**A08 was the one miss.** Ollama retrieved the printed-leaflet passage first and returned `unknown`. AFCD says it stopped printing the material and directs visitors to its online information. The deterministic adapter returned that policy with its citation. [AFCD FAQ, question 5](https://www.afcd.gov.hk/english/faq/faq_cou/faq_cou.html)

## Tests and approval records

Pytest passed **102/102**, including all **3/3** synthetic notice cases. Those three cases use invented notices and are scored only in pytest. Tests also covered read-only status queries, malformed tool arguments, model outages, reviewer permissions and transaction rollback.

The README demo started with zero requests, proposals, reviews or follow-ups. SQL confirmed that all 26 indexed passages and 16 source records matched the snapshot files. Approving the demo proposal twice produced one review and one follow-up. All six recorded events matched the database. In each adapter’s approval evaluation, rejection created zero follow-ups and six concurrent approvals returned the same follow-up ID, with one review and one creation event. [Demo response and audit](demo.json) · [Approval checks](../evaluation/support.py)
