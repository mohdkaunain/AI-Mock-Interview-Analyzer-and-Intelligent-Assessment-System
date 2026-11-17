# AI Mock Interview Analyzer — Window Switch Limit

## Files
- `app.py`: updated Streamlit application.
- `window_switch_component/index.html`: custom Streamlit component used to report browser-tab visibility changes.

## Setup
Keep `app.py` and the `window_switch_component` folder together:

```text
your-project/
├── app.py
├── answer_eval_model.pkl
├── questions.csv
└── window_switch_component/
    └── index.html
```

Install the app's existing dependencies and run:

```bash
streamlit run app.py
```

## Behavior
- First detected browser-tab visibility change: displays a warning.
- Second detected browser-tab visibility change: marks the interview as disqualified and stops the interview.

## Important limitation
This detects browser page visibility changes exposed by the browser. Browsers do not provide websites with a guaranteed way to detect every operating-system-level Alt+Tab or every application/window switch. It is not tamper-proof proctoring, and a visibility event can occasionally be affected by browser behavior.
