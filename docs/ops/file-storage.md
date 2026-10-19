# OPS-08: File storage policy

## The rule: the filesystem is ephemeral — design like it

Render free (and most container hosts) give an **ephemeral filesystem**: anything
written to disk vanishes on restart, redeploy, or sleep/wake. Therefore:

1. **Do not persist originals.** Uploaded resumes/papers are parsed in-memory
   (or in a temp dir) and the original bytes are discarded after extraction
   (SEC-08, PRIV-01). What lives in the DB is extracted *text and features* —
   and even the text of high-sensitivity fields is Fernet-encrypted
   (`studybuddy/field_encryption.py`, PRIV-04).
2. `uploads/` and `instance/` are working scratch, not storage. `.dockerignore`
   excludes them from images; backups never include them.
3. Never store user files in git.

## If persistence becomes a product need

(e.g. "keep my paper PDF so I can re-open it later") — use object storage,
never the local disk:

| Decision | Choice |
|---|---|
| Store | Cloudflare R2 (free tier 10 GB) or Supabase Storage |
| Bucket | **Private**; no public listing |
| Access | **Signed URLs** with short expiry (≤15 min), generated server-side per request |
| Lifecycle | Auto-expire objects after N days (configurable, default 90) |
| DB | Store only the object **key** (+ bucket, checksum), never the bytes |
| Encryption | Server-side encryption on; for high-sensitivity docs, client-side Fernet before upload |
| Deletion | "Delete my data" must delete the object too — cascade in the same transaction as the DB row |

## Migration path (when needed)

1. Add `R2_*` env vars (endpoint, key, secret, bucket) — never in git.
2. New uploads go to R2; reads prefer R2, fall back to legacy path during transition.
3. Backfill job moves any surviving local files, then the local path is removed.
4. Document retention + expiry in the privacy policy (PRIV-02/03).
