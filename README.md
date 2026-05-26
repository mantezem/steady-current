# Steady Current


## What v0.1 Includes

- Canonical topic tree with parent, prerequisite, and related-topic relationships (see `app/db/topics.yaml` and `app/db/relationships.yaml`).
- PostgreSQL source of truth with `pgvector` document embeddings.
- Semantic ingestion pipeline for official docs, architecture references, and exam resources.
- Retrieval service with topic and metadata filters.
- Adaptive planner that balances weak-topic reinforcement with prerequisite-aware progression.
- Instructor and quiz agents built with the OpenAI Agents SDK.
- Evaluation flow that stores quiz attempts and updates mastery percentages.
- Gradio UI for setup, dashboard, instructor chat, quiz, and topic tree browsing.

## Run With Docker

```bash
cp .env.example .env
# Add OPENAI_API_KEY to .env for live tutoring, quiz generation, and embeddings.
docker compose up --build
```

Open `http://localhost:7870`.

The app runs against the `postgres` service in Docker and is intended to be
started with Docker Compose.

## Database

On startup the app applies `app/db/schema.sql`, seeds the canonical topic tree, seeds official resource links, and inserts sample document chunks when no chunks exist. The ingestion command can be re-run:

```bash
docker compose exec app uv run --no-sync python -m app.ingestion.pipeline
```

The schema includes:

- `topics`
- `topic_relationships`
- `user_preferences`
- `user_mastery`
- `question_attempts`
- `resources`
- `document_chunks`

## Reset Progress

Learner progress is stored in PostgreSQL in `user_preferences`, `user_mastery`, and
`question_attempts` for the active `APP_USER_ID` (defaults to `default-user`).

To reset only that learner's progress and keep the seeded topics/resources/chunks:

```bash
docker compose exec postgres psql -U steady -d steady_current -c "DELETE FROM question_attempts WHERE user_id = 'default-user'; DELETE FROM user_mastery WHERE user_id = 'default-user'; DELETE FROM user_preferences WHERE user_id = 'default-user';"
```

If you changed `APP_USER_ID` in `.env`, replace `default-user` with that value.

To wipe everything in Postgres, including seeded content and embeddings, and rebuild
from scratch:

```bash
docker compose down -v
docker compose up --build
```

## Architecture

The app is a modulith:

```text
app/
  agents/       Instructor, quiz, evaluator, and retrieval tool wiring
  db/           PostgreSQL pool, migrations, repositories, seed data
  ingestion/    Re-runnable resource and chunk ingestion
  models/       Pydantic domain contracts
  planner/      Prerequisite-aware adaptive study planning
  prompts/      Agent instructions
  retrieval/    Embeddings, semantic chunking, pgvector search
  ui/           Gradio interface
  utils/        Configuration and startup helpers
```

## Notes

Without `OPENAI_API_KEY`, the UI still opens, seeds data, shows the dashboard/topic tree, and returns deterministic placeholder instructor/quiz responses. Add the key to enable live Agents SDK calls and OpenAI embeddings.
