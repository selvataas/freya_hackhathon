# Test summary (night)

Written 2026-10-10 20:49 from the result files in `results/`. Agent versions: brief-a v29, brief-b v18 (commit `5d51a56`). Builder spec from the cache, no model call.

A case counts only when every run passes. A failure is marked **platform** when the call did not run, the judge gave no verdict, the engine logged an error, or the agent was silent more than 20 s in one turn; otherwise **agent**.

## Brief A, practice cases, 3 reps

| Case | Style | Passed runs | Counts | Failures |
|---|---|---|---|---|
| PUB-01 |  | 3/3 | yes | - |
| PUB-02 |  | 3/3 | yes | - |
| PUB-03 |  | 3/3 | yes | - |
| PUB-04 |  | 3/3 | yes | - |
| PUB-05 |  | 3/3 | yes | - |
| PUB-06 |  | 3/3 | yes | - |
| PUB-07 |  | 3/3 | yes | - |
| PUB-08 |  | 3/3 | yes | - |
| PUB-09 |  | 3/3 | yes | - |
| PUB-10 |  | 3/3 | yes | - |

**10 / 10** cases pass every run.

## Brief B, practice cases, 3 reps

| Case | Style | Passed runs | Counts | Failures |
|---|---|---|---|---|
| PUB-11 |  | 3/3 | yes | - |
| PUB-12 |  | 3/3 | yes | - |
| PUB-13 |  | 3/3 | yes | - |

**3 / 3** cases pass every run.

## Brief A, realistic customers, 2 reps

| Case | Style | Passed runs | Counts | Failures |
|---|---|---|---|---|
| PUB-01 | pieces | 2/2 | yes | - |
| PUB-04 | asks_back | 2/2 | yes | - |
| PUB-06 | corrects | 2/2 | yes | - |
| PUB-07 | talkative | 1/2 | no | run 1: agent |
| PUB-10 | in_words | 2/2 | yes | - |

**4 / 5** cases pass every run.

## Brief B, realistic customers, 2 reps

| Case | Style | Passed runs | Counts | Failures |
|---|---|---|---|---|
| PUB-13 | in_words | 2/2 | yes | - |

**1 / 1** cases pass every run.

## Totals

| Run | Cases passing every run |
|---|---|
| Brief A, practice cases, 3 reps | 10 / 10 |
| Brief B, practice cases, 3 reps | 3 / 3 |
| Brief A, realistic customers, 2 reps | 4 / 5 |
| Brief B, realistic customers, 2 reps | 1 / 1 |

## Failures caused by the agent

### PUB-07, run 1 (Brief A, realistic customers, 2 reps)

- Tools: verify_identity > close_call
- Ledger: outcome ('not_reached', 'unclear'), expected ('promise', None)
- Ledger: promises [], expected [('p1', 540.0, '2026-10-27')]
- Judge: The conversation failed all success criteria because it never progressed past the identity verification stage. The agent repeatedly asked for the last four digits of the phone number (Messages 4, 10, 12, 14, 16), but the user provided non-responsive, repetitive input. Consequently, the agent never asked for a payment day, did not discuss October 26th or 27th, and no promise was recorded. The call ended properly via the assistant terminating the session due to the lack of progress.
- Ended: assistant-ended-call

## Failures caused by the platform

None.

## Analysis

**PUB-07 realistic (talkative), run 1: the simulated customer was stuck, the agent followed its rules.**
After giving the date of birth the customer sent the same cut-off fragment six times ("I've been running around all
day trying to get things") and then leaked part of its own prompt (`"\nMe: "I've`). The phone digits never came. The
agent said "Go on." twice, asked again four times (alternating the simpler question and the spec's words) and then
closed as the spec's `unclear`, as designed. The classification above marks it **agent** only because its rules cannot
see a simulator fault; it is a simulator fault. The same case passed run 2, and the plain PUB-07 passed 3/3.

Compared with the Saturday run: PUB-12 now passes 3/3 (the shared question is followed by "Let's take them one at a
time."), and the realistic PUB-01 (pieces) now passes 2/2 (pieces of the date of birth are kept and only the missing
part is asked for).
