"""Hugging Face provider adapters."""

from __future__ import annotations

from pathlib import Path

import requests

from app.config import Settings
from app.retry_utils import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from app.utils import ensure_directory


class ProviderFailure(RuntimeError):
    """Raised when the external provider cannot complete the request."""


class HFProvider:
    """Best-effort Hugging Face inference wrapper."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.hf_token:
            raise ProviderFailure("HF_TOKEN is not configured")

    def _endpoint(self, model_name: str) -> str:
        return f"https://api-inference.huggingface.co/models/{model_name}"

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((requests.RequestException, ProviderFailure)),
        reraise=True,
    )
    def _request(self, model_name: str, prompt: str, accept: str) -> requests.Response:
        response = requests.post(
            self._endpoint(model_name),
            headers={
                "Authorization": f"Bearer {self.settings.hf_token}",
                "Accept": accept,
            },
            json={"inputs": prompt},
            timeout=self.settings.provider_timeout_seconds,
        )
        if response.status_code >= 400:
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = {"error": response.text}
            message = str(error_payload.get("error") or error_payload)
            if "quota" in message.lower() or "credit" in message.lower():
                raise ProviderFailure(message)
            response.raise_for_status()
        return response

    def generate_video(self, prompt: str, output_path: Path) -> dict:
        ensure_directory(output_path.parent)
        response = self._request(self.settings.hf_video_model, prompt, "video/mp4")
        content_type = response.headers.get("content-type", "")
        if "video" not in content_type and not response.content:
            raise ProviderFailure(f"unexpected video response: {content_type}")
        output_path.write_bytes(response.content)
        return {"model": self.settings.hf_video_model, "content_type": content_type}

    def generate_image(self, prompt: str, output_path: Path) -> dict:
        ensure_directory(output_path.parent)
        response = self._request(self.settings.hf_image_model, prompt, "image/png")
        content_type = response.headers.get("content-type", "")
        if "image" not in content_type and not response.content:
            raise ProviderFailure(f"unexpected image response: {content_type}")
        output_path.write_bytes(response.content)
        return {"model": self.settings.hf_image_model, "content_type": content_type}
