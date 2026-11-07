# Security & Privileged Operations Policy

- **Bubblewrap Sandbox Policy**: All agent shell executions and commands must execute strictly within the Bubblewrap (`bwrap`) sandbox.
- **Privilege Escalation Control**: Commands requiring `sudo`, `pkexec`, or elevated root privileges are strictly blocked from host-level bypass. Any privileged execution must be requested through the structured approval queue and authorized by the user.
- **Zero Plaintext Secrets**: No plaintext passwords or credentials may be stored or logged in project files or environment defaults.
- **Antigravity CLI Boundaries**: Strict permission mode is enforced by default. Scoped bypass flags may only be enabled if explicitly configured in runtime settings for verified sandboxed sub-tasks.

