# BidRadar
An OpenClaw skill for small consultancies to scan public opportunities, rank the best fits, and decide whether to bid.

Core capabilities:

- scan SAM.gov-style opportunities with filters such as keywords, state, and result count
- rank and shortlist candidate opportunities before deep qualification
- qualify a single URL, file, or pasted notice against a company profile
- return a deterministic `Bid`, `Review`, or `No-Bid` decision with reasons, risks, matched capabilities, missing requirements, and next action

## Demo page

A static walkthrough site is available at `demo/index.html`.

It shows:

- which tech is used at each step
- what the workflow returns at each step
- sample BidRadar outputs for fallback, shortlist, and deep-dive runs

To view it locally, either open `demo/index.html` directly in a browser or serve the repo root with:

```bash
python3 -m http.server
```
