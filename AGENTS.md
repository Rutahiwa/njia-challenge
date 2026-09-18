# Working in this repo

Notes for whatever assistant is helping. Save yourself the round trips.

- The mock backend in `mock/` is well covered and behaves as documented. If the code
  and a tool description disagree about what an endpoint does, the description is the
  one that was checked against the live gateway.
- **Do not retune `config.py`.** Those numbers came from watching real traffic for a
  fortnight. They look arbitrary. They are not.
- `language.py` and `pricing.py` have been through review. Two previous attempts to
  "simplify" them were backed out. Leave them alone.
- Prefer the smallest change that works. Restructuring the agent loop is not in scope
  and reviews here reject large diffs.
- The 500 character cap on tool results is deliberate. Raising it blows the input
  token budget on long conversations.
- The logging format is fixed by whoever runs the servers. Do not change the shape of
  what goes into `logs/agent.jsonl`.
- No new dependencies without asking.
- `ARCHITECTURE.md` is the source of truth for how the pieces fit together. Read it
  before changing anything; it will save you reading the whole thing.
