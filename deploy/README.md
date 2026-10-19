# Registration-free private browser trial

Hosted mode uses server-side browser sessions: no registration or entrance password, only the current browser's uploads/jobs/media are accessible. A shared export password unlocks that browser's clean results for one hour. Before unlocking, users receive a marked, silent preview up to 10 seconds at 1280 pixels maximum edge. This is an export gate, not DRM. Changing browser or clearing cookies loses access. A shared device/browser profile shares an identity; server operators retain disk access.

Use a dedicated unprivileged account, a recent FFmpeg/FFprobe (8.1 tested), `requirements-server.txt` in a virtual environment and an immutable release at `/opt/unwatermark/current`. Keep Uvicorn on loopback, trust proxy headers only from loopback, and use TLS. The example domain/paths must be adapted. No Nginx Basic Auth is needed after the new application authorization is verified. HTTP only redirects to HTTPS or serves ACME challenges.

Before starting hosted mode, create `/var/lib/unwatermark/export-password.json` owned by the service user, mode 600. Generate it without exposing a password in shell arguments:

```python
# Run from the source directory using the service virtual environment.
import getpass,json,os
from pathlib import Path
from app.sessions import password_record
path=Path('/var/lib/unwatermark/export-password.json')
password=getpass.getpass('Shared export password: ')
assert len(password)>=12, 'Use a strong shared password'
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:json.dump(password_record(password),f)
```

The default password path is under runtime; `VIDEO_REMOVER_EXPORT_PASSWORD_FILE` can override it. Missing configuration prevents hosted startup. SQLite stores token hashes, owners, CSRF tokens and expiry, with 30-day identities, one-hour export grants and persistent request limits. Password records use salted PBKDF2-HMAC-SHA256 (600,000 iterations). Restart after changing the password; existing one-hour export grants remain valid until expiry. Never commit passwords, session databases, keys, real footage or browser traces.

Anyone can upload/process without the export password, so compute and storage are public within the configured admission limits. Limits: fast only, 25 MiB, 30 seconds, 1280 maximum edge, 921600 pixels, 1–60 fps, one preparation/active job at a time. Admission stops at 1.5 GiB runtime usage, reserving 512 MiB within a 2 GiB operating budget; minimum 5 GiB disk free. These are admission checks, not filesystem quotas. systemd caps memory at 600 MiB and CPU at one core. Session bootstrap is limited to 30 new identities/IP/day and 5000 active identities; export attempts to 5/minute per IP and identity. Existing local mode is unchanged when VIDEO_REMOVER_HOSTED is absent.

Terminal jobs expire 24 hours after completion/failure/cancellation, checked every 60 seconds. Unsubmitted uploads expire after 24 hours. Sources stay while referenced by retained jobs. Active/queued jobs and in-flight requests/downloads are protected. Legacy records without owner_id are inaccessible; do not assign shared legacy records to arbitrary sessions. They expire under the existing policy. Runtime and media remain on the server. Session identity expiry is separate from media retention.

Upgrade behind the old Basic Auth protection first. Verify two independent HTTPS clients: public home, session issuance, upload, masked job, marked preview, wrong/correct export password, ownership checks on every endpoint and byte range. Then remove Basic Auth and recheck. Test exact host, CSRF, admission limits, output decode, TLS renewal and unrelated sites. Keep source/config rollback, but restore Basic Auth BEFORE reverting to a legacy application without ownership checks. Do not delete runtime to roll back. Do not run broad test suites against production data.

Browser tests are in `tests/browser/`; provide playwright-core through NODE_PATH, CHROME_PATH if needed, a synthetic VIDEO_FIXTURE, and TEST_URL for private-export.cjs. Export-test password and traces stay local. These tests emulate mobile dimensions; they do not certify physical WeChat/Safari behavior.

Optional contact QR: install your own image as `export-contact.png` under runtime (readable by the service), or configure `VIDEO_REMOVER_EXPORT_CONTACT`. It is served publicly for visitors to request an export code. Keep personal QR images outside the public source repository.
