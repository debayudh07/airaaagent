# Manual scripts

Older ad-hoc scripts that call live APIs (they need real keys). They predate the `airaa` package:
`final_test.py`, `test_conversation_memory.py` and `test_dune_fix.py` import names from the old single-file
`main.py` that no longer exist, so update them to use `airaa.agent.Web3ResearchAgent` before running.
`test_dune_api_fixed.py` is standalone. The automated suite lives one level up and runs offline with `pytest`.
