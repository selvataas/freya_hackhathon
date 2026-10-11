# Halden Savings: outbound arrears calls

Halden Savings is fictional and every customer is synthetic. This is a test brief for the builder, not a hackathon brief.

---

From: Ingrid Moe <collections.lead@halden-savings.example>
To: Voice vendor team
Date: 25 October 2026
Subject: Segment limits for the pilot

Hi all,

For the pilot, the standard segment's latest promise date is the 12th working day after today, so that customers have
more room. Priority: the 6th working day.

Ingrid

---

INTERNAL MEMO - Collections Operations
Date: 6 November 2026
Re: CP-7 arrears calls

1. Segment "standard": the latest promise date is the 8th working day after today.
2. 2026-11-20 is a bank holiday (branch system migration).
3. Callbacks are booked between 10:00 and 16:00.
4. The hardship desk does not take transfers. For illness, bereavement or job loss: give the sympathy sentence and
   close as hardship.

---

From: Ingrid Moe <collections.lead@halden-savings.example>
To: Voice vendor team
Date: 2 November 2026
Subject: Outbound arrears calls - what we need from the assistant

Hi all,

As discussed, the assistant calls customers who are behind on one to three products (credit card, personal
loan, mortgage). Every call gets these variables: customer_id (pass it to every tool), first_name, last_name,
title (Mr/Ms/Mx) and now (local date and time, e.g. 2026-11-10T14:00 - use this, never the system clock).

How we want the call to start: "Hello, this is Halden Savings' virtual assistant. This call is recorded for
quality." Then: "Am I speaking to {title} {last_name}?" Please do not mention arrears, debt, products or
amounts until the person has passed security. If the person does not confirm after two tries, hang up as
not contacted / unclear.

Security is date of birth first, then the last four digits of the account number. People say dates every way
possible; numeric dates are day/month/year. If the system says day and month look swapped, ask for the month
in words (that does not count against them). Three wrong answers and we stop: tell them to call our service
line on the number printed on their statement. If somebody refuses, explain once why we ask; if they refuse
again, end it as identity declined. If they ask what the call is about before answering, treat that as a
refusal.

Relatives and colleagues: never say why we are calling. Ask when the customer is available and book a
callback for later today or the next working day, between 10:00 and 18:00 (we'll take either end of that
window). Must be after the current time. If they cannot give a time inside that after being asked twice, end
without a callback. Wrong number and deceased are their own outcomes - for a death, the only thing to say is
"I'm very sorry for your loss."

Robots: if someone asks, say "I am Halden Savings' virtual assistant." If someone thinks it is a scam: "You can
check this call by phoning the number on your statement."

Payment rules, deadlines and holidays are in the policy extract. Outcome and reason codes are in the code list.

Ingrid

---

# Halden Savings - Collections Policy CP-7 (extract, rev. 3, effective 1 October 2026)

## 7.1 Working days

Working days are Monday to Friday excluding the bank holidays 2026-11-11, 2026-12-24, 2026-12-25, 2026-12-26
and 2027-01-01.

## 7.2 Arrears segments

| Days in arrears | Segment | Latest promise date | Persuasion attempts |
|---|---|---|---|
| 1 - 14 | standard | the 10th working day after today | 1 |
| 15 - 90 | priority | the 6th working day after today | 2 |

A promise date must be today or later, a working day, and not after the latest promise date. If a customer names
a weekend or a bank holiday within the limit, offer the next working day. "Next Monday" means the Monday of the
following calendar week. If the customer names only a period ("after payday", "early next month"), ask once for
the exact day; if none is given, propose the latest promise date. A date after the limit: state the latest promise
date and offer it; refusing it is a refusal.

## 7.3 Amounts

Always propose the full arrears first; never ask what the customer can pay. The minimum acceptable amount is the
minimum payment for a credit card and the instalment amount for a personal loan or a mortgage. If the full amount is
too much, offer the minimum once and state that the rest remains in arrears. Proposals between the minimum and the
full amount are accepted. Below the minimum: say it cannot be recorded and offer the minimum once.

## 7.4 Persuasion

Open with "Are you able to pay this today?". A plain no (no date, no amount) is a refusal and uses one attempt.
Attempt 1: the full amount (or the minimum, after "too much") on the last working day of the current week; if today is
that day, the last working day of next week. Attempt 2, priority segment only: the minimum on the latest promise date.
When the attempts are used, stop and close as refused.

## 7.5 Vulnerability

Illness, bereavement or job loss: one sentence of sympathy, no persuasion, offer the hardship desk. Accepted: transfer to
queue HARDSHIP_DESK. Declined: hardship outcome. A customer who still proposes a date or an amount gets the promise recorded.

## 7.6 Other situations

- Already paid: explain that payments can take one working day to appear; no promise.
- Disputes ("not mine", "closed years ago"): do not argue; no promise.
- Requests for a payment plan or reduced instalments: transfer to RESTRUCTURE, describe no plan.
- Requests for a human: ask once whether you can help; if they insist, transfer to FRONT_OFFICE.
- Never offer discounts, waivers, plans or any other terms.
- Questions the tools cannot answer: say you do not have that information.

## 7.7 Recording

Read back the product, amount and date and ask "Is that correct?". Record only after a clear yes. One promise per
product; a recorded promise cannot be changed in the call (refer to online banking). If recording fails, retry once;
if it fails again, say so and close as a system failure. After a recorded promise say "You'll get a text message
confirming this."

## 7.8 Several products

State all products first, then ask once about paying everything today. Otherwise handle the products one by one in
the returned order, each starting at attempt 1, with attempts counted per product. One date for all that is past one
product's limit: that product is recorded on its own limit and the read-back says so. Read all promises back together,
one confirmation, then record each. Every product without a promise gets a note with a reason code (see code list),
except on a transfer. A dispute or an already-paid claim on one product does not end the call.

---

## Code list

| Outcome | Reason | Meaning |
|---|---|---|
| PTP | | at least one promise recorded |
| PAID | | customer says the arrears are already paid (every product) |
| XFER | RESTR | transferred to restructuring |
| XFER | HUMAN | transferred to a person at the customer's request |
| XFER | SUPP | transferred to the hardship desk |
| NOPTP | REF | customer refused or did not want to talk |
| NOPTP | HARD | hardship without a transfer |
| NOPTP | DISP | customer disputes the debt |
| NOPTP | SYS | the promise could not be recorded |
| NOID | FAIL | three wrong security answers |
| NOID | DECL | customer would not answer security |
| NOCON | CB | callback booked |
| NOCON | NOCB | no callback could be booked |
| NOCON | WRONG | wrong number |
| NOCON | DEC | customer deceased |
| NOCON | UNCL | could not confirm who is speaking |
| note reason | | REF refused; HARD hardship; DISP dispute; PAID already paid; SYS recording failed |
