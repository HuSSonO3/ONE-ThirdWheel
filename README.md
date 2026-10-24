# Project Name CHANGE

> A one-sentence description of what your project does and who it is for.

---

## Team Information 

| Field                  | Details                                     |
| ---------------------- | ------------------------------------------- |
| **Team Name**          | ONE ThirdWheel                              |
| **Team Domain**        | Domain 2                                    |
| **SDG Track (1–17)**   | CHANGE SDG 11 — Sustainable Cities and Communities |
| **Team Leader**        | Hussein Al-manifi                           |
| **University**         | University of Malaya                        |
| **Number of Members**  | 3                                           |

## Links CHANGE

| Resource          | Link                                           |
| ----------------- | ---------------------------------------------- |
| GitHub Repository | https://github.com/HuSSonO3/ONE-ThirdWheel     |
| Replit Project    |  |
| Live Demo         |                 |
| RunPod Endpoint   |      |
| Slide Deck        |                    |
| Demo Video        |              |

---

## Overview

### Problem CHANGE

Describe the real-world problem you are solving in 2–4 sentences. Who is affected, and why does it matter?

### Solution

Explain how your project uses AI to solve the problem and what makes it valuable.

### Key Features  CHANGE

- **Feature 1** — Short description.
- **Feature 2** — Short description.
- **Feature 3** — Short description.

### Tech Stack CHANGE

| Layer         | Technology                   |
| ------------- | ---------------------------- |
| Frontend      |              |
| Backend       |  |
| Database      |       |
| AI / Compute  |                 |
| Hosting / Dev |                        |

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
│   ├── scripts/         # shared · seed.py, gen_client.sh
│   ├── tests/
│   └── pyproject.toml   # one Python workspace for api + ai
├── submission/          # Required submission documents
├── .github/workflows/   # CI: lint + tests for all tiers, client diff check
├── docker-compose.yml   # postgres, minio, api, web
├── plan.md              # Build plan
├── LICENSE
└── README.md
```

Local setup: `docker compose up` (web on :5173, API on :8000, `GET /health`).

### Architecture

EX CHANGE
```
User ──► Replit (App / API) ──► RunPod Endpoint (GPU model)
                │
                └──► Response returned to user
```

---

## How to Run CHANGE

### Option 1 — Run on Replit

1. Open the [Replit Project](), or import this repository via **Create Repl → Import from GitHub**.
2. Open the **Secrets** tab (🔒) and add the variables listed in `.env.example`:
   - `RUNPOD_API_KEY`
   - `RUNPOD_ENDPOINT_ID`
3. Click **Run**. Replit uses the `.replit` file to start `python src/main.py`.

### Option 2 — Run Locally

```bash
# 1. Clone the repository
git clone https://github.com/HuSSonO3/ONE-ThirdWheel
cd your-project

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env            # then fill in your values

# 5. Run the app
python src/main.py
```

### Run Tests CHANGE

```bash
python -m unittest discover tests
```

---

## How We Use Replit CHANGE

Describe how your team used Replit. For example:

- **Development:** Collaborative coding in a shared Repl using Multiplayer.
- **Hosting:** The app is deployed with Replit Deployments at the Live Demo link above.
- **Secrets:** API keys are stored in Replit Secrets, never in the code.

📄 Proof of use: [`submission/SDC2026_ONEThirdWheel_Replit_POU.pdf`](submission/SDC2026_ONEThirdWheel_Replit_POU.pdf)

## How We Use RunPod *(Required)* CHANGE

Describe how your team used RunPod. For example:

- **Workload:** Model inference (e.g. text generation, image processing) runs on a RunPod GPU.
- **Setup:** `runpod/handler.py` is deployed as a **RunPod Serverless Endpoint**.
- **Integration:** The Replit app sends requests to the endpoint using `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID`.

Example request:

```bash
curl -X POST https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"prompt": "Hello"}}'
```

📄 Proof of use: [`submission/SDC2026_ONEThirdWheel_Runpod_POU.pdf`](submission/SDC2026_ONEThirdWheel_Runpod_POU.pdf)

---

## Challenges & Learnings CHANGE

- What challenges did you face, and how did you overcome them?
- What did your team learn?

## Future Improvements CHANGE

- [ ] Improvement 1
- [ ] Improvement 2

## Team

| Name        | Role                | GitHub                                   |
| ----------- | ------------------- | ---------------------------------------- |
| Member Name | Team Lead /  | [@HuSSonO3](https://github.com/HuSSonO3) |
| Member Name |             | [@aeiouhmed](https://github.com/aeiouhmed) |
| Member Name |         | [@Alyssaatmasava](https://github.com/Alyssaatmasava) |

---

## Submission Checklist

- [ ] Team name, domain (Domain 1 / Domain 2) and SDG track filled in
- [ ] Slide deck link added
- [ ] Demo video link added
- [ ] Replit used, with proof of use in `submission/`
- [ ] RunPod used, with proof of use in `submission/`
- [ ] Preliminary submission completed (`SDC2026_TeamName_Preliminary.pdf`)
- [ ] Technology declaration completed (`SDC2026_TeamName_TechDeclaration.pdf`)
- [ ] Submission files renamed with your team name (replace `TeamName`)
- [ ] "How to Run" steps verified
- [ ] No API keys or secrets committed to the repository

## License

This project is licensed under the [Apache License 2.0](LICENSE).

