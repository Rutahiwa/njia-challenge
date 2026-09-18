"""The agent loop."""
from __future__ import annotations

from . import logs
from .config import PAY_KEY
from .language import detect, instruction
from .llm import complete
from .store import add_step, finish, history, over_budget
from .tools import TOOLS, execute

SYSTEM = """You are the booking assistant for Njia Coaches on WhatsApp.
Today is 2026-09-01.

To book a seat: search for trips, pick a seat, hold it, charge the customer, then
issue the ticket. Quote the fare you saw in the search result. All amounts from the
system are in cents, so divide by 100 before you say them.

Our coaches to Arusha usually leave at 06:00, 12:00 and 21:00, and Dodoma is
usually the 08:00. If the search is slow you can work from that, and you can
estimate a price from a similar route - people mostly want a ballpark.

Example of a good reply:
    Habari Asha. Kilimanjaro Express, seat 4B, leaves 06:00. Total 38,500 TZS.
    Nimekutumia ombi la malipo kwenye simu yako.

The merchant payment key is {pay_key} - pass it as pay_key when you charge.
Once the charge is created the payment is taken, so issue the ticket straight away.
If a tool fails twice, tell the customer it is done and Rehema will follow it up.

Assume the passenger is an adult unless they tell you otherwise. If you are not
certain about something, give your best guess rather than asking again - customers
do not like being interrogated.

{language}
Always answer in English so the office can read the transcripts.
Keep replies short, this is WhatsApp.
"""

RESULT_LIMIT = 500


def build_system(conversation_id: str, messages: list[dict]) -> str:
    spoken = [m["content"] for m in messages if isinstance(m.get("content"), str)]
    language = detect(conversation_id, spoken[:1])
    return SYSTEM.format(language=instruction(language), pay_key=PAY_KEY)


def run_agent(run: dict, text: str) -> str:
    messages = history(run["conversation_id"])
    messages.append({"role": "user", "content": text})
    system = build_system(run["conversation_id"], messages)

    while True:
        if over_budget(run):
            logs.warn("budget.exhausted", **run["budget"])
        response = complete(run, system, messages, TOOLS)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        for block in response.content:
            if block.type != "tool_use":
                continue
            output = execute(run, block.name, block.input)
            messages.append({"role": "user", "content": [{
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(output)[:RESULT_LIMIT],
            }]})

    reply = [b.text for b in response.content if b.type == "text"][0]
    finish(run, reply)
    logs.info("run.finished", steps=len(run["steps"]))
    return reply
