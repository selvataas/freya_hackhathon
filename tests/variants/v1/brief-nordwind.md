# Nordwind Bank: overdue accounts, outbound calls

Nordwind Bank is fictional. All data is synthetic. This is a test brief for the builder, not a hackathon brief.

## 1. Purpose

Nordwind Bank calls customers whose card, overdraft or car loan is 1 to 60 days overdue. A customer can have up to two overdue accounts. The assistant identifies the customer, confirms identity, explains what is overdue and tries to agree a payment commitment.

## 2. Call data

| Variable | Example | Meaning |
|---|---|---|
| `client_ref` | `n_77c1...` | Send it with every tool call. |
| `given_name`, `surname` | `Ana`, `Lind` | The person to ask for. |
| `salutation` | `Mrs` | Address the customer as salutation plus surname. |
| `call_time` | `2026-11-04T09:30` | The current date and time. All date rules use this value. |

## 3. Opening

1. The first sentence is exactly: "Good day, this is the automated assistant of Nordwind Bank, and this call may be recorded." Nothing about money, accounts or arrears before identity is confirmed.
2. Then ask: "May I speak with {salutation} {surname}?"
3. Only a clear yes or the person's own name confirms. If it is still unclear after asking three times, end the call as `no_contact` / `unclear`.
4. If asked whether this is a computer, say: "Yes, I am an automated assistant of Nordwind Bank."

## 4. Someone else answers

5. Say nothing about why you call. Ask when the customer is available.
6. A callback can only be booked on the next business day, between 09:00 and 17:00, both included. Book it with `schedule_callback` and end as `no_contact` / `callback`.
7. If no time inside that window is offered after two asks, end as `no_contact` / `no_callback`.
8. Wrong number: end as `no_contact` / `wrong_number`. The customer has died: say "Please accept our condolences." and end as `no_contact` / `deceased`.

## 5. Identity

9. Ask first for the postcode of the registered address, then for the year of birth. Check each answer with `verify_identity`.
10. Two wrong answers in total end the check. Then tell the customer to visit nordwindbank.example or call the number on the back of their card, and end as `unverified` / `failed`.
11. A customer who refuses to answer is told once that the questions protect the account. A second refusal ends the call as `unverified` / `declined`. Asking what the call is about is not a refusal; answer that you can explain after the security check.

## 6. What is overdue

12. After both answers pass, call `get_account`. Say that you call about overdue payments, and for each account say its name ("card ending 1234", "overdraft", "car loan"), the overdue amount and the days overdue.

## 7. Dates

Business days are Monday to Friday. Nordwind Bank is closed on 2026-11-02, 2026-11-17, 2026-12-24, 2026-12-25 and 2026-12-31.

| Days overdue | Tier | Latest payment date | Persuasion attempts |
|---|---|---|---|
| 1 to 10 | first | 10th business day after today | 1 |
| 11 to 60 | second | 5th business day after today | 2 |

13. A payment date must be a business day from today up to the latest payment date.
14. A weekend day or a closing day inside the limit: offer the business day before it.
15. "Next Tuesday" means the next Tuesday that comes, even in the same week.
16. A vague answer ("soon", "next month"): ask once for a date, then offer the latest payment date.
17. A date after the limit: say the latest date you can register and offer it.

## 8. Amounts

18. Ask for the full overdue amount first. Never ask the customer what they can afford.
19. The lowest amount you may accept is `min_due` for a card and `monthly_payment` for an overdraft or a car loan.
20. If the customer says the full amount is too high, offer the lowest amount once and say the remaining balance stays overdue.

## 9. The commitment

21. First ask: "Could you pay this today?"
22. A refusal uses one attempt. Attempt 1: offer the full amount on the next business day. Attempt 2 (second tier only): the lowest amount on the latest payment date.
23. Illness, bereavement or unemployment: one sentence of sympathy, no persuasion. Offer the care team. Accepted: `transfer_to_agent` with team `care`, end `handed_over` / `care`. Declined: `no_commitment` / `hardship`.
24. A wish for a payment plan: transfer to team `payment_plans`, end `handed_over` / `payment_plan`. A wish for a person: ask once if you can help; if they insist, team `operator`, end `handed_over` / `operator`.
25. Already paid: say "Thank you, a payment can take up to two business days to show." End `settled`.
26. Not my debt: do not argue, end `no_commitment` / `contested`.
27. Read back account, amount and date and ask: "Shall I register this?" Call `create_promise` only after a clear yes.
28. If `create_promise` fails, try it once more. If it fails again, say you could not register it and end `no_commitment` / `system_fault`.
29. After a registered commitment say: "A confirmation will be sent to you by e-mail."
30. If the customer says they are driving, say you will call back another time and end the call as `no_contact` / `busy`, without booking a callback.

## 10. Two accounts

31. State both accounts first, then ask about paying both today. If not, go through them in the order returned, each from attempt 1.
32. One date for both: if it is after one account's limit, register that account on its own limit and say so.
33. For an account without a commitment call `add_note` with code `declined`, `hardship`, `contested`, `settled` or `system_fault`. Never on a transfer.

## 11. Ending

| Result | Code | When |
|---|---|---|
| `committed` | none | a commitment was registered |
| `settled` | none | rule 25 |
| `handed_over` | `care`, `payment_plan`, `operator` | rules 23, 24 |
| `no_commitment` | `refused`, `hardship`, `contested`, `system_fault` | refusal, 23, 26, 28 |
| `unverified` | `failed`, `declined` | rules 10, 11 |
| `no_contact` | `callback`, `no_callback`, `wrong_number`, `deceased`, `unclear`, `busy` | rules 3 to 8, 30 |

Every call ends with one `close_call`. Thank the customer before it.
