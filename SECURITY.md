# Security Policy

any_to_any.py follows a rolling release model.<br>
Security fixes are applied only to the latest commit on the `main` branch.

| Version                        | Supported |
| ------------------------------ | --------- |
| Latest commit on `main`        | Yes       |
| Tagged releases / past commits | No        |

If you are using a pinned version (a specific commit or release),
you are responsible for updating to a newer version that includes
security fixes.

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

- **Do not open a public issue**
- Use [GitHub's private vulnerability reporting](https://github.com/MK2112/any_to_any.py/security/advisories/new)
- If this option is unavailable, please contact: `mk2112 [at] protonmail [dot] com`

Please include:
- A brief and clear description of the issue
- An equally brief and clear description of the system on which the issue occurred
- Steps to reproduce
- Potential impact
- Whether you want to be given credit or remain anonymous

**We aim to respond within a few days. Response times may vary.**

We will acknowledge receipt and communicate an `accept` or `decline`

On `accept`:
- We will investigate and validate the issue
- Coordinate a fix and disclosure where appropriate
- Credit will be given unless you want to remain anonymous

On `decline`:
- We will provide a brief explanation of why the report is not considered a valid vulnerability
- No further action will be taken *unless new information is provided*

## Security Considerations

This project processes *user-supplied files*. To do so, it relies on external tools (e.g., FFmpeg).

### Untrusted File Input

- Treat all input files as **untrusted**
- Malformed media files may exploit underlying libraries (e.g., FFmpeg vulnerabilities)
- Processing untrusted files is inherently risky. Consider isolating execution
(e.g., containers, sandboxing) when handling files from unknown sources.
- Always sanitize file paths and arguments if modifying or extending the code

### File System Access

- Be cautious with output paths and overwrite behavior
- Avoid running the tool with elevated privileges

### Web UI

- The web interface is not hardened for public exposure
- Do not expose it to the internet without authentication and proper isolation
- Prefer binding to `localhost` (this is the default behavior)

### Resource Usage

- Large or malformed files may cause excessive CPU/memory usage
- Consider applying limits (e.g., cgroups, ulimits, container quotas, configuring the number of workers)

## Best Practices

- Run the tool in a **controlled environment** (e.g., container, sandbox)
- Keep dependencies (like FFmpeg) **up to date**
  - FFmpeg is not included with the pre-packaged binaries so that updating it becomes easier for the user
- Avoid processing sensitive files alongside untrusted ones
- Do not expose the service publicly without proper precautions

## Scope

This policy applies only to vulnerabilities in this repository's code.<br>
Issues in third-party dependencies (e.g., FFmpeg, Python libraries) should be reported to their respective maintainers.

## Acknowledgements

Responsible disclosure helps improve the security of any_to_any.py and the wider ecosystem.<br>
**Thank you for your efforts.**
