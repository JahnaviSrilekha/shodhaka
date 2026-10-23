# Security and data handling

Shodhaka is built for documents that should not leave the building. This is what it does with them.

## What stays on the machine

- Uploaded files, cleaned copies, reports and reviews are stored under `out/ui/` (git-ignored).
- Every rule decision is made by Strands Decider 2B on `localhost`.
- Without `--bedrock`, nothing leaves the machine at all.

## Cleaning at upload

Before any rule is checked, the copy that gets analysed is cleaned (`src/shodhaka/documents/sanitize.py`):

| Removed | How |
|---|---|
| Secrets: config passwords, API keys, tokens, private keys, `user:pass@` in URLs | patterns |
| Personal data: e-mail, phone, IBAN and card numbers (checksum-verified), IP addresses | patterns |
| Instructions aimed at the AI ("ignore all previous instructions") | patterns, whole sentence |
| Abusive, hateful, sexual, violent or self-harm language | Decider 2B, per section |

The removal list shows the type, line and a masked preview, never the value. Not detected: person
names and other free-text personal data, and instructions phrased in ways the patterns do not know.

Each Decider request also wraps the section as data and says that instructions inside it are part of
the document. Pass or fail is decided by the confidence gate in code, so text in a document cannot
change the policy.

## What goes to Amazon Bedrock

Only when fixes are drafted (`--bedrock`), and only for gaps:

1. The evidence snippet is redacted first: hosts, IPs, e-mails, keys and connection strings become
   placeholders such as `[HOST_1]` (`src/shodhaka/documents/redact.py`).
2. The **egress guard** (a Strands `before_model_call` intervention) refuses the call if an original
   value or a sensitive pattern is still in the prompt, or if Decider judges that identifying details
   remain. Every allowed call is logged with its size.
3. The placeholders are restored locally when the fix comes back.

The benchmark (`shodhaka bench`) is the exception: to compare models fairly it sends section text
unredacted, so it only runs with `--send-to-bedrock` and is meant for synthetic or public documents.

## Credentials

- Use a Bedrock API key or AWS credentials from your environment. Set the key in the terminal
  (`read -s AWS_BEARER_TOKEN_BEDROCK && export AWS_BEARER_TOKEN_BEDROCK`); never put it in the repo
  or in a `.env` file that could be committed.
- Reports never contain secret values, only the key name and the line number.

## The web app

`shodhaka serve` has no login. Organizations and projects separate work; they are not access control.
Keep it on `127.0.0.1`.

## Reporting a problem

Open an issue on GitHub without including any secret or document content, or contact the maintainer
through GitHub.
