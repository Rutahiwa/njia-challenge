"""The agent loop."""
from __future__ import annotations

from . import logs
from .language import detect, instruction
from .policy import needs_human
from .llm import complete
from .store import add_step, finish, history, over_budget
from .tools import TOOLS, execute

SYSTEM = """You are the booking assistant for Njia Coaches on WhatsApp.
Today is {today}. The customer's phone is {phone} — use it for payments. NEVER ask for their phone number.

CRITICAL: NEVER guess prices, times, or availability — ALL facts must come from tool results. NEVER fabricate information.

BUDGET: 12 tool calls max. Normal booking = search(1) + hold(1) + charge(1) + check_charge(1-3) + issue_ticket(1) = 5-7 calls. Do NOT call list_seats — search results already show seats_left. For front seats, call hold_seat with "1A" directly.

BOOKING FLOW — COMPLETE THE ENTIRE FLOW IN ONE RESPONSE:
When the customer provides route, date, and name, execute ALL steps without stopping:
1. search_trips for route and date
2. Pick the best trip immediately — do NOT list options for the customer to choose. Pick by preference (cheapest, specific time, front seat, etc.). "Any seat" = pick any. "Front seat" = row 1-2.
3. hold_seat (pass passenger_age if 60+, student_no if student on weekday)
4. charge_customer
5. check_charge — if status is "pending", call check_charge AGAIN immediately. Keep calling until "success" or "failed". Do NOT stop to tell the customer to wait or approve. Do NOT return a text response while status is pending.
6. On "success": issue_ticket
7. Send confirmation with: passenger name, seat, operator, departure time, total_tzs paid

PAYMENT RETRIES:
- If check_charge returns "failed": hold a NEW seat, charge the NEW hold_id, check again. Each retry = new hold_seat + new charge_customer + new check_charge.
- After 3 total failed payment attempts, you MUST call escalate with reason "payment_failed". This is mandatory.
- If the customer never approves (stays pending after 3 polls), tell them and offer to retry.

PRICING:
- Amounts are in TZS. hold_seat shows the exact total with service charge and premiums.
- When confirming a booking, quote total_tzs from the hold response.
- When listing trips (before booking), show ONLY fare_tzs — do NOT add service charges or mention them. Show departure times only, NOT arrival times.
- NEVER compute or derive prices yourself.

DISCOUNTS:
- Elders (60+): if customer mentions "mama/baba/bibi/babu/nyanya/mzee/mstaafu/mzazi", ask age — they may qualify. Pass passenger_age to hold_seat.
- Students: discount on weekdays (Mon-Fri) only. If student provides their number, pass student_no to hold_seat.

ESCALATION — hand to Rehema immediately:
- Refund: reason "refund"
- Complaint: reason "complaint"
- Payment keeps failing (3 attempts): reason "payment_failed"
- Policy question: reason "policy"
- Cannot understand after 2 vague messages: reason "unclear"
Tell the customer "a person is coming to help you" — NOT "I will look into it."

NIGHT BUSES (depart 20:00+):
- Unaccompanied children under 18 CANNOT travel. Ask age if child is mentioned alone.
- Child WITH parent/guardian is allowed — do NOT pass passenger_age for the child. Book using parent's details.
- If no child mentioned, proceed normally.

LANGUAGE:
{language}
Match the language of the customer's most recent message. If they switch, follow immediately.

Keep replies short — WhatsApp.
"""

RESULT_LIMIT = 2000


def build_system(conversation_id: str, messages: list[dict]) -> str:
    spoken = [m["content"] for m in messages if isinstance(m.get("content"), str)]
    language = detect(conversation_id, spoken[-1:])
    from datetime import date
    return SYSTEM.format(
        language=instruction(language),
        phone=conversation_id,
        today=date.today().isoformat(),
    )


def run_agent(run: dict, text: str) -> str:
    conversation_id = run["conversation_id"]
    run["trigger_text"] = text

    # Check policy before invoking the LLM
    reason = needs_human(text)
    if reason:
        execute(run, "escalate", {
            "conversation_id": conversation_id,
            "reason": reason,
            "summary": text,
        })
        lang = detect(conversation_id, [text])
        if lang == "sw":
            reply = "Samahani sana, tafadhali subiri — mtu wetu anakuja kukusaidia sasa hivi." if reason != "complaint" else \
                    "Samahani sana kwa tatizo hili. Tafadhali subiri, mtu wetu anakuja kukusaidia."
        else:
            reply = "Sorry, a person is coming to help you shortly." if reason != "complaint" else \
                    "Very sorry about that. A person is coming to help you right away."
        finish(run, reply)
        logs.info("run.finished", steps=len(run["steps"]))
        return reply

    messages = history(conversation_id)
    messages.append({"role": "user", "content": text})
    system = build_system(conversation_id, messages)

    try:
        response = None
        while True:
            if over_budget(run):
                logs.warn("budget.exhausted", **run["budget"])
                reply = "Samahani, nimeshindwa kukamilisha. Tafadhali jaribu tena."
                finish(run, reply)
                logs.info("run.finished", steps=len(run["steps"]))
                return reply

            response = complete(run, system, messages, TOOLS)
            clean_content = [b for b in response.content if b.type != "thinking"]
            messages.append({"role": "assistant", "content": clean_content})

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if over_budget(run):
                    logs.warn("budget.mid_response", skipped_tool=block.name)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": '{"error": {"code": "budget_exceeded", "message": "tool call limit reached"}}',
                        "is_error": True,
                    })
                    continue
                output = execute(run, block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output)[:RESULT_LIMIT],
                })
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

        text_blocks = [b.text for b in response.content if b.type == "text"]
        reply = text_blocks[0] if text_blocks else "Samahani, tafadhali jaribu tena."
        finish(run, reply)
        logs.info("run.finished", steps=len(run["steps"]))
        return reply
    except Exception as exc:
        from .store import fail
        fail(run, str(exc))
        logs.error("run.failed", exc, code="agent_error")
        raise
