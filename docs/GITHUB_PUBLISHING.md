# GitHub publishing and collaboration

Destination supplied by the group head: [mehranwazir/ai4015-subsurface-agent](https://github.com/mehranwazir/ai4015-subsurface-agent). The repository was checked as **public, empty, with push permission** before the first push. Git Credential Manager is installed; authentication uses the existing account flow, not pasted passwords/tokens.

## First publication

The project already has local history. Preserve it when pushing `main`; do not reinitialize or upload a ZIP that discards history. Verify the remote, inspect existing refs, commit the reviewed pack, then push without force. Confirm GitHub's `main` SHA equals local `HEAD` and that README/source/results render.

Record the actual outcome in the local handoff after publication. Creating an empty destination is not evidence that code was pushed, and configuring CI is not evidence that it passed.

## What partners should do next

The owner can add collaborators in repository settings; each member should use their own GitHub account and local Git identity. Clone this repository, create a branch for a real task, commit the work and open a pull request for group review. Give each member access needed for their role. A public repository lets the supervisor read the code; no supervisor GitHub handle is currently supplied for any additional access arrangement.

Do not fabricate member authorship on existing commits. The proposed responsibility plan is in [the Stage 7 team checklist](stage7/06_TEAM_AND_SUBMISSION.md).

## Included and recreated files

Tracked: source, tests, dependency configuration, documentation, actual metrics, selected observable traces and derived figures/predictions. Raw/processed datasets, local model binary, `.venv`, run scratch directories and `.env` are ignored and recreated by documented commands. Preserve source/data attribution in `NOTICE.md`.

The exposed chat credential should be rotated and replaced only in local `.env`. Never add a password, API key, token or credential-bearing URL to the repository. The offline CI does not need the Gemini key; do not add an API secret merely to run the software tests.

## Submission link and official instructions

Use the browser repository URL, without `.git`, as the Classroom link. Confirm source/results are readable while signed out. The owner should check the Actions tab after pushing and address actual failures; a queued run is not a pass.

Official references: [GitHub's local-code import instructions](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github), [creating a repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository). For an existing local repository, GitHub recommends an empty destination without initialized README/license/gitignore files.
