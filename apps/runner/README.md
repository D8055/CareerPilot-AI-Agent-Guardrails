# apps/runner — local agent runner (Phase 1)

Leases `intelligence_jobs` from the API, runs the LangGraph quality-pass
graph (retrieve → tailor → adversarial review, max 2 loops), and posts
results back. LLM access is the **Claude Agent SDK over the owner's Claude
Code subscription login** — no API key exists or is accepted. The API's
honesty guard re-validates everything on completion; a refuted or failed
pass leaves the deterministic result live.

**Gated by blocker B6:** not auto-started anywhere. Once Dhiren nods that
the runner may draw on his Max plan:

```powershell
pip install -r apps/runner/requirements.txt
python apps/runner/runner.py          # loop (Ctrl+C to stop)
python apps/runner/runner.py --once   # single poll, for testing
```

Rendering (Word COM) joins the runner when the private master resume docx is
wired in via env — deferred, tracked in the spec.
