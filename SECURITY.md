# Security and Privacy Policy

## Supported versions

Security fixes are applied to the `main` branch. There are no long-term
supported release branches at this stage.

## Reporting a vulnerability

Please **do not open a public issue** for a vulnerability or for anything that
contains device identifiers, authentication material, or personal health data.

Use GitHub's private vulnerability reporting for this repository
(**Security → Report a vulnerability**), or contact the maintainers privately.
Include:

- a short description and impact,
- affected version/commit,
- reproduction steps with **redacted** logs,
- a suggested fix if available.

We will acknowledge the report, investigate, and coordinate disclosure.

## Privacy rules for reports and pull requests

Never include any of the following in an issue, PR, discussion, capture, test
fixture, or commit:

- Bluetooth MAC addresses, BLE identity addresses, or advertising names that
  identify a specific unit,
- serial numbers, account IDs, device UDIDs, or Huawei IDs,
- pairing/bonding keys, HiChain credentials, session keys, tokens, or
  `secret_key`/`returnCodeMac` values,
- raw health records, raw PPG, sleep/SpO₂ exports, or the local SQLite database,
- packet captures from a real device unless they have been fully redacted.

Use synthetic values (for example `AA:BB:CC:DD:EE:FF`) and aggregated,
non-identifying metrics in tests and documentation.

## Out of scope

This project does not provide, and will not accept, instructions for:

- bypassing secure boot, firmware signatures, or INFO0 protections,
- extracting account-bound credentials or keys from a device or phone,
- destructive firmware modification, factory reset, or bootloader changes,
- medical diagnosis, treatment, or clinical decision-making.

The software is an independent interoperability and data-acquisition project.
It is not affiliated with Huawei and is not a medical device.
