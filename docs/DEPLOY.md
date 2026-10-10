# Deploying CardSense

The live setup:

| Piece | Where | URL |
|---|---|---|
| Frontend (React build) | Cloudflare Pages | https://card-sense.app |
| API (FastAPI, `docker/Dockerfile.api`) | Google Cloud Run, `asia-southeast1` | https://api.card-sense.app |
| Database | MongoDB Atlas free tier (M0) | — |
| DNS | Cloudflare | — |

`.app` domains are HTTPS-only (the whole TLD is HSTS-preloaded), so every URL above must be `https://`. Cloudflare and Cloud Run both issue certificates automatically.

## 1. Database: MongoDB Atlas

1. Create a free **M0** cluster, preferably in Singapore so it sits next to the API.
2. **Database Access**: add a user with a long generated password and the *Read and write to any database* role.
3. **Network Access**: allow `0.0.0.0/0`. Cloud Run has no fixed outbound IP on the free setup, so the password is the protection.
4. Copy the connection string (`mongodb+srv://…`). This is `MONGODB_URI`.
5. Load the card catalogue. From a machine that has the local database with the crawled cards:

   ```bash
   python -m db.copy_cards --source mongodb://localhost:27017 --target "mongodb+srv://…"
   MONGODB_URI="mongodb+srv://…" python -m db.setup_indexes
   ```

   Or crawl straight into Atlas with `MONGODB_URI="mongodb+srv://…" python -m crawler.run`.
   Check for cards stored twice with `MONGODB_URI="mongodb+srv://…" python -m db.dedupe_cards` (report only; `--apply` saves the records it deletes to `backups/` first, and `--restore <file>` puts them back).
6. **Atlas Search → Create Search Index → Vector Search (JSON editor)** on `cardsense.credit_cards`, named `credit_cards_embedding_index`:

   ```json
   {
     "fields": [{ "type": "vector", "path": "embedding", "numDimensions": 768, "similarity": "cosine" }]
   }
   ```

The sessions TTL index is created by the API on startup.

## 2. API: Google Cloud Run

Needs a Google Cloud project with billing enabled. Demo traffic stays inside the free tier, and `--max-instances 2` caps what a traffic spike can cost. Setting a budget alert under *Billing → Budgets* is still worth it.

```bash
gcloud auth login
gcloud config set project <project-id>
./deploy/cloudrun.sh
```

The first run enables the APIs, creates an Artifact Registry repo and asks for `MONGODB_URI` and `GEMINI_API_KEY`, which go into Secret Manager (never into the image or the repo). Every later run builds a new image and rolls out a new revision. To change a secret:

```bash
printf '%s' "new-value" | gcloud secrets versions add gemini-api-key --data-file=-
./deploy/cloudrun.sh
```

Plain settings (CORS origins, rate limit, upload size) live in `deploy/cloudrun.env.yaml`.

### Custom domain `api.card-sense.app`

```bash
gcloud domains verify card-sense.app        # one-time, opens Search Console
gcloud beta run domain-mappings create --service cardsense-api \
  --domain api.card-sense.app --region asia-southeast1
```

Then in Cloudflare DNS add `CNAME api → ghs.googlehosted.com` with the proxy **off** (grey cloud), so Google can issue the certificate. It can take a few minutes to an hour to go live.

`asia-southeast1` was picked because Cloud Run domain mappings are not offered in every region (Mumbai is one of the gaps).

## 3. Frontend: Cloudflare Pages

1. Move DNS to Cloudflare: add `card-sense.app` as a site on the free plan, then at the registrar replace the nameservers with the two Cloudflare gives you.
2. **Workers & Pages → Create → Pages → Connect to Git**, pick `ypg199/cardsense-ai`, and name the project `cardsense`:

   | Setting | Value |
   |---|---|
   | Production branch | `main` |
   | Root directory | `frontend` |
   | Build command | `npm run build` |
   | Build output directory | `dist` |
   | Environment variable `VITE_API_URL` | `https://api.card-sense.app` |
   | Environment variable `NODE_VERSION` | `20` |

3. **Custom domains**: add `card-sense.app` (and `www.card-sense.app` if wanted).

Every push to `main` redeploys, and pull requests get preview URLs on `*.cardsense.pages.dev`, which the API already accepts through `ALLOWED_ORIGIN_REGEX`. If the Pages project ends up with a different name, update that regex in `deploy/cloudrun.env.yaml`.

There is no `404.html`, so Pages serves `index.html` for unknown paths and React Router handles deep links such as `/analyser/<id>`. Security and cache headers are in `frontend/public/_headers`.

## Alternative: Render (no credit card)

`render.yaml` is a Render Blueprint for the API: **New → Blueprint**, pick the repo, and fill in `MONGODB_URI` and `GEMINI_API_KEY` when asked. The free plan sleeps after 15 idle minutes, so the first request after a quiet spell takes 30 to 60 seconds. Point `api.card-sense.app` at it with a CNAME to the `onrender.com` host and add the domain in Render's settings.

## Protecting the Gemini key

Statement uploads and sample runs are limited per client (`RATE_LIMIT_PER_HOUR`, 20 in the deploy config; off locally). The limit is held in each instance's memory, which is fine with at most two instances. The `/crawl` admin endpoints stay disabled unless `ADMIN_API_KEY` is set.

## Checking it

```bash
curl https://api.card-sense.app/health          # {"status":"ok",...}
curl -s https://api.card-sense.app/cards | head  # the card catalogue
```

Then open https://card-sense.app and try **Use sample statements**.
