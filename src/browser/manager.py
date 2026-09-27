import time
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field
from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError


class BrowserFetchResult(BaseModel):
    """
    Data model representing the outcome of a browser navigation and rendering attempt.
    """
    requested_url: str = Field(description="URL requested for browser navigation")
    final_url: Optional[str] = Field(default=None, description="Final canonical URL after redirects")
    status_code: Optional[int] = Field(default=None, description="HTTP status code returned by page response")
    html: Optional[str] = Field(default=None, description="Rendered HTML content of the page")
    success: bool = Field(default=False, description="True if page was successfully loaded and rendered")
    error_type: Optional[str] = Field(default=None, description="Categorized error type (TIMEOUT, NAVIGATION_ERROR, ACCESS_DENIED, CAPTCHA_DETECTED)")
    error_message: Optional[str] = Field(default=None, description="Detailed error diagnostic message")
    retrieved_at: str = Field(description="ISO timestamp when retrieval took place")


class BrowserManager:
    """
    Reusable Playwright browser manager handling isolated browser contexts,
    page navigation, conservative delays, clean shutdown, and failure detection.
    """
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    CAPTCHA_SIGNATURES: List[str] = [
        "captcha",
        "recaptcha",
        "hcaptcha",
        "cf-wrapper",
        "cf-turnstile",
        "pardon our interruption",
        "security check",
        "robot check",
        "verify you are a human"
    ]

    ACCESS_DENIED_SIGNATURES: List[str] = [
        "access denied",
        "403 forbidden",
        "429 too many requests",
        "request blocked",
        "imperva",
        "incapsula"
    ]

    def __init__(
        self,
        headless: bool = True,
        navigation_timeout_ms: int = 30000,
        request_delay_ms: int = 1000
    ):
        """
        Args:
            headless: Whether to run Chromium in headless mode.
            navigation_timeout_ms: Default navigation timeout in milliseconds.
            request_delay_ms: Delay in milliseconds applied before each navigation.
        """
        self.headless = headless
        self.navigation_timeout_ms = navigation_timeout_ms
        self.request_delay_ms = request_delay_ms

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._is_started = False

    def start(self) -> "BrowserManager":
        """
        Launches Playwright and Chromium browser instance.
        """
        if not self._is_started:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            self._is_started = True
        return self

    def close(self) -> None:
        """
        Closes Chromium browser and stops Playwright.
        """
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        self._is_started = False

    def __enter__(self) -> "BrowserManager":
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def create_context(self) -> BrowserContext:
        """
        Creates a fresh, isolated browser context (no shared user profile or cookies).
        """
        if not self._is_started or not self._browser:
            self.start()

        assert self._browser is not None
        context = self._browser.new_context(
            user_agent=self.DEFAULT_USER_AGENT,
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True
        )
        context.set_default_navigation_timeout(self.navigation_timeout_ms)
        return context

    def _check_access_or_captcha(self, status_code: Optional[int], html: Optional[str]) -> Optional[str]:
        """
        Inspects HTTP status code and rendered HTML for CAPTCHA or access denial signatures.

        Returns:
            Optional[str]: "CAPTCHA_DETECTED", "ACCESS_DENIED", or None if clean.
        """
        if status_code in (403, 429):
            return "ACCESS_DENIED"

        if not html:
            return None

        html_lower = html.lower()

        for sig in self.CAPTCHA_SIGNATURES:
            if sig in html_lower:
                return "CAPTCHA_DETECTED"

        for sig in self.ACCESS_DENIED_SIGNATURES:
            if sig in html_lower:
                return "ACCESS_DENIED"

        return None

    def fetch_page(self, url: str, wait_until: str = "domcontentloaded") -> BrowserFetchResult:
        """
        Fetches and renders a page using an isolated browser context.

        Args:
            url: Target URL to load.
            wait_until: Playwright load state ('domcontentloaded', 'load', or 'networkidle').

        Returns:
            BrowserFetchResult: Structured navigation and rendering outcome.
        """
        retrieved_at = datetime.now(timezone.utc).isoformat()

        # Apply conservative delay between requests
        if self.request_delay_ms > 0:
            time.sleep(self.request_delay_ms / 1000.0)

        context: Optional[BrowserContext] = None
        try:
            context = self.create_context()
            page = context.new_page()

            response = page.goto(url, wait_until=wait_until)
            status_code = response.status if response else None
            final_url = page.url
            html_content = page.content()

            # Check for CAPTCHA or Access Denial signatures
            block_type = self._check_access_or_captcha(status_code, html_content)
            if block_type:
                return BrowserFetchResult(
                    requested_url=url,
                    final_url=final_url,
                    status_code=status_code,
                    html=html_content,
                    success=False,
                    error_type=block_type,
                    error_message=f"Access restriction detected ({block_type})",
                    retrieved_at=retrieved_at
                )

            return BrowserFetchResult(
                requested_url=url,
                final_url=final_url,
                status_code=status_code,
                html=html_content,
                success=True,
                retrieved_at=retrieved_at
            )

        except PlaywrightTimeoutError as te:
            return BrowserFetchResult(
                requested_url=url,
                success=False,
                error_type="TIMEOUT",
                error_message=f"Navigation timed out after {self.navigation_timeout_ms}ms: {str(te)}",
                retrieved_at=retrieved_at
            )

        except PlaywrightError as pe:
            return BrowserFetchResult(
                requested_url=url,
                success=False,
                error_type="NAVIGATION_ERROR",
                error_message=f"Playwright navigation error: {str(pe)}",
                retrieved_at=retrieved_at
            )

        except Exception as e:
            return BrowserFetchResult(
                requested_url=url,
                success=False,
                error_type="NAVIGATION_ERROR",
                error_message=f"Unexpected navigation error: {str(e)}",
                retrieved_at=retrieved_at
            )

        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
