"""
WinSifter — File Organizer
Sorts files in a chosen directory into categorized subfolders.

Version 1.0

Copyleft ©️ 2026 Paul R. Charovkine

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog

import customtkinter as ctk

# ── Constants ─────────────────────────────────────────────────────────────────

APP_NAME = "WinSifter"
APPDATA  = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home())) / APP_NAME
CFG_FILE = APPDATA / "config.json"

DEFAULT_CATEGORIES = [
    {
        "name": "Shortcuts",
        "folder": "Shortcuts",
        "enabled": True,
        "extensions": [".lnk", ".url"],
    },
    {
        "name": "Documents",
        "folder": "Documents",
        "enabled": True,
        "extensions": [".txt", ".doc", ".docx", ".pdf", ".odt", ".rtf", ".md", ".pages"],
    },
    {
        "name": "Images",
        "folder": "Images",
        "enabled": True,
        "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".svg", ".ico", ".webp"],
    },
    {
        "name": "Videos",
        "folder": "Videos",
        "enabled": True,
        "extensions": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".m4v", ".webm"],
    },
    {
        "name": "Audio",
        "folder": "Audio",
        "enabled": True,
        "extensions": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
    },
    {
        "name": "Archives",
        "folder": "Archives",
        "enabled": True,
        "extensions": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"],
    },
    {
        "name": "Spreadsheets",
        "folder": "Spreadsheets",
        "enabled": True,
        "extensions": [".xls", ".xlsx", ".csv", ".ods"],
    },
    {
        "name": "Presentations",
        "folder": "Presentations",
        "enabled": True,
        "extensions": [".ppt", ".pptx", ".odp"],
    },
    {
        "name": "EXE",
        "folder": "EXE",
        "enabled": True,
        "extensions": [".exe", ".msi"],
    },
    {
        "name": "Code",
        "folder": "Code",
        "enabled": True,
        "extensions": [
            ".py", ".js", ".ts", ".html", ".htm", ".css", ".java",
            ".cpp", ".c", ".cs", ".php", ".rb", ".go", ".sh", ".bat", ".ps1",
        ],
    },
    {
        "name": "Fonts",
        "folder": "Fonts",
        "enabled": True,
        "extensions": [".ttf", ".otf", ".woff", ".woff2"],
    },
    {
        "name": "E-books",
        "folder": "E-books",
        "enabled": True,
        "extensions": [".epub", ".mobi", ".azw", ".azw3", ".fb2", ".cbz", ".cbr"],
    },
    {
        "name": "Disk Images",
        "folder": "Disk-Images",
        "enabled": True,
        "extensions": [".iso", ".img", ".dmg", ".vhd", ".vhdx"],
    },
    {
        "name": "Torrents",
        "folder": "Torrents",
        "enabled": True,
        "extensions": [".torrent"],
    },
    # "Other" must stay last — it is the catch-all (no extensions = match everything unmatched)
    {
        "name": "Other",
        "folder": "Other",
        "enabled": True,
        "extensions": [],
    },
]

DEFAULT_CONFIG: dict = {
    "prefix":       "Sifter-",
    "move_folders": False,
    "recursive":    False,
    "categories":   DEFAULT_CATEGORIES,
}


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CFG_FILE.exists():
        try:
            with open(CFG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for key, val in DEFAULT_CONFIG.items():
                data.setdefault(key, val)
            return data
        except Exception:
            pass
    return _deep_copy(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    APPDATA.mkdir(parents=True, exist_ok=True)
    with open(CFG_FILE, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


def _deep_copy(obj):
    return json.loads(json.dumps(obj))


# ── Core sifter logic ─────────────────────────────────────────────────────────

def build_ext_map(cfg: dict) -> dict:
    """Returns {'.ext': 'dest_folder_name'} for all enabled, non-catch-all categories."""
    ext_map: dict[str, str] = {}
    for cat in cfg["categories"]:
        if not cat["enabled"] or not cat["extensions"]:
            continue
        dest = cfg["prefix"] + cat["folder"]
        for ext in cat["extensions"]:
            ext_map.setdefault(ext.lower(), dest)
    return ext_map


def get_other_folder(cfg: dict) -> str | None:
    for cat in cfg["categories"]:
        if cat["name"] == "Other" and cat["enabled"]:
            return cfg["prefix"] + cat["folder"]
    return None


def get_dest_folder_names(cfg: dict) -> set:
    """All destination folder names — used to skip already-sorted content."""
    names = set()
    for cat in cfg["categories"]:
        names.add(cfg["prefix"] + cat["folder"])
    names.add(cfg["prefix"] + "Folders")
    return names


def resolve_dest(path: pathlib.Path) -> pathlib.Path:
    """If path already exists, return a unique variant by appending _1, _2, ..."""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def plan_actions(target_dir: str, cfg: dict) -> list:
    target     = pathlib.Path(target_dir)
    ext_map    = build_ext_map(cfg)
    other_dest = get_other_folder(cfg)
    dest_names = get_dest_folder_names(cfg)
    prefix     = cfg["prefix"]
    folders_dest = prefix + "Folders"

    items = list(target.rglob("*")) if cfg["recursive"] else list(target.iterdir())

    actions = []
    for item in items:
        if item == target:
            continue
        # Skip anything already inside a destination folder
        try:
            rel = item.relative_to(target)
        except ValueError:
            continue
        if rel.parts[0] in dest_names:
            continue

        if item.is_dir():
            if cfg["move_folders"] and item.name not in dest_names:
                dest_dir      = target / folders_dest / item.name
                dest_resolved = resolve_dest(dest_dir)
                actions.append({
                    "type":     "folder",
                    "src":      item,
                    "dest":     dest_resolved,
                    "category": folders_dest,
                    "conflict": dest_resolved != dest_dir,
                })

        elif item.is_file():
            ext         = item.suffix.lower()
            dest_folder = ext_map.get(ext) or other_dest
            if dest_folder is None:
                continue
            dest_file     = target / dest_folder / item.name
            dest_resolved = resolve_dest(dest_file)
            actions.append({
                "type":     "file",
                "src":      item,
                "dest":     dest_resolved,
                "category": dest_folder,
                "conflict": dest_resolved != dest_file,
            })

    return actions


def execute_actions(actions: list, log_cb) -> dict:
    moved = renamed = errors = 0
    for action in actions:
        try:
            action["dest"].parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(action["src"]), str(action["dest"]))
            if action["conflict"]:
                renamed += 1
                log_cb(
                    f"  [RENAMED]  {action['src'].name}"
                    f"  →  {action['dest'].parent.name}\\{action['dest'].name}"
                )
            else:
                moved += 1
                log_cb(f"  [MOVED]    {action['src'].name}  →  {action['dest'].parent.name}\\")
        except Exception as exc:
            errors += 1
            log_cb(f"  [ERROR]    {action['src'].name}: {exc}")
    return {"moved": moved, "renamed": renamed, "errors": errors}


# ── GUI ───────────────────────────────────────────────────────────────────────

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

FONT_MONO = ("Consolas", 12)


class WinSifterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("WinSifter")
        self.geometry("900x640")
        self.minsize(720, 520)
        self.config_data   = load_config()
        self._cat_row_vars: list = []
        self._build_ui()

    # ── Top-level UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 0))
        ctk.CTkLabel(
            hdr,
            text="WinSifter",
            font=ctk.CTkFont(family="Arial Black", size=34, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            hdr,
            text="  —  Organize your files, effortlessly.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        ).pack(side="left", pady=(8, 0))
        ctk.CTkButton(
            hdr,
            text="🌐  About",
            width=90,
            fg_color="#0088FF",
            hover_color="#006DD6",
            command=self._show_about,
        ).pack(side="right")

        # ── Tabs ──────────────────────────────────────────────────────────────
        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=20, pady=12)
        self.tabs.add("Main")
        self.tabs.add("Settings")
        self._build_main_tab(self.tabs.tab("Main"))
        self._build_settings_tab(self.tabs.tab("Settings"))

    def _show_about(self):
        win = ctk.CTkToplevel(self)
        win.title("About WinSifter")
        win.geometry("460x420")
        win.resizable(False, False)
        win.grab_set()  # modal

        ctk.CTkLabel(
            win,
            text="WinSifter",
            font=ctk.CTkFont(family="Arial Black", size=28, weight="bold"),
        ).pack(pady=(28, 2))

        ctk.CTkLabel(
            win,
            text="Version 1.0",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        ).pack()

        ctk.CTkLabel(
            win,
            text="File Organizer — sorts files into categorized subfolders.",
            font=ctk.CTkFont(size=12),
            wraplength=380,
            justify="center",
        ).pack(pady=(14, 0))

        ctk.CTkLabel(
            win,
            text="Copyright © 2026 Paul R. Charovkine",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(pady=(6, 0))

        ctk.CTkLabel(
            win,
            text="Released under the MIT License.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(pady=(2, 16))

        # Website link
        site_lbl = tk.Label(
            win,
            text="🌐  krypdoh.github.io/WinSifter",
            fg="#0088FF",
            cursor="hand2",
            font=("Segoe UI", 11, "underline"),
            bg=win.cget("bg"),
        )
        site_lbl.pack()
        site_lbl.bind("<Button-1>", lambda _: webbrowser.open("https://krypdoh.github.io/WinSifter"))

        ctk.CTkLabel(win, text="").pack(pady=4)  # spacer

        ctk.CTkButton(
            win,
            text="💛  Donate via PayPal",
            width=200,
            height=40,
            fg_color="#FFB300",
            hover_color="#E6A000",
            text_color="#1a1a1a",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: webbrowser.open("https://www.paypal.com/paypalme/paypaulc"),
        ).pack(pady=(4, 10))

        ctk.CTkButton(
            win,
            text="Close",
            width=100,
            fg_color="gray",
            hover_color="#555",
            command=win.destroy,
        ).pack(pady=(0, 20))

    # ── Main Tab ──────────────────────────────────────────────────────────────

    def _build_main_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        # Folder row
        folder_row = ctk.CTkFrame(parent, fg_color="transparent")
        folder_row.grid(row=0, column=0, sticky="ew", pady=(8, 4))
        folder_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(folder_row, text="Target Folder:", width=110, anchor="w").grid(
            row=0, column=0, padx=(0, 8), sticky="w"
        )
        self.folder_var = tk.StringVar()
        ctk.CTkEntry(
            folder_row,
            textvariable=self.folder_var,
            placeholder_text="Choose a folder to sort…",
        ).grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(
            folder_row, text="Browse", width=90, command=self._browse_folder
        ).grid(row=0, column=2, padx=(8, 0))

        # Options row
        opt_row = ctk.CTkFrame(parent, fg_color="transparent")
        opt_row.grid(row=1, column=0, sticky="ew", pady=4)

        self.move_folders_var = tk.BooleanVar(value=self.config_data.get("move_folders", False))
        ctk.CTkCheckBox(
            opt_row,
            text="Move Folders into a [Folders] subfolder",
            variable=self.move_folders_var,
            fg_color="#0088FF",
            hover_color="#006DD6",
        ).pack(side="left", padx=(0, 20))

        # Buttons row
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", pady=(4, 8))

        self.preview_btn = ctk.CTkButton(
            btn_row,
            text="▶  Preview",
            width=150,
            fg_color="#0088FF",
            hover_color="#006DD6",
            command=self._run_preview,
        )
        self.preview_btn.pack(side="left", padx=(0, 8))

        self.run_btn = ctk.CTkButton(
            btn_row,
            text="⚡  Run",
            width=150,
            fg_color="#00C853",
            hover_color="#009E42",
            command=self._run_sifter,
        )
        self.run_btn.pack(side="left")

        ctk.CTkButton(
            btn_row,
            text="Clear Log",
            width=100,
            fg_color="gray",
            hover_color="#555",
            command=self._clear_log,
        ).pack(side="right")

        # Log area
        self.log = ctk.CTkTextbox(
            parent,
            wrap="none",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log.grid(row=3, column=0, sticky="nsew")
        self.log.configure(state="disabled")
        self._log("WinSifter ready.  Choose a folder, then click  ▶ Preview  or  ⚡ Run.\n")

    # ── Settings Tab ──────────────────────────────────────────────────────────

    def _build_settings_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # ── Top controls ──────────────────────────────────────────────────────
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(8, 6))
        top.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(top, text="Folder Prefix:").grid(
            row=0, column=0, padx=(0, 6), sticky="w"
        )
        self.prefix_var = tk.StringVar(value=self.config_data.get("prefix", "Sifter-"))
        self.prefix_entry = ctk.CTkEntry(top, textvariable=self.prefix_var, width=130)
        self.prefix_entry.grid(row=0, column=1, padx=(0, 10))

        self.no_prefix_var = tk.BooleanVar(
            value=(self.config_data.get("prefix", "Sifter-") == "")
        )
        ctk.CTkCheckBox(
            top,
            text="No prefix",
            variable=self.no_prefix_var,
            command=self._toggle_prefix,
            fg_color="#0088FF",
            hover_color="#006DD6",
        ).grid(row=0, column=2, padx=(0, 20), sticky="w")

        ctk.CTkButton(
            top,
            text="💾  Save Settings",
            width=140,
            fg_color="#AA00FF",
            hover_color="#8800CC",
            command=self._save_settings,
        ).grid(row=0, column=3, padx=(0, 6))
        ctk.CTkButton(
            top,
            text="Reset Defaults",
            width=130,
            fg_color="gray",
            hover_color="#555",
            command=self._reset_defaults,
        ).grid(row=0, column=4)

        # ── Category table ────────────────────────────────────────────────────
        self.cat_scroll = ctk.CTkScrollableFrame(parent, label_text="Categories")
        self.cat_scroll.grid(row=1, column=0, sticky="nsew", pady=(0, 4))
        self._build_category_table()

        # ── Bottom: add category ──────────────────────────────────────────────
        bottom = ctk.CTkFrame(parent, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        ctk.CTkButton(
            bottom,
            text="＋  Add Category",
            width=150,
            fg_color="#0088FF",
            hover_color="#006DD6",
            command=self._add_category,
        ).pack(side="left", padx=(0, 8))

        # ── Advanced (collapsible) ────────────────────────────────────────────
        self.adv_frame = ctk.CTkFrame(parent, border_width=1, border_color="#FF1744")
        self.adv_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))

        adv_hdr = ctk.CTkFrame(self.adv_frame, fg_color="transparent")
        adv_hdr.pack(fill="x", padx=8, pady=4)

        self._adv_visible = False
        self.adv_toggle_btn = ctk.CTkButton(
            adv_hdr,
            text="▶  Advanced Settings",
            fg_color="#FF1744",
            hover_color="#CC0033",
            width=190,
            command=self._toggle_advanced,
        )
        self.adv_toggle_btn.pack(side="left")
        ctk.CTkLabel(
            adv_hdr,
            text="(use with caution)",
            text_color="#FF1744",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=8)

        self.adv_content = ctk.CTkFrame(self.adv_frame, fg_color="transparent")
        # Hidden by default — revealed by _toggle_advanced
        ctk.CTkLabel(
            self.adv_content,
            text=(
                "⚠  WARNING: Recursive mode processes ALL files in ALL subfolders."
                "  This cannot be easily undone.  Use with care."
            ),
            text_color="#FF1744",
            font=ctk.CTkFont(size=11, weight="bold"),
            wraplength=620,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(8, 2))
        self.recursive_var = tk.BooleanVar(value=self.config_data.get("recursive", False))
        ctk.CTkCheckBox(
            self.adv_content,
            text="Enable Recursive Mode  (sort files in all subfolders too)",
            variable=self.recursive_var,
            fg_color="#0088FF",
            hover_color="#006DD6",
        ).pack(anchor="w", padx=12, pady=(2, 10))

    # ── Category table ────────────────────────────────────────────────────────

    def _build_category_table(self):
        for widget in self.cat_scroll.winfo_children():
            widget.destroy()
        self._cat_row_vars = []

        headers     = ["On", "Category Name", "Folder Name", "Extensions  (comma-separated)", ""]
        col_weights = [0, 1, 1, 3, 0]
        for col, (h, w) in enumerate(zip(headers, col_weights)):
            ctk.CTkLabel(
                self.cat_scroll,
                text=h,
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=col, padx=4, pady=(0, 6), sticky="w")
            self.cat_scroll.grid_columnconfigure(col, weight=w)

        for i, cat in enumerate(self.config_data.get("categories", DEFAULT_CATEGORIES)):
            row        = i + 1
            is_other   = cat.get("name") == "Other"
            enabled_v  = tk.BooleanVar(value=cat.get("enabled", True))
            name_v     = tk.StringVar(value=cat.get("name", ""))
            folder_v   = tk.StringVar(value=cat.get("folder", ""))
            ext_v      = tk.StringVar(value=", ".join(cat.get("extensions", [])))

            ctk.CTkCheckBox(
                self.cat_scroll, text="", variable=enabled_v, width=24,
                fg_color="#0088FF", hover_color="#006DD6",
            ).grid(row=row, column=0, padx=4, pady=2)

            ctk.CTkEntry(
                self.cat_scroll,
                textvariable=name_v,
                state="disabled" if is_other else "normal",
            ).grid(row=row, column=1, padx=4, pady=2, sticky="ew")

            ctk.CTkEntry(
                self.cat_scroll, textvariable=folder_v
            ).grid(row=row, column=2, padx=4, pady=2, sticky="ew")

            ctk.CTkEntry(
                self.cat_scroll,
                textvariable=ext_v,
                state="disabled" if is_other else "normal",
            ).grid(row=row, column=3, padx=4, pady=2, sticky="ew")

            if not is_other:
                ctk.CTkButton(
                    self.cat_scroll,
                    text="✕",
                    width=30,
                    fg_color="#FF1744",
                    hover_color="#CC0033",
                    command=lambda idx=i: self._delete_category(idx),
                ).grid(row=row, column=4, padx=4, pady=2)

            self._cat_row_vars.append(
                {
                    "enabled":    enabled_v,
                    "name":       name_v,
                    "folder":     folder_v,
                    "extensions": ext_v,
                    "is_other":   is_other,
                }
            )

    def _gather_categories_from_ui(self) -> list:
        cats = []
        for row in self._cat_row_vars:
            raw_ext    = row["extensions"].get()
            extensions = [e.strip() for e in raw_ext.split(",") if e.strip()]
            cats.append(
                {
                    "name":       row["name"].get(),
                    "folder":     row["folder"].get(),
                    "enabled":    row["enabled"].get(),
                    "extensions": extensions,
                }
            )
        return cats

    # ── Settings actions ──────────────────────────────────────────────────────

    def _toggle_prefix(self):
        if self.no_prefix_var.get():
            self.prefix_var.set("")
            self.prefix_entry.configure(state="disabled")
        else:
            self.prefix_var.set("Sifter-")
            self.prefix_entry.configure(state="normal")

    def _toggle_advanced(self):
        if self._adv_visible:
            self.adv_content.pack_forget()
            self.adv_toggle_btn.configure(text="▶  Advanced Settings")
            self._adv_visible = False
        else:
            self.adv_content.pack(fill="x")
            self.adv_toggle_btn.configure(text="▼  Advanced Settings")
            self._adv_visible = True

    def _save_settings(self):
        self.config_data["prefix"]       = self.prefix_var.get()
        self.config_data["categories"]   = self._gather_categories_from_ui()
        self.config_data["move_folders"] = self.move_folders_var.get()
        self.config_data["recursive"]    = self.recursive_var.get()
        save_config(self.config_data)
        self._log("✔  Settings saved.\n")
        self.tabs.set("Main")

    def _reset_defaults(self):
        self.config_data = _deep_copy(DEFAULT_CONFIG)
        self.prefix_var.set(DEFAULT_CONFIG["prefix"])
        self.no_prefix_var.set(False)
        self.prefix_entry.configure(state="normal")
        self.recursive_var.set(False)
        self.move_folders_var.set(False)
        self._build_category_table()
        self._log(
            "✔  Settings reset to defaults (not yet saved — "
            "click  💾 Save Settings  to persist).\n"
        )

    def _add_category(self):
        cats = self._gather_categories_from_ui()
        # Insert before "Other" catch-all
        insert_at = next(
            (i for i, c in enumerate(cats) if c["name"] == "Other"), len(cats)
        )
        cats.insert(
            insert_at,
            {"name": "New Category", "folder": "New-Category", "enabled": True, "extensions": []},
        )
        self.config_data["categories"] = cats
        self._build_category_table()

    def _delete_category(self, idx: int):
        cats = self._gather_categories_from_ui()
        if 0 <= idx < len(cats):
            cats.pop(idx)
        self.config_data["categories"] = cats
        self._build_category_table()

    # ── Main tab actions ──────────────────────────────────────────────────────

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select folder to sort")
        if folder:
            self.folder_var.set(folder)

    def _live_config(self) -> dict:
        """Merge current UI state into config (does not write to disk)."""
        cfg = _deep_copy(self.config_data)
        cfg["prefix"]       = self.prefix_var.get()
        cfg["move_folders"] = self.move_folders_var.get()
        cfg["recursive"]    = self.recursive_var.get()
        cfg["categories"]   = self._gather_categories_from_ui()
        return cfg

    def _validate_target(self) -> str | None:
        target = self.folder_var.get().strip()
        if not target:
            self._log("✘  Please select a target folder first.\n")
            return None
        if not os.path.isdir(target):
            self._log(f"✘  Not a valid folder: {target}\n")
            return None
        return target

    def _run_preview(self):
        target = self._validate_target()
        if not target:
            return
        cfg     = self._live_config()
        actions = plan_actions(target, cfg)
        if not actions:
            self._log("▶  Preview:  No files found to move in this folder.\n")
            return
        self._log(f"▶  PREVIEW — {len(actions)} item(s) would be moved:\n   {target}\n")
        for a in actions:
            conflict_note = "  ← renamed to avoid conflict" if a["conflict"] else ""
            self._log(
                f"   {a['src'].name}"
                f"  →  {a['dest'].parent.name}\\{a['dest'].name}"
                f"{conflict_note}"
            )
        self._log(f"\n   {len(actions)} item(s) shown — click  ⚡ Run  to execute.\n")

    def _run_sifter(self):
        target = self._validate_target()
        if not target:
            return
        cfg     = self._live_config()
        actions = plan_actions(target, cfg)
        if not actions:
            self._log("⚡  Run:  No files found to move in this folder.\n")
            return
        self._log(f"⚡  RUNNING — sorting {len(actions)} item(s) in:\n   {target}\n")
        self._set_buttons(False)

        def worker():
            stats = execute_actions(actions, self._log)
            total = stats["moved"] + stats["renamed"]
            err_note = f", {stats['errors']} error(s)" if stats["errors"] else ""
            self._log(
                f"\n✔  Done.  {total} item(s) moved"
                f" ({stats['renamed']} renamed for conflicts){err_note}.\n"
            )
            self.after(0, lambda: self._set_buttons(True))

        threading.Thread(target=worker, daemon=True).start()

    def _set_buttons(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.preview_btn.configure(state=state)
        self.run_btn.configure(state=state)

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _log(self, text: str):
        def _append():
            self.log.configure(state="normal")
            if not text.endswith("\n"):
                self.log.insert("end", text + "\n")
            else:
                self.log.insert("end", text)
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(0, _append)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = WinSifterApp()
    app.mainloop()
