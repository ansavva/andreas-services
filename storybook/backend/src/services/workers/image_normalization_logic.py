import io
import os

from PIL import Image as PILImage
from werkzeug.datastructures import FileStorage

# Import pillow_heif for HEIC conversion
try:
    import pillow_heif
    print("[HEIC] pillow-heif module imported successfully")
except ImportError as e:
    pillow_heif = None
    print(f"Warning: pillow-heif not installed. HEIC format conversion will not work. Error: {e}")


# Allowed SDXL dimensions for AI generation
ALLOWED_SDXL_DIMENSIONS = [
    (1024, 1024), (1152, 896), (1216, 832), (1344, 768), (1536, 640),
    (640, 1536), (768, 1344), (832, 1216), (896, 1152),
]


def _find_best_sdxl_dimensions(width: int, height: int) -> tuple:
    """
    Find the closest allowed SDXL dimensions by aspect ratio

    Args:
        width: Original image width
        height: Original image height

    Returns:
        Tuple of (target_width, target_height)
    """
    orig_aspect = width / height
    best_match = None
    min_aspect_diff = float('inf')

    for allowed_w, allowed_h in ALLOWED_SDXL_DIMENSIONS:
        allowed_aspect = allowed_w / allowed_h
        aspect_diff = abs(orig_aspect - allowed_aspect)

        if aspect_diff < min_aspect_diff:
            min_aspect_diff = aspect_diff
            best_match = (allowed_w, allowed_h)

    return best_match


def _convert_heic_to_png(file: FileStorage, filename: str):
    """Convert HEIC/HEIF image to PNG without resizing"""
    if pillow_heif is None:
        print("[IMAGE CONVERT ERROR] pillow_heif not available, cannot convert HEIC")
        file.stream.seek(0)
        return file, filename

    try:
        file.stream.seek(0)
        file_data = file.stream.read()
        heif_file = pillow_heif.read_heif(file_data)
        img = PILImage.frombytes(heif_file.mode, heif_file.size, heif_file.data, "raw")
        if img.mode not in ('RGB', 'RGBA', 'L'):
            img = img.convert('RGB')

        output = io.BytesIO()
        img.save(output, format='PNG', optimize=True)
        output.seek(0)

        base_filename = os.path.splitext(filename)[0]
        new_filename = f"{base_filename}.png"

        new_file = FileStorage(
            stream=output,
            filename=new_filename,
            content_type='image/png'
        )

        return new_file, new_filename
    except Exception as e:
        print(f"Error converting HEIC image: {e}")
        file.stream.seek(0)
        return file, filename


def resize_image(file: FileStorage, filename: str):
    """
    Resize image: convert HEIC to PNG and resize to SDXL dimensions

    Args:
        file: FileStorage object containing image
        filename: Original filename

    Returns:
        Tuple of (processed FileStorage, new filename)
    """
    try:
        # Ensure we're at the start of the stream
        file.stream.seek(0)

        # Read the entire file into memory
        file_data = file.stream.read()
        print(f"[IMAGE NORMALIZE] Processing {filename}, size: {len(file_data)} bytes")

        # Handle HEIC files
        if filename.lower().endswith(('.heic', '.heif')):
            if pillow_heif is None:
                print("[IMAGE NORMALIZE ERROR] pillow_heif not available, cannot convert HEIC")
                file.stream.seek(0)
                return file, filename

            print(f"[IMAGE NORMALIZE] Converting HEIC to PNG")
            heif_file = pillow_heif.read_heif(file_data)
            img = PILImage.frombytes(heif_file.mode, heif_file.size, heif_file.data, "raw")
            print(f"[IMAGE NORMALIZE] HEIC converted, mode: {img.mode}, size: {img.size}")
        else:
            # Open regular image
            img = PILImage.open(io.BytesIO(file_data))
            print(f"[IMAGE NORMALIZE] Opened image, mode: {img.mode}, size: {img.size}")

        orig_width, orig_height = img.size

        # Find best SDXL dimensions
        target_width, target_height = _find_best_sdxl_dimensions(orig_width, orig_height)
        print(f"[IMAGE NORMALIZE] Resizing from {orig_width}x{orig_height} to {target_width}x{target_height}")

        # Calculate the scaling factor to fit within target dimensions while maintaining aspect ratio
        scale = min(target_width / orig_width, target_height / orig_height)
        new_width = int(orig_width * scale)
        new_height = int(orig_height * scale)

        # Resize image while maintaining aspect ratio
        img = img.resize((new_width, new_height), PILImage.Resampling.LANCZOS)

        # Create a new image with the target dimensions and paste the resized image centered
        final_img = PILImage.new('RGB', (target_width, target_height), (255, 255, 255))
        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2
        final_img.paste(img, (paste_x, paste_y))
        img = final_img

        # Convert to RGB if necessary (for PNG compatibility)
        if img.mode not in ('RGB', 'RGBA', 'L'):
            print(f"[IMAGE NORMALIZE] Converting from {img.mode} to RGB")
            img = img.convert('RGB')

        # Save as PNG to BytesIO
        output = io.BytesIO()
        img.save(output, format='PNG', optimize=True)
        output.seek(0)
        print(f"[IMAGE NORMALIZE] Saved as PNG, size: {len(output.getvalue())} bytes")
        output.seek(0)

        # Create new filename with .png extension
        base_filename = os.path.splitext(filename)[0]
        new_filename = f"{base_filename}.png"

        # Create a new FileStorage object
        new_file = FileStorage(
            stream=output,
            filename=new_filename,
            content_type='image/png'
        )

        return new_file, new_filename
    except Exception as e:
        print(f"Error normalizing image: {e}")
        import traceback
        traceback.print_exc()
        # Return original file if normalization fails
        file.stream.seek(0)
        return file, filename


def convert_heic_if_needed(file: FileStorage, filename: str):
    if filename.lower().endswith(('.heic', '.heif')):
        return _convert_heic_to_png(file, filename)
    file.stream.seek(0)
    return file, filename


__all__ = ["resize_image", "convert_heic_if_needed", "_convert_heic_to_png"]
