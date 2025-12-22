"""
Stability AI API Proxy - Clean wrapper for Stability AI API

This is a thin proxy layer that handles raw API calls to Stability AI.
Business logic for character generation should be in CharacterGenerationService.
"""
from typing import List, Dict, Any, Optional, BinaryIO
import requests
import base64
from io import BytesIO
import imghdr
from src.config import Config
from src.config.generation_models_config import generation_models_config

class StabilityService:
    """
    Clean API proxy for Stability AI

    Provides low-level methods for calling Stability AI endpoints:
    - generate_image(): Text-to-image and image-to-image generation
    - style_transfer(): Style transfer endpoint
    - generate_variants(): Multiple generation runs

    For business logic (character portraits, scenes, etc.), use CharacterGenerationService.
    """

    def __init__(self):
        self.api_key = Config.STABILITY_API_KEY
        self.provider = "stability_ai"
        self.api_host = generation_models_config.get_api_host(self.provider) or "https://api.stability.ai"
        self.default_engine = generation_models_config.get_default_engine(self.provider) or "stable-diffusion-xl-1024-v1-0"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }

    def _detect_image_type(self, image_data: bytes):
        """
        Detect image MIME type from bytes

        Returns:
            Tuple of (mime_type, extension)
        """
        # Try to detect using imghdr
        img_type = imghdr.what(None, h=image_data)

        # Map to MIME types
        mime_map = {
            'jpeg': ('image/jpeg', '.jpg'),
            'png': ('image/png', '.png'),
            'gif': ('image/gif', '.gif'),
            'webp': ('image/webp', '.webp')
        }

        if img_type in mime_map:
            return mime_map[img_type]

        # Fallback: check magic bytes
        if image_data.startswith(b'\xff\xd8\xff'):
            return ('image/jpeg', '.jpg')
        elif image_data.startswith(b'\x89PNG'):
            return ('image/png', '.png')
        elif image_data.startswith(b'GIF'):
            return ('image/gif', '.gif')
        elif image_data.startswith(b'RIFF') and b'WEBP' in image_data[:12]:
            return ('image/webp', '.webp')

        # Default to PNG
        return ('image/png', '.png')

    def generate_image(self, prompt: str,
                      negative_prompt: str = None,
                      width: int = 1024,
                      height: int = 1024,
                      steps: int = 30,
                      cfg_scale: float = 7.0,
                      style_preset: str = None,
                      init_image: BinaryIO = None,
                      init_image_mode: str = "IMAGE_STRENGTH",
                      image_strength: float = 0.35) -> Dict[str, Any]:
        """
        Generate an image using Stability.ai SDXL

        Args:
            prompt: Text description of desired image
            negative_prompt: What to avoid in the image
            width: Image width (default 1024)
            height: Image height (default 1024)
            steps: Number of diffusion steps (default 30)
            cfg_scale: How strictly to follow prompt (default 7.0)
            style_preset: Style preset (e.g., "comic-book", "digital-art", "photographic")
            init_image: Optional reference image for img2img
            init_image_mode: How to use init image ("IMAGE_STRENGTH" or "STEP_SCHEDULE")
            image_strength: Strength of init image influence (0.0-1.0)

        Returns:
            Dictionary with:
                - image_data: Base64 encoded image
                - seed: Generation seed
                - finish_reason: Why generation stopped
        """
        url = generation_models_config.get_endpoint(
            self.provider,
            'text_to_image',
            engine=self.default_engine
        )

        # Build request body
        body = {
            "text_prompts": [
                {"text": prompt, "weight": 1.0}
            ],
            "cfg_scale": cfg_scale,
            "height": height,
            "width": width,
            "steps": steps,
            "samples": 1
        }

        if negative_prompt:
            body["text_prompts"].append({
                "text": negative_prompt,
                "weight": -1.0
            })

        if style_preset:
            body["style_preset"] = style_preset

        # Use image-to-image endpoint if init_image provided
        if init_image:
            url = generation_models_config.get_endpoint(
                self.provider,
                'image_to_image',
                engine=self.default_engine
            )

            # Convert init_image to bytes
            # Handle both bytes and file-like objects
            if isinstance(init_image, bytes):
                image_bytes = init_image
            else:
                init_image.seek(0)
                image_bytes = init_image.read()

            # Images are already normalized to SDXL dimensions during upload
            # Convert to base64
            init_image_b64 = base64.b64encode(image_bytes).decode()

            # Detect image MIME type
            mime_type, ext = self._detect_image_type(image_bytes)

            # Build multipart form data
            files = {
                "init_image": (f"image{ext}", base64.b64decode(init_image_b64), mime_type)
            }

            # Add other params as form fields
            data = {
                "text_prompts[0][text]": prompt,
                "text_prompts[0][weight]": "1.0",
                "cfg_scale": str(cfg_scale),
                "steps": str(steps),
                "samples": "1",
                "init_image_mode": init_image_mode,
                "image_strength": str(image_strength)
            }

            if negative_prompt:
                data["text_prompts[1][text]"] = negative_prompt
                data["text_prompts[1][weight]"] = "-1.0"

            if style_preset:
                data["style_preset"] = style_preset

            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
                files=files,
                data=data
            )
        else:
            # Standard text-to-image
            response = requests.post(
                url,
                headers={**self.headers, "Content-Type": "application/json"},
                json=body
            )

        if response.status_code != 200:
            raise Exception(f"Stability API error: {response.status_code} - {response.text}")

        data = response.json()

        # Extract first artifact
        artifact = data["artifacts"][0]

        return {
            "image_data": artifact["base64"],
            "seed": artifact.get("seed"),
            "finish_reason": artifact.get("finishReason")
        }

    def generate_variants(self, prompt: str,
                         num_variants: int = 3,
                         **kwargs) -> List[Dict[str, Any]]:
        """
        Generate multiple variants of an image

        Args:
            prompt: Image description
            num_variants: Number of variants to generate
            **kwargs: Additional arguments passed to generate_image

        Returns:
            List of image result dictionaries
        """
        variants = []
        for _ in range(num_variants):
            result = self.generate_image(prompt=prompt, **kwargs)
            variants.append(result)

        return variants

    def style_transfer(self,
                      init_image: BinaryIO,
                      style_image: BinaryIO,
                      prompt: str,
                      style_strength: float = 0.8,
                      negative_prompt: Optional[str] = None,
                      output_format: str = "png") -> bytes:
        """
        Apply style transfer using Stability AI's Control Style Transfer endpoint

        This is the recommended approach for preserving kid likeness while applying
        a modern 3D animation style using a reference style image.

        Args:
            init_image: The kid's reference photo (preserves identity/pose)
            style_image: Backend style reference image (defines visual style)
            prompt: Text description of desired output
            style_strength: How strongly to apply style (0.0-1.0, default 0.8)
            negative_prompt: What to avoid in generation
            output_format: Output format ("png" or "jpeg")

        Returns:
            Raw image bytes

        Raises:
            ValueError: If style_strength out of range
            Exception: On API errors

        Reference:
            https://platform.stability.ai/docs/api-reference#tag/Control/paths/~1v2beta~1stable-image~1control~1style-transfer/post
        """
        if not (0.0 <= style_strength <= 1.0):
            raise ValueError(f"style_strength must be between 0.0 and 1.0, got {style_strength}")

        url = generation_models_config.get_endpoint(self.provider, 'style_transfer')

        # Prepare image files
        # Convert file-like objects to bytes
        if isinstance(init_image, bytes):
            init_bytes = init_image
        else:
            init_image.seek(0)
            init_bytes = init_image.read()

        if isinstance(style_image, bytes):
            style_bytes = style_image
        else:
            style_image.seek(0)
            style_bytes = style_image.read()

        # Detect MIME types
        init_mime, init_ext = self._detect_image_type(init_bytes)
        style_mime, style_ext = self._detect_image_type(style_bytes)

        # Build multipart form data
        files = {
            "init_image": (f"init{init_ext}", init_bytes, init_mime),
            "style_image": (f"style{style_ext}", style_bytes, style_mime)
        }

        data = {
            "prompt": prompt,
            "style_strength": str(style_strength),
            "output_format": output_format
        }

        if negative_prompt:
            data["negative_prompt"] = negative_prompt

        # Call API
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "image/*"  # Expect binary image response
        }

        response = requests.post(
            url,
            headers=headers,
            files=files,
            data=data,
            timeout=60
        )

        if response.status_code != 200:
            error_msg = f"Stability API style transfer error: {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail}"
            except:
                error_msg += f" - {response.text[:200]}"
            raise Exception(error_msg)

        # Return raw image bytes
        return response.content

    def image_to_bytes(self, base64_data: str) -> BytesIO:
        """
        Convert base64 image data to BytesIO object

        Args:
            base64_data: Base64 encoded image

        Returns:
            BytesIO object containing image bytes
        """
        image_bytes = base64.b64decode(base64_data)
        return BytesIO(image_bytes)
