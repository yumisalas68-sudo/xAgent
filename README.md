# Opportunity Hunter 🎯

Automated multi-agent X (Twitter) opportunity scout. Runs 24/7, sends real prize/competition/hackathon opportunities directly to your Telegram.

---

## How it works

```
ScrapeBadger monitors (hourly) → webhook → embed + similarity filter
→ Nemotron evaluator (free) → Groq checker (free) → Mistral tiebreaker (rare, paid)
→ Telegram notification
```

Every 10 approvals → Phrase Inventor generates new search phrases automatically.

---

## Setup (5 steps)

### 1. Clone & install
```bash
git clone <your-repo>
cd opportunity-hunter
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in all values in .env
```

### 3. Deploy to Railway
- Push to GitHub
- Connect repo to Railway (via Discord bot or web)
- Add all `.env` variables in Railway dashboard under **Variables**
- Railway auto-deploys and gives you a public URL

### 4. Set up ScrapeBadger monitors (run ONCE after deployment)
```bash
# Make sure WEBHOOK_BASE_URL is set to your Railway URL first
python -m scrapebadger.setup_monitors
```

### 5. Update your reference file anytime
Edit `data/real_opportunities.txt` — add new examples separated by `---`.
The system auto-reloads on the next webhook hit. No restart needed.

---

## Environment Variables

| Variable | Description |
|---|---|
| `SCRAPEBADGER_API_KEYS` | Comma-separated keys, one per account |
| `OPENROUTER_API_KEY` | Your OpenRouter key (for Nemotron free + paid models) |
| `GROQ_API_KEY` | Your Groq key (free tier) |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `WEBHOOK_BASE_URL` | Your Railway deployment URL |

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `POST /webhook` | ScrapeBadger delivers tweets here |
| `GET /health` | Railway health check |
| `GET /stats` | Agent scores, tweet counts, opportunities found |
| `GET /phrases` | All search phrases (user + invented) |

---

## Models used

| Agent | Model | Cost |
|---|---|---|
| Embedder | Perplexity Embed 0.6B | ~FREE ($0.004/M) |
| Primary Evaluator | NVIDIA Nemotron 3 Super | FREE |
| Cross-checker | Groq llama-3.3-70b | FREE |
| Phrase Inventor | NVIDIA Nemotron 3 Super | FREE |
| Tiebreaker | Mistral Small 4 | $0.15/$0.60 per M (rarely called) |

---

## Adding new search phrases
Either:
- Add manually to `data/search_phrases.txt` and re-run `setup_monitors.py`
- Let the Phrase Inventor do it automatically — check `/phrases` endpoint for invented phrases, then add the good ones to ScrapeBadger

---

## Agent survival
Each agent has a score. Score drops when it approves junk. Score below 35% → agent marked DEAD and excluded from pipeline. Check `/stats` to monitor.
