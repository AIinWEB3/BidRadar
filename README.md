# BidRadar
An OpenClaw skill for small consultancies to scan public opportunities, rank the best fits, and decide whether to bid.

Core capabilities:

- scan SAM.gov-style opportunities with filters such as keywords, state, and result count
- rank and shortlist candidate opportunities before deep qualification
- qualify a single URL, file, or pasted notice against a company profile
- return a `Bid`, `Review`, or `No-Bid` decision with reasons, risks, matched capabilities, missing requirements, and next action
- blend deterministic scoring with Contextual-backed semantic fit assessment when Contextual is configured

## Demo Frontend

This repo now includes a minimal JS demo app that runs the real Python skill and renders the generated report JSON in the browser.

Run it from the repo root:

```bash
npm start
```

Then open `http://127.0.0.1:3000`.

Notes:

- the server auto-loads `.env.bidradar.sh` if that file exists
- no frontend dependencies are required; the app uses Node built-ins plus plain browser JavaScript
- the UI exposes two live workflows: single-opportunity qualification and SAM scan
