# Decisions

Fill this in. It is read alongside `NOTES.md` and weighted the same.

Five choices below have no right answer. Each one is a real trade: the option you
turn down would have been better in some situation, and that situation exists. Some
of it is in the scenarios you cannot see.

**We are not scoring which way you went.** We have built this both ways and neither
is obviously correct. We are scoring whether you knew you were choosing, what you
paid for it, and what would make you change your mind.

Answer each in the same four parts. Half a page each is plenty. "I did not think
about this one" is a real answer and scores better than a reconstruction.

---

## The format

**What I did.** One or two sentences.

**What I turned down, and why it was tempting.** Name the alternative properly. If
you cannot argue for it, you did not consider it.

**What this costs me.** The case where my choice is the worse one. Be specific -
a customer doing a particular thing, a scenario shape, a failure mode.

**What would make me switch.** Something observable. A number, a log line, a
complaint from Rehema. Not "if the requirements changed".

---

## D1. How you split the tool surface

One MCP server or several. If several, split on what - read against write, domain,
trust boundary, who holds a credential, something else. If one, why the surface stays
small enough to reason about.

## D2. How much of the booking sequence is a single tool call

The backend makes you hold a seat, push a charge, poll it, then issue a ticket. That
can be four tools the model sequences, one tool that does the lot, or something
between. This is the biggest architectural call in the exercise. It decides how much
of the work is the model's judgement and how much is your code's.

## D3. Where the client's rules are enforced

The elder discount, the student weekday, no child alone on a night coach, refunds
never being yours to answer. In the prompt, in a policy layer the agent consults, or
inside the tool so it cannot be bypassed. You may have done different things for
different rules - if so, say what separates them.

## D4. Who writes what the customer reads

Every word from the model, fixed wording for outcomes your code already knows, or a
mix. Say where the line is and what decides which side something falls on.

## D5. What survives a restart

We kill the process mid-payment. Something has to be on disk. What did you write
down, at what moment, and what did you decide was cheap enough to lose.

---

## One more, not a trade

**D6. What you would tear up.** If you started again on Monday knowing what you know
now, what goes in the bin? One paragraph. This is the easiest section to write badly
and the most telling when it is written well.
