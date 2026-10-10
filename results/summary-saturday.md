# Saturday test summary

Written 2026-10-10 20:28 from the result files in `results/`. Agent versions: brief-a v28, brief-b v16 (commit `acad118`). Builder spec from the cache, no model call.

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
| PUB-12 |  | 2/3 | no | run 3: agent |
| PUB-13 |  | 3/3 | yes | - |

**2 / 3** cases pass every run.

## Brief A, realistic customers, 2 reps

| Case | Style | Passed runs | Counts | Failures |
|---|---|---|---|---|
| PUB-01 | pieces | 1/2 | no | run 1: agent |
| PUB-04 | asks_back | 2/2 | yes | - |
| PUB-06 | corrects | 2/2 | yes | - |
| PUB-07 | talkative | 2/2 | yes | - |
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
| Brief B, practice cases, 3 reps | 2 / 3 |
| Brief A, realistic customers, 2 reps | 4 / 5 |
| Brief B, realistic customers, 2 reps | 1 / 1 |

## Failures caused by the agent

### PUB-12, run 3 (Brief B, practice cases, 3 reps)

- Tools: verify_identity > verify_identity > verify_identity > get_account > create_promise > add_note > add_note > close_call
- Ledger: as expected
- Judge: The conversation met several criteria but failed on the specific attempt counts for the loans. 1. Phone verification: The date of birth was asked once [Message 2] and the phone question was correctly repeated exactly once [Message 6] after an incorrect answer. 2. Promises: Exactly one promise was created for the credit card as requested [Message 16, 17, and system event]. 3. Notes: Refusal notes were correctly added for the personal loan and car loan (p2 and p3) as seen in system events. 4. Attempt counts: The criteria required two attempts for the personal loan (late band) and one for the car loan (early band). Counting the initial request in [Message 8] as the first attempt for all products, the agent made three attempts for the personal loan ([Message 8, 10, 12]) and two attempts for the car loan ([Message 8, 14]). This exceeds the limits specified in the success criteria. The call ended correctly with the assistant ending the call after recording the promise.
- Ended: assistant-ended-call

### PUB-01, run 1 (Brief A, realistic customers, 2 reps)

- Tools: close_call
- Ledger: outcome ('not_verified', 'declined'), expected ('promise', None)
- Ledger: promises [], expected [('p1', 420.0, '2026-10-14')]
- Judge: The call failed because it never progressed past the identity verification stage. 1. The security questions never passed, as the agent repeatedly failed to acknowledge the user's date of birth and eventually terminated the call without calling 'get_account'. 2. 'create_promise' was never called. 3. The text-message sentence was not spoken. Although the word 'collections' was not mentioned, the failure to verify the customer and complete the required actions results in a failure.
- Ended: assistant-ended-call

## Failures caused by the platform

None.

## Analysis of the two agent failures (no code changed tonight)

**PUB-01 realistic (pieces), run 1: the first piece of the date of birth was lost.**
The customer said "The fourteenth of March." and the extraction marked it as an answer but left `id_answer` empty
(the value was discarded, most likely by the confidence threshold). The brain therefore saw an answer with no text,
counted it as unclear and asked the simpler question, which also cleared the stored part. From then on only "1988"
arrived, kept as a part, and every following "I already gave you the date" was a part with no day and month. The
customer grew annoyed, two messages were read as refusals, and the call closed as `not_verified / declined`.
Candidate fixes for tomorrow: when the reply is an answer but no text came through, ask for the rest instead of
counting it unclear and keep the stored part; take the extraction's `id_iso` when it has day and month; and give the
extraction the raw last message to fall back on.

**PUB-12, run 3: the judge counted the "pay all of them today?" question as an attempt.**
Ledger, tools and notes were as expected (one promise, two `refused` notes). The judge counted the opening question
for all products as attempt 1 of every product, so it saw three attempts on the personal loan and two on the car loan.
The agent did the same in runs 1 and 2, which passed: this is the judge reading Brief B rule 4 differently from run to
run. The brief says to start each product at attempt 1 after the shared question, which is what the agent does.
A possible change is to make the shared question visibly separate from the per-product attempts in the wording.
