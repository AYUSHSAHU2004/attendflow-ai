# LLM model and licence

## Model in use

| | |
|---|---|
| Model | `openai/gpt-oss-120b` (open-weight, mixture-of-experts, ~120B parameters) |
| Provider | Groq, OpenAI-compatible API (`https://api.groq.com/openai/v1`) |
| Licence | **Apache License 2.0** |
| Licence text | https://www.apache.org/licenses/LICENSE-2.0 |
| Model card | https://huggingface.co/openai/gpt-oss-120b |
| Chosen on | 2026-11-19 (Phase 0) |

### What the licence means for us (plain language)

- Apache 2.0 is a permissive open-source licence: we may use the model commercially,
  modify it and redistribute it.
- If we redistribute the weights, we must include the licence text and keep notices.
  We do not redistribute weights; we call a hosted API.
- There is no attribution clause like Llama's "Built with Llama".
- The model card also points to the publisher's usage policy (no harmful use). Our use
  (explaining timecard exceptions, drafting messages) is well within it.
- Use through Groq is also covered by Groq's own terms of service.

## Why not Llama 3.3 70B (the original plan)

On 2026-11-19 Groq's `/models` endpoint no longer listed `llama-3.3-70b-versatile`, and no
Llama chat model was on offer. We tested the two open-weight chat models it did list:

| Model | Licence | Result |
|---|---|---|
| `openai/gpt-oss-120b` | Apache 2.0 | Correct reply, ~2.5 s. **Chosen**: largest, strong tool calling and JSON. |
| `qwen/qwen3.8-27b` | not checked (not chosen) | Correct reply, ~2.3 s. Smaller model. |

## Switching models

Any OpenAI-compatible endpoint works by editing `.env` only:

```
LLM_BASE_URL=http://localhost:11434/v1   # e.g. Ollama, fully local
LLM_MODEL=gpt-oss:120b
LLM_API_KEY=ollama
```

Run `uv run attendflow-llm-test --list-models` to check the provider still serves the
configured model. If you switch, update this file with the new licence.
