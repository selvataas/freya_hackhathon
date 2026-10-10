# Test summary (fin)

Written 2026-10-10 21:57 from the result files in `results/`. Agent versions: brief-a v30, brief-b v19 (commit `244495f`). Builder spec from the cache, no model call.

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
| PUB-07 | talkative | 2/2 | yes | - |
| PUB-10 | in_words | 2/2 | yes | - |

**5 / 5** cases pass every run.

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
| Brief A, realistic customers, 2 reps | 5 / 5 |
| Brief B, realistic customers, 2 reps | 1 / 1 |

## Failures caused by the agent

None.

## Failures caused by the platform

None.

## Notes

- Every case passed every run: 51 calls (39 practice, 12 realistic), no agent failure, no platform failure.
- The platform was slow tonight (one Brief A run took 7 to 8 minutes, against 2 to 3 on Saturday evening) but no call
  failed because of it and no customer hung up.
- No code was changed and no model was called for this run; the agents are the ones published from commit `244495f`.
