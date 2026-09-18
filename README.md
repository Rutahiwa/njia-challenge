# Njia Coaches - booking agent

Mzee Kileo runs a coach company out of Ubungo. He wants WhatsApp to sell his
tickets so Rehema can stop answering the same question two hundred times a day.

**Read [`REQUIREMENTS.md`](./REQUIREMENTS.md) first.** It is meeting notes, a
transcribed voice note and a WhatsApp message. It is the entire specification and
nobody has tidied it up. Working out what it actually asks for is half of this
exercise.

There is already an agent in `app/`. The developer who wrote it has left. It books a
ticket, on a good day. Run `make evals` and see what it does on a bad one.

**Assume nothing in `app/` is correct.** Some of it is wrong in ways the scenarios
catch. Some of it is wrong in ways nothing catches, and you will only find it by
reading. We know what is in there. We are interested in how much of it you find.

Everything except the model is mocked: no real money moves, no real WhatsApp
account, no external service. The only call that leaves your machine goes to the
Anthropic API on your own key. Budget about $3; send us the receipt and we refund it.

## Run it

```bash
cp .env.example .env          # add your ANTHROPIC_API_KEY
make install
make mock                     # terminal 1 - the fake world, port 9311
make agent                    # terminal 2 - the agent, port 9310
make evals                    # terminal 3 - the score
make probe                    # and this - see below
```

Rehema's console is at http://localhost:9310.

## What is in the box

```
REQUIREMENTS.md   what the client said. the spec
mock/             the fake world: trips, seats, mobile money, WhatsApp.  DO NOT MODIFY
app/
  config.py       settings and limits
  logs.py         structured logging
  language.py     Swahili or English
  pricing.py      turning a quote into words
  policy.py       the rules from the brief
  store.py        runs, history, message ids
  llm.py          the model call
  tools.py        tool schemas and the executor
  agent.py        the loop and the prompt
  channel.py      WhatsApp in, WhatsApp out
  server.py       routes
web/              Rehema's console
evals/            twelve scenarios, the scorer and the answer probe.     DO NOT MODIFY
tests/            one smoke test. add your own
```

`make evals` resets the world before each scenario, posts WhatsApp messages at the
agent, waits for it to go quiet, then inspects what actually happened - which seats
were held, what was charged, which tickets exist, what went to a human, what was
said to the customer, and what you logged. It grades on the state of the world,
never on the wording of a reply.

## The answer probe

`make probe` asks the agent eight ordinary questions and checks each reply against
what the backend actually holds. When a reply says something the system never said,
it tells you:

```
P2  WRONG   the reply states a departure time that is not in the catalogue
```

It will not tell you why. There are several different reasons a reply can come out
wrong here and the probe cannot tell them apart. Neither can a customer.

The probe is not part of the twelve. We run it on your submission too.

## What you are being asked for

1. **Twelve out of twelve visible, and stay there.** We then run eight scenarios you
   have not seen, drawn from the same requirements. Special-casing the visible
   twelve will show up immediately.
2. **Put the tools behind MCP.** The agent talks to the backend over raw HTTP today.
   Stand up your own MCP server - or more than one - in front of `mock/`, and have the
   agent call its tools through it. We are not prescribing the transport or how you
   split the surface up, but we will ask why you split it the way you did, and which
   things you decided the server should hold rather than the agent. `mock/` does not
   change; your server sits in front of it. Every `tool` step in your trace records
   the server that served it.
3. **Inside the budget.** Twelve tool calls, 25,000 input tokens and 4,000 output
   tokens per run, whatever model you chose. The scorer counts them off the steps in
   your trace, not off your own totals.
4. **Survive a restart.** We `kill -9` the agent in the middle of a payment, start it
   again, and redeliver the WhatsApp webhook. Exactly one charge and one ticket may
   exist afterwards.
5. **Logs someone can grep.** See the contract below. A run that ends without either
   a reply to the customer or a handover to a human is a failure, whatever else it did.
6. **Escalation that works.** Some conversations are not the agent's to answer. The
   requirements say which. `POST /escalations` on the mock, with `reason` one of
   `refund`, `complaint`, `payment_failed`, `policy`, `unclear`, `other`.
7. **Every probe clean.** `make probe` at eight of eight.
8. **Finish the console.** Stream steps to `GET /runs/{id}/events` so Rehema watches
   it happen, show her why a run gave up, and make *Take over* actually stop the
   agent replying to that conversation.

## Rules

- **Any model, any provider - but it has to hold up on a small one.** Develop with
  whatever you like; add the SDK to `pyproject.toml`. We score the submission on a
  small, cheap model - GPT-5.4-mini class or below - and we pick the exact one at
  grading time, so **we must be able to change the model by editing one setting,
  without touching your loop.** Every `llm` step in your trace records which model
  made the call, and the token budget below does not move when the model gets bigger.

  A capable model will carry a loose design. A small one will not, and a small one is
  what Mzee Kileo can afford every month. In your notes: what you picked, what it
  costs him per conversation, and what broke when you dropped down a tier.
- **Do not change `mock/`, `evals/` or `tests/test_smoke.py`.** We diff them against
  the `pristine` tag and restore our own copies before scoring, so an edit there is
  visible and pointless. Read them as much as you like.
- Any library, framework or agent toolkit you like. If you bring one, say in your
  notes what it bought you.
- **Use Claude, Cursor, whatever you normally use.** We do. We are hiring the person
  who knows which of its suggestions to throw away.

## The contracts the scorer relies on

**Inbound message.** The harness posts this:

```
POST /webhook   {"message_id": "wa-1", "from": "+2557...", "text": "..."}
```

Replies go out through `POST http://localhost:9311/whatsapp/send` with `{to, text}`.

**Run trace.** Readable at `GET /runs/{run_id}`, listed at `GET /runs`:

```json
{
  "run_id": "run-a1b2c3d4",
  "conversation_id": "+255712345678",
  "status": "running | done | error",
  "budget": {"tool_calls": 6, "input_tokens": 9130, "output_tokens": 412},
  "steps": [
    {"type": "llm",  "model": "<whatever you used>", "system": "...",
     "input_tokens": 1200, "output_tokens": 80},
    {"type": "tool", "name": "hold_seat", "server": "<which MCP server>",
     "input": {...}, "output": {...}, "ms": 41}
  ],
  "reply": "..."
}
```

Keep that shape. Add fields if you want; do not remove these. `model` on every `llm`
step and `server` on every `tool` step are how the scorer sees what you built.

**Logs.** One JSON object per line in `logs/agent.jsonl`:

```json
{"ts": "2026-10-02T09:14:03.412Z", "level": "info", "event": "run.started",
 "run_id": "run-a1b2c3d4", "conversation_id": "+255712345678"}
{"ts": "...", "level": "error", "event": "tool.failed", "run_id": "...",
 "conversation_id": "...", "code": "hold_expired", "tool": "charge_customer"}
```

`ts`, `level`, `event`, `run_id` and `conversation_id` on every line. Every error
carries a `code`. Every run logs a `run.started` and one of `run.finished` /
`run.failed`. **Every failure the backend returns must reach the log.** The scorer
counts what the backend served and compares. Nothing gets swallowed.

## What to send back

The repo, plus a `NOTES.md` of about two pages:

**One.** The diagnosis table:

| Scenario | What actually went wrong | What I changed | Score before → after |
|---|---|---|---|

**Two.** What you could not pin down. The requirements are three messy documents
written by people with a business to run. Somewhere in there are instructions that
contradict each other and rules with a hole in the middle. List what you found, say
what you decided, and say what you would have asked Mzee Kileo if you could.

We weight this section heavily. Anyone can implement a rule they were given. We are
hiring for the part where the rule is not quite there.

**Three.** Three short paragraphs:

- The failure that took you longest, and how you found it.
- One thing you would do differently with a month instead of a weekend.
- Anything you left broken, and why you chose that.

We read `NOTES.md` first. A submission at 9/12 with a clear-eyed diagnosis beats a
12/12 we cannot follow.

## Time

A weekend. Twelve hours, and please do not go past it - if you run out, submit what
you have and say what was next. We would rather see how you prioritise than how late
you will stay up.
