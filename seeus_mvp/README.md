# SeeUs MVP (Streamlit + SQLite) — Deep Research Edition

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Enable OpenAI features
Set your OpenAI key, then use:
- **Report → Use LLM scoring (OpenAI)**
- **Report → Deep Research Mode → Generate Deep Research Brief**

macOS / Linux:
```bash
export OPENAI_API_KEY="YOUR_KEY"
streamlit run app.py
```

Windows (PowerShell):
```powershell
setx OPENAI_API_KEY "YOUR_KEY"
# restart terminal
streamlit run app.py
```

## Deep Research: what it does
Generates a **Relational Dynamics Brief** grounded only in:
- the answers you provided
- computed dimension scores
- detected contradictions (MVP checks)
- deltas over time (answer changes)

It explicitly avoids diagnosis or speculation.
Saved briefs and reports are stored in SQLite (`seeus.db`) under the `reports` table.


## PDF export
On the Report page, after generating a Deep Research Brief, use **Download PDF**.


## Growth dashboard
Use the **Growth** page in the sidebar to view timeline cards and submit monthly check-ins.
