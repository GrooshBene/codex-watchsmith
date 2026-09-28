# Watchsmith landing page

Approved Signal direction, based on README and the user-provided Univer reference.

Open `index.html` directly, or run `python3 -m http.server 8766 --bind 127.0.0.1 --directory landing` from the checkout and visit http://127.0.0.1:8766/. No build, external font, package installation, analytics, or external scripts required. All demos are local; no notification is sent. Copy buttons copy commands only.

The original three drafts and approval record are preserved under `design-demos/`. The development preview at design-demos/index.html mirrors this page; design-demos/comparison.html retains the original comparison. The website is deployed through GitHub Pages.

## Internal guides

`guides/index.html` is the documentation entry point, with Korean setup, notifications/privacy, and update/recovery pages. Content is adapted from `docs/SETUP.md`, `docs/RESULTS.md`, `docs/UPDATES.md`, and README.md. It is an end-user guide, not a full transcription of developer contracts. Update these pages when their source behavior changes. Shared `guides/guide.css` and `guide.js` must accompany the HTML; publish/copy the entire landing directory. Relative links support file:// and static hosting under a subpath. Download/account/OAuth links stay external because those actions belong to the official services.


## GitHub Pages deployment

Public URL: https://grooshbene.github.io/codex-watchsmith/

`.github/workflows/pages.yml` publishes changes to `landing/` on `main`, or a manual run on `main`. In repository Settings → Pages, the source must be **GitHub Actions**. Only the HTML pages and shared guide CSS/JavaScript are copied to the deployment artifact; screenshots, verification reports, design drafts, and repository files are excluded.

`landing/index.html` becomes the site root (no `/landing/` segment), with guides at `guides/`, `guides/setup.html`, `guides/notifications.html`, and `guides/updates.html`. Keep local links relative so they work beneath `/codex-watchsmith/`. New asset types must be explicitly added to the preparation step before linking them.

Review changes through a pull request to `main`. To recover a previous website, revert its changes through a pull request and let the same workflow deploy; no release tag or package publication is needed. The workflow publishes the website only and does not change the installed Watchsmith runtime.
