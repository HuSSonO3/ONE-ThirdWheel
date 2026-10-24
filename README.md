# TeamSync

> An AI-powered team chat that turns everyday work discussions into suggested tasks, so colleagues and managers always see up-to-date progress.

---

## Team Information 

| Field                  | Details                                     |
| ---------------------- | ------------------------------------------- |
| **Team Name**          | ONE ThirdWheel                              |
| **Team Domain**        | Domain 2                                    |
| **SDG Track (1–17)**   | SDG 8: Decent Work and Economic Growth      |
| **Team Leader**        | Hussein Al-Manifi                           |
| **University**         | University of Malaya                        |
| **Number of Members**  | 3                                           |

## Links

| Resource          | Link                                           |
| ----------------- | ---------------------------------------------- |
| GitHub Repository | https://github.com/HuSSonO3/ONE-ThirdWheel     |
| Live Demo         |                 |
| RunPod Endpoint   |  https://api.runpod.ai/v2/ezymgds6tvhvu9/    |
| Slide Deck        | [`submission/SDC2026_ONEThirdWheel_SlideDeck.pdf`](submission/SDC2026_ONEThirdWheel_SlideDeck.pdf) |
| Demo Video        |              |

---

## Overview

### Problem

Work gets discussed in group chats, private messages, and meetings, but keeping task records updated requires extra manual effort. Updates can become incomplete or outdated, leaving colleagues and managers repeatedly asking what is happening.

### Solution

TeamSync is an AI-powered internal communication and task-tracking tool that turns everyday work discussions into suggested tasks and progress updates. Users review and confirm changes, while group trackers and a consolidated team dashboard give authorized colleagues and managers visibility into ongoing work.


### Key Features

Disclamer: Not all features are implemented in the prototype as we are focused on making it run the main feature.

- **Visible Group Bot** — A bot task suggestions that appear when a task or a job can be recorded.
- **Private-Chat Capture** — It allows to turn off and on private chats and group chats reading to produce suggestions.
- **Group Project Tracker** — It tracks the tasks and jobs for all the members of any group.
- **Private-Chat Task Panel** — It tracks the tasks and jobs that were approved within private chats.
- **Consolidated Team Dashboard** — It allows teams to view and track their tasks and jobs throught out their groups.
- **Cross-Functional Coordination** — It helps multiple departments to work together in different groups and track all tasks and jobs properly.
- **Sharing and Delegation** — Tasks are assigned to colleagues under access rules, so managers can assign work down their reporting line and see what their team is doing.
- **Activity History** — Every task change is recorded with who made it and when.


### Tech Stack

| Layer         | Technology                   |
| ------------- | ---------------------------- |
| Frontend      |  TypeScript, React           |
| Backend       |  Python, FastAPI             |
| Database      |  PostgreSQL                  |
| AI / Compute  |  RunPod Serverless (vLLM, Qwen3-8B) |
| Hosting / Dev |  Replit, Docker Compose      |

---

## Project Structure

All code lives in `src/` (layout from `plan.md` §2).

```
.
├── src/
│   ├── contracts/       # shared · OpenAPI spec, WS events, events row, Tool interface
│   ├── migrations/      # shared · Alembic migrations (the schema)
│   ├── fixtures/        # shared · seed data used by all three tiers
│   ├── web/             # FE · React + TypeScript (Vite); web/src/api/ is generated
│   ├── api/             # BE · FastAPI: models, services, routers, access rules
│   ├── ai/              # AI · worker, tools, dispatcher
│   ├── scripts/         # shared · build_fixtures.py, seed.py, gen_client.sh
│   ├── tests/
│   ├── docker-compose.yml  # postgres, s3, api, web
│   ├── feature_spec.md     # Feature specification
│   ├── plan.md             # Build plan
│   └── pyproject.toml   # one Python workspace for api + ai
├── submission/          # Required submission documents
├── .github/workflows/   # CI: lint + tests for all tiers, client diff check
├── LICENSE
└── README.md
```

### Local setup

```bash
cd src
docker compose up --build            # postgres, minio, api (runs migrations), web
docker compose exec api python scripts/seed.py --reset   # load the fixtures
```

Web on http://localhost:5173, API on http://localhost:8000 (`GET /health`). Log in as any fixture
user, e.g. `grace.liu@example.com` (admin) / `password123`. If port 5432 is taken on the host, set
`POSTGRES_PORT=55432`.

Contracts live in `src/contracts/` (`openapi.yaml`, `ws-events.md`, `events-row.md`,
`tool-interface.md`, and `DECISIONS.md` for where they refine the feature spec). After editing
`openapi.yaml`, run `src/scripts/gen_client.sh`; after editing `scripts/build_fixtures.py`, run it.

### Architecture

TeamSync runs as a single deployment with four layers (system block diagram: Appendix 8.1 of
[`submission/SDC2026_ONEThirdWheel_Preliminary.pdf`](submission/SDC2026_ONEThirdWheel_Preliminary.pdf)):

1. **Users** — employees and managers use TeamSync in a web browser.
2. **Replit** — a React + TypeScript frontend talks to a FastAPI backend over REST and WebSockets. The backend is the only component that reads or writes data; it enforces permissions and runs the approval workflow.
3. **PostgreSQL** — stores users, conversations, messages, tasks, AI proposals and an audit log. Each task is one record shown in every authorised view.
4. **RunPod** — an open-source model (Qwen3-8B) behind a serverless endpoint returns structured task proposals. The backend validates each one; it becomes a task only after a person confirms it, and the AI never writes to the database directly.

---

## How to Run

### Option 1 — Run on Replit

1. Open the [Replit Project](), or import this repository via **Create Repl → Import from GitHub**.
2. Open the **Secrets** tab (🔒) and add the variables listed in `.env.example`:
   - `RUNPOD_API_KEY`
   - `RUNPOD_ENDPOINT_ID`
   - `AI_MODEL`
   - `ALLOWED_ORIGINS` (the public URL of your Replit app)
3. Create a **PostgreSQL** database in Replit; this sets `DATABASE_URL` automatically.
4. Click **Run**. Replit uses the `.replit` file to build the frontend, run the migrations, load the demo data into an empty database, and start the app on one port.

For a public deployment, publish as a **Reserved VM** (not Autoscale): the AI worker and the WebSocket connections live in the API process.

### Option 2 — Run Locally

Requires [Docker](https://www.docker.com/).

```bash
# 1. Clone the repository
git clone https://github.com/HuSSonO3/ONE-ThirdWheel
cd ONE-ThirdWheel

# 2. Configure environment variables
cp .env.example .env            # then fill in your values

# 3. Start PostgreSQL, the API (runs migrations) and the web app
cd src
docker compose up --build

# 4. Load the demo data (in a second terminal, from src/)
docker compose exec api python scripts/seed.py --reset
```

Open http://localhost:5173 and log in as `alice.moreau@example.com` / `password123`. Every demo user shares that password.

The AI reads a conversation after it has been quiet for 5 seconds. Post a clear request such as "Bob Tan, please fix the signup button bug by tomorrow 8am" in a channel with TeamSync on, and a suggestion appears for you to accept, modify or reject.

### Run Tests

```bash
cd src
uv sync
uv run pytest
```

Some tests need the PostgreSQL container from Option 2 to be running; they are skipped otherwise.

---

## How We Use Replit

- **Hosting:** The app runs as a single service on a Replit Reserved VM deployment: FastAPI serves the API, the WebSocket and the built React frontend from one port.
- **Database:** PostgreSQL provided by Replit, configured through `DATABASE_URL`.
- **Secrets:** The RunPod key, endpoint ID and model name are stored in Replit Secrets, never in the code.
- **Configuration:** The `.replit` file and the scripts in `scripts/` build the frontend, run the migrations and start the app.

📄 Proof of use: [`submission/SDC2026_ONEThirdWheel_Replit_POU.pdf`](submission/SDC2026_ONEThirdWheel_Replit_POU.pdf)

## How We Use RunPod *(Required)*

- **Workload:** The AI assistant reads new chat messages and chooses a tool (for example `propose_task`) using Qwen3-8B running on a RunPod GPU.
- **Setup:** A **RunPod Serverless Endpoint** running vLLM with native tool calling, exposing an OpenAI-compatible API.
- **Integration:** The API's AI worker (`src/ai/`) sends requests to the endpoint using `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID` and `AI_MODEL`. Proposals are never applied automatically; a person accepts, modifies or rejects each one.

Example request:

```bash
curl -X POST https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/openai/v1/chat/completions   -H "Authorization: Bearer $RUNPOD_API_KEY"   -H "Content-Type: application/json"   -d '{"model": "'"$AI_MODEL"'", "messages": [{"role": "user", "content": "Hello"}]}'
```

📄 Proof of use: [`submission/SDC2026_ONEThirdWheel_Runpod_POU.pdf`](submission/SDC2026_ONEThirdWheel_Runpod_POU.pdf)

---

## Challenges & Learnings

- What challenges did you face, and how did you overcome them?
The idea is quite big to implement espically with the amount of details that we needed to be careful about. We simplified it by chuncking the sections that we have to work on properly so it doesn't feel as overwhelming.
- What did your team learn? Of course we learned how to use new technologies such as Replit and RunPod. But we also learned more about how create a decently designed chat system as it has alot of things to consider regarding scale and feasability.

## Future Improvements

- As of now it should detect the intentions of tasks only, in the future it should do more work "Claims, Approvals, Leaves, Calenders"

## Team

| Name        | Role                 | GitHub                                   |
| ----------- | -------------------  | ---------------------------------------- |
| Hussein Al-Manifi | Team Lead / Backend  | [@HuSSonO3](https://github.com/HuSSonO3) |
| Ahmed Ibrahim | AI / Idea Lead       | [@aeiouhmed](https://github.com/aeiouhmed) |
| Alyssa Atmasava | Frontend / Documenter| [@Alyssaatmasava](https://github.com/Alyssaatmasava) |

---

## Submission Checklist

- [x] Team name, domain (Domain 1 / Domain 2) and SDG track filled in
- [x] Slide deck link added
- [ ] Demo video link added
- [x] Replit used, with proof of use in `submission/`
- [ ] RunPod used, with proof of use in `submission/`
- [x] Preliminary submission completed (`SDC2026_ONEThirdWheel_Preliminary.pdf`)
- [ ] Technology declaration completed (`SDC2026_TeamName_TechDeclaration.pdf`)
- [ ] Submission files renamed with your team name (replace `TeamName`)
- [ ] "How to Run" steps verified
- [x] No API keys or secrets committed to the repository

## License

This project is licensed under the [Apache License 2.0](LICENSE).

