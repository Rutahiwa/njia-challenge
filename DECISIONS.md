# Decisions

## D1. How you split the tool surface

**What I did.** Two MCP servers split on trust boundary: `njia-catalog` (port 9320, read-only: `search_trips`, `list_seats`, `check_charge`) and `njia-booking` (port 9321, write: `hold_seat`, `charge_customer`, `issue_ticket`, `escalate`). The payment credential (`PAY_KEY`) only exists in the booking server's environment. The catalog server has no secrets at all.

**What I turned down.** A single MCP server would have been simpler — one process, one port, no server mapping in `tools.py`, no split `_post` logic. It's tempting because the tool surface is only 7 tools, well within what a model can reason about. Three servers (trips / payments / escalation) was the other direction — more granular isolation, but escalation is a single POST and doesn't justify its own process.

**What this costs me.** Two processes to start and monitor. If `njia-booking` crashes, the customer can still search trips and check charge status but can't actually book — they get a confusing partial experience where search works but hold fails. With a single server, it's all-or-nothing, which is arguably easier to handle ("service down, try later"). The split also means `check_charge` lives in the catalog server even though it's conceptually part of the payment flow — I put it there because it's a read operation and doesn't need `PAY_KEY`, but someone maintaining this will find that unintuitive.

**What would make me switch.** If the tool count per server grows past ~10, the split starts paying for itself and I'd consider a third server. If I see `njia-booking` crashing independently of catalog (different failure mode, e.g., payment provider flaking), the split is vindicated. If both always fail together (because the mock backend is the actual single point of failure), the split was ceremony for nothing and I'd collapse to one server.

## D2. How much of the booking sequence is a single tool call

**What I did.** Four separate tools (`hold_seat` → `charge_customer` → `check_charge` → `issue_ticket`), sequenced by the model via prompt instructions. The prompt spells out the exact flow including retry logic: payment fails → new hold → new charge → new check, and after 3 failures → `escalate` with `payment_failed`.

**What I turned down.** A single compound `book_seat` tool that runs hold→charge→poll→ticket internally with fixed retry logic. This is genuinely tempting — it eliminates the entire class of bugs where the model stops mid-sequence (forgets to poll, forgets to issue ticket after success, stops to tell the customer "please wait" during a pending charge). A compound tool would guarantee either a ticket or a clear failure every time.

**What this costs me.** The model can fail the sequence. Specific ways: it sees `check_charge` return `pending` and generates a text response telling the customer to wait instead of polling again. It forgets to call `issue_ticket` after a successful charge. It retries with the same `hold_id` instead of getting a new hold. These are real bugs I hit during development — I fixed them with increasingly specific prompt instructions ("Do NOT stop to tell the customer to wait", "Do NOT return a text response while status is pending"), which is brittle. The 4-tool approach also eats more of the 12-call tool budget: a happy path takes 5-7 calls, a single retry takes 8-10, leaving very little room.

**What would make me switch.** If the model consistently fails to complete the sequence — specifically, if I see tickets not being issued after successful charges in the logs. Or if the tool budget drops below 8, making retries impossible with 4 separate tools. The thing keeping me on the 4-tool path: the graders test edge cases where the model needs judgment mid-flow (seat taken after hold attempt → pick another seat, payment fails → decide whether to retry or escalate). A compound tool would need its own branching logic for every edge case the graders invented, and I can't see those scenarios in advance.

## D3. Where the client's rules are enforced

**What I did.** Different rules live in different places, and the dividing line is: can the rule be checked with a string match before the LLM runs?

- **Refund/complaint detection**: `policy.py` runs `needs_human()` on the raw message text before the LLM is invoked. Pattern matching against word lists (English and Swahili). If it hits, the agent calls `escalate` and returns a fixed reply — the LLM never sees the message. This is in code because refund requests must never be answered by the bot, period.
- **Night bus minor restriction**: enforced by the backend mock (it rejects the hold). The prompt tells the model to ask about age when a child is mentioned for a night departure, but the actual gate is the backend. I chose this because "unaccompanied minor" has too many phrasings to catch with string matching ("mtoto wangu", "my son is 15", "traveling alone, she's young").
- **Elder/student discounts**: in the prompt. The model decides when to ask for age or student number based on conversational cues ("mama yangu", "mzee", "I'm a student"). It then passes `passenger_age` or `student_no` to `hold_seat`, and the backend computes the discount. The model doesn't calculate prices — it just passes the parameters.
- **Unclear escalation**: in the prompt. The model is told to escalate after 2 vague messages. `policy.py` has a `note_unclear` counter, but the model is the one deciding what counts as "unclear." This is the weakest link.

**What I turned down.** All rules in code — intercepting every tool call, validating parameters, rejecting calls that violate policy before they hit the backend. This would be deterministic but can't handle nuance. "Mama yangu anataka kwenda Dodoma" implies an elder but doesn't say so explicitly. Only the model can infer that and ask for age. The other extreme — all rules in the prompt — is fragile for hard constraints like refund escalation, where a single miss means the bot tries to process a refund.

**What this costs me.** The prompt-based rules depend on model quality. A weaker model might not recognize "mstaafu" (retiree) as an elder signal, or might not count vague messages correctly across turns. The `needs_human()` word list is necessarily incomplete — a customer who says "I want my fare returned" without using "refund" or any Swahili keyword will slip through to the LLM, which then has to catch it from the prompt instruction.

**What would make me switch.** If the unclear escalation fails in grading — if the model doesn't escalate after 2 genuinely vague messages — I'd move that counter into code with a heuristic (message length < 10 chars, no route/date/name detected → increment). If refund detection misses a case, I'd expand the word list rather than move it to the prompt.

## D4. Who writes what the customer reads

**What I did.** The model writes almost everything. Two exceptions: (1) policy-triggered escalation replies are fixed strings in `agent.py` — one for refunds, one for complaints, in Swahili or English based on `detect()`. These bypass the LLM entirely. (2) The prompt instructs the model to quote `total_tzs` from the `hold_seat` response, not to compute prices itself.

**What I turned down.** Fixed templates for all booking confirmations — code formats the reply with fields from the ticket response, model never touches the confirmation text. This is tempting because it guarantees correct numbers, correct format, and correct language every time. No risk of the model saying "35,000 TZS" when the backend said "37,500 TZS".

**What this costs me.** The model can quote wrong numbers. This actually happened: the model was computing service charge totals by adding fare + 2500 instead of reading `total_tzs` from the hold response. The fix was prompt engineering ("NEVER compute or derive prices yourself"), not templates. The model can also phrase things awkwardly or mix languages. A template would prevent both, but templates can't handle the long tail — customer asks "what does that include?", booking partially fails, customer sends a follow-up in a different language. The model handles all of that naturally.

**What would make me switch.** If the grading probe catches the model quoting a price that doesn't match the backend figure. That's the specific failure I'm worried about. The prompt fix ("NEVER derive prices yourself") works with Claude but might not transfer to a weaker model. If I see price mismatches in the eval logs, I'd switch the confirmation step to a template and only let the model write the conversational padding around it.

## D5. What survives a restart

**What I did.** SQLite database in WAL mode (`data/recovery.db`) with three tables: `seen_messages` (dedup — prevents reprocessing the same WhatsApp message), `runs` (run metadata, written at creation), and `payment_intents` (state machine: `holding` → `charging` → `done`/`failed`, written at each transition). On startup, `_resume_incomplete_payments()` in `server.py` checks for any intent stuck in `charging` state: it polls `check_charge`, issues the ticket if paid, sends the customer a message, and marks it done. Intents stuck in `holding` are marked failed (the hold likely expired).

**What I turned down.** A JSON file per conversation (simpler, human-readable, but a half-written JSON file after a crash is corrupt — you need to parse, detect truncation, recover). Redis (crash-safe, fast, but overkill for a single-process agent and adds an external dependency). Writing nothing and accepting double-charges (the customer gets charged twice, which is worse than any complexity cost).

**What this costs me.** SQLite adds ~200ms on first write (opening the connection, WAL setup). The recovery logic has edge cases: if the process crashes between `charge_customer` succeeding and `recovery.update_payment_state` being called, the intent stays in `holding` state and we mark it failed on restart — the customer was charged but gets no ticket. This is a real gap. I'd need to also store the charge_id at charge creation time to close it, which I do (the `update_payment_state` call in `tools.py` fires after `charge_customer` returns with a `charge_id`). But if the crash happens between the HTTP response and the SQLite write, we lose it. I decided this window is small enough.

I don't persist conversation history. That's cheap to lose — the customer sends a new message, the model starts fresh, and the worst case is the model asks "where would you like to go?" again.

**What would make me switch.** If the agent runs as multiple worker processes. SQLite WAL handles concurrent reads fine but concurrent writers will hit lock contention. At that point I'd move to PostgreSQL or Redis. If the crash-between-charge-and-write gap actually bites (a customer charged but no ticket and no recovery), I'd add a startup reconciliation step that scans recent charges from the payment provider.

---

## One more, not a trade

**D6. What you would tear up.** The prompt. It's a 4KB instruction manual trying to do too many jobs: booking flow sequencing, retry logic, pricing rules, discount eligibility, escalation protocol, language switching, night bus policy, and tool budget management. With Claude, it mostly works. But I watched it fail in specific ways — ignoring the "don't stop during pending" instruction, computing prices instead of quoting them, forgetting to escalate after the third payment failure. Each fix was another sentence bolted onto the prompt, making it longer and more fragile.

If I started Monday: I'd make `book_seat` a compound tool. It takes trip_id, seat, passenger_name, and optional age/student_no. Internally it runs hold → charge → poll (with retries) → ticket, with deterministic retry logic and proper failure escalation baked in. It returns either a ticket or an error with a reason. The model's job shrinks to: understand what the customer wants, call `search_trips`, pick a trip, call `book_seat`, and format the reply. The prompt drops to maybe 1KB. The model can't forget to poll, can't forget to issue a ticket, can't botch the retry sequence. I lose the ability for the model to make mid-flow judgment calls (seat taken → pick another automatically), but I'd handle that inside the compound tool with a seat fallback parameter. The trade is flexibility for determinism, and after watching the 4-tool sequence fail in enough ways, I'd take determinism.
