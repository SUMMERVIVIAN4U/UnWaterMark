# Invited trial deployment

Opt-in hosted mode is intended for trusted users sharing one workspace. It is not a multi-tenant service. The example domain must be changed for another deployment.

Use a dedicated unprivileged account and runtime directory, recent FFmpeg/FFprobe (8.1 tested), and `requirements-server.txt` in a virtual environment. Point `/opt/unwatermark/current` to an immutable source release. Install the unit and reverse proxy examples only after adapting paths, obtaining a valid TLS certificate, creating an Nginx-readable htpasswd file and testing `nginx -t`. Never store passwords or private keys in Git.

All routes, including media, docs and APIs, must be protected by the TLS proxy; Uvicorn listens only on loopback. Only loopback proxy forwarding is trusted. HTTP serves ACME challenges and redirects to HTTPS. Basic Authentication gives invited users access to ALL shared uploads and jobs; do not share credentials with untrusted users. Browser Basic Authentication has no application logout button; close the browser session to clear cached credentials as supported by your browser.

Hosted limits: fast only,25MiB uploads,30seconds,1280 maximum edge,921600pixels,1–60fps,one preparation/active job at a time. Runtime admission stops at1.5GiB to reserve512MiB within a2GiB operating budget; minimum5GiB disk free. These admission checks are not a filesystem quota. systemd caps memory600MiB,CPU one core,128tasks and256MiB per file. Existing local mode remains unchanged when VIDEO_REMOVER_HOSTED is absent.

No automatic deletion is enabled. Administrator must manage retained uploads/results and disk usage. If the OS kills the service at its resource ceiling, incomplete tasks are reported interrupted on restart. Avoid broad test suites on tiny shared production servers; use a bounded synthetic smoke test for upload→mask→job→poll→download and rejected requests.

After deployment verify unauthenticated401 on pages/API/media; authenticated success; exact-host and same-origin checks; engine/size/duration/queue guards; real output full decode; cert renewal and existing unrelated sites. Keep the old release/config for rollback. To roll back, stop the app, restore the previous release symlink and site configuration, validate Nginx then reload. Do not delete runtime when rolling back.
