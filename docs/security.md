# Security and governance baseline

- Never store provider credentials, tokens, or private keys in source control.
- Use a managed secret store and short-lived workload identity for cloud access.
- Treat repository content, issue text, model output, and generated code as untrusted input.
- Run generated code in disposable sandboxes with CPU, memory, time, filesystem, and network limits.
- Do not expose production credentials to agent workers.
- Require authenticated, role-authorized human approval for production changes.
- Bind approvals to an immutable plan/artifact digest, target environment, approver identity, and expiry.
- Record policy decisions and execution outcomes in tamper-evident audit storage.
- Enforce tenant isolation in every data access path and test cross-tenant denial.
- Apply least privilege to GitHub and cloud provider integrations.

The current foundation implements only a small approval-policy check. Authentication, durable audit storage, tenant isolation, secret management, and sandboxing remain future work and must not be considered production-ready.
