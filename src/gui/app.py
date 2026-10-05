"""
Desktop Application GUI for Adaptive News Article and Comment Collector.
Built with standard Tkinter / ttk for cross-platform local desktop execution.
Uses worker threads and queue polling to ensure UI responsiveness.
"""
import os
import sys
import queue
import threading
import subprocess
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from typing import List, Dict, Any, Optional

from src.config import CollectorConfig
from src.browser import BrowserManager
from src.collectors.batch import BatchCollector
from src.export import JSONExporter, CSVExporter
from src.models.summary import CollectionSummary
from src.models.extraction import ExtractionResult
from src.discovery.search import CandidateDiscoverer
from src.discovery.models import CandidateArticle
from src.gui.validation import (
    parse_url_input,
    validate_gui_config,
    format_result_log_line,
    format_article_table_row,
    format_article_detail_text
)
from src.integrations.supabase import (
    SupabaseMapper,
    SupabaseCSVExporter,
    SupabaseStagingDataset,
    SupabaseArticleRow,
    SupabaseCommentRow,
    SupabaseClient,
    SupabaseUploader
)
from src.gui.supabase_preview import (
    SUPABASE_ARTICLE_COLUMNS,
    SUPABASE_COMMENT_COLUMNS,
    format_supabase_article_tree_row,
    format_supabase_comment_tree_row,
    format_supabase_article_detail,
    format_supabase_comment_detail
)
from src.gui.supabase_upload import SupabaseUploadDialog, SupabaseUploadSummaryDialog


class ResizablePanel(ttk.LabelFrame):
    """
    A resizable container panel featuring a visible bottom-right two-axis drag grip handle.
    Supports independent horizontal, vertical, and diagonal resizing with minsize enforcement
    and double-click reset to automatic responsive behavior.
    """

    def __init__(
        self,
        parent,
        text: str = "",
        min_width: int = 200,
        min_height: int = 60,
        on_resize_callback=None,
        **kwargs
    ):
        super().__init__(parent, text=text, padding="4", **kwargs)
        self.min_width = min_width
        self.min_height = min_height
        self.on_resize_callback = on_resize_callback

        self.user_req_width: Optional[int] = None
        self.user_req_height: Optional[int] = None

        self._initial_fill: Optional[str] = None
        self._initial_expand: Optional[bool] = None

        self._start_x = 0
        self._start_y = 0
        self._start_w = 0
        self._start_h = 0

        # Bottom Grip Container Frame (right-aligned) - PACKED FIRST
        # Reserving bottom footprint first prevents child content in content_frame from clipping the corner grip
        self.grip_container = ttk.Frame(self)
        self.grip_container.pack(fill=tk.X, side=tk.BOTTOM, anchor=tk.SE)

        # Bottom-Right Corner Drag Grip Handle
        self.grip = ttk.Label(
            self.grip_container,
            text="◢",
            font=("Segoe UI", 9, "bold"),
            foreground="#666666",
            cursor="size_nw_se"
        )
        self.grip.pack(side=tk.RIGHT, anchor=tk.SE, padx=(0, 2), pady=(0, 2))

        # Inner Content Frame where child controls reside - PACKED SECOND
        self.content_frame = ttk.Frame(self)
        self.content_frame.pack(fill=tk.BOTH, expand=True)

        self.grip.bind("<ButtonPress-1>", self._on_grip_press)
        self.grip.bind("<B1-Motion>", self._on_grip_drag)
        self.grip.bind("<ButtonRelease-1>", self._on_grip_release)
        self.grip.bind("<Double-Button-1>", self._on_grip_double_click)

    def get_effective_width(self) -> int:
        if self.user_req_width is not None:
            return self.user_req_width
        return self.min_width

    def get_effective_height(self) -> int:
        if self.user_req_height is not None:
            return self.user_req_height
        return self.min_height

    def update_auto_width(self, container_w: int):
        if self.user_req_width is None:
            target_w = max(self.min_width, container_w)
            self._apply_panel_geometry(auto_w=target_w)

    def _apply_panel_geometry(self, auto_w: Optional[int] = None):
        if self._initial_fill is None:
            try:
                pinfo = self.pack_info()
                self._initial_fill = pinfo.get("fill", "none")
                raw_exp = pinfo.get("expand", False)
                if isinstance(raw_exp, str):
                    self._initial_expand = (raw_exp.lower() in ("1", "true", "yes"))
                else:
                    self._initial_expand = bool(raw_exp)
            except tk.TclError:
                pass

        target_w = self.user_req_width if self.user_req_width is not None else auto_w

        if self.user_req_width is not None and self.user_req_height is not None:
            self.config(width=self.user_req_width, height=self.user_req_height)
            self.pack_propagate(False)
            if self._initial_fill is not None:
                self.pack_configure(fill=tk.NONE, expand=False)
        elif self.user_req_width is not None:
            self.config(width=self.user_req_width)
            self.pack_propagate(False)
            if self._initial_fill is not None:
                self.pack_configure(fill=tk.Y, expand=False)
        elif self.user_req_height is not None:
            self.config(height=self.user_req_height)
            self.pack_propagate(False)
            if self._initial_fill is not None:
                self.pack_configure(fill=tk.X, expand=False)
        elif auto_w is not None:
            self.config(width=auto_w)
            self.pack_propagate(True)
            if self._initial_fill is not None:
                self.pack_configure(fill=self._initial_fill, expand=self._initial_expand)
        else:
            self.config(width=0, height=0)
            self.pack_propagate(True)
            if self._initial_fill is not None:
                self.pack_configure(fill=self._initial_fill, expand=self._initial_expand)

    def _on_grip_press(self, event):
        self._start_x = event.x_root
        self._start_y = event.y_root
        self._start_w = self.winfo_width()
        self._start_h = self.winfo_height()

    def _on_grip_drag(self, event):
        dx = event.x_root - self._start_x
        dy = event.y_root - self._start_y

        if abs(dx) > 2:
            new_w = max(self.min_width, self._start_w + dx)
            self.user_req_width = new_w

        if abs(dy) > 2:
            new_h = max(self.min_height, self._start_h + dy)
            self.user_req_height = new_h

        self._apply_panel_geometry()

        if self.on_resize_callback:
            self.on_resize_callback()

    def _on_grip_release(self, event):
        if self.on_resize_callback:
            self.on_resize_callback()

    def _on_grip_double_click(self, event):
        self.user_req_width = None
        self.user_req_height = None
        self.pack_propagate(True)
        self.config(width=0, height=0)
        if self.on_resize_callback:
            self.on_resize_callback()


class CollectionApp:
    """
    Main Tkinter application window for the News Article and Comment Collector.
    """

    DEFAULT_OUTPUT_DIR = "data/output"
    DEFAULT_INPUT_FILE = "data/input/urls.txt"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Adaptive News Article & Comment Collector")
        self.root.geometry("920x720")
        self.root.minsize(720, 500)

        self.queue: queue.Queue = queue.Queue()
        self.is_collecting = False
        self.worker_thread: Optional[threading.Thread] = None
        self.current_results: List[ExtractionResult] = []
        self.current_staging_dataset: Optional[SupabaseStagingDataset] = None
        self.resizable_panels: List[ResizablePanel] = []

        self._create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _update_workspace_geometry(self):
        """Updates canvas window dimensions and scrollregion based on viewport and requested panel sizes."""
        if not hasattr(self, "main_canvas") or not hasattr(self, "main_frame"):
            return

        self.root.update_idletasks()

        viewport_w = self.main_canvas.winfo_width()
        viewport_h = self.main_canvas.winfo_height()

        if viewport_w <= 1 or viewport_h <= 1:
            return

        # ---------------------------------------------------------------------
        # Application-level Section 3 (panel_results) nested propagation
        # ---------------------------------------------------------------------
        nested_req_w = 0
        nested_req_h = 0

        if hasattr(self, "panel_results") and hasattr(self, "panel_tree") and hasattr(self, "panel_detail"):
            # Measure actual Tkinter geometry overhead if widgets are rendered, else use minimal structural bounds
            overhead_w = 28
            if self.panel_results.winfo_width() > 1 and hasattr(self, "notebook") and self.notebook.winfo_width() > 1:
                measured_w_diff = self.panel_results.winfo_width() - self.notebook.winfo_width()
                if measured_w_diff > 0:
                    overhead_w = max(24, measured_w_diff + 12)

            overhead_h = 70
            if (
                self.panel_results.winfo_height() > 1
                and self.panel_tree.winfo_height() > 1
                and self.panel_detail.winfo_height() > 1
            ):
                measured_h_diff = self.panel_results.winfo_height() - (self.panel_tree.winfo_height() + self.panel_detail.winfo_height())
                if measured_h_diff > 0:
                    overhead_h = max(50, measured_h_diff)

            # Compute nested width requirement if panel_tree or panel_detail has a manual width set
            if self.panel_tree.user_req_width is not None or self.panel_detail.user_req_width is not None:
                widest_child = max(self.panel_tree.get_effective_width(), self.panel_detail.get_effective_width())
                nested_req_w = widest_child + overhead_w

            # Compute nested height requirement if panel_tree or panel_detail has a manual height set
            if self.panel_tree.user_req_height is not None or self.panel_detail.user_req_height is not None:
                stacked_children = self.panel_tree.get_effective_height() + self.panel_detail.get_effective_height()
                nested_req_h = stacked_children + overhead_h

            # Determine rendered dimensions for panel_results:
            # Explicit user outer manual size takes precedence unless cleared by a newer nested panel drag.
            if self.panel_results.user_req_width is not None:
                sec3_rendered_w = max(self.panel_results.user_req_width, self.panel_results.min_width)
            else:
                sec3_rendered_w = max(self.panel_results.min_width, nested_req_w)

            if self.panel_results.user_req_height is not None:
                sec3_rendered_h = max(self.panel_results.user_req_height, self.panel_results.min_height)
            else:
                sec3_rendered_h = max(self.panel_results.min_height, nested_req_h)

            # Apply rendered dimensions to panel_results
            if sec3_rendered_w > self.panel_results.min_width or self.panel_results.user_req_width is not None:
                self.panel_results.config(width=sec3_rendered_w)
                self.panel_results.pack_propagate(False)

            if sec3_rendered_h > self.panel_results.min_height or self.panel_results.user_req_height is not None:
                self.panel_results.config(height=sec3_rendered_h)
                self.panel_results.pack_propagate(False)
            elif self.panel_results.user_req_width is None and nested_req_w == 0 and nested_req_h == 0:
                # Restore automatic propagation if neither manual nor nested height is required
                self.panel_results.pack_propagate(True)
                self.panel_results.config(height=0)

        # ---------------------------------------------------------------------
        # Workspace Canvas Scrollregion & Window Geometry
        # ---------------------------------------------------------------------
        # Calculate rendered workspace width based on explicit panel requests and baseline bounds
        baseline_w = min(896, max(680, viewport_w - 4))
        workspace_w = baseline_w
        for panel in getattr(self, "resizable_panels", []):
            req_w = panel.get_effective_width()
            if req_w > workspace_w:
                workspace_w = req_w

        if nested_req_w > workspace_w:
            workspace_w = nested_req_w

        # Update automatic top-level panels to match workspace width
        for panel in [self.panel_input, self.panel_config, self.panel_results, self.panel_output]:
            if panel.user_req_width is None and (panel != self.panel_results or nested_req_w == 0):
                panel.update_auto_width(workspace_w - 12)

        total_content_h = max(self.main_frame.winfo_reqheight(), viewport_h - 4)

        # Position canvas_window: center if viewport_w > workspace_w, else left-anchor at 0
        if viewport_w > workspace_w + 4:
            x_offset = (viewport_w - workspace_w) // 2
        else:
            x_offset = 0

        self.main_canvas.coords(self.canvas_window, x_offset, 0)
        self.main_canvas.itemconfig(self.canvas_window, width=workspace_w, height=total_content_h)
        self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

    def _on_outer_panel_resize(self):
        self._update_workspace_geometry()

    def _on_tree_panel_resize(self):
        if hasattr(self, "panel_tree") and hasattr(self, "panel_results"):
            if self.panel_tree.user_req_width is not None:
                self.panel_results.user_req_width = None
            if self.panel_tree.user_req_height is not None:
                self.panel_results.user_req_height = None
        self._update_workspace_geometry()

    def _on_detail_panel_resize(self):
        if hasattr(self, "panel_detail") and hasattr(self, "panel_results"):
            if self.panel_detail.user_req_width is not None:
                self.panel_results.user_req_width = None
            if self.panel_detail.user_req_height is not None:
                self.panel_results.user_req_height = None
        self._update_workspace_geometry()

    def _on_supabase_articles_tree_resize(self):
        if hasattr(self, "panel_supabase_articles_tree") and hasattr(self, "panel_results"):
            if self.panel_supabase_articles_tree.user_req_width is not None:
                self.panel_results.user_req_width = None
            if self.panel_supabase_articles_tree.user_req_height is not None:
                self.panel_results.user_req_height = None
        self._update_workspace_geometry()

    def _on_supabase_article_detail_resize(self):
        if hasattr(self, "panel_supabase_article_detail") and hasattr(self, "panel_results"):
            if self.panel_supabase_article_detail.user_req_width is not None:
                self.panel_results.user_req_width = None
            if self.panel_supabase_article_detail.user_req_height is not None:
                self.panel_results.user_req_height = None
        self._update_workspace_geometry()

    def _on_supabase_comments_tree_resize(self):
        if hasattr(self, "panel_supabase_comments_tree") and hasattr(self, "panel_results"):
            if self.panel_supabase_comments_tree.user_req_width is not None:
                self.panel_results.user_req_width = None
            if self.panel_supabase_comments_tree.user_req_height is not None:
                self.panel_results.user_req_height = None
        self._update_workspace_geometry()

    def _on_supabase_comment_detail_resize(self):
        if hasattr(self, "panel_supabase_comment_detail") and hasattr(self, "panel_results"):
            if self.panel_supabase_comment_detail.user_req_width is not None:
                self.panel_results.user_req_width = None
            if self.panel_supabase_comment_detail.user_req_height is not None:
                self.panel_results.user_req_height = None
        self._update_workspace_geometry()

    def _create_widgets(self):
        """Constructs and lays out the application GUI components using Tkinter & TTK."""
        # Main Outer Container with Vertical & Horizontal Scrollbars
        outer_frame = ttk.Frame(self.root)
        outer_frame.pack(fill=tk.BOTH, expand=True)

        self.main_canvas = tk.Canvas(outer_frame, highlightthickness=0)
        self.v_scrollbar = ttk.Scrollbar(outer_frame, orient=tk.VERTICAL, command=self.main_canvas.yview)
        self.h_scrollbar = ttk.Scrollbar(outer_frame, orient=tk.HORIZONTAL, command=self.main_canvas.xview)
        self.main_canvas.configure(yscrollcommand=self.v_scrollbar.set, xscrollcommand=self.h_scrollbar.set)

        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Scrollable content frame inside canvas
        self.main_frame = ttk.Frame(self.main_canvas, padding="8")
        self.canvas_window = self.main_canvas.create_window((0, 0), window=self.main_frame, anchor="nw")

        def _on_canvas_configure(event):
            self._update_workspace_geometry()

        def _on_frame_configure(event):
            self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

        self.main_canvas.bind("<Configure>", _on_canvas_configure)
        self.main_frame.bind("<Configure>", _on_frame_configure)

        def _on_mousewheel(event):
            if event.delta:
                self.main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.main_canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")

        # ---------------------------------------------------------------------
        # Section 1: Article URLs Input Panel
        # ---------------------------------------------------------------------
        self.panel_input = ResizablePanel(
            self.main_frame,
            text=" 1. Article URLs Input ",
            min_width=340,
            min_height=80,
            on_resize_callback=self._update_workspace_geometry
        )
        self.panel_input.pack(side=tk.TOP, anchor=tk.NW, expand=False, pady=(0, 6))

        input_toolbar = ttk.Frame(self.panel_input.content_frame)
        input_toolbar.pack(fill=tk.X, expand=False, pady=(0, 4))

        lbl_input_prompt = ttk.Label(input_toolbar, text="Enter or paste article URLs (one per line):")
        lbl_input_prompt.pack(side=tk.LEFT, anchor=tk.W)

        btn_discover = ttk.Button(
            input_toolbar,
            text="Discover Candidates...",
            command=self._on_discover_candidates_clicked
        )
        btn_discover.pack(side=tk.RIGHT, padx=(4, 0))

        btn_load_file = ttk.Button(
            input_toolbar,
            text="Load from File...",
            command=self._on_load_file_clicked
        )
        btn_load_file.pack(side=tk.RIGHT, padx=(4, 0))

        btn_clear_urls = ttk.Button(
            input_toolbar,
            text="Clear",
            command=self._on_clear_urls_clicked
        )
        btn_clear_urls.pack(side=tk.RIGHT)

        self.url_text = scrolledtext.ScrolledText(
            self.panel_input.content_frame,
            height=2,
            wrap=tk.WORD,
            font=("Consolas", 10)
        )
        self.url_text.pack(fill=tk.BOTH, expand=True)
        self.url_text.insert(
            tk.END,
            "https://news.yahoo.com/article.html\n"
            "https://www.msn.com/en-us/news/politics/here-are-the-dates-to-know-for-the-2026-midterm-elections/ar-AA1WCoGY\n"
        )

        # ---------------------------------------------------------------------
        # Section 2: Collection Parameters & Operational Controls Panel
        # ---------------------------------------------------------------------
        self.panel_config = ResizablePanel(
            self.main_frame,
            text=" 2. Collection Parameters & Operational Controls ",
            min_width=460,
            min_height=90,
            on_resize_callback=self._update_workspace_geometry
        )
        self.panel_config.pack(side=tk.TOP, anchor=tk.NW, expand=False, pady=(0, 6))

        cfg_grid = ttk.Frame(self.panel_config.content_frame)
        cfg_grid.pack(fill=tk.X, expand=True)

        # Delay
        ttk.Label(cfg_grid, text="Inter-Article Delay (sec):").grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self.ent_delay = ttk.Entry(cfg_grid, width=10)
        self.ent_delay.insert(0, "2.0")
        self.ent_delay.grid(row=0, column=1, sticky=tk.W, padx=(0, 16), pady=2)

        # Max Articles
        ttk.Label(cfg_grid, text="Max Articles (limit):").grid(row=0, column=2, sticky=tk.W, padx=(0, 4), pady=2)
        self.ent_max_articles = ttk.Entry(cfg_grid, width=10)
        self.ent_max_articles.insert(0, "50")
        self.ent_max_articles.grid(row=0, column=3, sticky=tk.W, padx=(0, 16), pady=2)

        # Max Comments
        ttk.Label(cfg_grid, text="Max Comments / Article:").grid(row=0, column=4, sticky=tk.W, padx=(0, 4), pady=2)
        self.ent_max_comments = ttk.Entry(cfg_grid, width=10)
        self.ent_max_comments.insert(0, "50")
        self.ent_max_comments.grid(row=0, column=5, sticky=tk.W, padx=(0, 0), pady=2)

        # Navigation Timeout
        ttk.Label(cfg_grid, text="Navigation Timeout (sec):").grid(row=1, column=0, sticky=tk.W, padx=(0, 4), pady=4)
        self.ent_timeout = ttk.Entry(cfg_grid, width=10)
        self.ent_timeout.insert(0, "30")
        self.ent_timeout.grid(row=1, column=1, sticky=tk.W, padx=(0, 16), pady=4)

        # Topic / Research Label (User-editable, optional, blank by default)
        ttk.Label(cfg_grid, text="Topic / Research Label:").grid(row=1, column=2, sticky=tk.W, padx=(0, 4), pady=4)
        self.ent_topic = ttk.Entry(cfg_grid, width=32)
        self.ent_topic.grid(row=1, column=3, columnspan=3, sticky=tk.W, pady=4)

        # Execution Control & Progress Indicator row
        control_frame = ttk.Frame(self.panel_config.content_frame, padding="4")
        control_frame.pack(fill=tk.X, expand=False, pady=(4, 0))

        self.btn_start = ttk.Button(
            control_frame,
            text="Start Collection",
            command=self.on_start_clicked
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_status = ttk.Label(control_frame, text="Status: Ready to collect", font=("Segoe UI", 9, "italic"))
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.progress_bar = ttk.Progressbar(control_frame, mode="determinate", length=200)
        self.progress_bar.pack(side=tk.RIGHT)

        # ---------------------------------------------------------------------
        # Section 3: Progress Logs & Collection Summary Panel
        # ---------------------------------------------------------------------
        self.panel_results = ResizablePanel(
            self.main_frame,
            text=" 3. Progress Logs & Collection Summary ",
            min_width=480,
            min_height=180,
            on_resize_callback=self._on_outer_panel_resize
        )
        self.panel_results.pack(side=tk.TOP, anchor=tk.NW, expand=False, pady=(0, 6))

        self.notebook = ttk.Notebook(self.panel_results.content_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self._update_workspace_geometry())

        # Tab 1: Real-time Logs
        tab_logs = ttk.Frame(self.notebook)
        self.notebook.add(tab_logs, text=" Execution Progress Log ")

        self.log_text = scrolledtext.ScrolledText(
            tab_logs,
            height=5,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Tab 2: Research Article Results Table & Inspection
        tab_research = ttk.Frame(self.notebook)
        self.notebook.add(tab_research, text=" Research Article Results ")

        self.panel_tree = ResizablePanel(
            tab_research,
            text=" Research Article Results Table ",
            min_width=440,
            min_height=80,
            on_resize_callback=self._on_tree_panel_resize
        )
        self.panel_tree.pack(side=tk.TOP, anchor=tk.NW, fill=tk.BOTH, expand=True, pady=(0, 4))

        columns = ("platform", "title", "publisher", "pub_date", "art_status", "comment_status", "reported", "collected", "method")
        self.results_tree = ttk.Treeview(
            self.panel_tree.content_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=3
        )

        col_configs = [
            ("platform", "Platform", 75),
            ("title", "Title", 210),
            ("publisher", "Publisher", 95),
            ("pub_date", "Pub Date", 115),
            ("art_status", "Article Status", 95),
            ("comment_status", "Comment Status", 110),
            ("reported", "Reported", 65),
            ("collected", "Collected", 65),
            ("method", "Method / Note", 130)
        ]
        for col_id, col_name, col_width in col_configs:
            self.results_tree.heading(col_id, text=col_name)
            self.results_tree.column(col_id, width=col_width, minwidth=40, stretch=True)

        v_scroll = ttk.Scrollbar(self.panel_tree.content_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        h_scroll = ttk.Scrollbar(self.panel_tree.content_frame, orient=tk.HORIZONTAL, command=self.results_tree.xview)
        self.results_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.results_tree.pack(fill=tk.BOTH, expand=True)

        self.results_tree.bind("<<TreeviewSelect>>", self._on_tree_selection_changed)

        # Inspection Detail Panel inside Tab 2
        self.panel_detail = ResizablePanel(
            tab_research,
            text=" Selected Article Inspection Panel ",
            min_width=440,
            min_height=60,
            on_resize_callback=self._on_detail_panel_resize
        )
        self.panel_detail.pack(side=tk.TOP, anchor=tk.NW, fill=tk.BOTH, expand=True)

        self.detail_text = scrolledtext.ScrolledText(
            self.panel_detail.content_frame,
            height=2,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED
        )
        self.detail_text.pack(fill=tk.BOTH, expand=True)

        # Tab 3: Structured Collection Summary
        tab_summary = ttk.Frame(self.notebook)
        self.notebook.add(tab_summary, text=" Collection Run Summary ")

        self.summary_text = scrolledtext.ScrolledText(
            tab_summary,
            height=5,
            wrap=tk.WORD,
            font=("Consolas", 10),
            state=tk.DISABLED
        )
        self.summary_text.pack(fill=tk.BOTH, expand=True)

        # Tab 4: Supabase Articles Staging Preview & Inspection
        tab_supabase_articles = ttk.Frame(self.notebook)
        self.notebook.add(tab_supabase_articles, text=" Supabase Articles Staging ")

        self.panel_supabase_articles_tree = ResizablePanel(
            tab_supabase_articles,
            text=" Supabase Articles Staging Table (14 Schema Columns) ",
            min_width=440,
            min_height=80,
            on_resize_callback=self._on_supabase_articles_tree_resize
        )
        self.panel_supabase_articles_tree.pack(side=tk.TOP, anchor=tk.NW, fill=tk.BOTH, expand=True, pady=(0, 4))

        self.supabase_articles_tree = ttk.Treeview(
            self.panel_supabase_articles_tree.content_frame,
            columns=SUPABASE_ARTICLE_COLUMNS,
            show="headings",
            selectmode="browse",
            height=3
        )

        sup_art_col_configs = [
            ("id", "ID (Staging)", 80),
            ("title", "Title", 160),
            ("content", "Content (Raw)", 150),
            ("source", "Source", 80),
            ("created_at", "Created At", 110),
            ("url", "Canonical URL", 160),
            ("author", "Author", 90),
            ("published_date", "Published Date", 110),
            ("content_hash", "Content Hash", 100),
            ("clean_content", "Clean Content", 150),
            ("processing_status", "Proc Status", 85),
            ("processing_note", "Proc Note", 85),
            ("processed_at", "Processed At", 85),
            ("is_relevant", "Is Relevant", 75)
        ]
        for col_id, col_name, col_width in sup_art_col_configs:
            self.supabase_articles_tree.heading(col_id, text=col_name)
            self.supabase_articles_tree.column(col_id, width=col_width, minwidth=40, stretch=True)

        v_scroll_sa = ttk.Scrollbar(self.panel_supabase_articles_tree.content_frame, orient=tk.VERTICAL, command=self.supabase_articles_tree.yview)
        h_scroll_sa = ttk.Scrollbar(self.panel_supabase_articles_tree.content_frame, orient=tk.HORIZONTAL, command=self.supabase_articles_tree.xview)
        self.supabase_articles_tree.configure(yscrollcommand=v_scroll_sa.set, xscrollcommand=h_scroll_sa.set)

        v_scroll_sa.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll_sa.pack(side=tk.BOTTOM, fill=tk.X)
        self.supabase_articles_tree.pack(fill=tk.BOTH, expand=True)

        self.supabase_articles_tree.bind("<<TreeviewSelect>>", self._on_supabase_article_selected)

        self.panel_supabase_article_detail = ResizablePanel(
            tab_supabase_articles,
            text=" Selected Supabase Article Row Inspection ",
            min_width=440,
            min_height=60,
            on_resize_callback=self._on_supabase_article_detail_resize
        )
        self.panel_supabase_article_detail.pack(side=tk.TOP, anchor=tk.NW, fill=tk.BOTH, expand=True)

        self.supabase_article_detail_text = scrolledtext.ScrolledText(
            self.panel_supabase_article_detail.content_frame,
            height=2,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED
        )
        self.supabase_article_detail_text.pack(fill=tk.BOTH, expand=True)

        # Tab 5: Supabase Comments Staging Preview & Inspection
        tab_supabase_comments = ttk.Frame(self.notebook)
        self.notebook.add(tab_supabase_comments, text=" Supabase Comments Staging ")

        self.panel_supabase_comments_tree = ResizablePanel(
            tab_supabase_comments,
            text=" Supabase Comments Staging Table (6 Schema Columns) ",
            min_width=440,
            min_height=80,
            on_resize_callback=self._on_supabase_comments_tree_resize
        )
        self.panel_supabase_comments_tree.pack(side=tk.TOP, anchor=tk.NW, fill=tk.BOTH, expand=True, pady=(0, 4))

        self.supabase_comments_tree = ttk.Treeview(
            self.panel_supabase_comments_tree.content_frame,
            columns=SUPABASE_COMMENT_COLUMNS,
            show="headings",
            selectmode="browse",
            height=3
        )

        sup_cm_col_configs = [
            ("id", "ID (Staging)", 100),
            ("article_id", "Article ID (Staging)", 120),
            ("text", "Comment Text", 300),
            ("created_at", "Created At", 120),
            ("parent_comment_id", "Parent Comment ID", 120),
            ("published_date", "Published Date", 120)
        ]
        for col_id, col_name, col_width in sup_cm_col_configs:
            self.supabase_comments_tree.heading(col_id, text=col_name)
            self.supabase_comments_tree.column(col_id, width=col_width, minwidth=40, stretch=True)

        v_scroll_sc = ttk.Scrollbar(self.panel_supabase_comments_tree.content_frame, orient=tk.VERTICAL, command=self.supabase_comments_tree.yview)
        h_scroll_sc = ttk.Scrollbar(self.panel_supabase_comments_tree.content_frame, orient=tk.HORIZONTAL, command=self.supabase_comments_tree.xview)
        self.supabase_comments_tree.configure(yscrollcommand=v_scroll_sc.set, xscrollcommand=h_scroll_sc.set)

        v_scroll_sc.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll_sc.pack(side=tk.BOTTOM, fill=tk.X)
        self.supabase_comments_tree.pack(fill=tk.BOTH, expand=True)

        self.supabase_comments_tree.bind("<<TreeviewSelect>>", self._on_supabase_comment_selected)

        self.panel_supabase_comment_detail = ResizablePanel(
            tab_supabase_comments,
            text=" Selected Supabase Comment Row Inspection ",
            min_width=440,
            min_height=60,
            on_resize_callback=self._on_supabase_comment_detail_resize
        )
        self.panel_supabase_comment_detail.pack(side=tk.TOP, anchor=tk.NW, fill=tk.BOTH, expand=True)

        self.supabase_comment_detail_text = scrolledtext.ScrolledText(
            self.panel_supabase_comment_detail.content_frame,
            height=2,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED
        )
        self.supabase_comment_detail_text.pack(fill=tk.BOTH, expand=True)

        # ---------------------------------------------------------------------
        # Section 4: Output Access Panel
        # ---------------------------------------------------------------------
        self.panel_output = ResizablePanel(
            self.main_frame,
            text=" 4. Generated Dataset Outputs ",
            min_width=340,
            min_height=45,
            on_resize_callback=self._update_workspace_geometry
        )
        self.panel_output.pack(side=tk.TOP, anchor=tk.NW, expand=False)

        out_layout = ttk.Frame(self.panel_output.content_frame)
        out_layout.pack(fill=tk.X, expand=True)

        self.lbl_outputs = ttk.Label(
            out_layout,
            text="Outputs will be saved to: data/output/articles.json, data/output/articles.csv, data/output/comments.csv",
            font=("Segoe UI", 9)
        )
        self.lbl_outputs.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_open_folder = ttk.Button(
            out_layout,
            text="Open Output Folder",
            command=self._on_open_output_folder_clicked
        )
        btn_open_folder.pack(side=tk.RIGHT, padx=(4, 0))

        self.btn_export_supabase = ttk.Button(
            out_layout,
            text="Export Supabase CSVs...",
            command=self._on_export_supabase_clicked,
            state=tk.DISABLED
        )
        self.btn_export_supabase.pack(side=tk.RIGHT, padx=(4, 0))

        self.btn_upload_supabase = ttk.Button(
            out_layout,
            text="Upload to Supabase...",
            command=self._on_upload_supabase_clicked,
            state=tk.DISABLED
        )
        self.btn_upload_supabase.pack(side=tk.RIGHT, padx=(4, 0))

        # Sub-row in Section 4 for Supabase Validation Status
        sup_status_frame = ttk.Frame(self.panel_output.content_frame)
        sup_status_frame.pack(fill=tk.X, expand=True, pady=(4, 0))

        self.lbl_supabase_status = ttk.Label(
            sup_status_frame,
            text="Supabase Staging Status: Not generated yet",
            font=("Segoe UI", 9, "italic"),
            foreground="#555555"
        )
        self.lbl_supabase_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Register resizable panels for geometry calculations
        self.resizable_panels = [
            self.panel_input,
            self.panel_config,
            self.panel_results,
            self.panel_tree,
            self.panel_detail,
            self.panel_supabase_articles_tree,
            self.panel_supabase_article_detail,
            self.panel_supabase_comments_tree,
            self.panel_supabase_comment_detail,
            self.panel_output
        ]

    # -------------------------------------------------------------------------
    # Event Handlers & User Actions
    # -------------------------------------------------------------------------
    def _on_clear_urls_clicked(self):
        """Clears the URL input text area."""
        self.url_text.delete("1.0", tk.END)

    def _on_load_file_clicked(self):
        """Opens a file dialog to select a text file containing article URLs."""
        file_path = filedialog.askopenfilename(
            title="Select URL Input File",
            initialdir=os.getcwd(),
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.url_text.delete("1.0", tk.END)
                self.url_text.insert(tk.END, content)
                self._append_log(f"Loaded URLs from file: {file_path}")
            except Exception as e:
                messagebox.showerror("File Read Error", f"Could not read selected file:\n{str(e)}")

    def _on_open_output_folder_clicked(self):
        """Opens the output directory in Windows Explorer or default file manager."""
        out_dir = os.path.abspath(self.DEFAULT_OUTPUT_DIR)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        try:
            if sys.platform == "win32":
                os.startfile(out_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", out_dir])
            else:
                subprocess.Popen(["xdg-open", out_dir])
        except Exception as e:
            messagebox.showinfo("Output Location", f"Output folder location:\n{out_dir}")

    def on_start_clicked(self):
        """
        Validates input configuration, disables Start button, and launches worker thread.
        """
        if self.is_collecting:
            return

        # 1. Parse URLs
        raw_text = self.url_text.get("1.0", tk.END)
        urls = parse_url_input(raw_text)

        if not urls:
            messagebox.showwarning("No Input URLs", "Please enter at least one article URL before starting collection.")
            return

        # 2. Validate Configuration
        is_valid, parsed_cfg, err_msg = validate_gui_config(
            inter_article_delay_str=self.ent_delay.get().strip(),
            max_articles_str=self.ent_max_articles.get().strip(),
            max_comments_str=self.ent_max_comments.get().strip(),
            navigation_timeout_str=self.ent_timeout.get().strip(),
            topic_str=self.ent_topic.get().strip()
        )

        if not is_valid or not parsed_cfg:
            messagebox.showerror("Configuration Error", f"Invalid input parameters:\n\n{err_msg}")
            return

        # 3. Lock UI Controls
        self.is_collecting = True
        self.btn_start.config(state=tk.DISABLED)
        self.lbl_status.config(text=f"Status: Starting collection for {len(urls)} URL(s)...")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(urls)

        # Clear previous logs, summary, and results table
        self._clear_logs()
        self._clear_summary()
        self._populate_results_table([])
        self.current_staging_dataset = None
        self._clear_supabase_preview()
        self.lbl_supabase_status.config(
            text="Supabase Staging Status: Collection in progress...",
            foreground="#555555"
        )
        self.btn_export_supabase.config(state=tk.DISABLED)
        self.notebook.select(0)  # Switch to logs tab

        self._append_log(f"=== Starting Collection Run ===")
        self._append_log(f"Total Input URLs: {len(urls)}")
        self._append_log(f"Topic / Label: {parsed_cfg.get('topic_query') or 'None'}")
        self._append_log(f"Parameters: Delay={parsed_cfg['inter_article_delay']}s, "
                         f"Max Articles={parsed_cfg['max_articles']}, "
                         f"Max Comments={parsed_cfg['max_comments_per_article']}, "
                         f"Timeout={parsed_cfg['navigation_timeout_ms'] / 1000.0}s\n")

        # 4. Start Worker Thread
        self.worker_thread = threading.Thread(
            target=self._worker_collection_task,
            args=(urls, parsed_cfg),
            daemon=True
        )
        self.worker_thread.start()

        # 5. Start Queue Polling
        self.root.after(100, self._poll_queue)

    # -------------------------------------------------------------------------
    # Worker Thread (Background Network & Scraping Tasks)
    # -------------------------------------------------------------------------
    def _worker_collection_task(self, urls: List[str], config_dict: Dict[str, Any]):
        """
        Executes batch collection, exports, and summary generation outside the Tkinter main loop.
        Communicates with UI exclusively via self.queue.
        """
        try:
            delay = config_dict["inter_article_delay"]
            max_art = config_dict["max_articles"]
            max_comm = config_dict["max_comments_per_article"]
            timeout_ms = config_dict["navigation_timeout_ms"]
            topic_query = config_dict.get("topic_query")

            collector = BatchCollector()

            def progress_cb(index: int, total: int, res: Any):
                self.queue.put(("PROGRESS", index, total, res))

            with BrowserManager(headless=True, navigation_timeout_ms=timeout_ms) as bm:
                results = collector.collect_urls(
                    urls=urls,
                    browser_manager=bm,
                    max_comments=max_comm,
                    max_articles=max_art,
                    inter_article_delay=delay,
                    navigation_timeout_ms=timeout_ms,
                    topic_query=topic_query,
                    progress_callback=progress_cb
                )

            # Perform Standard Exports
            out_dir = self.DEFAULT_OUTPUT_DIR
            os.makedirs(out_dir, exist_ok=True)
            json_path = os.path.join(out_dir, "articles.json")

            articles = [r.article for r in results if r.article]

            JSONExporter.export_batch(articles, output_path=json_path)
            csv_paths = CSVExporter.export(articles, output_dir=out_dir)

            output_files = {
                "json": json_path,
                "articles_csv": csv_paths.get("articles_csv", os.path.join(out_dir, "articles.csv")),
                "comments_csv": csv_paths.get("comments_csv", os.path.join(out_dir, "comments.csv"))
            }

            # Generate CollectionSummary
            summary = BatchCollector.create_summary(results, output_files=output_files, topic_query=topic_query)

            # Supabase Staging Layer Execution (Additive & Isolated)
            staging_dataset = None
            staging_error = None
            if articles:
                try:
                    staging_dataset = SupabaseMapper.build_staging_dataset(articles)
                except Exception as stg_err:
                    staging_error = str(stg_err)

            self.queue.put(("COMPLETE", results, summary, output_files, staging_dataset, staging_error))

        except Exception as e:
            self.queue.put(("ERROR", str(e)))

    # -------------------------------------------------------------------------
    # UI Thread Queue Polling & Renderer Updates
    # -------------------------------------------------------------------------
    def _poll_queue(self):
        """
        Periodically polls queue on the main Tkinter UI thread to safely update widgets.
        """
        try:
            while True:
                msg = self.queue.get_nowait()
                msg_type = msg[0]

                if msg_type == "PROGRESS":
                    _, index, total, res = msg
                    log_line = format_result_log_line(res, index, total)
                    self._append_log(log_line)
                    self.progress_bar["value"] = index
                    self.lbl_status.config(text=f"Status: Processing URL {index} of {total}...")

                elif msg_type == "COMPLETE":
                    if len(msg) >= 6:
                        _, results, summary, output_files, staging_dataset, staging_error = msg
                    else:
                        _, results, summary, output_files = msg
                        staging_dataset = None
                        staging_error = None

                    self.progress_bar["value"] = self.progress_bar["maximum"]
                    self.lbl_status.config(text=f"Status: Collection Complete! ({len(results)} processed)")
                    self._append_log(f"\n=== Collection Run Finished ===")
                    self._append_log(f"Exported JSON: {output_files['json']}")
                    self._append_log(f"Exported Articles CSV: {output_files['articles_csv']}")
                    self._append_log(f"Exported Comments CSV: {output_files['comments_csv']}")

                    self._display_summary(summary)
                    self._populate_results_table(results)
                    self.lbl_outputs.config(
                        text=f"Outputs generated:\n"
                             f"• {output_files['json']}\n"
                             f"• {output_files['articles_csv']}\n"
                             f"• {output_files['comments_csv']}"
                    )

                    # Update Supabase Staging UI State
                    self._handle_supabase_staging_complete(staging_dataset, staging_error)

                    self.is_collecting = False
                    self.btn_start.config(state=tk.NORMAL)
                    return

                elif msg_type == "ERROR":
                    _, err_text = msg
                    self.lbl_status.config(text="Status: Collection Failed")
                    self._append_log(f"\n[CRITICAL ERROR]: {err_text}")
                    messagebox.showerror("Collection Error", f"An error occurred during collection:\n{err_text}")

                    self.is_collecting = False
                    self.btn_start.config(state=tk.NORMAL)
                    return

                elif msg_type == "SUPABASE_UPLOAD_COMPLETE":
                    _, summary = msg
                    self.btn_upload_supabase.config(state=tk.NORMAL)
                    status_text = "Supabase Upload Complete (Success)" if summary.success else "Supabase Upload Completed with Issues"
                    color = "green" if summary.success else "#b86b00"
                    self.lbl_supabase_status.config(text=f"Supabase Upload: {status_text}", foreground=color)
                    self._append_log(f"\n[SUPABASE UPLOAD COMPLETE]: {status_text}")

                    SupabaseUploadSummaryDialog(parent=self.root, summary=summary)

                elif msg_type == "SUPABASE_UPLOAD_ERROR":
                    _, err_text = msg
                    self.btn_upload_supabase.config(state=tk.NORMAL)
                    self.lbl_supabase_status.config(text=f"Supabase Upload Failed: {err_text}", foreground="red")
                    self._append_log(f"\n[SUPABASE UPLOAD ERROR]: {err_text}")
                    messagebox.showerror("Upload Error", f"An error occurred during Supabase upload:\n{err_text}")

        except queue.Empty:
            pass

        if self.is_collecting:
            self.root.after(100, self._poll_queue)

    def _append_log(self, message: str):
        """Appends a line to the log text widget on the main thread."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _clear_logs(self):
        """Clears the log text widget."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _display_summary(self, summary: CollectionSummary):
        """Displays formatted collection summary in the summary text widget."""
        self.summary_text.config(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert(tk.END, summary.format_terminal_summary())
        self.summary_text.config(state=tk.DISABLED)

    def _clear_summary(self):
        """Clears the summary text widget."""
        self.summary_text.config(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.config(state=tk.DISABLED)

    def _populate_results_table(self, results: List[ExtractionResult]):
        """Populates the Research Article Results treeview table and updates inspection panel."""
        self.current_results = list(results)

        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        for i, res in enumerate(results):
            row_vals = format_article_table_row(res)
            self.results_tree.insert("", tk.END, iid=str(i), values=row_vals)

        if results:
            first_item = self.results_tree.get_children()[0]
            self.results_tree.selection_set(first_item)
            self.results_tree.focus(first_item)
            self._on_tree_selection_changed(None)
        else:
            self._clear_detail_pane()

    def _on_tree_selection_changed(self, event=None):
        """Event handler for Treeview row selection; displays article inspection details."""
        selected_items = self.results_tree.selection()
        if not selected_items:
            self._clear_detail_pane()
            return

        try:
            index = int(selected_items[0])
            if 0 <= index < len(self.current_results):
                res = self.current_results[index]
                detail_str = format_article_detail_text(res)
                self.detail_text.config(state=tk.NORMAL)
                self.detail_text.delete("1.0", tk.END)
                self.detail_text.insert(tk.END, detail_str)
                self.detail_text.config(state=tk.DISABLED)
        except (ValueError, IndexError):
            self._clear_detail_pane()

    def _clear_detail_pane(self):
        """Clears the article detail inspection pane."""
        self.detail_text.config(state=tk.NORMAL)
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.config(state=tk.DISABLED)

    # -------------------------------------------------------------------------
    # Supabase Staging Preview & Export Helpers
    # -------------------------------------------------------------------------
    def _handle_supabase_staging_complete(
        self,
        staging_dataset: Optional[SupabaseStagingDataset],
        staging_error: Optional[str]
    ):
        """
        Handles post-collection Supabase staging state update on the main thread.
        Isolates staging state updates so failures do not affect standard collection output.
        """
        if staging_error:
            self.current_staging_dataset = None
            self._clear_supabase_preview()
            self.lbl_supabase_status.config(
                text=f"Supabase Staging Error: {staging_error}",
                foreground="red"
            )
            self.btn_export_supabase.config(state=tk.DISABLED)
            self.btn_upload_supabase.config(state=tk.DISABLED)
            self._append_log(f"[SUPABASE STAGING ERROR]: {staging_error}")

        elif staging_dataset:
            self.current_staging_dataset = staging_dataset
            self._populate_supabase_preview(staging_dataset)

            errors = staging_dataset.validation_errors
            warnings = staging_dataset.validation_warnings

            if errors:
                self.lbl_supabase_status.config(
                    text=f"Supabase Staging Invalid: {len(errors)} error(s), {len(warnings)} warning(s)",
                    foreground="red"
                )
                self.btn_export_supabase.config(state=tk.DISABLED)
                self.btn_upload_supabase.config(state=tk.DISABLED)
                self._append_log(f"[SUPABASE STAGING INVALID]: {len(errors)} error(s) prevent Supabase export.")
                for err in errors:
                    self._append_log(f"  • [ERROR] {err}")
            else:
                art_cnt = len(staging_dataset.articles)
                cm_cnt = len(staging_dataset.comments)
                if warnings:
                    self.lbl_supabase_status.config(
                        text=f"Supabase Staging Ready: {art_cnt} article(s), {cm_cnt} comment(s) ({len(warnings)} warning(s))",
                        foreground="#b86b00"
                    )
                    self._append_log(f"[SUPABASE STAGING READY]: Staging dataset built with {len(warnings)} warning(s). Export enabled.")
                    for w in warnings:
                        self._append_log(f"  • [WARNING] {w}")
                else:
                    self.lbl_supabase_status.config(
                        text=f"Supabase Staging Ready: {art_cnt} article(s), {cm_cnt} comment(s) (Valid)",
                        foreground="green"
                    )
                    self._append_log(f"[SUPABASE STAGING READY]: Staging dataset valid ({art_cnt} articles, {cm_cnt} comments). Export enabled.")

                self.btn_export_supabase.config(state=tk.NORMAL)
                self.btn_upload_supabase.config(state=tk.NORMAL)

        else:
            self.current_staging_dataset = None
            self._clear_supabase_preview()
            self.lbl_supabase_status.config(
                text="Supabase Staging Status: No articles collected.",
                foreground="#555555"
            )
            self.btn_export_supabase.config(state=tk.DISABLED)
            self.btn_upload_supabase.config(state=tk.DISABLED)

    def _populate_supabase_preview(self, dataset: SupabaseStagingDataset):
        """
        Populates both Supabase preview treeviews (Articles and Comments) and selects first row if present.
        """
        # Populate Articles Treeview
        for item in self.supabase_articles_tree.get_children():
            self.supabase_articles_tree.delete(item)

        for i, row in enumerate(dataset.articles):
            vals = format_supabase_article_tree_row(row)
            self.supabase_articles_tree.insert("", tk.END, iid=str(i), values=vals)

        if dataset.articles:
            first_art = self.supabase_articles_tree.get_children()[0]
            self.supabase_articles_tree.selection_set(first_art)
            self.supabase_articles_tree.focus(first_art)
            self._on_supabase_article_selected(None)
        else:
            self._clear_supabase_article_detail()

        # Populate Comments Treeview
        for item in self.supabase_comments_tree.get_children():
            self.supabase_comments_tree.delete(item)

        for i, row in enumerate(dataset.comments):
            vals = format_supabase_comment_tree_row(row)
            self.supabase_comments_tree.insert("", tk.END, iid=str(i), values=vals)

        if dataset.comments:
            first_cm = self.supabase_comments_tree.get_children()[0]
            self.supabase_comments_tree.selection_set(first_cm)
            self.supabase_comments_tree.focus(first_cm)
            self._on_supabase_comment_selected(None)
        else:
            self._clear_supabase_comment_detail()

    def _clear_supabase_preview(self):
        """Clears both Supabase preview treeviews and detail panes."""
        for item in self.supabase_articles_tree.get_children():
            self.supabase_articles_tree.delete(item)
        for item in self.supabase_comments_tree.get_children():
            self.supabase_comments_tree.delete(item)
        self._clear_supabase_article_detail()
        self._clear_supabase_comment_detail()

    def _on_supabase_article_selected(self, event=None):
        """Event handler for Supabase Article treeview row selection."""
        if not self.current_staging_dataset:
            self._clear_supabase_article_detail()
            return
        selected = self.supabase_articles_tree.selection()
        if not selected:
            self._clear_supabase_article_detail()
            return
        try:
            idx = int(selected[0])
            if 0 <= idx < len(self.current_staging_dataset.articles):
                row = self.current_staging_dataset.articles[idx]
                detail_str = format_supabase_article_detail(row)
                self.supabase_article_detail_text.config(state=tk.NORMAL)
                self.supabase_article_detail_text.delete("1.0", tk.END)
                self.supabase_article_detail_text.insert(tk.END, detail_str)
                self.supabase_article_detail_text.config(state=tk.DISABLED)
        except (ValueError, IndexError):
            self._clear_supabase_article_detail()

    def _clear_supabase_article_detail(self):
        """Clears the Supabase Article detail inspection pane."""
        self.supabase_article_detail_text.config(state=tk.NORMAL)
        self.supabase_article_detail_text.delete("1.0", tk.END)
        self.supabase_article_detail_text.config(state=tk.DISABLED)

    def _on_supabase_comment_selected(self, event=None):
        """Event handler for Supabase Comment treeview row selection."""
        if not self.current_staging_dataset:
            self._clear_supabase_comment_detail()
            return
        selected = self.supabase_comments_tree.selection()
        if not selected:
            self._clear_supabase_comment_detail()
            return
        try:
            idx = int(selected[0])
            if 0 <= idx < len(self.current_staging_dataset.comments):
                row = self.current_staging_dataset.comments[idx]
                detail_str = format_supabase_comment_detail(row)
                self.supabase_comment_detail_text.config(state=tk.NORMAL)
                self.supabase_comment_detail_text.delete("1.0", tk.END)
                self.supabase_comment_detail_text.insert(tk.END, detail_str)
                self.supabase_comment_detail_text.config(state=tk.DISABLED)
        except (ValueError, IndexError):
            self._clear_supabase_comment_detail()

    def _clear_supabase_comment_detail(self):
        """Clears the Supabase Comment detail inspection pane."""
        self.supabase_comment_detail_text.config(state=tk.NORMAL)
        self.supabase_comment_detail_text.delete("1.0", tk.END)
        self.supabase_comment_detail_text.config(state=tk.DISABLED)

    def _on_export_supabase_clicked(self):
        """
        Prompts user for export directory and exports current SupabaseStagingDataset to articles_supabase.csv and comments_supabase.csv.
        """
        if not self.current_staging_dataset or self.current_staging_dataset.validation_errors:
            messagebox.showwarning(
                "Export Unavailable",
                "Cannot export Supabase staging CSVs because the staging dataset is missing or contains validation errors."
            )
            return

        target_dir = filedialog.askdirectory(
            title="Select Output Folder for Supabase Staging CSVs",
            initialdir=os.path.abspath(self.DEFAULT_OUTPUT_DIR)
        )
        if not target_dir:
            return

        try:
            paths = SupabaseCSVExporter.export(self.current_staging_dataset, output_dir=target_dir)
            art_csv = paths.get("articles_csv", "")
            cm_csv = paths.get("comments_csv", "")
            self._append_log(f"\n[SUPABASE EXPORT SUCCESSFUL]:")
            self._append_log(f"  • Articles Staging CSV: {art_csv}")
            self._append_log(f"  • Comments Staging CSV: {cm_csv}")

            messagebox.showinfo(
                "Supabase Export Successful",
                f"Successfully exported Supabase staging CSVs to:\n\n"
                f"Articles: {art_csv}\n"
                f"Comments: {cm_csv}"
            )
        except Exception as e:
            self._append_log(f"[SUPABASE EXPORT ERROR]: Failed to write CSV files: {str(e)}")
            messagebox.showerror("Export Failed", f"An error occurred while exporting Supabase staging CSVs:\n\n{str(e)}")

    def _on_upload_supabase_clicked(self):
        """
        Launches the Supabase Direct Upload configuration & dry run dialog.
        """
        if not self.current_staging_dataset or self.current_staging_dataset.validation_errors:
            messagebox.showwarning(
                "Upload Unavailable",
                "Cannot upload to Supabase because the staging dataset is missing or contains validation errors."
            )
            return

        SupabaseUploadDialog(
            parent=self.root,
            dataset=self.current_staging_dataset,
            on_start_upload=self._start_supabase_upload
        )

    def _start_supabase_upload(self, config, dry_run_result):
        """
        Launches worker thread to execute direct upload to Supabase.
        """
        self._append_log("\n=== Starting Direct Upload to Supabase ===")
        self.lbl_supabase_status.config(
            text="Supabase Upload: Upload in progress...",
            foreground="#0055aa"
        )
        self.btn_upload_supabase.config(state=tk.DISABLED)

        thread = threading.Thread(
            target=self._worker_supabase_upload_task,
            args=(self.current_staging_dataset, config, dry_run_result),
            daemon=True
        )
        thread.start()

    def _worker_supabase_upload_task(self, dataset, config, dry_run_result):
        """
        Executes upload in background worker thread and posts summary to queue.
        """
        try:
            client = SupabaseClient(config=config)
            uploader = SupabaseUploader(client=client)
            summary = uploader.execute_upload(dataset, dry_run_result=dry_run_result)
            self.queue.put(("SUPABASE_UPLOAD_COMPLETE", summary))
        except Exception as ex:
            self.queue.put(("SUPABASE_UPLOAD_ERROR", str(ex)))

    def _on_discover_candidates_clicked(self):
        """Opens the Candidate Article Discovery dialog."""
        initial_topic = self.ent_topic.get().strip()
        CandidateDiscoveryDialog(
            parent=self.root,
            initial_topic=initial_topic,
            on_import_callback=self._on_candidates_imported
        )

    def _on_candidates_imported(self, imported_urls: List[str], topic_query: str):
        """Callback handling candidate URLs imported from the discovery dialog."""
        if not imported_urls:
            return

        current_content = self.url_text.get("1.0", tk.END).strip()
        new_urls_str = "\n".join(imported_urls)

        if current_content:
            combined = current_content + "\n" + new_urls_str
        else:
            combined = new_urls_str

        self.url_text.delete("1.0", tk.END)
        self.url_text.insert(tk.END, combined + "\n")

        if topic_query and not self.ent_topic.get().strip():
            self.ent_topic.delete(0, tk.END)
            self.ent_topic.insert(0, topic_query)

        self._append_log(f"Imported {len(imported_urls)} candidate URL(s) into input list.")
        self.lbl_status.config(text=f"Status: Imported {len(imported_urls)} candidate URL(s). Ready to collect.")

    def on_close(self):
        """Handles application shutdown when closing the main window."""
        if self.is_collecting:
            if not messagebox.askyesno("Confirm Exit", "A collection run is currently in progress. Are you sure you want to exit?"):
                return
        self.root.destroy()


class CandidateDiscoveryDialog(tk.Toplevel):
    """
    Tkinter Toplevel dialog for candidate article discovery and interactive preview/selection.
    Allows entering main search topics, selecting Yahoo/MSN source filters, max candidate counts,
    include/exclude keywords, and start/end dates.
    """
    def __init__(self, parent: tk.Tk, initial_topic: str = "", on_import_callback=None):
        super().__init__(parent)
        self.title("Candidate Article Discovery & Preview")
        self.geometry("920x650")
        self.minsize(640, 480)

        self.on_import_callback = on_import_callback
        self.queue: queue.Queue = queue.Queue()
        self.is_discovering = False
        self.discovered_candidates: List[CandidateArticle] = []

        self._create_widgets(initial_topic)
        self.transient(parent)
        self.grab_set()

    def _create_widgets(self, initial_topic: str):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Search Query & Filtering Parameters
        param_group = ttk.LabelFrame(main_frame, text=" 1. Search Topic & Discovery Filters ", padding="8")
        param_group.pack(fill=tk.X, expand=False, pady=(0, 8))

        grid = ttk.Frame(param_group)
        grid.pack(fill=tk.X, expand=True)

        # Configure columns so text entry fields stretch with window width
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(4, weight=1)

        # --- Row 0: Topic Query (Full Width Stretch) ---
        ttk.Label(grid, text="Discovery Search Query (Optional):").grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=3)
        self.ent_query = ttk.Entry(grid)
        self.ent_query.insert(0, initial_topic)
        self.ent_query.grid(row=0, column=1, columnspan=4, sticky=tk.EW, padx=(0, 0), pady=3)

        # --- Row 1: Query Help Text ---
        lbl_query_help = ttk.Label(
            grid,
            text="Optional query for external news search. If left blank, Include Keywords will be used.",
            font=("Segoe UI", 8, "italic"),
            foreground="#555555",
            wraplength=600
        )
        lbl_query_help.grid(row=1, column=1, columnspan=4, sticky=tk.W, pady=(0, 4))

        # --- Row 2: Sources & Max Candidates ---
        ttk.Label(grid, text="Sources:").grid(row=2, column=0, sticky=tk.W, padx=(0, 4), pady=3)
        sources_subframe = ttk.Frame(grid)
        sources_subframe.grid(row=2, column=1, sticky=tk.W, pady=3)
        self.var_yahoo = tk.BooleanVar(value=True)
        self.var_msn = tk.BooleanVar(value=True)
        self.chk_yahoo = ttk.Checkbutton(sources_subframe, text="Yahoo News", variable=self.var_yahoo)
        self.chk_yahoo.pack(side=tk.LEFT, padx=(0, 8))
        self.chk_msn = ttk.Checkbutton(sources_subframe, text="MSN", variable=self.var_msn)
        self.chk_msn.pack(side=tk.LEFT)

        ttk.Label(grid, text="Max Candidates:").grid(row=2, column=3, sticky=tk.E, padx=(16, 4), pady=3)
        self.ent_max = ttk.Entry(grid, width=8)
        self.ent_max.insert(0, "20")
        self.ent_max.grid(row=2, column=4, sticky=tk.W, pady=3)

        # --- Row 3: Include & Exclude Keywords ---
        ttk.Label(grid, text="Include Keywords:").grid(row=3, column=0, sticky=tk.W, padx=(0, 4), pady=3)
        inc_subframe = ttk.Frame(grid)
        inc_subframe.grid(row=3, column=1, sticky=tk.EW, pady=3)
        inc_subframe.columnconfigure(0, weight=1)
        
        self.ent_inc = ttk.Entry(inc_subframe)
        self.ent_inc.grid(row=0, column=0, sticky=tk.EW, padx=(0, 4))
        ttk.Label(inc_subframe, text="Mode:").grid(row=0, column=1, sticky=tk.W, padx=(2, 2))
        self.cmb_inc_mode = ttk.Combobox(inc_subframe, values=["ANY", "ALL"], width=5, state="readonly")
        self.cmb_inc_mode.set("ANY")
        self.cmb_inc_mode.grid(row=0, column=2, sticky=tk.W)

        ttk.Label(grid, text="Exclude Keywords:").grid(row=3, column=3, sticky=tk.E, padx=(16, 4), pady=3)
        self.ent_exc = ttk.Entry(grid)
        self.ent_exc.grid(row=3, column=4, sticky=tk.EW, pady=3)

        # --- Row 4: Keyword Help Examples & Search Button ---
        lbl_inc_help = ttk.Label(
            grid,
            text="Comma-separated (e.g. AI, Education). Searches headline + snippet.\nANY = match any term; ALL = match all terms.",
            font=("Segoe UI", 8, "italic"),
            foreground="#555555",
            wraplength=310
        )
        lbl_inc_help.grid(row=4, column=1, sticky=tk.W, pady=(0, 4))

        lbl_exc_help = ttk.Label(
            grid,
            text="Comma-separated (e.g. sports, finance). Searches headline + snippet.\nOmits candidates matching any term.",
            font=("Segoe UI", 8, "italic"),
            foreground="#555555",
            wraplength=310
        )
        lbl_exc_help.grid(row=4, column=4, sticky=tk.W, pady=(0, 4))

        self.btn_search = ttk.Button(grid, text="Discover Candidates", command=self.on_discover_clicked)
        self.btn_search.grid(row=4, column=3, columnspan=2, sticky=tk.E, pady=(4, 4))

        # Status & Progress
        self.lbl_status = ttk.Label(main_frame, text="Status: Enter query or keywords and click Discover Candidates", font=("Segoe UI", 9, "italic"))
        self.lbl_status.pack(fill=tk.X, expand=False, pady=(0, 4))

        # 2. Candidate Preview & Selection Table
        table_group = ttk.LabelFrame(main_frame, text=" 2. Discovered Candidates Preview & Selection ", padding="8")
        table_group.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        columns = ("select", "platform", "title", "pub_date", "domain", "url")
        self.tree = ttk.Treeview(table_group, columns=columns, show="headings", selectmode="extended")

        self.tree.heading("select", text="Select")
        self.tree.column("select", width=55, minwidth=40, stretch=False)
        self.tree.heading("platform", text="Platform")
        self.tree.column("platform", width=95, minwidth=60, stretch=False)
        self.tree.heading("title", text="Headline Title")
        self.tree.column("title", width=260, minwidth=100, stretch=True)
        self.tree.heading("pub_date", text="Publication Date")
        self.tree.column("pub_date", width=120, minwidth=80, stretch=False)
        self.tree.heading("domain", text="Domain")
        self.tree.column("domain", width=110, minwidth=80, stretch=False)
        self.tree.heading("url", text="Validated Article URL")
        self.tree.column("url", width=220, minwidth=100, stretch=True)

        v_scroll = ttk.Scrollbar(table_group, orient=tk.VERTICAL, command=self.tree.yview)
        h_scroll = ttk.Scrollbar(table_group, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.bind("<Button-1>", self._on_tree_click)

        # 3. Action Toolbar
        action_bar = ttk.Frame(main_frame)
        action_bar.pack(fill=tk.X, expand=False)

        btn_select_all = ttk.Button(action_bar, text="Select All", command=self._on_select_all)
        btn_select_all.pack(side=tk.LEFT, padx=(0, 4))

        btn_deselect_all = ttk.Button(action_bar, text="Deselect All", command=self._on_deselect_all)
        btn_deselect_all.pack(side=tk.LEFT, padx=(0, 4))

        btn_import = ttk.Button(action_bar, text="Import Selected Candidates to URL Input", command=self._on_import_clicked)
        btn_import.pack(side=tk.RIGHT)

    def _on_tree_click(self, event):
        """Toggles check state when clicking the select column."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            col = self.tree.identify_column(event.x)
            if col == "#1":  # 'select' column
                item_id = self.tree.identify_row(event.y)
                if item_id:
                    vals = list(self.tree.item(item_id, "values"))
                    vals[0] = "[  ]" if vals[0] == "[X]" else "[X]"
                    self.tree.item(item_id, values=vals)

    def _on_select_all(self):
        for item in self.tree.get_children():
            vals = list(self.tree.item(item, "values"))
            vals[0] = "[X]"
            self.tree.item(item, values=vals)

    def _on_deselect_all(self):
        for item in self.tree.get_children():
            vals = list(self.tree.item(item, "values"))
            vals[0] = "[  ]"
            self.tree.item(item, values=vals)

    def on_discover_clicked(self):
        if self.is_discovering:
            return

        query = self.ent_query.get().strip()
        inc_kws = [k.strip() for k in self.ent_inc.get().split(",") if k.strip()]
        inc_mode = (self.cmb_inc_mode.get() or "ANY").strip().upper()
        exc_kws = [k.strip() for k in self.ent_exc.get().split(",") if k.strip()]

        if not query and not inc_kws:
            messagebox.showwarning("Input Required", "Please enter a Discovery Search Query or at least one Include Keyword.")
            return

        if not self.var_yahoo.get() and not self.var_msn.get():
            messagebox.showwarning("Input Error", "Please select at least one source (Yahoo News or MSN).")
            return

        try:
            max_cands = int(self.ent_max.get().strip())
        except ValueError:
            messagebox.showerror("Input Error", "Max Candidates must be a valid integer.")
            return

        self.is_discovering = True
        self.btn_search.config(state=tk.DISABLED)
        status_query = query if query else ", ".join(inc_kws)
        self.lbl_status.config(text=f"Status: Discovering candidates for '{status_query}'...")

        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        thread = threading.Thread(
            target=self._worker_discover_task,
            args=(query, self.var_yahoo.get(), self.var_msn.get(), max_cands, inc_kws, inc_mode, exc_kws),
            daemon=True
        )
        thread.start()
        self.after(100, self._poll_discovery_queue)

    def _worker_discover_task(self, query, inc_yahoo, inc_msn, max_cands, inc_kws, inc_mode, exc_kws):
        try:
            discoverer = CandidateDiscoverer()
            cands = discoverer.discover(
                query=query,
                include_yahoo=inc_yahoo,
                include_msn=inc_msn,
                max_candidates=max_cands,
                include_keywords=inc_kws,
                include_keyword_mode=inc_mode,
                exclude_keywords=exc_kws
            )
            self.queue.put(("DONE", cands, query))
        except Exception as e:
            self.queue.put(("ERROR", str(e)))

    def _poll_discovery_queue(self):
        try:
            while True:
                msg = self.queue.get_nowait()
                if msg[0] == "DONE":
                    _, cands, query = msg
                    self.discovered_candidates = cands
                    valid_dates = sorted([c.publication_date[:10] for c in cands if c.publication_date])
                    if valid_dates:
                        earliest = valid_dates[0]
                        latest = valid_dates[-1]
                        if earliest == latest:
                            date_msg = f" Available dates in this search: {earliest}."
                        else:
                            date_msg = f" Available dates in this search: {earliest} to {latest}."
                    else:
                        date_msg = ""
                    self.lbl_status.config(text=f"Status: Discovered {len(cands)} candidate article(s).{date_msg}")
                    self.btn_search.config(state=tk.NORMAL)
                    self.is_discovering = False

                    for i, c in enumerate(cands):
                        pub_str = c.publication_date[:10] if c.publication_date else "N/A"
                        self.tree.insert("", tk.END, iid=str(i), values=(
                            "[X]",
                            c.platform,
                            c.title,
                            pub_str,
                            c.source_domain,
                            c.url
                        ))
                    return
                elif msg[0] == "ERROR":
                    _, err = msg
                    self.lbl_status.config(text=f"Status: Discovery error")
                    self.btn_search.config(state=tk.NORMAL)
                    self.is_discovering = False
                    messagebox.showerror("Discovery Error", f"Failed to discover candidates:\n{err}")
                    return
        except queue.Empty:
            pass

        if self.is_discovering:
            self.after(100, self._poll_discovery_queue)

    def _on_import_clicked(self):
        selected_urls = []
        for item in self.tree.get_children():
            vals = self.tree.item(item, "values")
            if vals[0] == "[X]":
                url = vals[5]
                selected_urls.append(url)

        if not selected_urls:
            messagebox.showwarning("No Selection", "Please select at least one candidate article to import.")
            return

        query = self.ent_query.get().strip()
        if self.on_import_callback:
            self.on_import_callback(selected_urls, query)

        self.destroy()


def main():
    """Main launcher entry point for the GUI application."""
    root = tk.Tk()
    app = CollectionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

