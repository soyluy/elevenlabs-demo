# Deniz-1 crew tools for an ElevenLabs voice agent

Webhook tools for a Turkish ElevenLabs voice agent: headcount, free cabins and
crew rotation dates computed in code, not by the LLM. All data is invented.

## Why

I built a voice agent for a vessel's radio operators ("Yarın gemide kaç kişi
olacak?": how many will be on board tomorrow?) and tried it two ways:

- **Crew list as a knowledge base:** the agent answered 9 instead of 10, and
  held the wrong number when challenged. The model was doing date arithmetic
  over a document.
- **Crew list behind these tools:** every test question answered correctly,
  including under incorrect pushback.

A count derived from dates belongs in code. The model picks the tool and speaks
the result.

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /pob?day_offset=1` | Headcount on a day, who boards and who leaves |
| `GET /cabins/free?day_offset=1` | Cabins with free beds |
| `GET /people?name=ali` | A person's cabin and dates; `ambiguous` when several match |

The agent passes `day_offset` (0 today, 1 tomorrow) rather than a date it
computed. Name matching is Turkish-aware and fuzzy, and returns both
"Ali Yılmaz" and "Ali Yıldız" for "Ali" so the agent asks instead of guessing.

## Run

```bash
pip install -r requirements.txt pytest httpx
DEMO_TODAY=2026-10-07 pytest -q
DEMO_TODAY=2026-10-07 uvicorn app:app --port 8000
cloudflared tunnel --url http://localhost:8000
```

Then add each endpoint as a GET webhook tool on the agent, using the tunnel URL.