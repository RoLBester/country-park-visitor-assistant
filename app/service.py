from uuid import uuid4

from . import db
from .context import resolve
from .model import ModelUnavailable
from .search import listed_indoor_facility, retrieve
from .snapshot import DAY, fact_citations, lookup
from .types import DraftTool, Lookup, Question, Reply, Selection

UNKNOWN = "I couldn't find a published answer to that question in the visitor-centre snapshot."
CLARIFY = "Which centre do you mean (Sai Kung, Shing Mun or Tai Mo Shan)?"


def ask(q: Question, model):
    ctx = resolve(q)
    with db.connect() as conn:
        rows = retrieve(conn, q.question, ctx.centre)
    found = {p["id"]: p for p in rows}
    sources = list(dict.fromkeys(p["source_id"] for p in rows))
    trace = [("retrieved", sources, {"passage_ids": list(found)})]
    reply = Reply(
        request_id=uuid4(),
        decision="unknown",
        answer=UNKNOWN,
        snapshot_date=DAY,
        citations=[],
        retrieved_passage_ids=list(found),
        selected_passage_ids=[],
        tools_used=[],
    )
    draft = None
    if ctx.clarify:
        reply.decision, reply.answer = "clarify", ctx.clarify
        return db.save_request(reply, None, trace)
    tool = "lookup_status" if ctx.timed else "propose_followup" if ctx.follow else None
    action = model.choose(q.question, ctx, rows, tool)
    try:
        if tool == "lookup_status":
            if action.name != tool:
                raise ValueError("Expected a status tool call.")
            args = Lookup.model_validate(action.args)
            if (args.centre, args.local_date, args.area) != (
                ctx.centre,
                ctx.day,
                ctx.area,
            ):
                raise ValueError("Tool arguments disagree with the visitor's request.")
            status = lookup(args)
            reply.lookup = status
            reply.answer, reply.decision, reply.citations = (
                status.message,
                "status",
                status.citations,
            )
            reply.tools_used.append(tool)
            trace.append(
                (
                    "lookup_status",
                    status.source_ids,
                    status.model_dump(mode="json", exclude={"citations"}),
                )
            )
            if ctx.follow or (status.status == "unknown" and not ctx.no_follow):
                tool = "propose_followup"
                try:
                    action = model.choose(q.question, ctx, rows, tool, status)
                except ModelUnavailable:
                    trace.append(
                        (
                            "proposal_unavailable",
                            status.source_ids,
                            {"outcome": "model_unavailable"},
                        )
                    )
                    reply.answer += (
                        " The model was unavailable to prepare a review draft."
                    )
                    return db.save_request(reply, None, trace)
            else:
                tool = None
        if tool == "propose_followup":
            if action.name != tool:
                raise ValueError("Expected a proposal tool call.")
            candidate = DraftTool.model_validate(action.args)
            allowed = set(sources) | (
                set(reply.lookup.source_ids) if reply.lookup else set()
            )
            if (
                candidate.centre != ctx.centre
                or not set(candidate.source_ids) <= allowed
            ):
                raise ValueError("Unverified proposal references or centre.")
            draft = candidate
            reply.tools_used.append(tool)
            if not reply.lookup:
                reply.decision = "proposal"
                reply.answer = (
                    "A local staff follow-up draft is awaiting reviewer approval."
                )
                reply.citations = fact_citations(
                    [p for p in rows if p["source_id"] in draft.source_ids]
                )
            else:
                reply.answer += (
                    " A local staff follow-up draft is awaiting reviewer approval."
                )
        elif not reply.lookup:
            if action.name != "respond":
                raise ValueError("Unrecognised action.")
            selection = Selection.model_validate(action.args)
            if not set(selection.passage_ids) <= found.keys():
                raise ValueError("A citation was outside the retrieved records.")
            if listed_indoor_facility(q.question, ctx.centre, found):
                pair = ["tms-access", "tms-closure"]
                trace.append(
                    (
                        "indoor_facility",
                        [found[k]["source_id"] for k in pair],
                        {
                            "model_decision": selection.decision,
                            "model_passage_ids": selection.passage_ids,
                            "passage_ids": pair,
                        },
                    )
                )
                selection = Selection(decision="answer", passage_ids=pair)
            if selection.decision == "clarify":
                reply.decision, reply.answer = "clarify", CLARIFY
            elif selection.decision == "answer" and selection.passage_ids:
                facts = [found[k] for k in dict.fromkeys(selection.passage_ids)]
                if not ctx.centre and any(p["centre"] for p in facts):
                    reply.decision, reply.answer = "clarify", CLARIFY
                else:
                    # The renovation covers the centre and its indoor facilities.
                    if {"tms-hours", "tms-access"} & set(selection.passage_ids):
                        if "tms-closure" not in found:
                            return db.save_request(reply, None, trace)
                        if all(p["id"] != "tms-closure" for p in facts):
                            facts.append(found["tms-closure"])
                    reply.decision = "answer"
                    reply.selected_passage_ids = [p["id"] for p in facts]
                    reply.citations = fact_citations(facts)
                    reply.answer = " ".join(p["text"] for p in facts)
    except ValueError:
        trace.append(
            (
                "action_declined",
                [],
                {"action": action.name, "outcome": "invalid_tool_or_evidence"},
            )
        )
        if reply.lookup:
            reply.answer += " A proposal could not be validated."
    return db.save_request(reply, draft, trace)
