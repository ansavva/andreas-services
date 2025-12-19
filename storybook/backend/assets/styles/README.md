# Style Reference Images

This directory contains backend-owned style reference images used for Stability AI style transfer.

## Required Images

Place the following style reference images in this directory:

1. **animated_3d_reference.png** - High-quality 3D animated 3D animated character
   - Example: A 3D animated character portrait with soft lighting, rounded features, large expressive eyes
   - Recommended size: 1024x1024 or larger

## How It Works

When a user uploads photos of their child and requests character generation:
1. User's kid photo becomes the `init_image` (preserves identity/likeness)
2. One of these style references becomes the `style_image` (defines visual style)
3. Stability AI's style transfer applies the artistic style while preserving facial features

## Finding Style References

Good sources for style reference images:
- Generate sample images using Stability AI text-to-image with your desired style
- Use existing modern 3D animation artwork (for internal use only - don't redistribute)
- Create your own styled character portraits
- Commission artists to create style references

## Format Requirements

- Format: PNG (preferred) or JPEG
- Size: Minimum 512x512, recommended 1024x1024
- Content: Should clearly show the desired artistic style
- Quality: High resolution, clear details
