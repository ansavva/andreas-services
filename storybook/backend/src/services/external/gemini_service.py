from __future__ import annotations

from typing import Any, Iterable, List, Optional
from io import BytesIO
import base64

from PIL import Image

from src.utils.config import AppConfig
from src.utils.config.generation_models_config import generation_models_config


class GeminiService:
    """Wrapper for Gemini image generation via Google GenAI SDK."""

    def __init__(self) -> None:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        self._genai = genai
        self._types = types
        self.client = genai.Client(api_key=AppConfig.GEMINI_API_KEY)

    def generate_images(
        self,
        prompt: str,
        profile: str,
        reference_images: Optional[Iterable[Any]] = None,
        *,
        aspect_ratio: Optional[str] = None,
        image_size: Optional[str] = None,
        image_only: bool = True,
    ) -> List[bytes]:
        provider = "gemini"
        gen_config = generation_models_config.get_generation_config(provider, profile)
        model_id = generation_models_config.get_model_id(provider, profile)
        if not model_id:
            raise ValueError("Gemini model id is not configured.")

        prompt_text = prompt.strip() if isinstance(prompt, str) else prompt
        contents: List[Any] = []
        for image in reference_images or []:
            contents.append(self._to_pil(image))
        contents.append(prompt_text)

        response_modalities = ["IMAGE"] if image_only else ["TEXT", "IMAGE"]
        image_config = None
        aspect_ratio = aspect_ratio or gen_config.get("aspect_ratio")
        image_size = image_size or gen_config.get("image_size")
        if aspect_ratio or image_size:
            config_kwargs = {}
            if aspect_ratio:
                config_kwargs["aspect_ratio"] = aspect_ratio
            if image_size:
                config_kwargs["image_size"] = image_size
            image_config = self._types.ImageConfig(**config_kwargs)

        config = self._types.GenerateContentConfig(
            response_modalities=response_modalities,
            image_config=image_config,
        )

        response = self.client.models.generate_content(
            model=model_id,
            contents=contents,
            config=config,
        )

        output_format = gen_config.get("output_format", "png").lower()
        format_name = "PNG" if output_format == "png" else "JPEG"
        images: List[bytes] = []
        for part in response.parts:
            if getattr(part, "text", None):
                continue

            inline_data = getattr(part, "inline_data", None)
            data = getattr(inline_data, "data", None) if inline_data else None
            if data:
                if isinstance(data, str):
                    images.append(base64.b64decode(data))
                else:
                    images.append(bytes(data))
                continue

            img = part.as_image()
            if img:
                buf = BytesIO()
                if hasattr(img, "save"):
                    try:
                        img.save(buf, format_name)
                    except TypeError:
                        img.save(buf)
                    images.append(buf.getvalue())
                elif isinstance(img, (bytes, bytearray)):
                    images.append(bytes(img))

        if not images:
            raise RuntimeError("Gemini returned no image outputs.")

        return images

    def _to_pil(self, image: Any) -> Image.Image:
        if isinstance(image, Image.Image):
            return image
        stream = getattr(image, "stream", None)
        if stream is not None:
            stream.seek(0)
            return Image.open(stream)
        if hasattr(image, "seek"):
            image.seek(0)
            return Image.open(image)
        raise ValueError("Unsupported reference image type for Gemini.")
