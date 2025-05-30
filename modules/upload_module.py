import streamlit as st
import os
import io
import zipfile
import tempfile
import shutil
import subprocess
from collections import Counter

SUPPORTED_EXTS = [".py", ".java", ".js", ".cpp", ".c", ".ts", ".go", ".rb", ".php", ".cs"]
LANG_MAP = {
    ".py": "Python", ".java": "Java", ".js": "JavaScript", ".cpp": "C++", ".c": "C", ".ts": "TypeScript", ".go": "Go", ".rb": "Ruby", ".php": "PHP", ".cs": "C#"
}
LANG_ICON = {
    "Python": "🐍", "Java": "☕", "JavaScript": "🟨", "C++": "💠", "C": "🔵", "TypeScript": "🔷", "Go": "🐹", "Ruby": "💎", "PHP": "🐘", "C#": "#️⃣"
}

BADGE_COLORS = ["#e0f7fa", "#ffe0b2", "#e1bee7", "#c8e6c9", "#ffccbc", "#f8bbd0", "#d7ccc8", "#b3e5fc"]

def detect_language(filename):
    ext = os.path.splitext(filename)[1]
    return LANG_MAP.get(ext, ext.lstrip("."))

def count_lines(file_bytes):
    try:
        return len(file_bytes.decode(errors="ignore").splitlines())
    except Exception:
        return 0

def badge(text, color="#e0e0e0"):
    return f'<span style="background-color:{color};border-radius:8px;padding:2px 8px;margin-right:4px;font-size:0.9em;">{text}</span>'

def clone_github_repo(repo_url, method, token=None):
    tmp_dir = tempfile.mkdtemp(prefix="refactflow_repo_")
    try:
        if method == "HTTPS":
            if token:
                url_parts = repo_url.split("://")
                if len(url_parts) == 2:
                    repo_url = f"{url_parts[0]}://{token}@{url_parts[1]}"
            cmd = ["git", "clone", "--depth", "1", repo_url, tmp_dir]
        elif method == "SSH":
            cmd = ["git", "clone", "--depth", "1", repo_url, tmp_dir]
        elif method == "GitHub CLI":
            cmd = ["gh", "repo", "clone", repo_url, tmp_dir]
        else:
            raise ValueError("Unknown clone method")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        return tmp_dir, None
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None, str(e)

def scan_repo_files(repo_dir):
    files = []
    for root, _, filenames in os.walk(repo_dir):
        for fname in filenames:
            ext = os.path.splitext(fname)[1]
            if ext in SUPPORTED_EXTS:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "rb") as f:
                        content = f.read()
                    lines = len(content.decode(errors="ignore").splitlines())
                    rel_path = os.path.relpath(fpath, repo_dir)
                    files.append({
                        "name": rel_path,
                        "size": len(content),
                        "lines": lines,
                        "language": LANG_MAP.get(ext, ext.lstrip(".")),
                    })
                except Exception:
                    continue
    return files

def render_upload_tab():
    st.header("📂 Upload Your Codebase")
    with st.container():
        st.markdown("### 1. Choose Upload Method")
        method = st.radio(
            "",
            ["📦 ZIP Upload", "🐙 GitHub Repository", "📄 Upload Individual Files"],
            index=0,
            horizontal=True,
            key="upload_method"
        )
        st.caption(f"Current upload method: {method}")
    st.session_state.setdefault("uploaded_files", [])
    st.session_state.setdefault("upload_summary", {})
    st.session_state.setdefault("github_clone_status", "idle")
    st.markdown("---")

    if method.startswith("📦"):
        with st.container():
            st.markdown("#### 📦 ZIP Upload")
            uploaded_zip = st.file_uploader("Upload a ZIP file:", type=["zip"], key="zip_upload")
            if uploaded_zip:
                with st.spinner("Extracting ZIP..."):
                    try:
                        with zipfile.ZipFile(uploaded_zip) as z:
                            file_list = [f for f in z.namelist() if not f.endswith("/")]
                            files = []
                            for fname in file_list:
                                if any(fname.endswith(ext) for ext in SUPPORTED_EXTS):
                                    with z.open(fname) as f:
                                        content = f.read()
                                        files.append({
                                            "name": fname,
                                            "size": len(content),
                                            "lines": count_lines(content),
                                            "language": detect_language(fname),
                                            "content": content  # Store raw bytes for in-memory access
                                        })
                            st.session_state["uploaded_files"] = files
                            st.toast(f"Extracted {len(files)} source files from ZIP.", icon="✅")
                    except Exception as e:
                        st.error(f"Failed to extract ZIP: {e}")
            else:
                st.info("Please upload a ZIP file to begin.")

    elif method.startswith("🐙"):
        with st.container():
            st.markdown("#### 🐙 GitHub Repository")
            repo_url = st.text_input("GitHub Repository URL", key="github_url")
            token = st.text_input("Personal Access Token (optional, for private repos)", type="password", key="github_token")
            clone_method = st.selectbox("Clone Method", ["HTTPS", "SSH", "GitHub CLI"], key="clone_method")
            clone_col, _ = st.columns([1, 3])
            with clone_col:
                if st.button("Clone Repo", key="clone_btn"):
                    if repo_url:
                        st.session_state["github_clone_status"] = "cloning"
                        with st.spinner("Cloning repository..."):
                            repo_dir, error = clone_github_repo(repo_url, clone_method, token if clone_method == "HTTPS" else None)
                            if error:
                                st.session_state["github_clone_status"] = "error"
                                st.error(f"Clone failed: {error}")
                            else:
                                files = scan_repo_files(repo_dir)
                                st.session_state["uploaded_files"] = files
                                st.session_state["repo_dir"] = repo_dir
                                st.session_state["github_clone_status"] = "done"
                                st.toast("Repository cloned successfully.", icon="✅")
                    else:
                        st.warning("Please enter a GitHub repository URL.")
            if st.session_state["github_clone_status"] == "cloning":
                st.info("Cloning in progress...")
            elif st.session_state["github_clone_status"] == "done":
                st.success("Clone complete.")
            elif st.session_state["github_clone_status"] == "error":
                st.error("Clone failed. Please check the details and try again.")

    elif method.startswith("📄"):
        with st.container():
            st.markdown("#### 📄 Upload Individual Source Files")
            uploaded_files = st.file_uploader(
                "Select one or more source files:",
                type=[ext.lstrip(".") for ext in SUPPORTED_EXTS],
                accept_multiple_files=True,
                key="multi_file_upload"
            )
            files = []
            if uploaded_files:
                with st.spinner("Processing files..."):
                    for f in uploaded_files:
                        content = f.read()
                        files.append({
                            "name": f.name,
                            "size": len(content),
                            "lines": count_lines(content),
                            "language": detect_language(f.name),
                            "content": content  # Store raw bytes for in-memory access
                        })
                    st.session_state["uploaded_files"] = files
                    st.toast(f"Uploaded {len(files)} files.", icon="✅")

    # --- Summary Panel ---
    files = st.session_state.get("uploaded_files", [])
    st.markdown("---")
    with st.container():
        st.markdown("### 2. Upload Summary")
        if files:
            total_files = len(files)
            total_lines = sum(f["lines"] for f in files)
            lang_counter = Counter(f["language"] for f in files)
            main_langs = ", ".join(f"{LANG_ICON.get(lang, '')} {lang} ({count})" for lang, count in lang_counter.most_common())
            col1, col2, col3 = st.columns([1, 2, 2])
            with col1:
                st.markdown(f"<div style='font-size:2em;font-weight:bold;'>{total_files}</div>", unsafe_allow_html=True)
                st.caption("Files")
            with col2:
                st.markdown(f"<div style='font-size:1.2em;'>{main_langs}</div>", unsafe_allow_html=True)
                st.caption("Languages")
            with col3:
                st.markdown(f"<div style='font-size:2em;font-weight:bold;'>{total_lines}</div>", unsafe_allow_html=True)
                st.caption("Total Lines of Code")
            st.markdown("#### File Details")
            def color_for_idx(idx):
                return BADGE_COLORS[idx % len(BADGE_COLORS)]
            file_rows = []
            for idx, f in enumerate(files):
                file_rows.append({
                    "Filename": f["name"],
                    "Size (bytes)": f["size"],
                    "Lines": f["lines"],
                    "Language": f["language"]
                })
            st.write(
                f"<div style='background:#f8f9fa;border-radius:8px;padding:8px 0 0 0;'>",
                unsafe_allow_html=True
            )
            st.dataframe(
                file_rows,
                use_container_width=True,
                hide_index=True,
                column_config={"Language": st.column_config.TextColumn("Language", help="Programming language", width="small")}
            )
            st.write("</div>", unsafe_allow_html=True)
        else:
            st.info("No files uploaded yet.") 