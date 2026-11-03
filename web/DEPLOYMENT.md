# Publish PANDA on Vercel

The production build serves the Cesium website, two GLBs, saved study summaries
and the tested Python simulation bundle. Simulations run on the visitor's device.
No Python backend, Cesium ion token, Vercel Function or environment variable is
required for this release.

## Connect GitHub and publish

1. Sign in to Vercel and choose **Add New → Project**.
2. Connect GitHub if needed. Grant access to **Judith989/PANDA-ABM**. If GitHub
   offers repository selection, select this repository only.
3. Import **PANDA-ABM** and select its `main` branch.
4. Keep **Root Directory** at the repository root (`./`). Do not select
   `dashboard`, `web/release`, `web/dist` or the old Sites checkout.
5. Use **Other** as Framework Preset. The committed `vercel.json` supplies:
   - Build Command: `node web/build.mjs`
   - Output Directory: `web/dist`
   - Install Command: empty (no npm or pip dependencies to install)
6. Leave Environment Variables empty and select **Deploy**.
7. When ready, open the production URL and check the 3D lot, a small live
   simulation, a matched comparison and its downloadable provenance record.

The first visitor simulation loads the browser Python runtime and scientific
libraries. Subsequent requests reuse that worker. Initial loading and simulation
execution are separate timings. Rendering can be throttled in an occluded
browser window; do not interpret background frame measurements as active-view
animation performance.

## What belongs in GitHub

Commit the current `panda_abm/` source and corrected `data/lot_config.json`,
the dashboard HTML/JS/CSS and worker adapters, `web/build.mjs`, the small
`web/release/` asset snapshot, `package.json`, `vercel.json` and deployment docs.
The snapshot includes the GLBs, Python source ZIP, configuration, replay,
verification fixtures and selected aggregate study evidence.

The `.gitattributes` file preserves the exact source bytes used for integrity
checks, including when moving between Windows and Vercel's Linux build host.

For the first code-only push, these commands include the deployment and current
simulation implementation while leaving paper drafts and raw outputs out:

```powershell
git add .gitattributes .gitignore .vercelignore vercel.json package.json README.md
git add panda_abm data dashboard web scripts tests requirements.txt requirements-analysis.txt
git diff --cached --stat
git commit -m "Prepare parking simulation platform for Vercel"
git push origin main
```

Review the staged summary before committing. Existing unrelated changes should
be deselected if you do not intend to publish them. Do not use `git add .` for
this initial release: the working tree also contains unpublished paper material.
The commands above leave `paper/`, `research/`, raw results and temporary files
out of the initial code commit.

Do not commit `.env`, `.vercel/`, credentials, virtual environments, local Sites
checkouts, `web/dist/`, temporary files or the downloaded scientific wheels.
Paper drafts and raw experiment folders are not needed for deployment.

The build downloads pinned runtime files from the official Pyodide CDN and
checks every SHA-256 digest. It verifies that the current repository's Python
source and interface agree with the tested snapshot. A stale bundle fails the
build instead of silently publishing a different model.

## Refresh a release after code changes

From the repository root, with the scientific Python dependencies installed:

```powershell
python scripts/build_public_platform.py
python scripts/prepare_vercel_release.py
node web/build.mjs --offline
```

The first command uses local study archives to regenerate published evidence.
Vercel does not need those raw archives: it consumes the checked-in snapshot.
Repeat the relevant ABM verification when decision logic or parameters change,
then commit and push the updated source and snapshot together.

For a local preview of exactly what Vercel will serve:

```powershell
node web/build.mjs --offline
python -m http.server 8768 --bind 127.0.0.1 --directory web/dist
```

The default online build (`node web/build.mjs`) exercises the production download
path. The `--offline` check uses locally cached runtime files and verifies the
same hashes. Neither build reruns the research experiments or changes ABM rules.
