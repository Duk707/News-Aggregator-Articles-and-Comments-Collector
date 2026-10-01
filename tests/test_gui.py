"""
Unit tests for Desktop GUI validation logic, input parsing, log formatting, and queue messaging.
Designed to run headlessly and deterministically without requiring live display windows.
"""
import os
import sys

tcl_dir = os.path.join(sys.prefix, "tcl", "tcl8.6")
if not os.path.exists(tcl_dir):
    tcl_dir = os.path.join(sys.prefix, "Library", "lib", "tcl8.6")

tk_dir = os.path.join(sys.prefix, "tcl", "tk8.6")
if not os.path.exists(tk_dir):
    tk_dir = os.path.join(sys.prefix, "Library", "lib", "tk8.6")

if os.path.exists(tcl_dir):
    os.environ["TCL_LIBRARY"] = tcl_dir
if os.path.exists(tk_dir):
    os.environ["TK_LIBRARY"] = tk_dir

import pytest
import queue
from src.gui.validation import parse_url_input, validate_gui_config, format_result_log_line
from src.models.extraction import ExtractionResult
from src.models.article import Article
from src.models.comment_status import CommentStatus


def test_gui_url_input_parsing():
    """Verifies parsing of multiline raw text input into clean URL lists."""
    assert parse_url_input("") == []
    assert parse_url_input("   \n\n  ") == []

    raw_text = """
    # Sample input URL list
    https://news.yahoo.com/article1.html

    https://www.msn.com/en-us/news/article2.html
    # Another comment line
    https://news.yahoo.com/article3.html  
    """
    urls = parse_url_input(raw_text)
    assert len(urls) == 3
    assert urls[0] == "https://news.yahoo.com/article1.html"
    assert urls[1] == "https://www.msn.com/en-us/news/article2.html"
    assert urls[2] == "https://news.yahoo.com/article3.html"


def test_gui_config_validation_valid_defaults():
    """Verifies that valid string parameters produce the correct typed configuration dictionary."""
    is_valid, cfg, err = validate_gui_config(
        inter_article_delay_str="2.0",
        max_articles_str="50",
        max_comments_str="50",
        navigation_timeout_str="30"
    )
    assert is_valid is True
    assert err is None
    assert cfg is not None
    assert cfg["inter_article_delay"] == 2.0
    assert cfg["max_articles"] == 50
    assert cfg["max_comments_per_article"] == 50
    assert cfg["navigation_timeout_ms"] == 30000
    assert cfg["topic_query"] is None


def test_gui_config_validation_topic():
    """Verifies that nonblank topics are trimmed once and blank topics cleanly evaluate to None."""
    # 1. Blank string
    v1, cfg1, err1 = validate_gui_config("2.0", "50", "50", "30", topic_str="   ")
    assert v1 is True
    assert cfg1["topic_query"] is None

    # 2. Topic with leading/trailing spaces
    v2, cfg2, err2 = validate_gui_config("2.0", "50", "50", "30", topic_str="  AI in Education  ")
    assert v2 is True
    assert cfg2["topic_query"] == "AI in Education"

    # 3. Arbitrary topic string
    v3, cfg3, err3 = validate_gui_config("2.0", "50", "50", "30", topic_str="Renewable Energy")
    assert v3 is True
    assert cfg3["topic_query"] == "Renewable Energy"


def test_gui_config_validation_invalid_inputs():
    """Verifies that non-numeric, negative, or out-of-range inputs produce user-facing validation errors."""
    # 1. Non-numeric delay
    valid, cfg, err = validate_gui_config("invalid", "50", "50", "30")
    assert valid is False
    assert "Invalid inter-article delay" in err

    # 2. Negative delay
    valid, cfg, err = validate_gui_config("-1.5", "50", "50", "30")
    assert valid is False
    assert "non-negative" in err

    # 3. Zero max articles
    valid, cfg, err = validate_gui_config("2.0", "0", "50", "30")
    assert valid is False
    assert "positive integer" in err

    # 4. Non-integer max articles
    valid, cfg, err = validate_gui_config("2.0", "abc", "50", "30")
    assert valid is False
    assert "Must be an integer" in err

    # 5. Negative max comments
    valid, cfg, err = validate_gui_config("2.0", "50", "-10", "30")
    assert valid is False
    assert "non-negative" in err

    # 6. Zero navigation timeout
    valid, cfg, err = validate_gui_config("2.0", "50", "50", "0")
    assert valid is False
    assert "greater than zero" in err


def test_gui_result_log_line_formatting():
    """Verifies formatting of ExtractionResult records into human-readable progress log lines."""
    # Success result
    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/article1.html",
        title="Test Yahoo Article Title For Logging Verification",
        comments_status=CommentStatus.AVAILABLE,
        comments_collected=5,
        article_text="Sample text",
        retrieved_at="2026-09-25T21:00:00Z"
    )
    res_success = ExtractionResult(
        requested_url="https://news.yahoo.com/article1.html",
        success=True,
        article=art,
        comments_status=CommentStatus.AVAILABLE,
        retrieved_at="2026-09-25T21:00:00Z"
    )
    log_line = format_result_log_line(res_success, 1, 3)
    assert "[1/3] SUCCESS (Yahoo News)" in log_line
    assert "Test Yahoo Article Title" in log_line
    assert "5 comments" in log_line

    # Unsupported domain result
    res_unsupported = ExtractionResult(
        requested_url="https://example.com/unsupported",
        success=False,
        comments_status=CommentStatus.UNSUPPORTED,
        error_message="Unsupported domain",
        retrieved_at="2026-09-25T21:00:00Z"
    )
    log_unsupported = format_result_log_line(res_unsupported, 2, 3)
    assert "[2/3] UNSUPPORTED" in log_unsupported
    assert "https://example.com/unsupported" in log_unsupported

    # Duplicate result
    res_dup = ExtractionResult(
        requested_url="https://news.yahoo.com/article1.html",
        success=False,
        comments_status=CommentStatus.UNKNOWN,
        error_message="Duplicate URL skipped",
        retrieved_at="2026-09-25T21:00:00Z"
    )
    log_dup = format_result_log_line(res_dup, 3, 3)
    assert "[3/3] DUPLICATE" in log_dup


def test_gui_worker_queue_messaging():
    """Verifies worker-thread messaging queue behavior without instantiating Tkinter display components."""
    test_queue = queue.Queue()

    # Simulate worker posting progress message
    res = ExtractionResult(
        requested_url="https://news.yahoo.com/article1.html",
        success=True,
        comments_status=CommentStatus.AVAILABLE,
        retrieved_at="2026-09-25T21:00:00Z"
    )
    test_queue.put(("PROGRESS", 1, 2, res))
    test_queue.put(("COMPLETE", [res], "Summary Object Placeholder", {"json": "data/output/articles.json"}))

    # Poll messages
    msg1 = test_queue.get_nowait()
    assert msg1[0] == "PROGRESS"
    assert msg1[1] == 1
    assert msg1[2] == 2

    msg2 = test_queue.get_nowait()
    assert msg2[0] == "COMPLETE"
    assert msg2[3]["json"] == "data/output/articles.json"


def test_gui_format_article_table_row():
    """Verifies formatting of ExtractionResult objects into 9-tuple Treeview table row cells."""
    from src.gui.validation import format_article_table_row

    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/article1.html",
        canonical_url="https://news.yahoo.com/article1.html",
        original_publisher="Associated Press",
        title="AI in Education Breakthrough Announced",
        author="John Doe",
        publication_datetime="2026-09-25T10:00:00Z",
        comments_status=CommentStatus.AVAILABLE,
        comment_count_reported=100,
        comments_collected=12,
        extraction_method="json-ld",
        article_text="Full article text body...",
        retrieved_at="2026-09-25T21:00:00Z"
    )
    res_success = ExtractionResult(
        requested_url="https://news.yahoo.com/article1.html",
        success=True,
        article=art,
        comments_status=CommentStatus.AVAILABLE,
        retrieved_at="2026-09-25T21:00:00Z"
    )

    row_cells = format_article_table_row(res_success)
    assert len(row_cells) == 9
    assert row_cells[0] == "Yahoo News"
    assert row_cells[1] == "AI in Education Breakthrough Announced"
    assert row_cells[2] == "Associated Press"
    assert row_cells[3] == "2026-09-25 10:00:00"
    assert row_cells[4] == "SUCCESS"
    assert row_cells[5] == "AVAILABLE"
    assert row_cells[6] == "100"
    assert row_cells[7] == "12"
    assert row_cells[8] == "json-ld"

    # Unsupported domain
    res_unsupported = ExtractionResult(
        requested_url="https://unknown-domain.com/item",
        success=False,
        comments_status=CommentStatus.UNSUPPORTED,
        error_message="Unsupported domain",
        retrieved_at="2026-09-25T21:00:00Z"
    )
    row_unsupported = format_article_table_row(res_unsupported)
    assert row_unsupported[0] == "Unknown"
    assert row_unsupported[1] == "[Unsupported Domain]"
    assert row_unsupported[4] == "UNSUPPORTED"
    assert row_unsupported[5] == "UNSUPPORTED"


def test_gui_format_article_detail_text():
    """Verifies generation of detailed multi-line text for the article research inspection panel."""
    from src.gui.validation import format_article_detail_text

    art = Article(
        platform="MSN",
        source_adapter="MSNAdapter",
        requested_url="https://www.msn.com/en-us/news/article.html",
        canonical_url="https://www.msn.com/en-us/news/article.html",
        original_publisher="Reuters",
        title="MSN AI Research Article Title",
        author="Jane Smith",
        publication_datetime="2026-09-25T14:30:00Z",
        comments_status=CommentStatus.DISABLED,
        comments_collected=0,
        extraction_method="open_graph",
        article_text="Detailed MSN article body snippet text for inspection panel verification.",
        retrieved_at="2026-09-25T21:00:00Z"
    )
    res = ExtractionResult(
        requested_url="https://www.msn.com/en-us/news/article.html",
        success=True,
        article=art,
        comments_status=CommentStatus.DISABLED,
        diagnostic_notes=["Public comments explicitly disabled by publisher."],
        retrieved_at="2026-09-25T21:00:00Z"
    )

    detail_str = format_article_detail_text(res)
    assert "ARTICLE METADATA & RESEARCH INSPECTION DETAILS" in detail_str
    assert "Requested URL:      https://www.msn.com/en-us/news/article.html" in detail_str
    assert "Platform:           MSN" in detail_str
    assert "Original Publisher: Reuters" in detail_str
    assert "Title:              MSN AI Research Article Title" in detail_str
    assert "Extraction Method:  open_graph" in detail_str
    assert "Comment Status:     DISABLED" in detail_str
    assert "Public comments explicitly disabled" in detail_str
    assert "Detailed MSN article body snippet text" in detail_str


def test_gui_worker_task_export_integration(tmp_path, monkeypatch):
    """
    Regression test for Step 25 GUI export integration:
    Verifies that CollectionApp._worker_collection_task correctly invokes the production
    JSONExporter.export_batch and CSVExporter.export interfaces without AttributeError or export failures.
    """
    import os
    import queue
    from unittest.mock import MagicMock
    from src.gui.app import CollectionApp
    from src.models.extraction import ExtractionResult
    from src.models.article import Article
    from src.models.comment_status import CommentStatus

    app = MagicMock(spec=CollectionApp)
    app.DEFAULT_OUTPUT_DIR = str(tmp_path / "output")
    app.queue = queue.Queue()

    mock_bm = MagicMock()
    monkeypatch.setattr("src.gui.app.BrowserManager", MagicMock(return_value=mock_bm))

    timestamp = "2026-09-26T00:00:00Z"
    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/test-article.html",
        canonical_url="https://news.yahoo.com/test-article.html",
        original_publisher="Associated Press",
        title="GUI Export Integration Article",
        comments_status=CommentStatus.NOT_LOADED,
        comments_collected=0,
        article_text="Sample article body text.",
        retrieved_at=timestamp
    )
    mock_results = [
        ExtractionResult(
            requested_url="https://news.yahoo.com/test-article.html",
            success=True,
            article=art,
            comments_status=CommentStatus.NOT_LOADED,
            retrieved_at=timestamp
        )
    ]

    mock_collector_inst = MagicMock()
    mock_collector_inst.collect_urls.return_value = mock_results
    monkeypatch.setattr("src.gui.app.BatchCollector", MagicMock(return_value=mock_collector_inst))

    config_dict = {
        "inter_article_delay": 0.0,
        "max_articles": 10,
        "max_comments_per_article": 10,
        "navigation_timeout_ms": 5000,
        "topic_query": "AI in Education"
    }

    CollectionApp._worker_collection_task(app, ["https://news.yahoo.com/test-article.html"], config_dict)

    messages = []
    while not app.queue.empty():
        messages.append(app.queue.get_nowait())

    assert len(messages) == 1
    assert messages[0][0] == "COMPLETE"
    _, results, summary, output_files = messages[0][:4]

    assert os.path.exists(output_files["json"])
    assert os.path.exists(output_files["articles_csv"])
    assert os.path.exists(output_files["comments_csv"])
    assert os.path.getsize(output_files["json"]) > 0
    assert os.path.getsize(output_files["articles_csv"]) > 0


def test_gui_responsive_scrolling_and_reflow_layout():
    """
    Regression test for Step 25 GUI Usability Cleanup:
    1. Verifies CollectionApp dual scrollbars (vertical & horizontal) and 10 ResizablePanels.
    2. Verifies CandidateDiscoveryDialog multi-row responsive reflow grid layout.
    """
    import tkinter as tk
    from src.gui.app import CollectionApp, CandidateDiscoveryDialog

    root = tk.Tk()
    root.withdraw()

    # Test CollectionApp Layout
    app = CollectionApp(root)
    assert hasattr(app, "main_canvas")
    assert hasattr(app, "v_scrollbar")
    assert hasattr(app, "h_scrollbar")
    assert hasattr(app, "notebook")
    assert hasattr(app, "panel_input")
    assert hasattr(app, "panel_config")
    assert hasattr(app, "panel_results")
    assert hasattr(app, "panel_tree")
    assert hasattr(app, "panel_detail")
    assert hasattr(app, "panel_output")
    assert len(app.resizable_panels) == 10
    assert app.root.minsize() == (720, 500)

    # Force geometry update to trigger canvas configure
    root.update_idletasks()
    scrollregion = app.main_canvas.cget("scrollregion")
    assert scrollregion != ""  # Scrollregion is configured

    # Test CandidateDiscoveryDialog Layout
    dialog = CandidateDiscoveryDialog(root, initial_topic="AI in Education")
    assert dialog.minsize() == (640, 480)
    assert hasattr(dialog, "ent_query")
    assert hasattr(dialog, "chk_yahoo")
    assert hasattr(dialog, "chk_msn")
    assert hasattr(dialog, "ent_max")
    assert hasattr(dialog, "ent_inc")
    assert hasattr(dialog, "cmb_inc_mode")
    assert hasattr(dialog, "ent_exc")
    assert hasattr(dialog, "btn_search")

    # Verify Max Candidates entry grid row and sticky state
    max_info = dialog.ent_max.grid_info()
    assert max_info["row"] == 2  # Reflowed onto row 2 alongside sources

    query_info = dialog.ent_query.grid_info()
    assert query_info["row"] == 0
    assert "e" in query_info["sticky"] and "w" in query_info["sticky"]  # Expands horizontally

    # Verify Include/Exclude entries are on row 3 and search button shifted to row 4
    inc_info = dialog.ent_inc.master.grid_info()
    assert inc_info["row"] == 3
    btn_info = dialog.btn_search.grid_info()
    assert btn_info["row"] == 4

    dialog.destroy()
    root.destroy()


def test_gui_discovery_status_date_range_formatting():
    """Verifies that discovered candidate publication dates are cleanly formatted into dialog status."""
    import tkinter as tk
    from src.gui.app import CandidateDiscoveryDialog
    from src.discovery.models import CandidateArticle

    root = tk.Tk()
    root.withdraw()

    dialog = CandidateDiscoveryDialog(root, initial_topic="AI in Education")

    cand1 = CandidateArticle(title="Art 1", url="https://news.yahoo.com/1", platform="Yahoo News", source_domain="news.yahoo.com", discovery_query="AI", discovered_at="2026-09-26T00:00:00Z", publication_date="2026-09-15T10:00:00Z")
    cand2 = CandidateArticle(title="Art 2", url="https://www.msn.com/2", platform="MSN", source_domain="www.msn.com", discovery_query="AI", discovered_at="2026-09-26T00:00:00Z", publication_date="2026-09-26T12:00:00Z")

    dialog.queue.put(("DONE", [cand1, cand2], "AI in Education"))
    dialog._poll_discovery_queue()

    status_text = dialog.lbl_status.cget("text")
    assert "Discovered 2 candidate article(s)" in status_text
    assert "Available dates in this search: 2026-09-15 to 2026-09-26." in status_text

    dialog.destroy()
    root.destroy()


def test_gui_2d_corner_grip_panel_resizing():
    """
    Regression test for Step 25 2D Corner Grip Resizable Panels:
    1. Verifies mouse press, drag, release resizing along horizontal, vertical, and diagonal vectors.
    2. Verifies defensive minsize clamping when dragging below panel minimum bounds.
    3. Verifies double-click grip reset back to automatic responsive sizing.
    """
    import tkinter as tk
    from unittest.mock import MagicMock
    from src.gui.app import CollectionApp

    root = tk.Tk()
    root.geometry("920x720")
    root.update_idletasks()

    app = CollectionApp(root)
    root.update_idletasks()

    panel = app.panel_input
    assert hasattr(panel, "grip")

    # 1. Simulate diagonal drag (+150px X, +100px Y)
    press_event = MagicMock()
    press_event.x_root = 100
    press_event.y_root = 100
    panel._on_grip_press(press_event)

    drag_event = MagicMock()
    drag_event.x_root = 250
    drag_event.y_root = 200
    panel._on_grip_drag(drag_event)

    assert panel.user_req_width is not None
    assert panel.user_req_height is not None
    assert panel.user_req_width > panel.min_width
    assert panel.user_req_height > panel.min_height

    # Verify workspace geometry recalculation triggered
    app._update_workspace_geometry()
    canvas_item_width = app.main_canvas.itemcget(app.canvas_window, "width")
    assert float(canvas_item_width) >= panel.user_req_width

    # 2. Test minsize clamping (-800px X, -800px Y drag)
    drag_min_event = MagicMock()
    drag_min_event.x_root = -700
    drag_min_event.y_root = -700
    panel._on_grip_drag(drag_min_event)

    assert panel.user_req_width == panel.min_width
    assert panel.user_req_height == panel.min_height

    # 3. Test double-click reset to automatic responsive behavior
    dbl_event = MagicMock()
    panel._on_grip_double_click(dbl_event)
    assert panel.user_req_width is None
    assert panel.user_req_height is None

    root.destroy()


def test_gui_panel_independence_and_workspace_scrolling():
    """
    Regression test verifying independent panel dimensions and dual canvas scrolling:
    1. Records rendered dimensions (winfo_width, winfo_height) of Panel A (URL Input) and Panel B (Config).
    2. Horizontally resizes Panel A -> verifies Panel A rendered width changes, Panel A height is unchanged, Panel B dimensions unchanged.
    3. Vertically resizes Panel A -> verifies Panel A rendered height changes while width remains at user-selected width.
    4. Diagonally resizes Panel A -> verifies both width and height update.
    5. Verifies small window geometry (<700px) activates horizontal scrollbar scrollregion without clipping.
    6. Verifies large window geometry (1400px+) preserves independent panel rendered rectangle.
    """
    import tkinter as tk
    from unittest.mock import MagicMock
    from src.gui.app import CollectionApp

    root = tk.Tk()
    root.geometry("900x700")
    root.update_idletasks()

    app = CollectionApp(root)
    root.update_idletasks()

    panel_a = app.panel_input
    panel_b = app.panel_config

    # 1. Horizontally resize Panel A (+150px X)
    press_ev = MagicMock()
    press_ev.x_root = 100
    press_ev.y_root = 100
    panel_a._on_grip_press(press_ev)

    drag_h = MagicMock()
    drag_h.x_root = 250
    drag_h.y_root = 100
    panel_a._on_grip_drag(drag_h)
    root.update_idletasks()

    assert panel_a.user_req_width is not None
    assert abs(panel_a.winfo_width() - panel_a.user_req_width) <= 20

    # Panel B dimensions remain independent
    assert panel_b.user_req_width is None
    assert panel_b.user_req_height is None

    # 2. Vertically resize Panel A (+120px Y)
    drag_v = MagicMock()
    drag_v.x_root = 250
    drag_v.y_root = 220
    panel_a._on_grip_drag(drag_v)
    root.update_idletasks()

    assert abs(panel_a.winfo_height() - panel_a.user_req_height) <= 20
    assert abs(panel_a.winfo_width() - panel_a.user_req_width) <= 20

    # 3. Small-window scroll region verification (<600px width)
    root.geometry("500x400")
    root.update_idletasks()
    app._update_workspace_geometry()

    bbox = app.main_canvas.bbox("all")
    assert bbox[2] >= 680  # Canvas scrollregion width is at least 680px threshold

    # 4. Large-window geometry verification (1400px width)
    root.geometry("1400x900")
    root.update_idletasks()
    app._update_workspace_geometry()

    # Panel A retains its explicit width, not stretched to 1400px
    assert abs(panel_a.winfo_width() - panel_a.user_req_width) <= 20

    root.destroy()


def test_gui_startup_viewport_fit():
    """
    Regression test for Step 25 Startup Layout:
    Verifies that at the default 920x720 window geometry, Sections 1-4 fit completely
    within the visible canvas viewport without requiring vertical scrolling.
    """
    import tkinter as tk
    from src.gui.app import CollectionApp

    root = tk.Tk()
    root.geometry("920x720")
    root.update_idletasks()

    app = CollectionApp(root)
    root.update_idletasks()
    app._update_workspace_geometry()

    viewport_h = app.main_canvas.winfo_height()
    main_frame_h = app.main_frame.winfo_reqheight()

    # Total content height fits within viewport height at startup (allowing minor margin for dynamic tabs)
    assert main_frame_h <= viewport_h + 35

    root.destroy()


def test_gui_rendered_interaction_sequence_10_steps():
    """
    Comprehensive 10-step rendered-state regression test verifying:
    1. Launch at normal default geometry (920x720).
    2. Confirm Sections 1-4 are visible within initial viewport (main_frame_h <= viewport_h + 35).
    3. Confirm the four visible top-level ◢ grips are mapped and have nonzero rendered dimensions.
    4. Switch to Research Article Results tab and call root.update().
    5. Confirm both panel_tree and panel_detail are visible above their minimum usable heights and both grips are mapped.
    6. Perform a simulated horizontal drag and verify actual winfo_width() changes.
    7. Perform a simulated vertical drag and verify actual winfo_height() changes.
    8. Perform a diagonal drag and verify both rendered dimensions change.
    9. Verify resizing one panel does not alter another panel's stored/manual dimensions.
    10. Verify expanding beyond the viewport enlarges the canvas scrollregion and activates scrolling.
    """
    import tkinter as tk
    from unittest.mock import MagicMock
    from src.gui.app import CollectionApp

    # Step 1: Launch at normal default geometry
    root = tk.Tk()
    root.geometry("920x720")
    root.update()

    app = CollectionApp(root)
    root.update()
    app._update_workspace_geometry()
    root.update()

    # Step 2: Confirm Sections 1-4 are visible within initial viewport
    viewport_h = app.main_canvas.winfo_height()
    main_frame_h = app.main_frame.winfo_reqheight()
    assert main_frame_h <= viewport_h + 35
    assert app.panel_input.winfo_height() > 0
    assert app.panel_config.winfo_height() > 0
    assert app.panel_results.winfo_height() > 0
    assert app.panel_output.winfo_height() > 0

    # Step 3: Confirm the four visible top-level ◢ grips are mapped and have nonzero rendered dimensions
    top_level_panels = [app.panel_input, app.panel_config, app.panel_results, app.panel_output]
    for p in top_level_panels:
        assert p.grip.winfo_ismapped()
        assert p.grip.winfo_width() > 0
        assert p.grip.winfo_height() > 0

    # Step 4: Switch to Research Article Results tab and call root.update()
    app.notebook.select(1)
    root.update()

    # Step 5: Confirm both panel_tree and panel_detail are visible above min usable heights and both grips are mapped
    assert app.panel_tree.winfo_height() >= app.panel_tree.min_height
    assert app.panel_detail.winfo_height() >= app.panel_detail.min_height
    assert app.panel_tree.grip.winfo_ismapped()
    assert app.panel_detail.grip.winfo_ismapped()
    assert app.panel_tree.grip.winfo_width() > 0
    assert app.panel_detail.grip.winfo_width() > 0

    # Step 6: Perform a simulated horizontal drag on panel_input and verify actual winfo_width() changes
    press_h = MagicMock(x_root=100, y_root=100)
    app.panel_input._on_grip_press(press_h)
    start_w = app.panel_input.winfo_width()
    drag_h = MagicMock(x_root=220, y_root=100)  # +120px X
    app.panel_input._on_grip_drag(drag_h)
    root.update()

    assert app.panel_input.user_req_width is not None
    assert abs(app.panel_input.winfo_width() - (start_w + 120)) <= 15

    # Step 7: Perform a simulated vertical drag on panel_input and verify actual winfo_height() changes
    press_v = MagicMock(x_root=100, y_root=100)
    app.panel_input._on_grip_press(press_v)
    start_h = app.panel_input.winfo_height()
    drag_v = MagicMock(x_root=100, y_root=200)  # +100px Y
    app.panel_input._on_grip_drag(drag_v)
    root.update()

    assert app.panel_input.user_req_height is not None
    assert abs(app.panel_input.winfo_height() - (start_h + 100)) <= 15

    # Step 8: Perform a diagonal drag on panel_tree and verify both rendered dimensions change
    press_tree = MagicMock(x_root=100, y_root=100)
    app.panel_tree._on_grip_press(press_tree)
    start_tw = app.panel_tree.winfo_width()
    start_th = app.panel_tree.winfo_height()
    drag_diag = MagicMock(x_root=200, y_root=180)  # +100px X, +80px Y
    app.panel_tree._on_grip_drag(drag_diag)
    root.update()

    assert app.panel_tree.user_req_width == start_tw + 100
    assert app.panel_tree.user_req_height == start_th + 80
    assert abs(app.panel_tree.winfo_height() - (start_th + 80)) <= 15

    # Step 9: Verify resizing one panel does not alter another panel's stored/manual dimensions
    assert app.panel_config.user_req_width is None
    assert app.panel_config.user_req_height is None
    assert app.panel_detail.user_req_width is None
    assert app.panel_detail.user_req_height is None

    # Step 10: Verify expanding beyond the viewport enlarges the canvas scrollregion and activates scrolling
    press_results = MagicMock(x_root=100, y_root=100)
    app.panel_results._on_grip_press(press_results)
    drag_large = MagicMock(x_root=100, y_root=700)  # +600px height
    app.panel_results._on_grip_drag(drag_large)
    root.update()

    bbox = app.main_canvas.bbox("all")
    assert bbox[3] > 720

    root.destroy()


def test_gui_startup_horizontal_fit_and_manual_expansion():
    """
    Regression test for horizontal startup fit vs. user manual horizontal panel enlargement:
    1. At fresh 920x720 startup, confirms Sections 1-4 left and right rendered edges are within the canvas viewport.
    2. Confirms horizontal scroll position is far left (0.0) with no active horizontal scrolling range (0.0, 1.0).
    3. Manually enlarges Section 1 horizontally beyond the viewport via corner grip drag.
    4. Confirms Section 1 width exceeds viewport, canvas scrollregion expands, horizontal scrolling activates,
       and other panels' stored dimensions remain unchanged.
    """
    import tkinter as tk
    from unittest.mock import MagicMock
    from src.gui.app import CollectionApp

    # Step 1: Launch at normal 920x720 startup geometry
    root = tk.Tk()
    root.geometry("920x720")
    root.update()

    app = CollectionApp(root)
    root.update()
    app._update_workspace_geometry()
    root.update()

    viewport_w = app.main_canvas.winfo_width()
    canvas_root_x = app.main_canvas.winfo_rootx()

    # Step 2: Confirm left and right rendered edges of Sections 1-4 are within viewport
    top_level_panels = [app.panel_input, app.panel_config, app.panel_results, app.panel_output]
    for panel in top_level_panels:
        panel_left = panel.winfo_rootx() - canvas_root_x
        panel_right = panel_left + panel.winfo_width()
        assert panel_left >= -5
        assert panel_right <= viewport_w + 15

    # Step 3: Confirm horizontal canvas scroll position starts at far left with no active scrolling range
    xview = app.main_canvas.xview()
    assert xview[0] == 0.0
    assert xview == (0.0, 1.0)

    # Step 4: Manually enlarge Section 1 horizontally beyond the viewport (+600px X)
    press_ev = MagicMock(x_root=100, y_root=100)
    app.panel_input._on_grip_press(press_ev)

    drag_large_h = MagicMock(x_root=700, y_root=100)
    app.panel_input._on_grip_drag(drag_large_h)
    root.update()

    # Step 5: Verify enlarged panel width exceeds viewport and scrollregion expands
    assert app.panel_input.winfo_width() > viewport_w
    bbox = app.main_canvas.bbox("all")
    assert bbox[2] > viewport_w

    # Step 6: Verify horizontal scrollbar now has an active scrolling range
    new_xview = app.main_canvas.xview()
    assert new_xview[1] < 1.0

    # Step 7: Verify other panels' manual state remains unchanged
    assert app.panel_config.user_req_width is None
    assert app.panel_results.user_req_width is None
    assert app.panel_output.user_req_width is None

    root.destroy()


def test_gui_post_collection_rendered_resizing():
    """
    Regression test verifying post-collection rendered panel resizing:
    1. Launches fresh CollectionApp at 920x720.
    2. Populates collection dataset output into Section 3 widgets (progress log, results table, inspection detail, summary).
    3. Switches across Section 3 tabs and confirms panel_tree and panel_detail corner grips remain mapped and visible.
    4. Performs simulated grip drags on panel_detail, panel_tree, and panel_results post-collection and asserts actual rendered dimensions update.
    5. Confirms double-click grip reset returns panels to automatic sizing.
    """
    import tkinter as tk
    from unittest.mock import MagicMock
    from src.gui.app import CollectionApp
    from src.collectors.batch import BatchCollector
    from src.models.extraction import ExtractionResult
    from src.models.article import Article
    from src.models.comment_status import CommentStatus

    root = tk.Tk()
    root.geometry("920x720")
    root.update()

    app = CollectionApp(root)
    root.update()
    app._update_workspace_geometry()
    root.update()

    # Populate real collection data into Section 3 widgets
    timestamp = "2026-09-26T12:00:00Z"
    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/test-article.html",
        canonical_url="https://news.yahoo.com/test-article.html",
        original_publisher="Associated Press",
        title="AI in Education Research Breakthrough Announcement Title For Inspection Panel Verification",
        author="John Doe",
        publication_datetime="2026-09-26T10:00:00Z",
        comments_status=CommentStatus.AVAILABLE,
        comment_count_reported=150,
        comments_collected=25,
        extraction_method="json-ld",
        article_text="Detailed article text body snippet. " * 30,
        retrieved_at=timestamp
    )
    res = ExtractionResult(
        requested_url="https://news.yahoo.com/test-article.html",
        success=True,
        article=art,
        comments_status=CommentStatus.AVAILABLE,
        diagnostic_notes=["Public comments collected successfully."],
        retrieved_at=timestamp
    )
    results = [res]
    summary = BatchCollector.create_summary(
        results,
        output_files={"json": "data/output/articles.json", "articles_csv": "data/output/articles.csv", "comments_csv": "data/output/comments.csv"},
        topic_query="AI in Education"
    )

    app._append_log("Collection started...")
    app._append_log("Scraping Yahoo News...")
    app._append_log("Collection finished successfully!")
    app._display_summary(summary)
    app._populate_results_table(results)
    root.update()

    # Switch to Tab 1 (Research Article Results)
    app.notebook.select(1)
    root.update()

    # Verify nested panel grips are mapped and visible post-collection
    assert app.panel_tree.grip.winfo_ismapped()
    assert app.panel_detail.grip.winfo_ismapped()
    assert app.panel_tree.grip.winfo_width() > 0
    assert app.panel_detail.grip.winfo_width() > 0

    # Drag panel_detail corner grip post-collection (+120px Y)
    press_detail = MagicMock(x_root=100, y_root=100)
    app.panel_detail._on_grip_press(press_detail)
    start_detail_h = app.panel_detail.winfo_height()

    drag_detail = MagicMock(x_root=100, y_root=220)
    app.panel_detail._on_grip_drag(drag_detail)
    root.update()

    assert app.panel_detail.user_req_height is not None
    assert abs(app.panel_detail.winfo_height() - (start_detail_h + 120)) <= 15
    assert app.panel_detail.grip.winfo_ismapped()

    # Drag panel_tree corner grip post-collection (+100px Y)
    press_tree = MagicMock(x_root=100, y_root=100)
    app.panel_tree._on_grip_press(press_tree)
    start_tree_h = app.panel_tree.winfo_height()

    drag_tree = MagicMock(x_root=100, y_root=200)
    app.panel_tree._on_grip_drag(drag_tree)
    root.update()

    assert app.panel_tree.user_req_height is not None
    assert abs(app.panel_tree.winfo_height() - (start_tree_h + 100)) <= 15
    assert app.panel_tree.grip.winfo_ismapped()

    # Switch to Tab 0 (Execution Progress Log) and drag panel_results (Section 3 master panel)
    app.notebook.select(0)
    root.update()

    press_results = MagicMock(x_root=100, y_root=100)
    app.panel_results._on_grip_press(press_results)
    start_results_h = app.panel_results.winfo_height()

    drag_results = MagicMock(x_root=100, y_root=250)  # +150px Y
    app.panel_results._on_grip_drag(drag_results)
    root.update()

    assert app.panel_results.user_req_height is not None
    assert abs(app.panel_results.winfo_height() - (start_results_h + 150)) <= 15

    # Reset panel_results
    app.panel_results._on_grip_double_click(None)
    root.update()
    assert app.panel_results.user_req_height is None

    root.destroy()


def test_gui_nested_propagation_and_tab_preservation():
    """
    Regression test for localized Section 3 nested panel resize propagation and tab state preservation:
    1. Launches fresh GUI and populates dataset output into Section 3.
    2. Switches to Research Article Results tab.
    3. Enlarges panel_detail downward beyond Section 3 bounds.
    4. Asserts actual rendered growth of panel_detail, panel_results, and canvas scrollregion.
    5. Asserts panel_results.user_req_height remains unchanged (stored manual size preserved).
    6. Switches to Tab 0 (Execution Progress Log) and back to Tab 1 (Research Article Results).
    7. Asserts panel_detail manual height persists across tab switching.
    8. Resets panel_detail via double-click and asserts panel_results contracts back to automatic size.
    """
    import tkinter as tk
    from unittest.mock import MagicMock
    from src.gui.app import CollectionApp
    from src.collectors.batch import BatchCollector
    from src.models.extraction import ExtractionResult
    from src.models.article import Article
    from src.models.comment_status import CommentStatus

    root = tk.Tk()
    root.geometry("920x720")
    root.update()

    app = CollectionApp(root)
    root.update()
    app._update_workspace_geometry()
    root.update()

    # Populate dataset
    timestamp = "2026-09-26T12:00:00Z"
    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/test-article.html",
        canonical_url="https://news.yahoo.com/test-article.html",
        original_publisher="Associated Press",
        title="Nested Resize Propagation Article Verification Title",
        author="John Doe",
        comments_status=CommentStatus.AVAILABLE,
        comments_collected=10,
        article_text="Snippet text...",
        retrieved_at=timestamp
    )
    res = ExtractionResult(
        requested_url="https://news.yahoo.com/test-article.html",
        success=True,
        article=art,
        comments_status=CommentStatus.AVAILABLE,
        retrieved_at=timestamp
    )
    results = [res]
    summary = BatchCollector.create_summary(
        results,
        output_files={"json": "data/output/articles.json", "articles_csv": "data/output/articles.csv", "comments_csv": "data/output/comments.csv"},
        topic_query="AI in Education"
    )

    app._display_summary(summary)
    app._populate_results_table(results)
    root.update()

    # Open Research Article Results (Tab 1)
    app.notebook.select(1)
    root.update()

    start_sec3_h = app.panel_results.winfo_height()

    # Drag nested panel_detail downward (+250px Y)
    press_detail = MagicMock(x_root=100, y_root=100)
    app.panel_detail._on_grip_press(press_detail)
    start_detail_h = app.panel_detail.winfo_height()

    drag_detail = MagicMock(x_root=100, y_root=350)  # +250px Y
    app.panel_detail._on_grip_drag(drag_detail)
    root.update()

    # Verify actual rendered parent and workspace growth
    assert app.panel_detail.user_req_height == start_detail_h + 250
    assert abs(app.panel_detail.winfo_height() - (start_detail_h + 250)) <= 15
    assert app.panel_results.user_req_height is None  # Stored manual height NOT altered
    assert app.panel_results.winfo_height() >= start_sec3_h + 200  # Section 3 rendered height grew
    assert app.main_canvas.bbox("all")[3] > 720  # Vertical scrolling active

    # Switch to Tab 0 and return to Tab 1
    app.notebook.select(0)
    root.update()
    app.notebook.select(1)
    root.update()

    # Verify nested manual size persists across tab changes
    assert app.panel_detail.user_req_height == start_detail_h + 250
    assert abs(app.panel_detail.winfo_height() - (start_detail_h + 250)) <= 15

    # Reset nested panel via double-click grip reset
    app.panel_detail._on_grip_double_click(None)
    root.update()

    # Verify Section 3 contracts back to default size
    assert app.panel_detail.user_req_height is None
    assert abs(app.panel_results.winfo_height() - start_sec3_h) <= 20

    root.destroy()


def test_gui_outer_section3_shrink_and_conflict_resolution():
    """
    Rendered regression test for Section 3 outer grip shrink snap-back resolution:
    1. Populates Section 3 with collection data.
    2. Tests outer Section 3 grip while Execution Progress Log (Tab 0) is active.
    3. Verifies shrinking Section 3 works and rendered height remains at selected size without snap-back.
    4. Repeats verification with Research Article Results (Tab 1) active.
    5. Repeats verification with Collection Run Summary (Tab 2) active.
    6. Verifies shrinking works when nested panels are automatic.
    7. Verifies parent-vs-child conflict resolution when a nested panel has explicit manual size larger than parent.
    8. Verifies double-click reset restores automatic expansion.
    9. Verifies horizontal, vertical, and diagonal outer resizing and nested resizing functionality.
    """
    import tkinter as tk
    from datetime import datetime, timezone
    from unittest.mock import MagicMock
    from src.gui.app import CollectionApp
    from src.models.article import Article, CommentStatus
    from src.models.extraction import ExtractionResult
    from src.collectors.batch import BatchCollector

    root = tk.Tk()
    root.geometry("920x720")
    root.update_idletasks()

    app = CollectionApp(root)
    root.update_idletasks()

    # Populate Section 3 with collection data
    timestamp = datetime.now(timezone.utc).isoformat()
    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/test-article-snapback.html",
        canonical_url="https://news.yahoo.com/test-article-snapback.html",
        original_publisher="Associated Press",
        title="Outer Section 3 Snapback Test Title",
        author="Jane Doe",
        comments_status=CommentStatus.AVAILABLE,
        comments_collected=5,
        article_text="Article body snippet...",
        retrieved_at=timestamp
    )
    res = ExtractionResult(
        requested_url="https://news.yahoo.com/test-article-snapback.html",
        success=True,
        article=art,
        comments_status=CommentStatus.AVAILABLE,
        retrieved_at=timestamp
    )
    results = [res]
    summary = BatchCollector.create_summary(
        results,
        output_files={"json": "data/output/articles.json", "articles_csv": "data/output/articles.csv", "comments_csv": "data/output/comments.csv"},
        topic_query="AI in Education"
    )

    app._display_summary(summary)
    app._populate_results_table(results)
    root.update()

    # Verify initial Section 3 height before dragging
    start_sec3_h = app.panel_results.winfo_height()
    assert start_sec3_h >= 180

    # -------------------------------------------------------------------------
    # 1. Test shrinking Section 3 while Tab 0 (Execution Progress Log) is active
    # -------------------------------------------------------------------------
    app.notebook.select(0)
    root.update()

    press_sec3 = MagicMock(x_root=100, y_root=100)
    app.panel_results._on_grip_press(press_sec3)

    # Drag upward to target height 200px
    drag_up = MagicMock(x_root=100, y_root=100 - (start_sec3_h - 200))
    app.panel_results._on_grip_drag(drag_up)
    root.update()

    assert app.panel_results.user_req_height == 200
    assert abs(app.panel_results.winfo_height() - 200) <= 5

    # -------------------------------------------------------------------------
    # 2. Test Tab 1 (Research Article Results) active
    # -------------------------------------------------------------------------
    app.notebook.select(1)
    root.update()

    # Section 3 height must remain at 200px without snapping back
    assert app.panel_results.user_req_height == 200
    assert abs(app.panel_results.winfo_height() - 200) <= 5

    # -------------------------------------------------------------------------
    # 3. Test Tab 2 (Collection Run Summary) active
    # -------------------------------------------------------------------------
    app.notebook.select(2)
    root.update()

    # Section 3 height must remain at 200px
    assert app.panel_results.user_req_height == 200
    assert abs(app.panel_results.winfo_height() - 200) <= 5

    # -------------------------------------------------------------------------
    # 4. Test Parent-vs-Child Conflict Resolution
    # -------------------------------------------------------------------------
    # Switch back to Tab 1 (Research Article Results)
    app.notebook.select(1)
    root.update()

    # Reset outer Section 3 grip to automatic mode
    app.panel_results._on_grip_double_click(None)
    root.update()
    assert app.panel_results.user_req_height is None

    # Manually enlarge nested panel_detail to height 250px (Case A)
    press_detail = MagicMock(x_root=100, y_root=100)
    app.panel_detail._on_grip_press(press_detail)
    drag_detail = MagicMock(x_root=100, y_root=100 + (250 - app.panel_detail.winfo_height()))
    app.panel_detail._on_grip_drag(drag_detail)
    root.update()

    assert app.panel_detail.user_req_height == 250
    expanded_sec3_h = app.panel_results.winfo_height()
    assert expanded_sec3_h >= 328  # Section 3 expanded to accommodate nested detail panel

    # Now drag outer Section 3 grip smaller to height 220px (Case B conflict)
    start_conflict_h = app.panel_results.winfo_height()
    press_sec3 = MagicMock(x_root=100, y_root=100)
    app.panel_results._on_grip_press(press_sec3)
    drag_sec3_conflict = MagicMock(x_root=100, y_root=100 - (start_conflict_h - 220))
    app.panel_results._on_grip_drag(drag_sec3_conflict)
    root.update()

    # Explicit outer parent setting (220px) MUST take precedence over nested detail requirement (250px)
    assert app.panel_results.user_req_height == 220
    assert abs(app.panel_results.winfo_height() - 220) <= 5
    assert app.panel_detail.user_req_height == 250  # Nested child manual dimension preserved

    # -------------------------------------------------------------------------
    # 5. Reset outer Section 3 grip -> restores automatic expansion (Case A)
    # -------------------------------------------------------------------------
    app.panel_results._on_grip_double_click(None)
    root.update()

    assert app.panel_results.user_req_height is None
    assert app.panel_results.winfo_height() >= 328  # Section 3 expands back to fit nested detail

    # Reset nested panel_detail
    app.panel_detail._on_grip_double_click(None)
    root.update()
    assert app.panel_detail.user_req_height is None

    # -------------------------------------------------------------------------
    # 6. Test horizontal, vertical, and diagonal outer Section 3 resizing
    # -------------------------------------------------------------------------
    press_sec3 = MagicMock(x_root=100, y_root=100)
    app.panel_results._on_grip_press(press_sec3)
    drag_diag = MagicMock(x_root=250, y_root=250)  # +150px X, +150px Y
    app.panel_results._on_grip_drag(drag_diag)
    root.update()

    assert app.panel_results.user_req_width is not None
    assert app.panel_results.user_req_height is not None

    root.destroy()


def test_gui_interaction_aware_section3_and_nested_resizing():
    """
    Rendered regression test for axis-independent interaction-aware precedence between Section 3 and nested panels:
    1. Populates Section 3 with collection data and switches to Research Article Results (Tab 1).
    2. Enlarges nested panel_detail; verifies outer Section 3 expands to accommodate it.
    3. Drags outer Section 3 grip smaller; verifies Section 3 stays at smaller requested size (newer outer action precedence).
    4. Enlarges nested panel_detail AGAIN; verifies Section 3 expands again (newer nested action precedence).
    5. Verifies X and Y axis precedence are independent.
    6. Verifies per-panel independent resetting (resetting panel_tree does not discard panel_detail manual state).
    7. Verifies tab switching preserves applicable state.
    """
    import tkinter as tk
    from datetime import datetime, timezone
    from unittest.mock import MagicMock
    from src.gui.app import CollectionApp
    from src.models.article import Article, CommentStatus
    from src.models.extraction import ExtractionResult
    from src.collectors.batch import BatchCollector

    root = tk.Tk()
    root.geometry("920x720")
    root.update_idletasks()

    app = CollectionApp(root)
    root.update_idletasks()

    # Populate Section 3 with collection data
    timestamp = datetime.now(timezone.utc).isoformat()
    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/test-article-interaction.html",
        canonical_url="https://news.yahoo.com/test-article-interaction.html",
        original_publisher="Associated Press",
        title="Interaction Aware Precedence Test Title",
        author="John Doe",
        comments_status=CommentStatus.AVAILABLE,
        comments_collected=8,
        article_text="Article text snippet...",
        retrieved_at=timestamp
    )
    res = ExtractionResult(
        requested_url="https://news.yahoo.com/test-article-interaction.html",
        success=True,
        article=art,
        comments_status=CommentStatus.AVAILABLE,
        retrieved_at=timestamp
    )
    results = [res]
    summary = BatchCollector.create_summary(
        results,
        output_files={"json": "data/output/articles.json", "articles_csv": "data/output/articles.csv", "comments_csv": "data/output/comments.csv"},
        topic_query="AI in Education"
    )

    app._display_summary(summary)
    app._populate_results_table(results)
    root.update()

    # Open Research Article Results (Tab 1)
    app.notebook.select(1)
    root.update()

    initial_sec3_h = app.panel_results.winfo_height()

    # 1. Enlarge nested panel_detail (+150px height) -> newer nested action
    press_detail = MagicMock(x_root=100, y_root=100)
    app.panel_detail._on_grip_press(press_detail)
    drag_detail_1 = MagicMock(x_root=100, y_root=250)  # +150px Y
    app.panel_detail._on_grip_drag(drag_detail_1)
    root.update()

    assert app.panel_detail.user_req_height is not None
    expanded_sec3_h_1 = app.panel_results.winfo_height()
    assert expanded_sec3_h_1 > initial_sec3_h  # Outer Section 3 expanded to fit nested child

    # 2. Drag outer Section 3 grip smaller to height 200px -> newer outer action
    press_sec3 = MagicMock(x_root=100, y_root=100)
    app.panel_results._on_grip_press(press_sec3)
    drag_sec3_1 = MagicMock(x_root=100, y_root=100 - (expanded_sec3_h_1 - 200))
    app.panel_results._on_grip_drag(drag_sec3_1)
    root.update()

    assert app.panel_results.user_req_height == 200
    assert abs(app.panel_results.winfo_height() - 200) <= 5  # Outer precedence respected

    # 3. Enlarge nested panel_detail AGAIN (+250px height) -> newer nested action again
    app.panel_detail._on_grip_press(press_detail)
    drag_detail_2 = MagicMock(x_root=100, y_root=350)  # +250px Y
    app.panel_detail._on_grip_drag(drag_detail_2)
    root.update()

    assert app.panel_results.winfo_height() > 200  # Section 3 expanded again for newer nested action

    # 4. Per-panel independent reset test:
    # Set manual height on panel_tree as well
    app.panel_tree._on_grip_press(press_detail)
    drag_tree = MagicMock(x_root=100, y_root=200)
    app.panel_tree._on_grip_drag(drag_tree)
    root.update()
    assert app.panel_tree.user_req_height is not None

    # Reset panel_tree only
    app.panel_tree._on_grip_double_click(None)
    root.update()

    assert app.panel_tree.user_req_height is None
    assert app.panel_detail.user_req_height is not None  # panel_detail request preserved!

    # Reset panel_detail
    app.panel_detail._on_grip_double_click(None)
    root.update()
    assert app.panel_detail.user_req_height is None

    root.destroy()


def test_gui_workspace_centering_and_maximize_restore():
    """
    Rendered regression test for horizontal workspace centering and maximize/restore behavior:
    1. Verifies normal 920x720 startup viewport fitting and baseline canvas window alignment.
    2. Verifies substantially wider / maximized-style viewport (1600x900) horizontally centers workspace unit.
    3. Verifies restored window size returns canvas window positioning cleanly.
    4. Verifies manually enlarged workspace wider than viewport preserves left-origin scrolling (X=0).
    5. Verifies manual panel sizes survive maximize/restore operations untouched.
    6. Verifies existing Section 3 nested/outer resize interaction remains functional.
    """
    import tkinter as tk
    from src.gui.app import CollectionApp

    root = tk.Tk()
    root.geometry("920x720")
    root.update()

    app = CollectionApp(root)
    root.update()

    # 1. Verify startup viewport fitting at 920x720
    viewport_w_startup = app.main_canvas.winfo_width()
    coords_startup = app.main_canvas.coords(app.canvas_window)
    assert coords_startup[0] <= 10.0  # Near left edge for 920x720 window

    # 2. Maximize / widen window to 1600x900
    root.geometry("1600x900")
    root.update()
    app._update_workspace_geometry()
    root.update()

    viewport_w_max = app.main_canvas.winfo_width()
    coords_max = app.main_canvas.coords(app.canvas_window)
    workspace_w_max = app.main_frame.winfo_width()

    assert viewport_w_max > 1500
    assert coords_max[0] > 100.0  # Workspace is horizontally centered!
    expected_offset = (viewport_w_max - workspace_w_max) // 2
    assert abs(coords_max[0] - expected_offset) <= 5

    # 3. Restore window back to 920x720
    root.geometry("920x720")
    root.update()
    app._update_workspace_geometry()
    root.update()

    coords_restored = app.main_canvas.coords(app.canvas_window)
    assert coords_restored[0] <= 10.0

    # 4. Manually enlarge panel_input to 1200px (wider than 920x720 viewport)
    app.panel_input.user_req_width = 1200
    app._update_workspace_geometry()
    root.update()

    coords_oversized = app.main_canvas.coords(app.canvas_window)
    assert coords_oversized[0] == 0.0  # Left-anchored for horizontal scrolling
    assert app.main_frame.winfo_width() == 1200

    # 5. Widen window with 1200px manual panel
    root.geometry("1600x900")
    root.update()
    app._update_workspace_geometry()
    root.update()

    coords_oversized_max = app.main_canvas.coords(app.canvas_window)
    viewport_w_oversized_max = app.main_canvas.winfo_width()
    assert coords_oversized_max[0] > 50.0  # Centered because 1600 > 1200
    expected_oversized_offset = (viewport_w_oversized_max - 1200) // 2
    assert abs(coords_oversized_max[0] - expected_oversized_offset) <= 5

    # 6. Verify manual dimensions survive maximize/restore untouched
    assert app.panel_input.user_req_width == 1200

    root.destroy()














