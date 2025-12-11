# Andreas Services

This repository is a small portfolio of independently deployed applications that share a single source tree for convenience. Each directory under the root represents its own deployable unit with its own tech stack, pipeline, and README:

- **`storybook/`** – AI-assisted portrait studio composed of a Flask API and a Vite/NextUI front end.
- **`humbugg/`** – Secret gift-exchange platform built with an ASP.NET Core API, React web client, AWS Cognito auth, and MongoDB.

Because the projects have separate cloud resources and release cadences, changes should normally be scoped to a single directory. Refer to the README in each folder for details on setup, technology choices, prerequisites, and deployment assumptions.

## Navigating the repo

| App | Stack highlights | Notes |
| --- | --- | --- |
| [`storybook`](storybook/README.md) | Python/Flask API with AWS Cognito + AWS S3 + Replicate, Vite/NextUI front end | Back end manages training data, model training, and image generation. |
| [`humbugg`](humbugg/README.md) | ASP.NET Core API + AWS Cognito auth + React web UI + MongoDB | Purpose-built for managing and matching members of seasonal gift-exchange groups. |

Each application directory can be cloned, tested, and deployed on its own without touching the others. When in doubt, open the app-specific README and follow the instructions there.
