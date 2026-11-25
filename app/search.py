import hashlib
import math
import re
from collections import Counter

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
