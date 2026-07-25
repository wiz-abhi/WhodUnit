# Deploying the Whodunit replay

The app is a **static** site (HTML + CSS + vanilla JS, no backend, no build step).
No cold start, no server to break during judging. Two ways to host it; either
gives you a stable public URL for the submission's "Deployed link" field.

---

## Option A — Hugging Face static Space (recommended)

No HF token needed; everything happens in the browser.

1. Sign in at <https://huggingface.co> (free account).
2. Go to <https://huggingface.co/new-space>.
3. Fill in:
   - **Owner**: your username (e.g. `wiz-abhi`)
   - **Space name**: `whodunit-replay`
   - **License**: MIT
   - **Select the Space SDK**: **Static**
   - Visibility: **Public**
4. Click **Create Space**.
5. Open the **Files** tab → **Add file** → **Upload files**.
6. Drag in the **contents of this `replay/` directory** (not the folder itself):
   - `index.html`
   - `README.md`  ← its YAML front-matter tells the Space it's a static site
   - `data/` (explain-result.json, webhook.log, permalink.txt)
   - `assets/` (the four PNGs)

   > You can drag whole folders; HF preserves `data/` and `assets/` paths, which
   > is what `index.html` references. Keep the structure identical.
7. **Commit changes to main**. The Space builds in a few seconds.

Your URL will be:

```
https://<username>-whodunit-replay.hf.space
```

e.g. `https://wiz-abhi-whodunit-replay.hf.space`. The Space page itself is
`https://huggingface.co/spaces/<username>/whodunit-replay`.

### Alternative: push with git instead of drag-and-drop

```bash
# from the repo root
git clone https://huggingface.co/spaces/<username>/whodunit-replay hf-space
cp -r replay/index.html replay/README.md replay/data replay/assets hf-space/
cd hf-space
git add .
git commit -m "Whodunit interactive replay (seed 778)"
git push
```

(HF will prompt for your username + an access token as the git password — create
one at <https://huggingface.co/settings/tokens> with **write** scope. Nothing is
committed here for you; the token stays local to your git client.)

---

## Option B — GitHub Pages (fallback, same files)

Because it's plain static files, the same `replay/` directory doubles as a Pages
site:

1. Push this repo to GitHub (already `github.com/wiz-abhi/WhodUnit`).
2. Repo **Settings → Pages**.
3. **Source**: Deploy from a branch → **main** → folder **`/` (root)**, then in
   the published site open `/replay/`. (Pages cannot point at a subfolder as the
   root, so the URL is `https://<user>.github.io/WhodUnit/replay/`.)
   - To get a clean root URL instead, copy `replay/`'s contents into a `docs/`
     folder or a `gh-pages` branch root and set Pages to serve from there.
4. Wait for the green check; the URL appears at the top of the Pages settings.

---

## After deploying

Put the resulting URL in **field 7 (Deployed link)** of the submission form and in
the "Live replay" link near the top of the repo `README.md` (both currently marked
as placeholders).

Sanity check once live: open the URL, click **Run whodunit explain**, step to
**Verify** and confirm the receipt snaps to `mined 61 · SigNoz 61 · MATCH`, and on
**Determinism** hit **Run again** — the hash must stay
`95f8835759e2865ec90f17b45df7f1f74f9944484bad4f014e0f209826f91fb5`.
