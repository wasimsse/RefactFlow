import streamlit as st
import tempfile
import os
import re
import json
import csv as pycsv
from streamlit_ace import st_ace
import plotly.graph_objects as go
import plotly.express as px
import networkx as nx
import pandas as pd
import numpy as np

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

# --- Agentic Code Smell Detection System ---
from typing import List, Dict

class SmellReport:
    def __init__(self, file_name, location, category, smell_type, description, lines, confidence, refactor, suggestion, reason=None):
        self.file_name = file_name
        self.location = location
        self.category = category
        self.smell_type = smell_type
        self.description = description
        self.lines = lines
        self.confidence = confidence
        self.refactor = refactor
        self.suggestion = suggestion
        self.reason = reason
    def as_dict(self):
        return {
            "File Name": self.file_name,
            "Location": self.location,
            "Category": self.category,
            "Type of Code Smell": self.smell_type,
            "Short Description": self.description,
            "Line Numbers": self.lines,
            "Confidence": round(self.confidence, 2),
            "Reason": self.reason or "",
            "Refactoring Recommended": self.refactor,
            "Suggested Refactoring Technique": self.suggestion
        }

# --- Project-wide stats for dynamic thresholds ---
def compute_project_stats(all_files, file_contents):
    class_sizes = []
    method_sizes = []
    for fname in all_files:
        code = file_contents[fname]
        try:
            import javalang
            tree = list(javalang.parse.parse(code))
            for path, node in tree:
                if isinstance(node, javalang.tree.ClassDeclaration):
                    start = getattr(node, 'position', None)
                    if start:
                        class_sizes.append(len(code.splitlines()))
                if isinstance(node, javalang.tree.MethodDeclaration):
                    start = getattr(node, 'position', None)
                    if start:
                        method_sizes.append(len(code.splitlines()))
        except Exception:
            # fallback: regex
            class_sizes += [len(m.group(0).splitlines()) for m in re.finditer(r'class\s+\w+[^{]*\{[^}]*\}', code, re.DOTALL)]
            method_sizes += [len(m.group(0).splitlines()) for m in re.finditer(r'(public|private|protected)?\s+\w+\s+\w+\s*\([^)]*\)\s*\{[^}]*\}', code, re.DOTALL)]
    stats = {
        'class_median': float(np.median(class_sizes)) if class_sizes else 0,
        'method_median': float(np.median(method_sizes)) if method_sizes else 0
    }
    return stats

class ClassSmellAgent:
    @staticmethod
    def detect(code, file_name, project_stats=None, all_files=None, file_contents=None):
        reports = []
        category = "Class-Level Code Smells"
        try:
            import javalang
            tree = list(javalang.parse.parse(code))
            class_names = set()
            parent_map = {}
            for path, node in tree:
                if isinstance(node, javalang.tree.ClassDeclaration):
                    cname = node.name
                    class_names.add(cname)
                    # Refused Bequest: subclass does not use inherited members
                    if node.extends:
                        parent = node.extends.name if hasattr(node.extends, 'name') else str(node.extends)
                        parent_map[cname] = parent
                        # Heuristic: if class has few methods/fields and extends a parent, flag
                        methods = node.methods or []
                        fields = node.fields or []
                        if len(methods) < 2 and len(fields) < 2:
                            confidence = 0.7
                            reason = f"Class '{cname}' extends '{parent}' but has few own members."
                            reports.append(SmellReport(
                                file_name, cname, category, "Refused Bequest",
                                f"Class '{cname}' extends '{parent}' but does not use much of its inheritance.",
                                f"?", confidence, "Maybe", "Review Inheritance, Refactor", reason
                            ))
                    # Inappropriate Intimacy: accesses many fields/methods of another class
                    body = code
                    for other in class_names:
                        if other != cname and len(re.findall(rf'{other}\\.', body)) > 5:
                            confidence = 0.8
                            reason = f"Class '{cname}' accesses '{other}' members >5 times."
                            reports.append(SmellReport(
                                file_name, cname, category, "Inappropriate Intimacy",
                                f"Class '{cname}' is too intimate with '{other}'.",
                                f"?", confidence, "Yes", "Reduce Coupling, Refactor", reason
                            ))
                    # God Class
                    if len(code.splitlines()) > project_stats['class_median'] * 2 and len(methods) > 10 and len(fields) > 10:
                        confidence = min(1.0, (len(code.splitlines())-project_stats['class_median'])/project_stats['class_median'])
                        reason = f"LOC={len(code.splitlines())}, methods={len(methods)}, fields={len(fields)}, median LOC={project_stats['class_median']}"
                        reports.append(SmellReport(
                            file_name, cname, category, "God Class",
                            f"Class '{cname}' is a God Class (large, many methods/fields).",
                            f"?", confidence, "Yes", "Extract Class, Reduce Responsibilities", reason
                        ))
                    # Large Class (separate)
                    if len(code.splitlines()) > project_stats['class_median'] * 1.5:
                        confidence = min(1.0, (len(code.splitlines())-project_stats['class_median'])/project_stats['class_median'])
                        reason = f"LOC={len(code.splitlines())}, median LOC={project_stats['class_median']}"
                        reports.append(SmellReport(
                            file_name, cname, category, "Large Class",
                            f"Class '{cname}' is large ({len(code.splitlines())} LOC).",
                            f"?", confidence, "Yes", "Extract Class, Reduce Size", reason
                        ))
                    # Lazy Class: very small class
                    if len(code.splitlines()) < project_stats['class_median'] * 0.3 and len(methods) < 2:
                        confidence = 0.9
                        reason = f"LOC={len(code.splitlines())}, methods={len(methods)}, median LOC={project_stats['class_median']}"
                        reports.append(SmellReport(
                            file_name, cname, category, "Lazy Class",
                            f"Class '{cname}' is very small and may not justify its existence.",
                            f"?", confidence, "Yes", "Inline Class, Merge with another", reason
                        ))
                    # Data Class: mostly fields, few methods
                    if len(fields) > 3 and len(methods) <= 2:
                        confidence = 0.8
                        reason = f"fields={len(fields)}, methods={len(methods)}"
                        reports.append(SmellReport(
                            file_name, cname, category, "Data Class",
                            f"Class '{cname}' is a Data Class (mostly fields, few methods).",
                            f"?", confidence, "Yes", "Encapsulate Data, Add Behavior", reason
                        ))
                    # Temporary Field: field only used in some methods
                    for field in fields:
                        fname = getattr(field.declarators[0], 'name', '?') if hasattr(field, 'declarators') and field.declarators else '?'
                        used = any(fname in m.body for m in methods if hasattr(m, 'body'))
                        if not used:
                            confidence = 0.7
                            reason = f"Field '{fname}' not used in most methods."
                            reports.append(SmellReport(
                                file_name, fname, category, "Temporary Field",
                                f"Field '{fname}' is only used in a subset of methods.",
                                f"?", confidence, "Maybe", "Move Field, Refactor", reason
                            ))
                    # Swiss Army Knife: implements many interfaces
                    interfaces = getattr(node, 'implementing', [])
                    if hasattr(node, 'implements') and node.implements:
                        interfaces = node.implements
                    if interfaces and len(interfaces) > 3:
                        confidence = min(1.0, (len(interfaces)-3)/3 + 0.5)
                        reason = f"Implements {len(interfaces)} interfaces."
                        reports.append(SmellReport(
                            file_name, cname, category, "Swiss Army Knife",
                            f"Class '{cname}' implements many interfaces.",
                            f"?", confidence, "Maybe", "Split Responsibilities, Reduce Interfaces", reason
                        ))
            # Divergent Change: class with many unrelated methods (by name)
            for path, node in tree:
                if isinstance(node, javalang.tree.ClassDeclaration):
                    methods = node.methods or []
                    prefixes = set(m.name.split('_')[0] for m in methods if hasattr(m, 'name'))
                    if len(prefixes) > 5:
                        confidence = 0.7
                        reason = f"Class has methods with many different prefixes: {prefixes}"
                        reports.append(SmellReport(
                            file_name, node.name, category, "Divergent Change",
                            f"Class '{node.name}' may have too many responsibilities.",
                            f"?", confidence, "Maybe", "Split Class, Single Responsibility", reason
                        ))
            # Parallel Inheritance Hierarchies: mirrored class hierarchies
            if all_files and file_contents:
                for fname, fcode in file_contents.items():
                    if fname == file_name:
                        continue
                    try:
                        t2 = list(javalang.parse.parse(fcode))
                        for path2, node2 in t2:
                            if isinstance(node2, javalang.tree.ClassDeclaration) and node2.extends:
                                parent2 = node2.extends.name if hasattr(node2.extends, 'name') else str(node2.extends)
                                for cname, parent in parent_map.items():
                                    if parent2 != parent and parent2.lower().startswith(parent.lower()[:3]):
                                        confidence = 0.7
                                        reason = f"Class '{node2.name}' extends '{parent2}', similar to '{parent}'."
                                        reports.append(SmellReport(
                                            fname, node2.name, category, "Parallel Inheritance Hierarchies",
                                            f"Class '{node2.name}' and '{cname}' may be part of parallel hierarchies.",
                                            f"?", confidence, "Maybe", "Review Hierarchies, Refactor", reason
                                        ))
                    except Exception:
                        continue
            return reports
        except Exception:
            class_pattern = re.compile(r'class\s+(\w+)[^{]*\{', re.MULTILINE)
            for m in class_pattern.finditer(code):
                cname = m.group(1)
                header = code[max(0, m.start()-100):m.start()]
                interfaces = re.findall(r'implements\s+([\w,\s]+)', header)
                if interfaces:
                    iface_list = [i.strip() for i in interfaces[0].split(',') if i.strip()]
                    if len(iface_list) > 3:
                        confidence = min(1.0, (len(iface_list)-3)/3 + 0.5)
                        reason = f"Implements {len(iface_list)} interfaces."
                        reports.append(SmellReport(
                            file_name, cname, category, "Swiss Army Knife",
                            f"Class '{cname}' implements many interfaces.",
                            f"{m.start()}-{m.end()}", confidence, "Maybe", "Split Responsibilities, Reduce Interfaces", reason
                        ))
            return reports

class MethodSmellAgent:
    @staticmethod
    def detect(code, file_name, project_stats=None):
        reports = []
        category = "Method-Level Code Smells"
        method_pattern = re.compile(r'(public|private|protected)?\s+\w+\s+(\w+)\s*\(([^)]*)\)\s*\{', re.MULTILINE)
        method_bodies = []
        all_method_names = set()
        for m in method_pattern.finditer(code):
            mname = m.group(2)
            all_method_names.add(mname)
            params_str = m.group(3)
            start = m.end() - 1
            brace_count = 1
            i = start
            while i < len(code) and brace_count > 0:
                i += 1
                if code[i-1] == '{':
                    brace_count += 1
                elif code[i-1] == '}':
                    brace_count -= 1
            mbody = code[start:i-1]
            method_bodies.append((mname, mbody, params_str, m.start(), i))
            # Feature Envy: method uses more fields of another class than its own (simple heuristic)
            field_accesses = re.findall(r'(\w+)\.(\w+)', mbody)
            objects = set(obj for obj, field in field_accesses)
            if len(objects) > 3:
                confidence = min(1.0, (len(objects)-3)/3 + 0.5)
                reason = f"Method uses fields of {len(objects)} different objects."
                reports.append(SmellReport(
                    file_name, mname, category, "Feature Envy",
                    f"Method '{mname}' may be envious of other classes' data.",
                    f"{m.start()}-{i}", confidence, "Yes", "Move Method, Reduce External Field Access", reason
                ))
            # Long Method
            loc = len(mbody.splitlines())
            threshold = project_stats['method_median']*1.5 if project_stats and project_stats['method_median'] else 50
            if loc > threshold:
                confidence = min(1.0, (loc-threshold)/threshold + 0.5)
                reason = f"LOC={loc}, threshold={threshold}"
                reports.append(SmellReport(
                    file_name, mname, category, "Long Method",
                    f"Method '{mname}' is very long ({loc} LOC).",
                    f"{m.start()}-{i}", confidence, "Yes", "Extract Method, Decompose Logic", reason
                ))
            # Long Parameter List
            params = re.findall(r'\w+', m.group(0).split('(',1)[1].split(')',1)[0])
            if len(params) > 5:
                confidence = min(1.0, (len(params)-5)/5 + 0.5)
                reason = f"{len(params)} parameters"
                reports.append(SmellReport(
                    file_name, mname, category, "Long Parameter List",
                    f"Method '{mname}' has a long parameter list ({len(params)} params).",
                    f"{m.start()}-{i}", confidence, "Yes", "Introduce Parameter Object", reason
                ))
            # Duplicated Code: identical method bodies (simple: hash)
            import hashlib
            method_hash = hashlib.md5(mbody.encode()).hexdigest()
            if not hasattr(MethodSmellAgent, '_method_hashes'):
                MethodSmellAgent._method_hashes = {}
            if method_hash in MethodSmellAgent._method_hashes:
                confidence = 1.0
                reason = f"Method body duplicated with '{MethodSmellAgent._method_hashes[method_hash]}'"
                reports.append(SmellReport(
                    file_name, mname, category, "Duplicated Code",
                    f"Method '{mname}' is a duplicate of another method.",
                    f"{m.start()}-{i}", confidence, "Yes", "Remove Duplicate, Refactor", reason
                ))
            else:
                MethodSmellAgent._method_hashes[method_hash] = mname
            # Message Chains: long chains of method calls
            if len(re.findall(r'\.[a-zA-Z_][a-zA-Z0-9_]*\(', mbody)) > 3:
                confidence = 0.8
                reason = f"Long message chain detected."
                reports.append(SmellReport(
                    file_name, mname, category, "Message Chains",
                    f"Method '{mname}' contains a long message chain.",
                    f"{m.start()}-{i}", confidence, "Maybe", "Reduce Chaining, Use Intermediate Variables", reason
                ))
            # Switch Statements
            if re.search(r'switch\s*\(', mbody):
                confidence = 0.7
                reason = f"Switch statement present."
                reports.append(SmellReport(
                    file_name, mname, category, "Switch Statement",
                    f"Method '{mname}' contains a switch statement.",
                    f"{m.start()}-{i}", confidence, "Maybe", "Replace with Polymorphism", reason
                ))
            # Primitive Obsession: many primitive params
            primitive_types = ["int", "float", "double", "long", "short", "byte", "boolean", "char", "String"]
            param_types = [p.split()[0] for p in params_str.split(',') if p.strip() and len(p.split()) > 1]
            primitive_count = sum(1 for t in param_types if t in primitive_types)
            if primitive_count > 3:
                confidence = min(1.0, (primitive_count-3)/3 + 0.5)
                reason = f"{primitive_count} primitive parameters."
                reports.append(SmellReport(
                    file_name, mname, category, "Primitive Obsession",
                    f"Method '{mname}' has many primitive parameters.",
                    f"{m.start()}-{i}", confidence, "Yes", "Use Value Objects, Refactor Params", reason
                ))
            # Middle Man: method only delegates to another method
            lines = [l.strip() for l in mbody.splitlines() if l.strip() and not l.strip().startswith('//')]
            if len(lines) == 1 and re.match(r'(return\s+)?\w+\.\w+\(.*\);', lines[0]):
                confidence = 0.9
                reason = f"Method only delegates: {lines[0]}"
                reports.append(SmellReport(
                    file_name, mname, category, "Middle Man",
                    f"Method '{mname}' only delegates to another method.",
                    f"{m.start()}-{i}", confidence, "Maybe", "Inline Method, Remove Middle Man", reason
                ))
        # Repeated Switches: multiple switches on same variable
        switch_vars = []
        for mname, mbody, params_str, mstart, mend in method_bodies:
            for sw in re.finditer(r'switch\s*\((\w+)\)', mbody):
                switch_vars.append(sw.group(1))
        from collections import Counter
        for var, count in Counter(switch_vars).items():
            if count > 1:
                confidence = min(1.0, (count-1)/2 + 0.5)
                reason = f"Switch on '{var}' appears {count} times."
                reports.append(SmellReport(
                    file_name, var, category, "Repeated Switches",
                    f"Multiple switch statements on variable '{var}'.",
                    "?", confidence, "Yes", "Replace with Polymorphism, Refactor", reason
                ))
        # Speculative Generality: abstract methods/classes/interfaces never used, or methods with 'hook', 'extension', 'future' in name not called
        # Abstract methods/classes/interfaces (simple regex)
        abstract_class_pattern = re.compile(r'abstract\s+class\s+(\w+)', re.MULTILINE)
        interface_pattern = re.compile(r'interface\s+(\w+)', re.MULTILINE)
        abstract_method_pattern = re.compile(r'abstract\s+\w+\s+(\w+)\s*\(', re.MULTILINE)
        for m in abstract_class_pattern.finditer(code):
            cname = m.group(1)
            # Heuristic: if class name not used elsewhere in file
            if code.count(cname) == 1:
                confidence = 0.8
                reason = f"Abstract class '{cname}' not used in file."
                reports.append(SmellReport(
                    file_name, cname, category, "Speculative Generality",
                    f"Abstract class '{cname}' appears unused.",
                    f"{m.start()}-{m.end()}", confidence, "Maybe", "Remove or Implement Class", reason
                ))
        for m in interface_pattern.finditer(code):
            iname = m.group(1)
            if code.count(iname) == 1:
                confidence = 0.8
                reason = f"Interface '{iname}' not used in file."
                reports.append(SmellReport(
                    file_name, iname, category, "Speculative Generality",
                    f"Interface '{iname}' appears unused.",
                    f"{m.start()}-{m.end()}", confidence, "Maybe", "Remove or Implement Interface", reason
                ))
        for m in abstract_method_pattern.finditer(code):
            mname = m.group(1)
            if code.count(mname) == 1:
                confidence = 0.8
                reason = f"Abstract method '{mname}' not used in file."
                reports.append(SmellReport(
                    file_name, mname, category, "Speculative Generality",
                    f"Abstract method '{mname}' appears unused.",
                    f"{m.start()}-{m.end()}", confidence, "Maybe", "Remove or Implement Method", reason
                ))
        # Methods with 'hook', 'extension', 'future' in name not called
        for mname, mbody, params_str, mstart, mend in method_bodies:
            if any(x in mname.lower() for x in ['hook', 'extension', 'future']) and code.count(mname) == 1:
                confidence = 0.7
                reason = f"Method '{mname}' has speculative name and is not called."
                reports.append(SmellReport(
                    file_name, mname, category, "Speculative Generality",
                    f"Method '{mname}' appears to be speculative and unused.",
                    f"{mstart}-{mend}", confidence, "Maybe", "Remove or Use Method", reason
                ))
        # Control Flag: boolean variable used to control flow
        for mname, mbody, params_str, mstart, mend in method_bodies:
            bool_vars = re.findall(r'boolean\s+(\w+)', mbody)
            for var in bool_vars:
                sets = len(re.findall(rf'{var}\s*=\s*(true|false)', mbody))
                checks = len(re.findall(rf'if\s*\(\s*{var}\s*\)', mbody))
                if sets == 1 and checks > 1:
                    confidence = min(1.0, (checks-1)/2 + 0.5)
                    reason = f"Boolean flag '{var}' set once, checked {checks} times."
                    reports.append(SmellReport(
                        file_name, mname, category, "Control Flag",
                        f"Method '{mname}' uses control flag '{var}' for flow control.",
                        f"{mstart}-{mend}", confidence, "Maybe", "Refactor to use break/return, Remove Flag", reason
                    ))
        return reports

class FieldSmellAgent:
    @staticmethod
    def detect(code, file_name):
        reports = []
        category = "Field-Level Code Smells"
        # Public Fields
        field_pattern = re.compile(r'public\s+\w+\s+(\w+)\s*;', re.MULTILINE)
        for m in field_pattern.finditer(code):
            fname = m.group(1)
            confidence = 1.0
            reason = "Field is declared public."
            reports.append(SmellReport(
                file_name, fname, category, "Public Field",
                f"Field '{fname}' is public.",
                f"{m.start()}-{m.end()}", confidence, "Yes", "Encapsulate Field, Use Getter/Setter", reason
            ))
        # Constant Interface: interface with only static final fields
        interface_pattern = re.compile(r'interface\s+(\w+)[^{]*\{([^}]*)\}', re.DOTALL)
        for m in interface_pattern.finditer(code):
            iname = m.group(1)
            body = m.group(2)
            fields = re.findall(r'(public\s+)?(static\s+)?(final\s+)?\w+\s+\w+\s*;', body)
            non_constant_fields = [f for f in fields if not (f[1] and f[2])]
            if fields and not non_constant_fields:
                confidence = 1.0
                reason = f"All fields in interface '{iname}' are static final."
                reports.append(SmellReport(
                    file_name, iname, category, "Constant Interface",
                    f"Interface '{iname}' is a constant interface (only static final fields).",
                    f"{m.start()}-{m.end()}", confidence, "Yes", "Refactor to Utility Class or Enum", reason
                ))
        # Mutable Static Fields: static fields that are not final
        static_field_pattern = re.compile(r'(public|private|protected)?\s+static\s+(?!final)\w+\s+(\w+)\s*;', re.MULTILINE)
        for m in static_field_pattern.finditer(code):
            fname = m.group(2)
            confidence = 1.0
            reason = "Static field is mutable (not final)."
            reports.append(SmellReport(
                file_name, fname, category, "Mutable Static Field",
                f"Field '{fname}' is static and mutable.",
                f"{m.start()}-{m.end()}", confidence, "Yes", "Make Field Final or Refactor", reason
            ))
        return reports

class ArchitectureSmellAgent:
    @staticmethod
    def detect(code, file_name, all_files, file_contents):
        reports = []
        category = "Architecture-Level Code Smells"
        # Cyclic Dependency: detect cycles across files (simple import graph)
        import_graph = {}
        for fname, fcode in file_contents.items():
            imports = re.findall(r'import\s+([\w\.]+);', fcode)
            import_graph[fname] = set(imports)
        # Detect cycles (simple DFS)
        def has_cycle(graph, start, visited=None, stack=None):
            if visited is None: visited = set()
            if stack is None: stack = set()
            visited.add(start)
            stack.add(start)
            for dep in graph.get(start, []):
                dep_file = next((f for f in graph if f.endswith(dep.replace('.', '/') + '.java')), None)
                if dep_file:
                    if dep_file not in visited:
                        if has_cycle(graph, dep_file, visited, stack):
                            return True
                    elif dep_file in stack:
                        return True
            stack.remove(start)
            return False
        if has_cycle(import_graph, file_name):
            confidence = 1.0
            reason = "Import cycle detected in project."
            reports.append(SmellReport(
                file_name, file_name, category, "Cyclic Dependency",
                f"File '{file_name}' is part of a cyclic dependency.",
                "?", confidence, "Yes", "Refactor dependencies, decouple modules", reason
            ))
        # God Package: package with many classes
        package_pattern = re.compile(r'package\s+([\w\.]+);', re.MULTILINE)
        package_name = None
        m = package_pattern.search(code)
        if m:
            package_name = m.group(1)
            class_count = sum(1 for f, c in file_contents.items() if f != file_name and f.startswith(package_name.replace('.', '/')))
            if class_count > 10:
                confidence = min(1.0, (class_count-10)/10 + 0.5)
                reason = f"Package '{package_name}' has {class_count} classes."
                reports.append(SmellReport(
                    file_name, package_name, category, "God Package",
                    f"Package '{package_name}' contains too many classes.",
                    "?", confidence, "Yes", "Split Package, Modularize", reason
                ))
        # Unstable Dependency: package depends on many others but few depend on it
        if package_name:
            outgoing = set()
            incoming = set()
            for f, c in file_contents.items():
                if f.startswith(package_name.replace('.', '/')):
                    outgoing.update(re.findall(r'import\s+([\w\.]+);', c))
                else:
                    if re.search(rf'import\s+{re.escape(package_name)}[\.;]', c):
                        incoming.add(f)
            if len(outgoing) > 5 and len(incoming) < 2:
                confidence = 0.8
                reason = f"Package '{package_name}' depends on {len(outgoing)} others, but only {len(incoming)} depend on it."
                reports.append(SmellReport(
                    file_name, package_name, category, "Unstable Dependency",
                    f"Package '{package_name}' is unstable (many outgoing, few incoming dependencies).",
                    "?", confidence, "Maybe", "Refactor dependencies, stabilize package", reason
                ))
        # Ambiguous Service: class/interface with generic/service name and few methods
        ambiguous_names = ["Service", "Manager", "Processor", "Handler", "Util"]
        class_pattern = re.compile(r'(class|interface)\s+(\w+)[^{]*\{', re.MULTILINE)
        for m in class_pattern.finditer(code):
            cname = m.group(2)
            if any(x.lower() in cname.lower() for x in ambiguous_names):
                method_count = len(re.findall(r'(public|private|protected)?\s+\w+\s+\w+\s*\([^)]*\)\s*\{', code))
                if method_count < 3:
                    confidence = 0.7
                    reason = f"Class/interface '{cname}' has ambiguous name and few methods."
                    reports.append(SmellReport(
                        file_name, cname, category, "Ambiguous Service",
                        f"Class/interface '{cname}' may be an ambiguous service.",
                        f"?", confidence, "Maybe", "Rename or clarify responsibility", reason
                    ))
        # Architecture Violation: class in wrong package or violates layering (simple heuristic)
        if package_name:
            if ("controller" in package_name and "service" in code) or ("service" in package_name and "dao" in code):
                confidence = 0.8
                reason = f"Class in package '{package_name}' references lower/higher layer."
                reports.append(SmellReport(
                    file_name, package_name, category, "Architecture Violation",
                    f"Class in package '{package_name}' may violate architecture layering.",
                    "?", confidence, "Yes", "Refactor to respect layering", reason
                ))
        return reports

class MiscSmellAgent:
    @staticmethod
    def detect(code, file_name, project_stats=None):
        reports = []
        category = "Miscellaneous or General Code Smells"
        # Magic Number
        for i, line in enumerate(code.splitlines(), 1):
            if re.search(r"[^\w]([0-9]{2,})[^\w]", line):
                confidence = 0.8
                reason = f"Possible magic number in line: {line.strip()}"
                reports.append(SmellReport(
                    file_name, "?", category, "Magic Number",
                    f"Possible magic number in line: {line.strip()}",
                    str(i), confidence, "Yes", "Replace with named constant", reason
                ))
        # Magic String
        for i, line in enumerate(code.splitlines(), 1):
            if re.search(r'"[A-Za-z]{4,}"', line):
                confidence = 0.7
                reason = f"Possible magic string in line: {line.strip()}"
                reports.append(SmellReport(
                    file_name, "?", category, "Magic String",
                    f"Possible magic string in line: {line.strip()}",
                    str(i), confidence, "Yes", "Replace with named constant", reason
                ))
        # Dead Code: unused methods (simple demo: methods never called in file)
        method_pattern = re.compile(r'(public|private|protected)?\s+\w+\s+(\w+)\s*\([^)]*\)\s*\{', re.MULTILINE)
        method_names = [m.group(2) for m in method_pattern.finditer(code)]
        for mname in method_names:
            if len(re.findall(rf'\b{re.escape(mname)}\b', code)) == 1:
                confidence = 0.9
                reason = f"Method '{mname}' is never called in this file."
                reports.append(SmellReport(
                    file_name, mname, category, "Dead Code",
                    f"Method '{mname}' appears to be unused.",
                    "?", confidence, "Yes", "Remove unused method", reason
                ))
        # Commented-Out Code
        for i, line in enumerate(code.splitlines(), 1):
            if re.match(r'\s*//.*;|\s*//.*\{', line):
                confidence = 0.7
                reason = f"Possible commented-out code in line: {line.strip()}"
                reports.append(SmellReport(
                    file_name, "?", category, "Commented-Out Code",
                    f"Possible commented-out code in line: {line.strip()}",
                    str(i), confidence, "Maybe", "Remove or clarify comment", reason
                ))
        # Too Many Comments
        comment_lines = [l for l in code.splitlines() if l.strip().startswith('//') or l.strip().startswith('/*')]
        if len(comment_lines) > len(code.splitlines()) * 0.3:
            confidence = 0.8
            reason = f"{len(comment_lines)} comment lines out of {len(code.splitlines())} total."
            reports.append(SmellReport(
                file_name, "?", category, "Too Many Comments",
                f"File has a high ratio of comments.",
                "?", confidence, "Maybe", "Remove unnecessary comments, improve code clarity", reason
            ))
        # Empty Catch Blocks
        for m in re.finditer(r'catch\s*\([^)]*\)\s*\{\s*\}', code):
            confidence = 0.9
            reason = "Empty catch block detected."
            reports.append(SmellReport(
                file_name, "?", category, "Empty Catch Block",
                f"Empty catch block detected.",
                f"{m.start()}-{m.end()}", confidence, "Yes", "Handle exception or log", reason
            ))
        # Exception Swallowing: catch block with only a comment or log
        for m in re.finditer(r'catch\s*\([^)]*\)\s*\{([^}]*)\}', code, re.DOTALL):
            body = m.group(1)
            if re.match(r'\s*(//.*|log\.|logger\.)', body.strip()):
                confidence = 0.8
                reason = "Catch block only logs or comments, may swallow exception."
                reports.append(SmellReport(
                    file_name, "?", category, "Exception Swallowing",
                    f"Catch block may swallow exception.",
                    f"{m.start()}-{m.end()}", confidence, "Maybe", "Rethrow or handle exception", reason
                ))
        # Logger Misuse: use of System.out/err instead of logger
        for i, line in enumerate(code.splitlines(), 1):
            if re.search(r'System\.(out|err)\.print', line):
                confidence = 0.8
                reason = f"System.out/err used for logging in line: {line.strip()}"
                reports.append(SmellReport(
                    file_name, "?", category, "Logger Misuse",
                    f"System.out/err used for logging.",
                    str(i), confidence, "Yes", "Use proper logger", reason
                ))
        return reports

class DependencySmellAgent:
    @staticmethod
    def detect(code, file_name, all_files, file_contents):
        reports = []
        category = "Package and Dependency Smells"
        # Fat Interface: interface with > 10 methods (already present)
        interface_pattern = re.compile(r'interface\s+(\w+)[^{]*\{', re.MULTILINE)
        for m in interface_pattern.finditer(code):
            iname = m.group(1)
            start = m.end() - 1
            brace_count = 1
            i = start
            while i < len(code) and brace_count > 0:
                i += 1
                if code[i-1] == '{':
                    brace_count += 1
                elif code[i-1] == '}':
                    brace_count -= 1
            ibody = code[start:i-1]
            method_count = len(re.findall(r'\w+\s+\w+\s*\([^)]*\)\s*;', ibody))
            threshold = 10
            if method_count > threshold:
                confidence = min(1.0, (method_count-threshold)/threshold + 0.5)
                reason = f"Interface '{iname}' has {method_count} methods."
                reports.append(SmellReport(
                    file_name, iname, category, "Fat Interface",
                    f"Interface '{iname}' has {method_count} methods.",
                    f"{m.start()}-{i}", confidence, "Yes", "Split Interface, Apply Interface Segregation", reason
                ))
        # Unbalanced Abstractions: package with many concrete classes, few abstractions
        package_pattern = re.compile(r'package\s+([\w\.]+);', re.MULTILINE)
        m = package_pattern.search(code)
        if m:
            package_name = m.group(1)
            concrete = 0
            abstractions = 0
            for f, c in file_contents.items():
                if f.startswith(package_name.replace('.', '/')):
                    if re.search(r'(abstract\s+class|interface)\s+\w+', c):
                        abstractions += 1
                    elif re.search(r'class\s+\w+', c):
                        concrete += 1
            if concrete > 5 and abstractions < 2:
                confidence = 0.8
                reason = f"{concrete} concrete classes, {abstractions} abstractions in package."
                reports.append(SmellReport(
                    file_name, package_name, category, "Unbalanced Abstractions",
                    f"Package '{package_name}' has many concrete classes and few abstractions.",
                    "?", confidence, "Yes", "Add abstractions, refactor package", reason
                ))
        # Insufficient Modularization: package with too many classes
        if m:
            package_name = m.group(1)
            class_count = sum(1 for f, c in file_contents.items() if f.startswith(package_name.replace('.', '/')) and re.search(r'class\s+\w+', c))
            if class_count > 15:
                confidence = min(1.0, (class_count-15)/10 + 0.5)
                reason = f"Package '{package_name}' has {class_count} classes."
                reports.append(SmellReport(
                    file_name, package_name, category, "Insufficient Modularization",
                    f"Package '{package_name}' may lack modularization (too many classes).",
                    "?", confidence, "Yes", "Split package, modularize", reason
                ))
        # Dependency Concentration: class/package with many incoming dependencies
        if m:
            package_name = m.group(1)
            incoming = 0
            for f, c in file_contents.items():
                if f != file_name and re.search(rf'import\s+{re.escape(package_name)}[\.;]', c):
                    incoming += 1
            if incoming > 8:
                confidence = min(1.0, (incoming-8)/8 + 0.5)
                reason = f"Package '{package_name}' has {incoming} incoming dependencies."
                reports.append(SmellReport(
                    file_name, package_name, category, "Dependency Concentration",
                    f"Package '{package_name}' is a dependency concentration point.",
                    "?", confidence, "Yes", "Refactor, reduce coupling", reason
                ))
        return reports

class SmellAgent:
    @staticmethod
    def detect(code, file_name, all_files=None, file_contents=None, project_stats=None):
        results = []
        results += ClassSmellAgent.detect(code, file_name, project_stats, all_files, file_contents)
        results += MethodSmellAgent.detect(code, file_name, project_stats)
        results += FieldSmellAgent.detect(code, file_name)
        results += ArchitectureSmellAgent.detect(code, file_name, all_files, file_contents)
        results += MiscSmellAgent.detect(code, file_name, project_stats)
        results += DependencySmellAgent.detect(code, file_name, all_files, file_contents)
        return [r.as_dict() for r in results]

def detect_code_smells(code, file_name, all_files=None, file_contents=None, project_stats=None):
    return SmellAgent.detect(code, file_name, all_files, file_contents, project_stats)

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
def analyze_structural_metrics(code, tree, fallback=False):
    lines = code.splitlines()
    loc = len(lines)
    eloc = len([l for l in lines if l.strip() and not l.strip().startswith('//') and not l.strip().startswith('/*')])
    if fallback or not tree:
        class_count = len(re.findall(r'class\s+\w+', code))
        interface_count = len(re.findall(r'interface\s+\w+', code))
        method_count = len(re.findall(r'(public|private|protected)?\s+\w+\s+\w+\s*\([^)]*\)\s*\{', code))
        field_count = len(re.findall(r'(public|private|protected)?\s+\w+\s+\w+\s*(=|;)', code))
        accessor_count = len(re.findall(r'(get|set)\w+\s*\(', code))
        package_count = len(re.findall(r'package\s+[\w\.]+;', code))
        return {
            'Lines of Code (LOC)': loc,
            'Effective Lines of Code (eLOC)': eloc,
            'Number of Classes': class_count,
            'Number of Interfaces': interface_count,
            'Number of Methods per Class': method_count / class_count if class_count else 0,
            'Number of Fields per Class': field_count / class_count if class_count else 0,
            'Number of Packages': package_count,
            'Maximum Class Size': 0,
            'Maximum Method Size (in LOC)': 0,
            'Number of Accessors (getters/setters)': accessor_count
        }
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

def analyze_complexity_metrics(code, tree, fallback=False, debug=None):
    if fallback or not tree:
        # Find all methods
        method_pattern = re.compile(r'(public|private|protected)?\s+\w+\s+(\w+)\s*\([^)]*\)\s*\{', re.MULTILINE)
        method_spans = [(m.start(), m.end(), m.group(2)) for m in method_pattern.finditer(code)]
        lines = code.splitlines()
        method_metrics = []
        for idx, (start, end, mname) in enumerate(method_spans):
            # Find method body (naive brace matching)
            brace_count = 0
            body_start = code.find('{', end-1)
            if body_start == -1:
                continue
            i = body_start
            while i < len(code):
                if code[i] == '{':
                    brace_count += 1
                elif code[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        break
                i += 1
            method_body = code[body_start+1:i] if brace_count == 0 else code[body_start+1:]
            # Cyclomatic: 1 + decision points
            cyclomatic = 1 + len(re.findall(r'\b(if|for|while|case|catch|throw)\b', method_body))
            cyclomatic += len(re.findall(r'&&|\|\|', method_body))
            cyclomatic += len(re.findall(r'\?\s*:', method_body))  # ternary
            # Cognitive: +1 for each decision, +1 for each nesting level
            cognitive = 0
            nest = 0
            max_nest = 0
            for c in method_body:
                if c == '{':
                    nest += 1
                    max_nest = max(max_nest, nest)
                elif c == '}':
                    nest -= 1
            cognitive += len(re.findall(r'\b(if|for|while|case|catch|throw|else|finally|break|continue|return)\b', method_body))
            cognitive += max_nest
            # Switch complexity: number of case statements in method
            switch_complexity = len(re.findall(r'switch\s*\(', method_body))
            case_count = len(re.findall(r'case\s+[^:]+:', method_body))
            # Control flow: all control flow statements
            control_flow = len(re.findall(r'\b(if|for|while|do|switch|case|catch|throw)\b', method_body))
            # Number of conditions
            num_conditions = len(re.findall(r'\b(if|else if|while|for|case)\b', method_body))
            method_metrics.append({
                'name': mname,
                'cyclomatic': cyclomatic,
                'cognitive': cognitive,
                'nesting': max_nest,
                'switch': switch_complexity,
                'case': case_count,
                'control_flow': control_flow,
                'num_conditions': num_conditions
            })
        # Aggregate
        if method_metrics:
            cyclomatic_total = sum(m['cyclomatic'] for m in method_metrics)
            cognitive_total = sum(m['cognitive'] for m in method_metrics)
            max_nesting = max(m['nesting'] for m in method_metrics)
            switch_total = sum(m['switch'] for m in method_metrics)
            control_flow_total = sum(m['control_flow'] for m in method_metrics)
            avg_conditions = sum(m['num_conditions'] for m in method_metrics) / len(method_metrics)
        else:
            cyclomatic_total = cognitive_total = max_nesting = switch_total = control_flow_total = avg_conditions = 0
        if debug is not None:
            debug['complexity_methods'] = method_metrics
        return {
            'Cyclomatic Complexity (approx)': cyclomatic_total,
            'Cognitive Complexity (approx)': cognitive_total,
            'Nesting Depth (approx)': max_nesting,
            'Switch Complexity': switch_total,
            'Control Flow Complexity': control_flow_total,
            'Number of Conditions per Method (approx)': round(avg_conditions, 2)
        }
    # If not fallback, use the original logic
    cyclomatic = len(re.findall(r'\\b(if|for|while|case|catch|throw|&&|\\|\\|)\\b', code)) + 1
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

def analyze_coupling_metrics(code, tree, fallback=False, file_path=None, all_files=None, file_contents=None):
    # Use DependencyAgent if project context is available
    if all_files is not None and file_contents is not None and file_path is not None:
        dep_result = DependencyAgent.analyze(file_path, code, all_files, file_contents)
        fan_in = len(dep_result['incoming'])
        fan_out = len(dep_result['outgoing'])
        ext_deps = fan_in  # For Java, external dependencies are typically imports (fan-in)
    else:
        # Improved regex for imports (fan-in) and object creation (fan-out)
        fan_in = len(re.findall(r'^\s*import\s+[\w\.\*]+;', code, re.MULTILINE))
        # Fan-out: count unique class names instantiated (new ClassName())
        fan_out = len(set(re.findall(r'new\s+([A-Z][A-Za-z0-9_]*)\s*\(', code)))
        ext_deps = fan_in
    cbo = len(re.findall(r'\bimplements\b', code)) + len(re.findall(r'\bextends\b', code))
    rfc = len(re.findall(r'\bpublic\s+\w+\s+\w+\s*\(', code))
    ca = fan_in  # For Java, Ca is the number of classes that depend on this class (approx. fan-in)
    # Remove Ce and Instability (not relevant for Java)
    return {
        'Coupling Between Object Classes (CBO)': cbo,
        'Response for a Class (RFC)': rfc,
        'Fan-In': fan_in,
        'Fan-Out': fan_out,
        'Afferent Coupling (Ca)': ca,
        'Number of External Dependencies': ext_deps
    }

def extract_classes_with_braces(code):
    # Returns a list of (class_name, class_body) tuples
    classes = []
    pattern = re.compile(r'class\s+(\w+)[^{]*\{', re.MULTILINE)
    for match in pattern.finditer(code):
        class_name = match.group(1)
        start = match.end() - 1
        brace_count = 1
        i = start
        while i < len(code) and brace_count > 0:
            i += 1
            if code[i-1] == '{':
                brace_count += 1
            elif code[i-1] == '}':
                brace_count -= 1
        class_body = code[start:i-1]
        classes.append((class_name, class_body))
    return classes

def analyze_cohesion_metrics(code, tree, fallback=False, debug=None):
    result = {
        'Lack of Cohesion in Methods (LCOM)': 0,
        'Tight Class Cohesion (TCC)': 0,
        'Number of Method Pairs Sharing Fields': 0
    }
    if fallback or not tree:
        if debug is not None:
            debug['cohesion_classes'] = []
        class_blocks = extract_classes_with_braces(code)
        lcom_total = 0
        tcc_total = 0
        method_pairs_total = 0
        for class_name, class_body in class_blocks:
            # Improved field regex: supports annotations, modifiers, multiline, and initialization
            field_pattern = re.compile(r'(?:@[\w]+\s*)*(?:private|protected|public|static|final|transient|volatile|\s)*\s*([\w\<\>\[\]]+)\s+(\w+)\s*(=|;)', re.MULTILINE)
            fields = field_pattern.findall(class_body)
            field_names = [f[1] for f in fields]
            # Improved method regex: supports annotations, modifiers, multiline
            method_pattern = re.compile(r'(?:@[\w]+\s*)*(?:public|private|protected|static|final|synchronized|abstract|native|\s)*\s*[\w\<\>\[\]]+\s+(\w+)\s*\([^)]*\)\s*\{', re.MULTILINE)
            method_iter = list(method_pattern.finditer(class_body))
            methods = []
            for idx, m in enumerate(method_iter):
                mname = m.group(1)
                start = m.end() - 1
                brace_count = 1
                i = start
                while i < len(class_body) and brace_count > 0:
                    i += 1
                    if class_body[i-1] == '{':
                        brace_count += 1
                    elif class_body[i-1] == '}':
                        brace_count -= 1
                mbody = class_body[start:i-1]
                methods.append((mname, mbody))
            method_field_usage = []
            for mname, mbody in methods:
                # Support both 'field' and 'this.field' usage
                used_fields = [fname for fname in field_names if re.search(r'\b(this\.)?'+re.escape(fname)+r'\b', mbody)]
                method_field_usage.append(set(used_fields))
            lcom = 0
            tcc = 0
            pairs = 0
            for i in range(len(method_field_usage)):
                for j in range(i+1, len(method_field_usage)):
                    pairs += 1
                    if method_field_usage[i] and method_field_usage[j]:
                        if method_field_usage[i].intersection(method_field_usage[j]):
                            tcc += 1
                        else:
                            lcom += 1
            lcom_total += lcom
            tcc_total += tcc
            method_pairs_total += pairs
            if debug is not None:
                debug['cohesion_classes'].append({
                    'class_name': class_name,
                    'fields': field_names,
                    'methods': [m[0] for m in methods],
                    'method_field_usage': [list(u) for u in method_field_usage],
                    'lcom': lcom,
                    'tcc': tcc,
                    'pairs': pairs
                })
        result['Lack of Cohesion in Methods (LCOM)'] = lcom_total
        result['Tight Class Cohesion (TCC)'] = tcc_total
        result['Number of Method Pairs Sharing Fields'] = method_pairs_total
        return result
    # If not fallback, return the default result
    return result

def analyze_oo_metrics(code, tree, fallback=False, debug=None):
    if fallback or not tree:
        if debug is not None:
            debug['oo_classes'] = []
            debug['oo_code_head'] = code[:500]
        # Improved regex for class/interface/abstract class extraction (robust for inner classes, generics, annotations, multiline)
        class_pattern = re.compile(r'(?:@[\w]+\s*)*(abstract\s+)?class\s+(\w+)(?:\s+extends\s+([\w<>]+))?(?:\s+implements\s+([\w,\s<>]+))?', re.MULTILINE)
        interface_pattern = re.compile(r'(?:@[\w]+\s*)*interface\s+(\w+)', re.MULTILINE)
        method_pattern = re.compile(r'(?:@[\w]+\s*)*(?:public|private|protected|static|final|synchronized|abstract|native|\s)*\s*[\w\<\>\[\]]+\s+(\w+)\s*\([^)]*\)\s*\{', re.MULTILINE)
        override_pattern = re.compile(r'@Override', re.MULTILINE)
        field_pattern = re.compile(r'(?:@[\w]+\s*)*(?:private|protected|public|static|final|transient|volatile|\s)*\s*([\w\<\>\[\]]+)\s+(\w+)\s*(=|;)', re.MULTILINE)
        # Find all classes and interfaces
        parents = {}
        children = {}
        abstract_classes = set()
        interfaces = set(interface_pattern.findall(code))
        class_defs = {}
        for m in class_pattern.finditer(code):
            is_abstract = m.group(1) is not None
            cname = m.group(2)
            parent = m.group(3)
            impls = m.group(4)
            if is_abstract:
                abstract_classes.add(cname)
            if parent:
                parents[cname] = parent
                children.setdefault(parent, []).append(cname)
            if impls:
                for iface in [i.strip() for i in impls.split(',') if i.strip()]:
                    parents[cname + ':' + iface] = iface
                    children.setdefault(iface, []).append(cname)
            class_defs[cname] = {'abstract': is_abstract, 'parent': parent, 'implements': impls, 'methods': [], 'fields': [], 'overrides': 0}
        # Find methods and fields for each class
        for cname in class_defs:
            # Find class body (robust for inner classes)
            class_body_pattern = re.compile(r'class\s+' + re.escape(cname) + r'[^{]*\{', re.MULTILINE)
            class_body_match = class_body_pattern.search(code)
            if not class_body_match:
                continue
            start = class_body_match.end() - 1
            brace_count = 1
            i = start
            while i < len(code) and brace_count > 0:
                i += 1
                if code[i-1] == '{':
                    brace_count += 1
                elif code[i-1] == '}':
                    brace_count -= 1
            class_body = code[start:i-1]
            # Methods
            methods = method_pattern.findall(class_body)
            class_defs[cname]['methods'] = methods
            # Fields
            fields = field_pattern.findall(class_body)
            class_defs[cname]['fields'] = [f[1] for f in fields]
            # Overrides
            class_defs[cname]['overrides'] = len(override_pattern.findall(class_body))
        # WMC: total number of methods
        wmc = sum(len(class_defs[c]['methods']) for c in class_defs)
        # DIT: max inheritance depth
        def get_dit(cls):
            depth = 0
            while cls in parents:
                cls = parents[cls]
                depth += 1
            return depth
        dit = max([get_dit(c) for c in class_defs] or [0])
        # NOC: number of children (subclasses)
        noc = sum(len(children[c]) for c in children if c in class_defs)
        # MIF/AIF: ratio of overridden methods/fields to total methods/fields
        total_methods = sum(len(class_defs[c]['methods']) for c in class_defs)
        total_fields = sum(len(class_defs[c]['fields']) for c in class_defs)
        total_overrides = sum(class_defs[c]['overrides'] for c in class_defs)
        mif = total_overrides / (total_methods or 1)
        aif = 0  # Not enough info for attribute inheritance in fallback
        # Abstractness: (abstract classes + interfaces) / total types
        total_types = len(class_defs) + len(interfaces)
        abstractness = (len(abstract_classes) + len(interfaces)) / (total_types or 1)
        # Specialization Index: overridden methods / total methods
        specialization = total_overrides / (total_methods or 1)
        if debug is not None:
            debug['oo_classes'] = [{
                'class_name': c,
                'parent': class_defs[c]['parent'],
                'implements': class_defs[c]['implements'],
                'methods': class_defs[c]['methods'],
                'fields': class_defs[c]['fields'],
                'overrides': class_defs[c]['overrides']
            } for c in class_defs]
            debug['oo_inheritance'] = {'parents': parents, 'children': children, 'abstract_classes': list(abstract_classes), 'interfaces': list(interfaces)}
            if not class_defs:
                debug['oo_warning'] = 'No classes detected. This file may not contain any class definitions.'
        return {
            'Weighted Methods per Class (WMC)': wmc,
            'Depth of Inheritance Tree (DIT)': dit,
            'Number of Children (NOC)': noc,
            'Method Inheritance Factor (MIF)': round(mif, 2),
            'Attribute Inheritance Factor (AIF)': round(aif, 2),
            'Abstractness (A)': round(abstractness, 2),
            'Specialization Index': round(specialization, 2)
        }
    # If not fallback, use the original logic
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

def analyze_maintainability_metrics(code, tree, fallback=False):
    if fallback or not tree:
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

def analyze_reliability_metrics(code, tree, fallback=False):
    if fallback or not tree:
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

def analyze_duplication_metrics(code, tree, fallback=False):
    if fallback or not tree:
        duplicated_blocks = len(re.findall(r'(\bif\b|\bfor\b|\bwhile\b|\bswitch\b)', code))
        duplicated_lines = len([l for l in code.splitlines() if code.splitlines().count(l) > 1])
        similar_methods = len(re.findall(r'(public|private|protected)?\s+\w+\s+\w+\s*\([^)]*\)\s*\{', code))
        return {
            'Number of Duplicated Blocks': duplicated_blocks,
            'Duplicated Lines Density (%)': duplicated_lines,
            'Number of Similar Methods': similar_methods
        }
    duplicated_blocks = 0
    duplicated_lines = 0
    similar_methods = 0
    return {
        'Number of Duplicated Blocks': duplicated_blocks,
        'Duplicated Lines Density (%)': duplicated_lines,
        'Number of Similar Methods': similar_methods
    }

def analyze_documentation_metrics(code, tree, fallback=False):
    if fallback or not tree:
        todo_tags = len(re.findall(r'TODO|FIXME', code))
        naming_violations = len(re.findall(r'[^a-zA-Z0-9_](var|tmp|foo|bar)[^a-zA-Z0-9_]', code))
        blank_line_density = len([l for l in code.splitlines() if not l.strip()]) / (len(code.splitlines()) or 1)
        identifier_length = sum(len(m) for m in re.findall(r'\b\w+\b', code)) / (len(re.findall(r'\b\w+\b', code)) or 1)
        return {
            'Number of TODO / FIXME Tags': todo_tags,
            'Naming Convention Violations': naming_violations,
            'Blank Line Density': blank_line_density,
            'Identifier Length Average': identifier_length
        }
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

def analyze_security_metrics(code, tree, fallback=False):
    if fallback or not tree:
        hardcoded_creds = len(re.findall(r'password|passwd|secret|api[_-]?key', code, re.IGNORECASE))
        deprecated_apis = len(re.findall(r'@Deprecated', code))
        unused_imports = len(re.findall(r'import\s+\w+;\s*$', code, re.MULTILINE))
        missing_modifiers = len(re.findall(r'(public|private|protected)?\s+\w+\s+\w+\s*;', code))
        public_data_members = len(re.findall(r'public\s+\w+\s+\w+;', code))
        unsafe_casts = len(re.findall(r'\([A-Za-z0-9_]+\)\s*\w+', code))
        return {
            'Number of Hardcoded Credentials': hardcoded_creds,
            'Use of Deprecated APIs': deprecated_apis,
            'Unused Imports or Variables': unused_imports,
            'Missing or Incomplete Access Modifiers': missing_modifiers,
            'Public Data Members Count': public_data_members,
            'Unsafe Type Casts': unsafe_casts
        }
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
    fallback = False
    debug = {}
    javalang_exc = None
    try:
        import javalang
        tree = list(javalang.parse.parse(code))
    except Exception as e:
        tree = []
        fallback = True
        javalang_exc = str(e)
    # Gather project context if available
    all_files = None
    file_contents = None
    if 'uploaded_files' in st.session_state:
        all_files = [f['name'] for f in st.session_state['uploaded_files']]
        file_contents = {f['name']: (f['content'].decode('utf-8', errors='ignore') if 'content' in f else '') for f in st.session_state['uploaded_files']}
    metrics = {}
    metrics['Structural Metrics'] = analyze_structural_metrics(code, tree, fallback)
    metrics['Complexity Metrics'] = analyze_complexity_metrics(code, tree, fallback, debug)
    metrics['Coupling and Dependency Metrics'] = analyze_coupling_metrics(
        code, tree, fallback, file_path=file_path, all_files=all_files, file_contents=file_contents)
    metrics['Cohesion Metrics'] = analyze_cohesion_metrics(code, tree, fallback, debug)
    metrics['Object-Oriented Design Metrics'] = analyze_oo_metrics(code, tree, fallback, debug)
    metrics['Maintainability and Readability'] = analyze_maintainability_metrics(code, tree, fallback)
    metrics['Reliability and Testability Metrics'] = analyze_reliability_metrics(code, tree, fallback)
    metrics['Code Duplication and Redundancy'] = analyze_duplication_metrics(code, tree, fallback)
    metrics['Documentation and Style'] = analyze_documentation_metrics(code, tree, fallback)
    metrics['Security and Quality Flags'] = analyze_security_metrics(code, tree, fallback)
    if fallback:
        metrics['_warnings'] = ["javalang parsing failed, using regex/statistical fallback. Metrics are approximate."]
        if javalang_exc:
            metrics['_debug'] = {'javalang_exception': javalang_exc}
        metrics['_debug'] = metrics.get('_debug', {})
        metrics['_debug'].update(debug)
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
        # Debug output for troubleshooting file reading
        try:
            st.warning(f"[DEBUG] File path: {file_path}")
            if file_path and os.path.exists(file_path):
                st.warning(f"[DEBUG] File size: {os.path.getsize(file_path)} bytes")
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    preview = f.read(200)
                st.warning(f"[DEBUG] File preview: {preview}")
            else:
                st.warning("[DEBUG] File does not exist at path.")
        except Exception as e:
            st.warning(f"[DEBUG] Exception while reading file: {e}")
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

    # Show warning if fallback was used
    if '_warnings' in metrics:
        for w in metrics['_warnings']:
            st.warning(w)
    # Expand Debug Info by default if fallback was used
    if '_debug' in metrics:
        debug_expanded = '_warnings' in metrics  # expand if fallback
        st.expander("Debug Info", expanded=debug_expanded).write(metrics['_debug'])

    # --- Main Tabs ---
    main_tabs = st.tabs(["Code Metrics", "Dependencies", "Code Smells"])
    with main_tabs[0]:
        # --- Dropdown for Metric Category ---
        metric_categories = [k for k in metrics.keys() if not k.startswith('_')]
        selected_category = st.selectbox("Select a metric category:", metric_categories, key="category_dropdown")
        group_metrics = metrics[selected_category]
        st.write(f"DEBUG: {selected_category} group_metrics type: {type(group_metrics)} value: {group_metrics}")
        if not isinstance(group_metrics, dict):
            st.error(f"Metrics for '{selected_category}' are not available due to an internal error. Type: {type(group_metrics)} Value: {group_metrics}")
            st.stop()
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
            if group.startswith('_'):
                continue
            if not isinstance(group_metrics, dict):
                continue
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
        # --- Dependency Analysis ---
        all_files = [f["name"] for f in files]
        file_contents = {f["name"]: (f["content"].decode("utf-8", errors="ignore") if "content" in f else "") for f in files}
        # Only analyze dependencies for the selected file (fast)
        with st.spinner("Analyzing dependencies for selected file..."):
            dep_result = DependencyAgent.analyze(selected_file, code_content, all_files, file_contents)
        incoming = dep_result["incoming"]
        outgoing = dep_result["outgoing"]
        all_files = dep_result["all_files"]

        st.markdown(f"**Selected file:** `{selected_file}`")
        st.markdown(f"**Incoming dependencies:** {len(incoming)}")
        st.markdown(f"**Outgoing dependencies:** {len(outgoing)}")

        # --- Display incoming and outgoing files in a compact, readable way ---
        def short_name(path):
            return os.path.basename(path)
        st.markdown("<style> .dep-table td {padding: 4px 12px;} .dep-table tr:hover {background: #f6f6f6;} </style>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Files that depend on this file (incoming):**")
            if incoming:
                st.markdown('<table class="dep-table">' + ''.join(
                    f'<tr><td title="{f}">{short_name(f)}</td></tr>' for f in incoming
                ) + '</table>', unsafe_allow_html=True)
            else:
                st.info("No incoming dependencies detected.")
        with col2:
            st.markdown("**Files this file depends on (outgoing):**")
            if outgoing:
                st.markdown('<table class="dep-table">' + ''.join(
                    f'<tr><td title="{f}">{short_name(f)}</td></tr>' for f in outgoing
                ) + '</table>', unsafe_allow_html=True)
            else:
                st.info("No outgoing dependencies detected.")

        # --- Build Simplified Dependency Graph (selected file + direct deps only) ---
        G = nx.DiGraph()
        G.add_node(selected_file)
        for dep in outgoing:
            G.add_node(dep)
            G.add_edge(selected_file, dep)
        for dep in incoming:
            G.add_node(dep)
            G.add_edge(dep, selected_file)
        # --- Cycle Detection ---
        try:
            cycles = list(nx.simple_cycles(G))
        except Exception:
            cycles = []
        has_cycle = any(selected_file in c for c in cycles)
        cycle_nodes = set()
        for c in cycles:
            if selected_file in c:
                cycle_nodes.update(c)
        # Node colors: selected (green), outgoing (blue), incoming (red), cycle (orange)
        node_colors = []
        node_labels = []
        node_hover = []
        for n in G.nodes():
            if n == selected_file:
                node_colors.append("#52c41a")  # green always for selected
            elif n in cycle_nodes:
                node_colors.append("#faad14")  # orange for cycle (not selected)
            elif n in outgoing:
                node_colors.append("#1890ff")  # blue
            elif n in incoming:
                node_colors.append("#ff4d4f")  # red
            node_labels.append(short_name(n))
            node_hover.append(n)
        pos = nx.spring_layout(G, seed=42, k=0.7, iterations=50)
        edge_x = []
        edge_y = []
        for src, dst in G.edges():
            x0, y0 = pos[src]
            x1, y1 = pos[dst]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]
        node_x = [pos[n][0] for n in G.nodes()]
        node_y = [pos[n][1] for n in G.nodes()]
        edge_trace = go.Scatter(x=edge_x, y=edge_y, line=dict(width=1, color="#888"), hoverinfo='none', mode='lines')
        node_trace = go.Scatter(
            x=node_x, y=node_y, mode='markers+text',
            marker=dict(size=18, color=node_colors, line=dict(width=2, color='#333')),
            text=node_labels,
            textposition="bottom center",
            hoverinfo='text',
            hovertext=node_hover
        )
        fig = go.Figure(data=[edge_trace, node_trace])
        fig.update_layout(
            title="File Dependency Network (Selected File)",
            showlegend=False,
            margin=dict(l=10, r=10, t=40, b=10),
            height=500,
            plot_bgcolor="#fff",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        )
        st.plotly_chart(fig, use_container_width=True)
        legend = """
        **Legend:**
        - <span style='color:#52c41a;font-weight:bold;'>Green</span>: Selected file
        - <span style='color:#1890ff;font-weight:bold;'>Blue</span>: Outgoing dependencies (files this file depends on)
        - <span style='color:#ff4d4f;font-weight:bold;'>Red</span>: Incoming dependencies (files that depend on this file)
        - <span style='color:#faad14;font-weight:bold;'>Orange</span>: File(s) involved in a dependency cycle
        """
        st.markdown(legend, unsafe_allow_html=True)
        if has_cycle:
            st.warning(f"Dependency cycle detected involving: {', '.join(short_name(n) for n in cycle_nodes)}. Cycles can cause maintenance and build issues.")

        # --- Dependency Impact Score ---
        impact_score = len(incoming) * len(outgoing)
        st.markdown(f"**Dependency Impact Score:** <span style='font-size:1.3em;font-weight:bold;'>{impact_score}</span>", unsafe_allow_html=True)
        if impact_score >= 16:
            st.info("High impact: This file is both widely used and highly dependent on others. Refactoring or changes here may have broad effects.")
        elif impact_score >= 6:
            st.info("Moderate impact: This file is important in the dependency network.")
        else:
            st.info("Low impact: This file is not a major hub in the dependency network.")

    with main_tabs[2]:
        st.markdown("### Code Smells")
        smell_tabs = st.tabs(["All Code Smells in Project", "Code Smells in Selected File"])
        all_files = [f["name"] for f in files]
        file_contents = {f["name"]: (f["content"].decode("utf-8", errors="ignore") if "content" in f else "") for f in files}
        project_stats = compute_project_stats(all_files, file_contents)
        # --- Tab 1: All Code Smells in Project ---
        with smell_tabs[0]:
            if "all_smells" not in st.session_state:
                st.session_state["all_smells"] = None
            if st.button("Analyze All Files for Code Smells"):
                st.session_state["all_smells"] = None  # Reset before running
                all_smells = []
                progress = st.progress(0, text="Analyzing files...")
                debug_area = st.empty()
                for i, fname in enumerate(all_files):
                    fcode = file_contents[fname]
                    debug_area.info(f"Analyzing: {fname} ({i+1}/{len(all_files)})")
                    try:
                        smells = detect_code_smells(fcode, fname, all_files, file_contents, project_stats)
                        all_smells.extend(smells)
                    except Exception as e:
                        debug_area.error(f"Error analyzing {fname}: {e}")
                    progress.progress((i+1)/len(all_files), text=f"{i+1} of {len(all_files)} files analyzed")
                progress.empty()
                debug_area.empty()
                st.session_state["all_smells"] = all_smells
            if st.session_state["all_smells"] is not None:
                all_smells = st.session_state["all_smells"]
                if not all_smells:
                    st.success("No significant code smells detected in the project.")
                else:
                    df = pd.DataFrame(all_smells)
                    # --- Summary Cards ---
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Total Code Smells", len(df))
                    col2.metric("Files with Smells", df['File Name'].nunique())
                    most_common = df['Type of Code Smell'].mode()[0] if not df.empty else "-"
                    col3.metric("Most Common Smell", most_common)
                    
                    if not df.empty:
                        fig = px.pie(df, names='Type of Code Smell', title='Code Smell Distribution', hole=0.4)
                        st.plotly_chart(fig, use_container_width=True)
                    # --- Filters ---
                    min_confidence = st.slider("Minimum Confidence", 0.0, 1.0, 0.7, 0.05, key="proj_confidence")
                    all_types = df["Type of Code Smell"].unique().tolist()
                    selected_types = st.multiselect("Show only these code smell types:", all_types, default=all_types, key="proj_types")
                    filtered_df = df[(df["Confidence"] >= min_confidence) & (df["Type of Code Smell"].isin(selected_types))]
                    st.dataframe(filtered_df, use_container_width=True)
                    st.download_button("Download Project Code Smell Report (CSV)", data=filtered_df.to_csv(index=False), file_name="project_code_smell_report.csv", mime="text/csv")
                    st.download_button("Download Project Code Smell Report (JSON)", data=filtered_df.to_json(orient='records', indent=2), file_name="project_code_smell_report.json", mime="application/json")
            else:
                st.info("Click the button above to analyze all files for code smells.")

        # --- Tab 2: Code Smells in Selected File ---
        with smell_tabs[1]:
            smell_report = detect_code_smells(code_content, selected_file, all_files, file_contents, project_stats)
            if not smell_report:
                st.success("No code smells detected in the selected file.")
            else:
                st.markdown(f"### Code Smells in `{selected_file}`")
                st.write(f"**Total code smells:** {len(smell_report)}")
                df = pd.DataFrame(smell_report)
                # --- Summary Cards ---
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Code Smells", len(df))
                col2.metric("Type Count", df['Type of Code Smell'].nunique())
                most_common = df['Type of Code Smell'].mode()[0] if not df.empty else "-"
                col3.metric("Most Common Smell", most_common)
                
                if not df.empty:
                    fig = px.pie(df, names='Type of Code Smell', title='Code Smell Distribution', hole=0.4)
                    st.plotly_chart(fig, use_container_width=True)
                # --- Filters ---
                min_confidence = st.slider("Minimum Confidence", 0.0, 1.0, 0.7, 0.05, key="file_confidence")
                all_types = df["Type of Code Smell"].unique().tolist()
                selected_types = st.multiselect("Show only these code smell types:", all_types, default=all_types, key="file_types")
                filtered_df = df[(df["Confidence"] >= min_confidence) & (df["Type of Code Smell"].isin(selected_types))]
                category_order = [
                    "Class-Level Code Smells",
                    "Method-Level Code Smells",
                    "Field-Level Code Smells",
                    "Architecture-Level Code Smells",
                    "Package and Dependency Smells",
                    "Miscellaneous or General Code Smells"
                ]
                for category in category_order:
                    cat_df = filtered_df[filtered_df["Category"] == category]
                    if not cat_df.empty:
                        with st.expander(f"{category} ({len(cat_df)})", expanded=True):
                            st.dataframe(cat_df.drop(columns=["File Name", "Category"]), use_container_width=True)
                st.download_button("Download Code Smell Report (CSV)", data=filtered_df.to_csv(index=False), file_name="code_smell_report_selected_file.csv", mime="text/csv")
                st.download_button("Download Code Smell Report (JSON)", data=filtered_df.to_json(orient='records', indent=2), file_name="code_smell_report_selected_file.json", mime="application/json")