# Publishing updates

Repository: https://github.com/jayburkard/ha-solark-local

HACS installs this integration from this public repository as a custom Integration
repository. Acceptance into the HACS default catalog is a separate process.

For a new version:

1. Update `custom_components/solark_local/manifest.json` and `CHANGELOG.md`.
2. Run the automated tests and check the Validate workflow on GitHub.
3. Commit and push the tested changes to `main`.
4. Optionally publish a GitHub release with a matching tag, for example `v0.1.0`.
   HACS can also install directly from the default branch without a release.

Keep the repository description and topics populated; suggested topics are
`home-assistant`, `hacs`, `sol-ark`, and `solar`.

Do not commit credentials or unsanitized hardware captures and test results.
The integration requires no cloud or MQTT credentials.
