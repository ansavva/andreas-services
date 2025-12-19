"""
Stability.ai Service - Wrapper for Stability API interactions
Handles character generation, scene generation, and illustration creation using SDXL
"""
from typing import List, Dict, Any, Optional, BinaryIO
import requests
import base64
from io import BytesIO
import imghdr
from src.config import Config
from src.config.prompts_config import prompts_config

class StabilityService:
    """
    Service for interacting with Stability.ai API
    Used for character portraits, preview scenes, and story page illustrations
    """

    def __init__(self):
        self.api_key = Config.STABILITY_API_KEY
        self.api_host = "https://api.stability.ai"
        self.default_engine = "stable-diffusion-xl-1024-v1-0"  # SDXL
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
        url = f"{self.api_host}/v1/generation/{self.default_engine}/text-to-image"

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
            url = f"{self.api_host}/v1/generation/{self.default_engine}/image-to-image"

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

    def generate_character_portrait(self,
                                    reference_images: List[BinaryIO],
                                    child_name: Optional[str] = None,
                                    user_description: Optional[str] = None,
                                    style: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a stylized character portrait from reference photos

        Args:
            reference_images: List of child photos (file-like objects)
            child_name: Optional name of the child
            user_description: Optional custom description to add to prompt
            style: Optional style preset for generation (validates against allowed presets)

        Returns:
            Dictionary with image_data and metadata

        Raises:
            ValueError: If style preset is invalid
        """
        # Validate and set style preset
        if style is None:
            style = prompts_config.get_character_default_style()
        elif not prompts_config.is_valid_style_preset(style):
            raise ValueError(f"Invalid style preset: {style}. Must be one of: {prompts_config.get_available_style_presets()}")

        # Build prompt from config
        prompt = prompts_config.build_character_prompt(child_name, user_description)
        negative_prompt = prompts_config.get_character_negative_prompt()
        image_strength = prompts_config.get_character_image_strength()

        return self.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            style_preset=style,
            init_image=reference_images[0] if reference_images else None,
            image_strength=image_strength
        )

    def generate_preview_scene(self,
                              scene_name: str,
                              character_description: str,
                              reference_image: BinaryIO = None,
                              style: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a preview scene with the character

        Args:
            scene_name: Name of the scene (e.g., "park", "space", "pirate")
            character_description: Description of the character for consistency
            reference_image: Optional character reference image
            style: Optional style preset (validates against allowed presets)

        Returns:
            Dictionary with image_data and metadata

        Raises:
            ValueError: If style preset is invalid
        """
        # Validate and set style preset
        if style is None:
            style = prompts_config.get_character_default_style()
        elif not prompts_config.is_valid_style_preset(style):
            raise ValueError(f"Invalid style preset: {style}. Must be one of: {prompts_config.get_available_style_presets()}")

        # Build scene prompt from config
        prompt = prompts_config.build_scene_prompt(scene_name, character_description)
        negative_prompt = prompts_config.get_scene_negative_prompt()

        return self.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            style_preset=style,
            init_image=reference_image,
            image_strength=0.3 if reference_image else 0.0
        )

    def generate_story_illustration(self,
                                    prompt: str,
                                    character_bible: Dict[str, Any] = None,
                                    character_reference: BinaryIO = None,
                                    must_avoid: List[str] = None,
                                    style: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate an illustration for a story page

        Args:
            prompt: Detailed scene description
            character_bible: Character traits and visual details
            character_reference: Character reference image
            must_avoid: List of elements to avoid
            style: Optional style preset (validates against allowed presets)

        Returns:
            Dictionary with image_data and metadata

        Raises:
            ValueError: If style preset is invalid
        """
        # Validate and set style preset
        if style is None:
            style = prompts_config.get_character_default_style()
        elif not prompts_config.is_valid_style_preset(style):
            raise ValueError(f"Invalid style preset: {style}. Must be one of: {prompts_config.get_available_style_presets()}")

        # Enhance prompt with character consistency
        full_prompt = prompt
        if character_bible:
            character_desc = character_bible.get("visual_description", "")
            if character_desc:
                full_prompt = f"{character_desc}, {prompt}"

        # Build negative prompt from config
        negative_prompt = prompts_config.build_story_negative_prompt(must_avoid)

        return self.generate_image(
            prompt=full_prompt,
            negative_prompt=negative_prompt,
            style_preset=style,
            init_image=character_reference,
            image_strength=0.25 if character_reference else 0.0,
            width=1024,
            height=1024
        )

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

        url = f"{self.api_host}/v2beta/stable-image/control/style-transfer"

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
