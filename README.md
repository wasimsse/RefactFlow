# RefactFlow

A modular, agent-based static analysis and refactoring tool for Java code, inspired by SonarQube, with a modern Streamlit UI.

---

## Features

- **Java Code Metrics**: Structural, complexity, coupling, cohesion, OO, maintainability, reliability, duplication, documentation, and security metrics.
- **Modern Visualizations**: Interactive, attractive charts (bar, pie, radar, donut, line) powered by Plotly.
- **Agentic Architecture**: Modular agents for metrics, code smells, and dependencies.
- **Flexible Upload**: Analyze code from ZIP, GitHub repo, or individual files.
- **Extensible UI**: Tabs for upload, analysis, refactoring, testing, visualization, and export.
- **No LLM/API Required**: All static analysis is local and privacy-friendly.

---

## Quick Start

1. **Install requirements:**
    ```bash
    pip install -r requirements.txt
    ```

2. **Run the app:**
    ```bash
    streamlit run app.py
    ```

3. **Upload your Java project** (ZIP, GitHub, or files) and explore the analysis!

---

## Project Structure

- `app.py` — Main Streamlit app
- `modules/` — Modular backend and UI logic
    - `upload_module.py` — Upload/clone code
    - `analyze_module.py` — Metrics, charts, and analysis
    - `refactor_module.py` — Refactoring suggestions (placeholder)
    - `apply_module.py` — Apply code changes (placeholder)
    - `test_module.py` — Test/validate (placeholder)
    - `visual_module.py` — Visual reports (placeholder)
    - `export_module.py` — Export results (placeholder)
    - `sidebar.py` — Sidebar for settings

---

## Requirements

```
streamlit
streamlit-ace
plotly
javalang
```

---

## Screenshots

*(Add screenshots of the UI and charts here)*

---

## License

MIT License

---

## Acknowledgments

- Inspired by SonarQube and RefactAI ([wasimsse/RefactAI](https://github.com/wasimsse/RefactAI))
- Built with Streamlit, Plotly, and javalang

---

## Contributing

Pull requests and issues are welcome! 