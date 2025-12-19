# AI Prompts

This directory contains markdown files for AI generation prompts. Using markdown files instead of YAML strings gives you:

- Better formatting and readability
- Multi-line prompts with proper structure
- Easy editing with rich text support
- Version control friendly

## Files

- `style_transfer_prompt.md` - Main prompt for style transfer character generation
- `style_transfer_negative.md` - Negative prompt for style transfer
- `character_base_prompt.md` - Legacy base prompt for image-to-image generation
- `character_negative_prompt.md` - Legacy negative prompt for character generation

## Usage

Edit these files directly to customize prompts. The backend will automatically load them when generating images.
