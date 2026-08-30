# Acceptance expectations

The plan must identify the read-then-write race across api.py and store.py, propose one atomic
store operation rather than an in-process lock, preserve the boolean caller contract, and specify a
concurrent test that proves no more than the configured limit is accepted.
