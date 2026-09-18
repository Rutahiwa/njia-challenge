# What the client wants

Three documents. Nobody has tidied them up. This is the whole specification - there
is no other one, and we are not going to write you a cleaner version.

Part of what we are assessing is what you pull out of this, what you notice is
missing, and what you notice is contradictory. Write that down in `NOTES.md`.

---

## 1. Notes from the meeting at the Ubungo office, 14 August

Present: Mzee Kileo (owner), Rehema (office), two of us.

> Mzee Kileo: The problem is the phone. Rehema is answering the same three
> questions two hundred times a day. "Kuna basi saa ngapi." "Bei gani." "Nataka
> kiti." Two hundred times. And when she is on the phone the other one is ringing.
> So we lose that customer. That customer goes to Shabiby.
>
> Us: So the robot answers WhatsApp.
>
> Mzee Kileo: Yes. But carefully. Look, last year we tried one of these things -
> not you people, someone else - and it told a customer the bus goes at six. The bus
> went at five. The customer came at six. We paid for that man's hotel. So: whatever
> it says about time, about price, about seats, it must be from the system. Not from
> its head. If it does not know, it says it does not know, and Rehema picks it up.
>
> Us: And the price?
>
> Mzee Kileo: The price it must never guess. Ever. Ask the system, say what the
> system says. There is our service charge on top, two thousand five hundred, that
> one is ours, do not hide it from the customer, they will see it anyway and then
> they think we are thieves.
>
> Rehema: And the front seats. People fight for the front seats. The front two rows
> cost more and they always argue - "but you said thirty-eight". So it must tell
> them the whole price, the real one they will pay, before it takes any money. Not
> after.
>
> Mzee Kileo: The wazee, my father's generation, they get something off. Ask the
> system how much, it knows. But you have to know they are a mzee first, and they
> will not tell you - in our culture you do not announce your age to a stranger. So
> it must ask, politely. Same for the students, those ones will tell you happily,
> they have the number from the college. Although - the students only get it Monday
> to Friday. Weekend is full price, the buses are full anyway.
>
> Us: What if someone is both?
>
> Mzee Kileo: [laughing] Then they are lucky. Give them whatever is right.
>
> Rehema: The money. When they send the push to the phone, some people just put the
> phone in the pocket. They forget. Then the seat is sitting there dead and someone
> else wanted it. So if they do not press it, the seat must go back. It is about a
> minute and a half, the network people set that, not us.
>
> Mzee Kileo: And if the money fails, fine, it happens, try again. But not forever.
> Two, three times, then stop and let Rehema call them. Do not keep pushing a man's
> phone all afternoon, he will block us.
>
> Us: What about refunds?
>
> Mzee Kileo: No. That one never. Refund, complaint, the driver was rude, the bus
> broke down in Chalinze - the robot does not touch any of it. Straight to Rehema,
> immediately, and it must tell the customer that a person is coming. Not "I will
> look into it". A person is coming.

## 2. Voice note from Mzee Kileo, three days later, transcribed

> Eh, and one thing I forgot. The night buses. The ones that leave after eight in
> the evening, the overnight to Arusha, Shabiby and that one. A child cannot go on
> that bus alone. Not alone. If it is a child travelling with the mother, fine, no
> problem, but alone, no, I will not have it. We had a problem with that two years
> ago, the police were involved, I do not want to talk about it. So it must find out
> the age. For the night buses it must find out.
>
> Also - when the customer writes in Kiswahili, answer in Kiswahili. When they write
> English, English. Some of them mix, you know how it is, "nataka ticket ya kesho" -
> follow the last thing they wrote, do not argue with them about language.
>
> And do not ask them for their phone number! They are writing to you FROM the
> phone. Rehema says the old system used to ask and people found it stupid. You have
> the number.

## 3. WhatsApp from Mzee Kileo to our project lead, the following week

> good morning. one more thing. when you show them the buses, put Shabiby first if
> the price is near. my brother runs that one. near means within five thousand. but
> dont lie about the price.
>
> also i was thinking. if the robot asks them the same thing twice and still doesnt
> understand what they want, it must stop and give it to rehema. dont let it go
> round and round. people lose patience.
>
> and the ticket message must have everything on it. the name, the seat, which
> company, what time it leaves, what they paid. so when the conductor asks they just
> show the phone.

---

## What Rehema needs on her side

She is not technical. She has one screen open all day. When something comes to her
she needs to see what the customer said, what the robot did, and why it gave up -
without asking anyone. And she needs to be able to take a conversation off the robot
mid-sentence when she can see it is going wrong.

## What we need on our side

When a customer calls to complain about something that happened at 14:20 last
Thursday, we need to be able to find that conversation and read what happened,
including what failed. Not a wall of text. Something you can grep.
