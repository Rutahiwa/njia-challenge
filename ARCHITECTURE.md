# How the booking agent works

Written up as I went. Some of this is from the first week, some from later.
- J.M., handover notes

## Shape

```
WhatsApp webhook  ->  channel.receive  ->  debounce  ->  agent.run_agent
                                                              |
                                              llm.complete  <-+->  tools.execute
                                                                        |
                                                                   mock backend
```

`server.py` is thin on purpose. Everything that matters is in `agent.py` and
`tools.py`.

## Message handling

`channel.receive` is idempotent on `message_id`. WhatsApp redelivers more than you
would think, especially on the Tigo route, so the first thing we do with an inbound
message is check whether we have seen that id before and drop it if we have.

Messages that arrive close together are collected and handled as one request. The
window is in `config.DEBOUNCE_SECONDS` and was tuned against real traffic from the
Ubungo office - people send three or four fragments and then stop.

## Conversation state

`store.history` keeps the conversation keyed by the customer's number, trimmed to the
most recent `MAX_HISTORY` turns so the context stays inside budget. Older turns fall
off the front.

## Tools

`tools.TOOLS` is the surface the model sees. `tools.execute` runs the call.

`search_trips` returns the full result set for a route and date. The backend does not
paginate this endpoint, so one call is enough - `search_all` exists only to keep the
shape consistent with the others.

Writes are safe to retry. `_request` derives the idempotency key from the payload, so
if the gateway times out and we send the same hold or the same charge again, the
backend recognises it and returns the first response instead of acting twice. This is
why the retry loop can be as simple as it is.

Backend errors come back to the model with their `code` intact so it can decide what
to do - take another seat, ask the customer to try the payment again, and so on.

## Language

`language.detect` re-reads the conversation on every inbound message and returns `sw`
or `en`. Customers switch mid-conversation constantly and we follow them. The word
list is small but it covers what people actually type.

## Pricing

Never compute a price. `pricing.py` takes the quote the backend returned and turns it
into the sentence we send, service charge included. Everything the customer is told
about money goes through there.

## Policy

`policy.py` holds the rules from the client meeting - the elder discount, the student
discount, night coaches and minors, when a conversation stops being ours to answer.
The agent loop consults it before it acts, which keeps the rules in one place instead
of scattered through the prompt.

## Payments

A charge is a push to the customer's handset. It comes back `pending` and settles
later. `CHARGE_POLL_ATTEMPTS` and `CHARGE_POLL_INTERVAL` control how long we wait
before we give up and tell them. `MAX_PAYMENT_ATTEMPTS` caps how many times we will
push to one handset.

Seat holds live for `HOLD_TTL` seconds, which matches the backend. If the customer
does not approve the push inside that window the seat goes back and we start again.

## Logging

One JSON object per line in `logs/agent.jsonl`, so you can grep it. Every run writes
a `run.started` and a `run.finished` or `run.failed`, every backend failure writes an
`error` with the code attached.

## Recent changes

- **20 Aug** - fixed the double charge some customers saw on a flaky network. The
  retry was generating a new idempotency key each attempt. Now derived from the
  payload.
- **27 Aug** - language was being decided once per conversation and never revisited.
  Now re-evaluated per message.
- **02 Sep** - trimmed conversation history to keep long chats inside the token
  budget.
- **09 Sep** - wired `policy.py` into the loop. The rules used to live in the prompt.

## Still to do

- The console needs the live stream and the takeover button.
- Nobody has looked at what happens if the process dies mid-payment.
