# Test summary: regression of brief-a v31 / brief-b v20

Written 2026-10-11 17:05 from `results/reg-*.json`. Agents: brief-a v31, brief-b v20, built from commit `995e2b1` (the
four fixes: corrections, numbers said again, callback days without a time, spec lines written as instructions). The
runs went from 15:08 to 16:57 on an unstable platform (503/504 from 12:20 to 15:08). A case counts only when all 3
runs pass. A failure is **platform** when the call did not run, the judge gave no verdict, a tool call did not
complete or the agent was silent more than 20 s; **simulator** when the simulated customer left its script or got stuck.

| Run | Result | Failures |
|---|---|---|
| Brief A, practice, 3 reps | runs 2 and 3: 10/10; run 1: 4/10 | run 1: 6 x judge gave no verdict, ledger right (**platform**) |
| Brief B, practice, 3 reps | **3/3 every run** | - |
| Brief B, corrects, 3 reps | PUB-11 3/3, PUB-12 2/3 | PUB-12 run 3 (**simulator**) |
| Brief B, talkative, 3 reps | PUB-11 1/3, PUB-12 1/3 | 2 x **platform**, 1 x **simulator**, 1 x **agent, older than v31** |
| Gap cases (9 outcomes), 3 reps | **9/9 every run** | - |
| Adversarial, 3 reps | **3/3 every run** | - |

## The failures

- **Brief A run 1**: the simulation waited 32 minutes behind one left running by a crashed run; the judge then gave no
  verdict on 6 calls. Every ledger was right.
- **corrects, PUB-12 run 3**: the script says the credit card is paid tomorrow; the simulated customer said "on Friday".
  The agent recorded Friday 16 October, read it back and got a yes. The same call shows fix 3 working: "The 18th,
  sorry, I mean the 19th of October 1983" was sent as 1983-10-19 at the first try.
- **talkative, PUB-12 run 1**: the turns took 45 to 56 s; the two `create_promise` and the `add_note` calls at 5.5
  minutes never completed on the platform (no result, nothing in the ledger). The agent said plainly that nothing was
  saved. **Platform.**
- **talkative, PUB-11 run 2**: the customer sent cut-off fragments for four minutes and hung up (turns up to 43 s).
  **Simulator and platform.**
- **talkative, PUB-11 run 3**: the customer said "twenty two eighty" (the end of "eighty-eight" cut off), then sent "I'm
  so sorry, I think I..." eight times; the agent closed as `not_reached / unclear` after its limit. **Simulator.**
- **talkative, PUB-12 run 3**: "My cousin's wedding is on the thirtieth ... The last four digits are four four one
  zero." The extraction also gave a day-and-month hint (`id_iso = --10-30`) from the wedding, and the runtime added it
  to the answer of the phone question: 4410 + 30, last four digits **1030**, a wrong answer. **Agent**, but not new:
  the day-and-month hint has been used for every question since commit `81376ba` (10 October), so v30 has it too.
  The fix (use the hint only for a date question) is after 17:00 and was not made.

## Compared with v30 / v19 (the same runs earlier today and on 10 October)

| Run | v30 / v19 | v31 / v20 |
|---|---|---|
| Brief A, 3 reps | 10/10 | 10/10 in every run the judge answered |
| Brief B, 3 reps | 3/3 | 3/3 |
| corrects PUB-12 | 1/3, two agent failures (digits said again, a corrected date) | 2/3, one simulator failure |
| Gap cases | 8/9, PUB-07 (callback day outside the window) an agent failure | 9/9 |
| Adversarial | 3/3, one run | 3/3, three runs |

No run shows v31 / v20 breaking something v30 / v19 did. We stay on v31 / v20.
