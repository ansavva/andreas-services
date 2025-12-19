"""
Style Reference Image Manager

Manages backend-owned style reference images used for Stability AI style transfer.
Each style_id maps to a specific reference image that defines the visual style.
"""
from pathlib import Path
from typing import Optional, BinaryIO
import io

class StyleReferenceManager:
    """
    Manages style reference images for style transfer

    Currently supported style:
    - pixar_3d: Pixar-style 3D animated character (default)
    """

    def __init__(self):
        # Path to style reference images directory
        self.styles_dir = Path(__file__).parent.parent.parent / "assets" / "styles"

        # Map style_id to filename
        # Currently only supporting Pixar 3D style
        self.style_map = {
            "pixar_3d": "pixar_3d_reference.png"
        }

    def get_available_styles(self) -> list:
        """Get list of available style IDs"""
        return list(self.style_map.keys())

    def is_valid_style(self, style_id: str) -> bool:
        """Check if style_id is valid"""
        return style_id in self.style_map

    def get_style_image(self, style_id: str) -> BinaryIO:
        """
        Load and return style reference image

        Args:
            style_id: Style identifier

        Returns:
            BytesIO object containing image data

        Raises:
            ValueError: If style_id is invalid
            FileNotFoundError: If style image file doesn't exist
        """
        if not self.is_valid_style(style_id):
            raise ValueError(
                f"Invalid style_id '{style_id}'. "
                f"Must be one of: {self.get_available_styles()}"
            )

        filename = self.style_map[style_id]
        filepath = self.styles_dir / filename

        if not filepath.exists():
            raise FileNotFoundError(
                f"Style reference image not found: {filepath}. "
                f"Please add the required style reference images to {self.styles_dir}"
            )

        # Read image into BytesIO
        with open(filepath, 'rb') as f:
            image_data = f.read()

        return io.BytesIO(image_data)

    def get_default_style(self) -> str:
        """Get default style ID"""
        return "pixar_3d"


# Singleton instance
style_references = StyleReferenceManager()
