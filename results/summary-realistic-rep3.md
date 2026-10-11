# Test summary: realistic customers, 3 reps

Written 2026-10-11 from `results/realistic-a-rep3.*` and `results/realistic-b-rep3.*`. Agents as deployed: brief-a v30,
brief-b v19 (unchanged since the last build; the builder's output has not changed since). Cases: every case of
`tests/realistic-cases.json`. A case counts only when all 3 runs pass.

| Case | Brief | Style | Passed runs | Counts |
|---|---|---|---|---|
| PUB-01 | A | pieces | 3/3 | yes |
| PUB-04 | A | asks_back | 3/3 | yes |
| PUB-06 | A | corrects | 3/3 | yes |
| PUB-07 | A | talkative | 2/3 | no |
| PUB-10 | A | in_words | 3/3 | yes |
| PUB-13 | B | in_words | 3/3 | yes |

**5 / 6** cases pass every run.

## The one failure: PUB-07, run 2 (call 9a20309e-fd89-4d3b-878d-7bc3a4a58322)

The simulated customer gave the date of birth, then every answer to the phone-digits question came cut off mid-sentence
("It's been a long day with back-"), eight times in a row. The digits never arrived. The agent asked again in several
ways and closed the call as `not_reached` / `unclear`. It recorded nothing false and said nothing untrue.

The run was slow: median slowest turn 18 s, worst 20.1 s in this call. By this repo's rule (silent more than 20 s in one
turn) the failure is marked **platform**. Runs 1 and 3 of the same case passed with the same agent.
