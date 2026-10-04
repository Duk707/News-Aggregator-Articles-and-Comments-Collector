"""
Supabase Upload & Dry Run GUI Dialogs (Step 29).
Provides configuration inputs, read-only dry run preview, optional user authentication,
and explicit double-confirmation before triggering direct Supabase upload.
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional, Callable

from src.integrations.supabase.config import SupabaseClientConfig, load_supabase_config, save_supabase_client_config
from src.integrations.supabase.client import SupabaseClient
from src.integrations.supabase.uploader import SupabaseUploader, UploadDryRunResult, UploadExecutionSummary
from src.integrations.supabase.models import SupabaseStagingDataset


class SupabaseUploadSummaryDialog(tk.Toplevel):
    """
    Dialog presenting the final upload execution summary report.
    """
    def __init__(self, parent: tk.Widget, summary: UploadExecutionSummary):
        super().__init__(parent)
        self.title("Supabase Direct Upload - Execution Summary")
        self.geometry("650x550")
        self.minsize(500, 400)
        self.transient(parent)
        self.grab_set()

        self._build_ui(summary)

    def _build_ui(self, summary: UploadExecutionSummary):
        frame = ttk.Frame(self, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)

        lbl_header = ttk.Label(
            frame,
            text="Supabase Direct Upload - Execution Summary",
            font=("Segoe UI", 12, "bold")
        )
        lbl_header.pack(anchor=tk.W, pady=(0, 10))

        txt_area = scrolledtext.ScrolledText(frame, font=("Consolas", 10), wrap=tk.WORD)
        txt_area.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        txt_area.insert(tk.END, summary.format_summary_text())
        txt_area.configure(state="disabled")

        btn_close = ttk.Button(frame, text="Close", command=self.destroy)
        btn_close.pack(anchor=tk.E)


class SupabaseUploadDialog(tk.Toplevel):
    """
    Dialog for configuring Supabase connection, running read-only dry runs,
    authenticating users, and launching explicit direct uploads.
    """
    def __init__(
        self,
        parent: tk.Widget,
        dataset: SupabaseStagingDataset,
        on_start_upload: Callable[[SupabaseClientConfig, UploadDryRunResult], None]
    ):
        super().__init__(parent)
        self.title("Upload Dataset to Supabase (Step 29)")
        self.geometry("680x620")
        self.minsize(600, 500)
        self.transient(parent)
        self.grab_set()

        self.dataset = dataset
        self.on_start_upload = on_start_upload
        self.current_config = load_supabase_config()
        self.client = SupabaseClient(config=self.current_config)
        self.uploader = SupabaseUploader(client=self.client)

        self.latest_dry_run_result: Optional[UploadDryRunResult] = None

        self._build_ui()

    def _build_ui(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Connection Config Frame
        lf_config = ttk.LabelFrame(main_frame, text="1. Supabase Connection Settings", padding="10")
        lf_config.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(lf_config, text="Supabase URL:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.entry_url = ttk.Entry(lf_config, width=50)
        self.entry_url.grid(row=0, column=1, sticky=tk.EW, pady=2, padx=(5, 0))
        self.entry_url.insert(0, self.current_config.supabase_url)

        ttk.Label(lf_config, text="Anon Key:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.entry_key = ttk.Entry(lf_config, width=50, show="*")
        self.entry_key.grid(row=1, column=1, sticky=tk.EW, pady=2, padx=(5, 0))
        self.entry_key.insert(0, self.current_config.supabase_anon_key)

        self.var_save_config = tk.BooleanVar(value=True)
        chk_save = ttk.Checkbutton(lf_config, text="Save connection parameters locally (excludes tokens/passwords)", variable=self.var_save_config)
        chk_save.grid(row=2, column=1, sticky=tk.W, pady=(5, 0), padx=(5, 0))

        lf_config.columnconfigure(1, weight=1)

        # 2. Authentication (Optional) Frame
        lf_auth = ttk.LabelFrame(main_frame, text="2. User Authentication (Optional)", padding="10")
        lf_auth.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(lf_auth, text="Email:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.entry_email = ttk.Entry(lf_auth, width=30)
        self.entry_email.grid(row=0, column=1, sticky=tk.W, pady=2, padx=(5, 10))

        ttk.Label(lf_auth, text="Password:").grid(row=0, column=2, sticky=tk.W, pady=2)
        self.entry_pass = ttk.Entry(lf_auth, width=20, show="*")
        self.entry_pass.grid(row=0, column=3, sticky=tk.W, pady=2, padx=(5, 10))

        btn_login = ttk.Button(lf_auth, text="Log In", command=self._on_login_clicked)
        btn_login.grid(row=0, column=4, sticky=tk.W, pady=2)

        self.lbl_auth_status = ttk.Label(lf_auth, text="Role: anon (Unauthenticated)", font=("Segoe UI", 9, "italic"))
        self.lbl_auth_status.grid(row=1, column=0, columnspan=5, sticky=tk.W, pady=(5, 0))

        # 3. Read-Only Dry Run Frame
        lf_dry = ttk.LabelFrame(main_frame, text="3. Pre-Upload Dry Run Analysis", padding="10")
        lf_dry.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        btn_dry_run = ttk.Button(lf_dry, text="Run Read-Only Dry Run", command=self._on_dry_run_clicked)
        btn_dry_run.pack(anchor=tk.W, pady=(0, 5))

        self.txt_dry_output = scrolledtext.ScrolledText(lf_dry, font=("Consolas", 9), height=10)
        self.txt_dry_output.pack(fill=tk.BOTH, expand=True)
        self.txt_dry_output.insert(tk.END, "Click 'Run Read-Only Dry Run' to verify connection and analyze article conflict cases.")
        self.txt_dry_output.configure(state="disabled")

        # 4. Action Frame
        f_actions = ttk.Frame(main_frame)
        f_actions.pack(fill=tk.X)

        self.btn_upload = ttk.Button(
            f_actions,
            text="Upload to Supabase...",
            state="disabled",
            command=self._on_upload_clicked
        )
        self.btn_upload.pack(side=tk.RIGHT, padx=(5, 0))

        btn_cancel = ttk.Button(f_actions, text="Cancel", command=self.destroy)
        btn_cancel.pack(side=tk.RIGHT)

    def _sync_config_from_inputs(self) -> SupabaseClientConfig:
        url = self.entry_url.get().strip()
        key = self.entry_key.get().strip()
        self.current_config.supabase_url = url
        self.current_config.supabase_anon_key = key
        self.client.config = self.current_config
        return self.current_config

    def _on_login_clicked(self):
        config = self._sync_config_from_inputs()
        if not config.is_configured():
            messagebox.showerror("Configuration Error", "Please provide a valid Supabase URL and Anon Key.", parent=self)
            return

        email = self.entry_email.get().strip()
        password = self.entry_pass.get()

        if not email or not password:
            messagebox.showerror("Login Error", "Please enter email and password.", parent=self)
            return

        try:
            self.client.login(email, password)
            self.lbl_auth_status.configure(text=f"Authenticated as: {email} (role: authenticated)")
            messagebox.showinfo("Login Success", f"Successfully authenticated as {email}.", parent=self)
        except Exception as ex:
            self.lbl_auth_status.configure(text="Role: anon (Login Failed)")
            messagebox.showerror("Authentication Failed", str(ex), parent=self)

    def _on_dry_run_clicked(self):
        config = self._sync_config_from_inputs()
        if not config.is_configured():
            messagebox.showerror("Configuration Error", "Please provide a valid Supabase URL and Anon Key.", parent=self)
            return

        try:
            res = self.uploader.run_dry_run(self.dataset)
            self.latest_dry_run_result = res

            lines = [
                "=== READ-ONLY DRY RUN RESULT ===",
                f"Connectivity OK:     {res.connectivity_ok}",
                f"API Key Valid:       {res.api_key_valid}",
                f"Read Access OK:      {res.read_access_ok}",
                f"Active Role:         {res.active_role}",
                f"Write Permission:    {res.write_access_note}",
                "",
                "--- Article Conflict Analysis ---",
                f"  Case A (New Inserts):     {res.article_case_a_inserts}",
                f"  Case B (Clean Matches):   {res.article_case_b_links}",
                f"  Case C (URL Warnings):    {res.article_case_c_warnings}",
                f"  Case D (Title Blocks):    {res.article_case_d_blocks}",
                "",
                f"Can Proceed with Upload:   {res.can_proceed}"
            ]

            if res.article_conflict_messages:
                lines.append("\n--- Conflict Messages ---")
                for art_id, msg in res.article_conflict_messages.items():
                    lines.append(f"  [Staged Article #{art_id}] {msg}")

            if res.error_message:
                lines.append(f"\nError Details: {res.error_message}")

            self.txt_dry_output.configure(state="normal")
            self.txt_dry_output.delete("1.0", tk.END)
            self.txt_dry_output.insert(tk.END, "\n".join(lines))
            self.txt_dry_output.configure(state="disabled")

            if res.can_proceed:
                self.btn_upload.configure(state="normal")
            else:
                self.btn_upload.configure(state="disabled")

        except Exception as ex:
            messagebox.showerror("Dry Run Error", f"An error occurred during dry run:\n{ex}", parent=self)
            self.btn_upload.configure(state="disabled")

    def _on_upload_clicked(self):
        if not self.latest_dry_run_result or not self.latest_dry_run_result.can_proceed:
            messagebox.showerror("Upload Error", "Dry run must be executed and pass before uploading.", parent=self)
            return

        config = self._sync_config_from_inputs()

        art_count = len(self.dataset.articles)
        cmt_count = len(self.dataset.comments)
        confirm = messagebox.askyesno(
            "Confirm Supabase Direct Upload",
            f"Are you sure you want to execute direct upload to Supabase?\n\n"
            f"Dataset containing {art_count} articles and {cmt_count} comments will be uploaded.\n"
            f"Supabase URL: {config.supabase_url}\n"
            f"Role: {self.latest_dry_run_result.active_role}\n\n"
            f"This action will modify the public.articles and public.comments tables on Supabase.",
            parent=self
        )

        if confirm:
            if self.var_save_config.get():
                try:
                    save_supabase_client_config(config)
                except Exception:
                    pass

            dry_run = self.latest_dry_run_result
            self.destroy()
            self.on_start_upload(config, dry_run)
