# Technical appendix: Jev and general LLMs

Separate from the main deck; built by `scripts/llm_appendix/` and never read by the hub or the deck builders.

| File | What it is |
|---|---|
| [Jev-vs-LLMs_technical-appendix.pptx](Jev-vs-LLMs_technical-appendix.pptx) | The appendix deck, with speaker notes and source links |
| [Jev-vs-LLMs_technical-appendix.pdf](Jev-vs-LLMs_technical-appendix.pdf) | The same as a PDF |
| [data/scorecard.csv](data/scorecard.csv) | One row per backend: accuracy, gate, confidence, latency, cost |
| [data/per_incident.csv](data/per_incident.csv) | Every call: backend, set, run, incident, answer, gate outcome, latency, cost |
| [previews/](previews) | One PNG per slide |

Backends: Jev 1.13 (TypeSafe API), Claude Sonnet 5.5, GPT-6.1 Sol, Gemini 3.8 Flash, GPT-6 Luna, Qwen3.8 Flash. Sets: base (three runs), shuffled, injected, harder;
56 synthetic incidents each. Raw logs: `work/results/llm_appendix/`.

Rebuild without API calls: `./jev/bin/python scripts/llm_appendix/analyze.py && ./jev/bin/python scripts/llm_appendix/build_deck.py`.
Re-run the measurements (paid): `./jev/bin/python scripts/llm_appendix/run.py --max-usd 20`.
