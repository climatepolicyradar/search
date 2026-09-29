# test: Prefect deployment sizing

We were looking at deciding on the right size for our Prefect deployments to
ensure we get the right balanace between speed and cost.

## Results

| \_AB_SAMPLE_RATE | index    |
| ---------------- | -------- |
| 0.1              | passages |

We got the following results running some sampled tests on our passages feeder.

| variant    | task size            | flow run  | billed    | files/min | $/hr   | A/B run | full feed       | annual |
| ---------- | -------------------- | --------- | --------- | --------- | ------ | ------- | --------------- | ------ |
| batch-1    | 1024 / 4GB / 50GiB   | 31.28 min | 32.28 min | 19.3      | 0.0619 | $0.033  | 5.23 h → $0.324 | $118   |
| batch-5    | 2048 / 8GB / 50GiB   | 23.29 min | 24.44 min | 26.0      | 0.1202 | $0.049  | 3.90 h → $0.469 | $171   |
| batch-10   | 2048 / 16GB / 50GiB  | 20.37 min | 21.36 min | 29.7      | 0.1557 | $0.055  | 3.41 h → $0.531 | $194   |
| batch-25   | 4096 / 24GB / 100GiB | 26.28 min | 27.41 min | 23.0      | 0.2784 | $0.127  | 4.40 h → $1.224 | $447   |
| v1 control | 1024 / 4GB / 20GiB   | —         | —         | 19.7      | 0.0583 | —       | 5.12 h → $0.299 | $109   |
| v1 indexer | 4096 / 16GB / 50GiB  | —         | —         | —         | 0.2367 | —       | —               | —      |

## Decision

Go with `batch-10` as it only incurs a small cost increase, but significant time
gains.
