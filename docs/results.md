# Evaluation results

Both adapters ran through FastAPI against PostgreSQL 19.0 with pgvector 0.8.7 on 26 November 2026. Each run used a fresh schema. The 43 API cases use synthetic visitor questions and reviewer actions. Three additional rule cases use invented notices and run only in pytest. [Labels](../evaluation/cases.json) · [Scoring code](../evaluation/run.py)

| What had to match | Deterministic adapter | Ollama with gpt-oss:20b |
| --- | ---: | ---: |
| Guidance answer, expected content, specific passage and source | 12/12 | 11/12 |
| Native lookup call or fixture equivalent, exact arguments, status, rule and source | 16/16 | 16/16 |
| Unknown or clarification, with no tool action | 6/6 | 6/6 |
| Draft, review decision, final rows and audit history | 9/9 | 9/9 |
| All API cases | **43/43** | **42/43** |

The model used public passages and synthetic questions with the local Ollama server. The service resolved visitor-supplied centre and date information and offered the permitted function for that request. A lookup earned credit only when the adapter returned the call and the database-backed API produced the expected response. The boundary score includes clarifications the service can make before inference. These are development cases. [Fixture observations](../evaluation/observed-fixture.json) · [Real-model observations and model digest](../evaluation/observed-ollama.json)

## Observed cases

- **A02, equipment.** Both runs returned Shing Mun’s map, hiking poles and power bank with the centre’s *Hiking Equipment Loan Service* citation. [AFCD centre page](https://www.afcd.gov.hk/english/country/cou_lea/cou_lea_ven/shingmun.html)
- **A08, printed leaflets.** The real model answered that it could not find a published answer. Retrieval had supplied the correct passage. AFCD says it stopped printing the material and makes visitor information available online. The scorer counted the abstention as a miss. [AFCD FAQ, question 5](https://www.afcd.gov.hk/english/faq/faq_cou/faq_cou.html)
- **L05–L06, lunar dates.** Both runs returned a scheduled closure on Sunday 7 February 2027, lunar day two. On Tuesday 9 February they returned published hours of 09:30–16:30 under the public holiday rule. [HKO calendar](https://www.hko.gov.hk/en/gts/time/calendar/text/files/T2027e.txt) · [1823 events](https://www.1823.gov.hk/common/ical/en.json)
- **L08 and L11, renovations.** The whole-centre closure overrode the normal Tai Mo Shan timetable on 1 July 2026. For 2 January 2027 both runs returned unknown and staged a review draft. The source gave no reopening date. [AFCD notice](https://www.hiking.gov.hk/console/public/uploads/news/fd2be37e754a5b6f18f13b50323e587846fcf797.pdf)
- **R05 and R08, reviewer decisions.** Direct SQL checks found zero follow-ups after rejection. Six simultaneous approvals returned the same result, with one review, one follow-up and one creation event. The worked demo also records the source IDs, tool outcome, reviewer, decision and Hong Kong timestamps. [Demo and audit](demo.json)

**pytest passed 70/70 checks.** This includes all three synthetic notice cases (3/3), argument validation, the absence of writes on a direct status lookup, out-of-request citations, model outages, reviewer authentication and rollback after an interrupted audit write. The synthetic cases are excluded from both API denominators.
