import streamlit as st
import tempfile
import os
import re
import json
import csv as pycsv
from streamlit_ace import st_ace
import plotly.graph_objects as go
import plotly.express as px

# --- MetricAgent ---
class MetricAgent:
    @staticmethod
    def analyze(code, file_path=None):
        debug = {}
        warnings = []
        strategy = None
        # 1. Try javalang
        try:
            import javalang
            tree = javalang.parse.parse(code)
            class_count = 0
            method_count = 0
            for path, node in tree:
                if isinstance(node, javalang.tree.ClassDeclaration):
                    class_count += 1
                    method_count += len([m for m in node.methods])
            strategy = "javalang"
            result = {
                "Lines of Code (LOC)": len(code.splitlines()),
                "Number of classes": class_count,
                "Number of methods": method_count,
                "_strategy": strategy,
                "_warnings": warnings,
                "_debug": debug
            }
            return result
        except Exception as e:
            warnings.append(f"javalang failed: {e}. Falling back to regex/statistical analysis.")
        # 2. Regex/statistical fallback
        strategy = "regex-fallback"
        class_count = len(re.findall(r'class\s+\w+', code))
        method_count = len(re.findall(r'(public|private|protected)?\s+\w+\s+\w+\s*\([^)]*\)\s*\{', code))
        keyword_counts = {kw: len(re.findall(rf'\b{kw}\b', code)) for kw in ["public", "private", "protected", "static", "final", "void", "int", "String"]}
        warnings.append("Using regex/statistical fallback. Only basic metrics are available.")
        result = {
            "Lines of Code (LOC)": len(code.splitlines()),
            "Number of classes": class_count,
            "Number of methods": method_count,
            "_strategy": strategy,
            "_warnings": warnings,
            "_debug": debug
        }
        result.update({f"Keyword: {k}": v for k, v in keyword_counts.items()})
        return result

# --- SmellAgent ---
class SmellAgent:
    @staticmethod
    def analyze(code):
        smells = []
        lines = code.splitlines()
        # Long Method
        method_blocks = re.findall(r'(public|private|protected)?\s+\w+\s+\w+\s*\([^)]*\)\s*\{', code)
        if method_blocks:
            method_starts = [i for i, l in enumerate(lines) if re.match(r'(public|private|protected)?\s+\w+\s+\w+\s*\([^)]*\)\s*\{', l.strip())]
            for idx, start in enumerate(method_starts):
                end = method_starts[idx+1] if idx+1 < len(method_starts) else len(lines)
                length = end - start
                if length > 50:
                    smells.append({
                        "type": "Long Method",
                        "severity": "Moderate" if length < 100 else "Critical",
                        "lines": f"{start+1}-{end}",
                        "explanation": f"Method is {length} lines long."
                    })
        # Duplicate Code (identical method names)
        method_names = re.findall(r'(?:public|private|protected)?\s+\w+\s+(\w+)\s*\([^)]*\)\s*\{', code)
        from collections import Counter
        for name, count in Counter(method_names).items():
            if count > 1:
                smells.append({
                    "type": "Duplicate Code",
                    "severity": "Moderate",
                    "lines": "?",
                    "explanation": f"Method '{name}' is defined multiple times."
                })
        # Magic Number
        for i, line in enumerate(lines, 1):
            if re.search(r"[^\w]([0-9]{2,})[^\w]", line):
                smells.append({
                    "type": "Magic Number",
                    "severity": "Minor",
                    "lines": str(i),
                    "explanation": f"Possible magic number in line: {line.strip()}"
                })
        if not smells:
            smells = [{
                "type": "No Smell",
                "severity": "Minor",
                "lines": "N/A",
                "explanation": "No significant code smells detected."
            }]
        return smells

# --- DependencyAgent ---
class DependencyAgent:
    @staticmethod
    def analyze(selected_file, code_content, all_files, file_contents):
        outgoing = set()
        incoming = set()
        this_base = os.path.splitext(os.path.basename(selected_file))[0]
        for other in all_files:
            if other == selected_file:
                continue
            other_base = os.path.splitext(os.path.basename(other))[0]
            if re.search(rf"import\\s+.*{other_base}[;.]", code_content) or re.search(rf"\b{other_base}\b", code_content):
                outgoing.add(other)
        for fname, fcode in file_contents.items():
            if fname == selected_file:
                continue
            if re.search(rf"import\\s+.*{this_base}[;.]", fcode) or re.search(rf"\b{this_base}\b", fcode):
                incoming.add(fname)
        return {"incoming": list(incoming), "outgoing": list(outgoing), "all_files": list(all_files)}

# --- Helper Functions for Metric Groups ---
def analyze_structural_metrics(code, tree):
    lines = code.splitlines()
    loc = len(lines)
    eloc = len([l for l in lines if l.strip() and not l.strip().startswith('//') and not l.strip().startswith('/*')])
    class_count = 0
    interface_count = 0
    method_counts = []
    field_counts = []
    accessor_count = 0
    package_count = 0
    max_class_size = 0
    max_method_size = 0
    for path, node in tree:
        if hasattr(node, 'fields') and hasattr(node, 'methods'):
            class_count += 1
            field_counts.append(len(getattr(node, 'fields', [])))
            method_counts.append(len(getattr(node, 'methods', [])))
            class_start = getattr(node, 'position', None)
            if class_start:
                class_end = max([getattr(n, 'position', class_start).line for _, n in tree if hasattr(n, 'position') and hasattr(n, 'line')], default=class_start.line)
                class_size = class_end - class_start.line + 1
                max_class_size = max(max_class_size, class_size)
        if node.__class__.__name__ == 'InterfaceDeclaration':
            interface_count += 1
        if node.__class__.__name__ == 'PackageDeclaration':
            package_count += 1
        if node.__class__.__name__ == 'MethodDeclaration':
            method_start = getattr(node, 'position', None)
            if method_start:
                method_end = method_start.line + len(getattr(node, 'body', []) or [])
                method_size = method_end - method_start.line + 1
                max_method_size = max(max_method_size, method_size)
            # Accessors
            if node.name.startswith('get') or node.name.startswith('set'):
                accessor_count += 1
    return {
        'Lines of Code (LOC)': loc,
        'Effective Lines of Code (eLOC)': eloc,
        'Number of Classes': class_count,
        'Number of Interfaces': interface_count,
        'Number of Methods per Class': sum(method_counts) / class_count if class_count else 0,
        'Number of Fields per Class': sum(field_counts) / class_count if class_count else 0,
        'Number of Packages': package_count,
        'Maximum Class Size': max_class_size,
        'Maximum Method Size (in LOC)': max_method_size,
        'Number of Accessors (getters/setters)': accessor_count
    }

def analyze_complexity_metrics(code, tree):
    # Placeholders for complexity metrics (real cyclomatic/cognitive complexity would need deeper analysis)
    cyclomatic = 0
    cognitive = 0
    nesting = 0
    switch_complexity = 0
    control_flow = 0
    conditions = 0
    for path, node in tree:
        if node.__class__.__name__ == 'MethodDeclaration':
            body = getattr(node, 'body', []) or []
            cyclomatic += len([n for n in body if hasattr(n, 'statement')])
            cognitive += len([n for n in body if hasattr(n, 'expression')])
            nesting += sum(1 for n in body if hasattr(n, 'block'))
            conditions += len([n for n in body if hasattr(n, 'condition')])
        if node.__class__.__name__ == 'SwitchStatement':
            switch_complexity += 1
        if node.__class__.__name__ in ['IfStatement', 'ForStatement', 'WhileStatement', 'DoStatement']:
            control_flow += 1
    return {
        'Cyclomatic Complexity (approx)': cyclomatic,
        'Cognitive Complexity (approx)': cognitive,
        'Nesting Depth (approx)': nesting,
        'Switch Complexity': switch_complexity,
        'Control Flow Complexity': control_flow,
        'Number of Conditions per Method (approx)': conditions
    }

def analyze_coupling_metrics(code, tree):
    # Placeholders for coupling metrics
    cbo = 0
    rfc = 0
    fan_in = 0
    fan_out = 0
    ca = 0
    ce = 0
    instability = 0
    ext_deps = 0
    for path, node in tree:
        if node.__class__.__name__ == 'ClassDeclaration':
            cbo += len(getattr(node, 'implements', []) or [])
            rfc += len(getattr(node, 'methods', []) or [])
            fan_out += len(getattr(node, 'fields', []) or [])
    instability = ce / (ca + ce) if (ca + ce) else 0
    return {
        'Coupling Between Object Classes (CBO)': cbo,
        'Response for a Class (RFC)': rfc,
        'Fan-In': fan_in,
        'Fan-Out': fan_out,
        'Afferent Coupling (Ca)': ca,
        'Efferent Coupling (Ce)': ce,
        'Instability (I)': instability,
        'Number of External Dependencies': ext_deps
    }

def analyze_cohesion_metrics(code, tree):
    # Placeholders for cohesion metrics
    lcom = 0
    tcc = 0
    method_pairs = 0
    return {
        'Lack of Cohesion in Methods (LCOM)': lcom,
        'Tight Class Cohesion (TCC)': tcc,
        'Number of Method Pairs Sharing Fields': method_pairs
    }

def analyze_oo_metrics(code, tree):
    # Placeholders for OO metrics
    wmc = 0
    dit = 0
    noc = 0
    mif = 0
    aif = 0
    abstractness = 0
    specialization = 0
    return {
        'Weighted Methods per Class (WMC)': wmc,
        'Depth of Inheritance Tree (DIT)': dit,
        'Number of Children (NOC)': noc,
        'Method Inheritance Factor (MIF)': mif,
        'Attribute Inheritance Factor (AIF)': aif,
        'Abstractness (A)': abstractness,
        'Specialization Index': specialization
    }

def analyze_maintainability_metrics(code, tree):
    # Placeholders for maintainability metrics
    maintainability = 0
    comment_density = len([l for l in code.splitlines() if l.strip().startswith('//') or l.strip().startswith('/*')]) / (len(code.splitlines()) or 1)
    javadoc_density = len([l for l in code.splitlines() if l.strip().startswith('/**')]) / (len(code.splitlines()) or 1)
    avg_comment_length = sum(len(l) for l in code.splitlines() if l.strip().startswith('//')) / (len([l for l in code.splitlines() if l.strip().startswith('//')]) or 1)
    ratio_commented = 0
    return {
        'Maintainability Index (approx)': maintainability,
        'Comment Density': comment_density,
        'Javadoc Density': javadoc_density,
        'Average Comment Length': avg_comment_length,
        'Ratio of Commented vs. Un-commented Classes': ratio_commented
    }

def analyze_reliability_metrics(code, tree):
    # Placeholders for reliability/testability metrics
    exception_handlers = len(re.findall(r'catch\s*\(', code))
    catch_density = exception_handlers / (len(code.splitlines()) or 1)
    assertions = len(re.findall(r'assert\s', code))
    ratio_tested = 0
    unit_tests = len(re.findall(r'@Test', code))
    return {
        'Number of Exception Handlers': exception_handlers,
        'Catch Block Density': catch_density,
        'Assertions per Method': assertions,
        'Ratio of Tested vs. Untested Classes': ratio_tested,
        'Number of Unit Test Methods': unit_tests
    }

def analyze_duplication_metrics(code, tree):
    # Placeholders for duplication/redundancy metrics
    duplicated_blocks = 0
    duplicated_lines = 0
    similar_methods = 0
    return {
        'Number of Duplicated Blocks': duplicated_blocks,
        'Duplicated Lines Density (%)': duplicated_lines,
        'Number of Similar Methods': similar_methods
    }

def analyze_documentation_metrics(code, tree):
    # Placeholders for documentation/style metrics
    todo_tags = len(re.findall(r'TODO|FIXME', code))
    naming_violations = 0
    blank_line_density = len([l for l in code.splitlines() if not l.strip()]) / (len(code.splitlines()) or 1)
    identifier_length = 0
    return {
        'Number of TODO / FIXME Tags': todo_tags,
        'Naming Convention Violations': naming_violations,
        'Blank Line Density': blank_line_density,
        'Identifier Length Average': identifier_length
    }

def analyze_security_metrics(code, tree):
    # Placeholders for security/quality flags
    hardcoded_creds = len(re.findall(r'password|passwd|secret|api[_-]?key', code, re.IGNORECASE))
    deprecated_apis = len(re.findall(r'@Deprecated', code))
    unused_imports = len(re.findall(r'import\s+\w+;\s*$', code, re.MULTILINE))
    missing_modifiers = 0
    public_data_members = 0
    unsafe_casts = len(re.findall(r'\([A-Za-z0-9_]+\)\s*\w+', code))
    return {
        'Number of Hardcoded Credentials': hardcoded_creds,
        'Use of Deprecated APIs': deprecated_apis,
        'Unused Imports or Variables': unused_imports,
        'Missing or Incomplete Access Modifiers': missing_modifiers,
        'Public Data Members Count': public_data_members,
        'Unsafe Type Casts': unsafe_casts
    }

# --- Main Java Analysis Function ---
def analyze_java_code(code, file_path=None):
    try:
        import javalang
        tree = list(javalang.parse.parse(code))
    except Exception as e:
        tree = []
    metrics = {}
    metrics['Structural Metrics'] = analyze_structural_metrics(code, tree)
    metrics['Complexity Metrics'] = analyze_complexity_metrics(code, tree)
    metrics['Coupling and Dependency Metrics'] = analyze_coupling_metrics(code, tree)
    metrics['Cohesion Metrics'] = analyze_cohesion_metrics(code, tree)
    metrics['Object-Oriented Design Metrics'] = analyze_oo_metrics(code, tree)
    metrics['Maintainability and Readability'] = analyze_maintainability_metrics(code, tree)
    metrics['Reliability and Testability Metrics'] = analyze_reliability_metrics(code, tree)
    metrics['Code Duplication and Redundancy'] = analyze_duplication_metrics(code, tree)
    metrics['Documentation and Style'] = analyze_documentation_metrics(code, tree)
    metrics['Security and Quality Flags'] = analyze_security_metrics(code, tree)
    return metrics

# --- Streamlit UI ---
def render_analyze_tab():
    st.header("Java Code Analysis (SonarQube-inspired)")
    st.caption("Comprehensive static analysis for Java. No LLMs or API keys required.")
    files = st.session_state.get("uploaded_files", [])
    if not files:
        st.info("Upload or clone a Java project to begin analysis.")
        return
    file_names = [f["name"] for f in files]
    selected_file = st.selectbox("Select a Java file to analyze:", file_names, key="analyze_file")
    file_obj = next((f for f in files if f["name"] == selected_file), None)
    code_content = None
    file_path = None
    if file_obj:
        repo_dir = st.session_state.get("repo_dir")
        if repo_dir:
            file_path = os.path.join(repo_dir, file_obj["name"])
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    code_content = f.read()
            except Exception:
                code_content = ""
        else:
            if "content" in file_obj:
                try:
                    code_content = file_obj["content"].decode("utf-8", errors="ignore")
                except Exception:
                    code_content = ""
            else:
                code_content = ""
            file_path = file_obj["name"]
    if not code_content or len(code_content.strip()) == 0:
        st.warning(f"Could not read file content or file is empty. File: {file_path}")
        st.write(f"File path: {file_path}")
        return
    st.markdown("#### Code Preview")
    st_ace(value=code_content, language="java", theme='monokai', readonly=True, show_gutter=True, key=f"ace_code_preview_{selected_file}")
    run_key = f"analyze_{selected_file}_java_sonarqube"
    if st.session_state.get(run_key) is None:
        try:
            with st.spinner(f"Running SonarQube-inspired static analysis for Java..."):
                metrics = analyze_java_code(code_content, file_path=file_path)
                st.session_state[run_key] = {"metrics": metrics, "file_path": file_path, "content_length": len(code_content)}
        except Exception as e:
            st.session_state[run_key] = {"metrics": {"error": str(e)}, "file_path": file_path, "content_length": len(code_content)}
            st.error(f"Error during analysis: {e}")
    results = st.session_state[run_key]
    metrics = results["metrics"]
    st.markdown("---")
    st.markdown(f"**File path:** {results['file_path']}")
    st.markdown(f"**Code content length:** {results['content_length']}")

    # --- Main Tabs ---
    main_tabs = st.tabs(["Code Metrics", "Dependencies", "Code Smells"])
    with main_tabs[0]:
        # --- Dropdown for Metric Category ---
        metric_categories = list(metrics.keys())
        selected_category = st.selectbox("Select a metric category:", metric_categories, key="category_dropdown")
        group_metrics = metrics[selected_category]
        metric_names = list(group_metrics.keys())

        # --- Cards for Key Values ---
        card_cols = st.columns(min(4, len(metric_names)))
        for j, k in enumerate(metric_names):
            v = group_metrics[k]
            # Color coding by value/severity (simple heuristics)
            color = "#f0f2f6"  # default
            if isinstance(v, (int, float)):
                if 'complexity' in k.lower() or 'depth' in k.lower():
                    if v > 10:
                        color = "#ff4d4f"  # red
                    elif v > 5:
                        color = "#faad14"  # yellow
                    else:
                        color = "#52c41a"  # green
                elif 'cohesion' in k.lower() or 'maintainability' in k.lower():
                    if v < 0.3:
                        color = "#ff4d4f"
                    elif v < 0.6:
                        color = "#faad14"
                    else:
                        color = "#52c41a"
                elif 'duplicat' in k.lower() or 'violation' in k.lower() or 'hardcoded' in k.lower():
                    if v > 0:
                        color = "#ff4d4f"
                    else:
                        color = "#52c41a"
                elif 'comment' in k.lower():
                    if v > 0.2:
                        color = "#52c41a"
                    else:
                        color = "#faad14"
            with card_cols[j % len(card_cols)]:
                st.markdown(f"""
                    <div style='border-radius:10px;border:1px solid #d9d9d9;background:{color};margin-bottom:12px;padding:12px 10px;box-shadow:0 2px 8px #0001;'>
                        <span style='font-size:1.1em;font-weight:bold;'>{k}</span><br/>
                        <span style='font-size:1.5em;'>{v}</span>
                    </div>
                """, unsafe_allow_html=True)

        # --- Modern Chart Section ---
        chart_keys = [k for k in metric_names if isinstance(group_metrics[k], (int, float))]
        chart_vals = [group_metrics[k] for k in chart_keys]
        # Structural Metrics: Bar, Pie, Line
        if selected_category == "Structural Metrics":
            if chart_vals and len(chart_vals) > 1:
                bar_fig = px.bar(x=chart_keys, y=chart_vals, color=chart_keys, color_discrete_sequence=px.colors.qualitative.Set2)
                bar_fig.update_layout(height=320, title="Structural Metrics (Bar Chart)", xaxis_title="Metric", yaxis_title="Value")
                st.plotly_chart(bar_fig, use_container_width=True)
            # Pie chart for class/interface/method distribution
            pie_keys = [k for k in chart_keys if any(x in k for x in ["Class", "Interface", "Method"])]
            pie_vals = [group_metrics[k] for k in pie_keys]
            if pie_keys and sum(pie_vals) > 0:
                pie_fig = px.pie(names=pie_keys, values=pie_vals, color_discrete_sequence=px.colors.sequential.RdBu)
                pie_fig.update_traces(textinfo='label+percent', pull=[0.05]*len(pie_keys))
                pie_fig.update_layout(title="Class/Interface/Method Distribution", height=300)
                st.plotly_chart(pie_fig, use_container_width=True)
            # Line chart for LOC trend
            if "Lines of Code (LOC)" in group_metrics:
                loc = group_metrics["Lines of Code (LOC)"]
                line_fig = go.Figure([go.Scatter(x=list(range(1, loc+1)), y=[1]*loc, mode='lines', line=dict(color="#52c41a"))])
                line_fig.update_layout(height=200, title="LOC Distribution (Line Chart)")
                st.plotly_chart(line_fig, use_container_width=True)
        # Complexity/Coupling/Cohesion/OO: Radar + Bar
        elif selected_category in ["Complexity Metrics", "Coupling and Dependency Metrics", "Cohesion Metrics", "Object-Oriented Design Metrics"]:
            if chart_vals and len(chart_vals) > 2:
                radar_fig = go.Figure()
                radar_fig.add_trace(go.Scatterpolar(r=chart_vals, theta=chart_keys, fill='toself', name=selected_category, marker=dict(color="#636efa")))
                radar_fig.update_traces(hoverinfo="all", marker_line_width=2)
                radar_fig.update_layout(polar=dict(radialaxis=dict(visible=True)), showlegend=False, height=350, title=f"{selected_category} (Spider Web)")
                st.plotly_chart(radar_fig, use_container_width=True)
            if chart_vals and len(chart_vals) > 1:
                bar_fig = px.bar(x=chart_keys, y=chart_vals, color=chart_keys, color_discrete_sequence=px.colors.qualitative.Pastel)
                bar_fig.update_layout(height=300, title=f"{selected_category} (Bar Chart)", xaxis_title="Metric", yaxis_title="Value")
                st.plotly_chart(bar_fig, use_container_width=True)
        # Maintainability/Documentation: Horizontal bar
        elif selected_category in ["Maintainability and Readability", "Documentation and Style"]:
            if chart_vals and len(chart_vals) > 1:
                hbar_fig = px.bar(x=chart_vals, y=chart_keys, orientation='h', color=chart_keys, color_discrete_sequence=px.colors.qualitative.G10)
                hbar_fig.update_layout(height=320, title=f"{selected_category} (Horizontal Bar)", xaxis_title="Value", yaxis_title="Metric")
                st.plotly_chart(hbar_fig, use_container_width=True)
        # Reliability/Duplication/Security: Donut or Bar
        elif selected_category in ["Reliability and Testability Metrics", "Code Duplication and Redundancy", "Security and Quality Flags"]:
            if chart_vals and len(chart_vals) > 1:
                donut_fig = px.pie(names=chart_keys, values=chart_vals, hole=0.5, color_discrete_sequence=px.colors.sequential.Plasma)
                donut_fig.update_traces(textinfo='label+percent', pull=[0.03]*len(chart_keys))
                donut_fig.update_layout(title=f"{selected_category} (Donut Chart)", height=320)
                st.plotly_chart(donut_fig, use_container_width=True)
            if chart_vals and len(chart_vals) > 1:
                bar_fig = px.bar(x=chart_keys, y=chart_vals, color=chart_keys, color_discrete_sequence=px.colors.qualitative.Set3)
                bar_fig.update_layout(height=300, title=f"{selected_category} (Bar Chart)", xaxis_title="Metric", yaxis_title="Value")
                st.plotly_chart(bar_fig, use_container_width=True)

        # --- Download Buttons ---
        st.markdown("---")
        st.download_button("Download Metrics as JSON", data=json.dumps(metrics, indent=2), file_name="java_metrics.json", mime="application/json")
        csv_rows = []
        for group, group_metrics in metrics.items():
            for k, v in group_metrics.items():
                csv_rows.append({"Group": group, "Metric": k, "Value": v})
        csv_str = ''
        if csv_rows:
            import io
            output = io.StringIO()
            writer = pycsv.DictWriter(output, fieldnames=["Group", "Metric", "Value"])
            writer.writeheader()
            writer.writerows(csv_rows)
            csv_str = output.getvalue()
        st.download_button("Download Metrics as CSV", data=csv_str, file_name="java_metrics.csv", mime="text/csv")

    with main_tabs[1]:
        st.markdown("### Dependencies")
        st.info("Dependency analysis coming soon.")

    with main_tabs[2]:
        st.markdown("### Code Smells")
        st.info("Code smell detection coming soon.")  