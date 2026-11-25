"""Generate credentials for one local installation. Preserve an existing configuration."""

import os
from pathlib import Path
from secrets import token_urlsafe

root = Path(__file__).resolve().parents[1]
lines = (root / ".env.example").read_text().splitlines()
secrets = {"POSTGRES_PASSWORD", "REVIEWER_TOKEN", "VISITOR_TOKEN"}
try:
    handle = os.open(root / ".env", os.O_WRONLY | os.O_EXCL | os.O_CREAT, 0o600)
except FileExistsError:
    print("Using the existing .env.")
else:
    with os.fdopen(handle, "w") as file:
        for line in lines:
            name = line.partition("=")[0]
            print(f"{name}={token_urlsafe(32)}" if name in secrets else line, file=file)
    print("Created .env with local database and reviewer credentials.")
