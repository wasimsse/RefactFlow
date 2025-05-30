import streamlit as st
from modules.upload_module import render_upload_tab
from modules.analyze_module import render_analyze_tab
from modules.refactor_module import render_refactor_tab
from modules.apply_module import render_apply_tab
from modules.test_module import render_test_tab
from modules.visual_module import render_visual_tab
from modules.export_module import render_export_tab
from modules.sidebar import render_sidebar

st.set_page_config(page_title="RefactFlow: Modular AI Refactoring", layout="wide")

# Sidebar for persistent settings
render_sidebar()

st.title("RefactFlow: Modular AI-Powered Refactoring System")

# Tabs for each pipeline step
tabs = st.tabs([
    "📂 Upload Code",
    "📊 Analyze & Smells",
    "🧩 Refactoring Suggestions",
    "🛠 Apply Changes",
    "🧪 Test & Validate",
    "📈 Visual Reports",
    "📤 Export Results"
])

with tabs[0]:
    render_upload_tab()
with tabs[1]:
    render_analyze_tab()
with tabs[2]:
    render_refactor_tab()
with tabs[3]:
    render_apply_tab()
with tabs[4]:
    render_test_tab()
with tabs[5]:
    render_visual_tab()
with tabs[6]:
    render_export_tab() 