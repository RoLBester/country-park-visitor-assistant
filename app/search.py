import hashlib
import math
import re
from collections import Counter

from .types import Centre

STOP = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "can",
    "centre",
    "center",
    "country",
    "date",
    "do",
    "does",
    "for",
    "from",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "park",
    "parks",
    "please",
    "the",
    "there",
    "they",
    "this",
    "to",
    "visitor",
    "visitors",
    "what",
    "where",
    "which",
    "will",
    "with",
    "you",
    "your",
    "sai",
    "kung",
    "shing",
    "mun",
    "tai",
    "mo",
    "shan",
}


def words(text):
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


# Ignore question framing when checking whether a passage covers the requested topic.
QUESTION_FRAMING = {
    "about",
    "also",
    "any",
    "as",
    "available",
    "by",
    "centres",
    "could",
    "currently",
    "find",
    "get",
    "give",
    "goes",
    "has",
    "here",
    "if",
    "inside",
    "know",
    "like",
    "located",
    "many",
    "may",
    "much",
    "offered",
    "our",
    "policy",
    "provide",
    "provided",
    "provides",
    "s",
    "should",
    "some",
    "sort",
    "tell",
    "their",
    "them",
    "these",
    "those",
    "under",
    "us",
    "use",
    "using",
    "we",
    "who",
    "would",
}


def evidence_terms(text):
    terms = set()
    for word in words(text):
        if word in QUESTION_FRAMING:
            continue
        if word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and not word.endswith("ss"):
            word = word.removesuffix("s")
        terms.add(word)
    return terms


def question_topics(question):
    requested = evidence_terms(question)
    if re.search(r"\bhow much\b", question, re.IGNORECASE):
        requested.add("cost")
    if re.search(
        r"\bhow (?:to |(?:do|can|should) (?:i|we|you) )?get (?:there|to)\b",
        question,
        re.IGNORECASE,
    ):
        requested.add("transport")
    return requested


def supports_topic(passage, requested):
    keywords = evidence_terms(passage["keywords"])
    return (
        math.isfinite(passage["similarity"])
        and bool(requested & keywords)
        and requested <= keywords | evidence_terms(passage["text"])
    )


def listed_indoor_facility(question, centre, found):
    if centre != Centre.TAI or not {"tms-access", "tms-closure"} <= found.keys():
        return False
    requested = question_topics(question)
    return bool(
        requested & {"toilet", "restroom", "bathroom", "ramp"}
    ) and supports_topic(found["tms-access"], requested)


def embedding(text):
    """A deterministic lexical vector for this short, English-language collection."""
    vector = [0.0] * 384
    for token, count in Counter(words(text)).items():
        slot = int.from_bytes(
            hashlib.blake2b(token.encode(), digest_size=4).digest(), "big"
        ) % len(vector)
        vector[slot] += 1 + math.log(count)
    return "[" + ",".join(f"{v:.5f}" for v in vector) + "]"


def retrieve(conn, question, centre, limit=6):
    vec = embedding(question)
    rows = conn.execute(
        """
        SELECT id, source_id, centre, locator, text, keywords,
               1 - (embedding <=> %s::vector) AS similarity
        FROM passages
        WHERE (%s::text IS NULL OR centre IS NULL OR centre = %s)
        ORDER BY embedding <=> %s::vector, id
        LIMIT %s
    """,
        (vec, centre, centre, vec, limit),
    ).fetchall()
    # Keep the operative renovation notice beside retrieved descriptions of this site.
    if centre == "tai-mo-shan" and all(p["id"] != "tms-closure" for p in rows):
        rows.extend(
            conn.execute(
                """SELECT id, source_id, centre, locator, text, keywords,
                    1 - (embedding <=> %s::vector) AS similarity FROM passages WHERE id='tms-closure'""",
                (vec,),
            ).fetchall()
        )
    return rows
