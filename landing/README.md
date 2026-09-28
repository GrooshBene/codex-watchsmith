# Watchsmith landing page

Approved Signal direction, based on README and the user-provided Univer reference.

Open `index.html` directly, or run `python3 -m http.server 8766 --bind 127.0.0.1 --directory landing` from the checkout and visit http://127.0.0.1:8766/. No build, external font, package installation, analytics, or external scripts required. All demos are local; no notification is sent. Copy buttons copy commands only.

The original three drafts and approval record are preserved under `design-demos/`. The development preview at design-demos/index.html mirrors this page; design-demos/comparison.html retains the original comparison. The website is deployed through Cloudflare Pages Direct Upload.

## Internal guides

`guides/index.html` is the documentation entry point, with Korean setup, notifications/privacy, and update/recovery pages. Content is adapted from `docs/SETUP.md`, `docs/RESULTS.md`, `docs/UPDATES.md`, and README.md. It is an end-user guide, not a full transcription of developer contracts. Update these pages when their source behavior changes. Shared `guides/guide.css` and `guide.js` must accompany the HTML; publish/copy the HTML pages and their shared CSS/JavaScript together. Relative links support file:// and static hosting under a subpath. Download/account/OAuth links stay external because those actions belong to the official services.

## Cloudflare Pages deployment

Public URL: https://codex-watchsmith.pages.dev/

The `codex-watchsmith` project uses Cloudflare Pages Direct Upload. This is a static site on the free service: no Functions, Workers runtime code, paid plan, analytics, or custom domain is required. GitHub Actions is not used for website deployment. Source changes do not automatically publish; upload a new deployment after reviewing changes.

Package only `index.html`, `guides/*.html`, `guides/guide.css`, and `guides/guide.js` from this directory. Keep `index.html` at the ZIP root and preserve the `guides/` subdirectory. Exclude screenshots, verification reports, this README, design drafts, and repository files. In Cloudflare, open Workers & Pages → codex-watchsmith → Create a new deployment, select Production, upload the ZIP, and deploy.

The site root has no `/landing/` or repository-name segment. Guides are available under `/guides/`, `/guides/setup.html`, `/guides/notifications.html`, and `/guides/updates.html` (Cloudflare may redirect HTML paths to extensionless URLs). Keep internal links relative. After deploying, check the homepage, all four guides, and the shared CSS/JavaScript over HTTPS.

Review source changes through a pull request to `main`. To recover a previous site, upload a previously verified package as a new production deployment. No release tag or package publication is needed. Direct Upload projects cannot be converted to Git integration in place; automatic Git deployments require a new project.
