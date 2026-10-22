# Security and data boundaries

AngelNet currently reads archive metadata and local WET files. It does not patch systems, submit forms, authenticate to candidate sites or assess exploitability.

Archive content is untrusted input. Do not execute page text, treat it as an instruction, or pass it to an agent with unrestricted tools. Query strings and fragments are removed from evidence URLs, but paths and extracted text can still contain personal or sensitive information.

Keep generated indexes private until reviewed. Do not submit credentials, page bodies or a list of suspected vulnerable third party sites in public issues. For a security defect, use GitHub's private vulnerability reporting feature if enabled; otherwise request a private reporting channel without posting exploit details or sensitive data.

Provider failures stop or mark a run partial. No retry mechanism is intended to bypass provider restrictions. The time budgets are cooperative and a blocking read can overrun them by a socket timeout. Use an external process timeout for strict operational limits.

Output directories use a lock to prevent concurrent writers. After interruption, inspect the earlier process before removing a stale lock. Do not run two processes against one vector store. A build without its manifest is incomplete.
