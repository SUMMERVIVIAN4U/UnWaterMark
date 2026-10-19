# Approved: registration-free private browser workspace

User selected option 2: no registration or entry password, each browser sees only its own records, shared password required to export processed videos. Keep hosted limits and 24-hour retention. Local-only mode stays unchanged.

Use random opaque Secure/HttpOnly/SameSite=Lax cookies and a SQLite session store. Store only token digests; 30-day identity, one-hour export unlock; no cross-browser recovery. CSRF token plus same-origin checks on mutations. No user-supplied owner identifiers. Session bootstrap and unlock attempts are rate limited, expiry rows pruned. Credentials are stored as salted PBKDF2-HMAC-SHA256 (600,000 iterations) hashes outside source control; use the previous shared password for export.

Persist owner_id in upload and job records, propagate it on retry. Filter lists, authorize metadata, media including byte ranges, masks, cancel/retry and task creation. No-owner legacy records fail closed and expire normally. Knowing the shared export password grants no other browser's resources. Keep a single global processing slot and bounded storage; public upload now consumes server compute without knowing the password as explicitly selected.

Before unlocking provide only a reduced-resolution, watermarked, maximum 3-second preview, no clean video through preview tasks or alternate routes. After unlock stream the full result through the ownership-protected result route. Password access is a distribution gate, not DRM.

Deploy application authentication behind existing Basic Auth first; remove Basic Auth only after ownership and export checks pass. Never roll back to an unprotected legacy app. Tests cover A/B sessions, copied links, byte ranges, forged owner, restart, expiration, CSRF, wrong passwords, rate limits and preview/full output. Mobile emulation does not establish real WeChat compatibility; actual device confirmation remains explicit.
