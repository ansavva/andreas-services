# Style Transfer Implementation Guide

## Overview

The storybook backend now supports **Stability AI's Style Transfer endpoint** for character portrait generation. This is the **RECOMMENDED** method as it provides better preservation of kid likeness while applying artistic styles (3D animation studio, animation, etc.).

## Architecture

### How It Works

1. **User provides**: Kid reference photo(s) + optional text description
2. **Backend provides**: Style reference image (3D animated character example, etc.)
3. **Stability AI**: Combines them using style transfer to create a stylized portrait that preserves the kid's likeness

### Key Components

- **New Endpoint**: `POST /api/characters/project/{project_id}/portrait-stylized`
- **Style Reference Manager**: `src/config/style_references.py` - Maps style_id to backend-owned reference images
- **Stability Service**: `src/services/stability_service.py` - Added `style_transfer()` method
- **Configuration**: `config/config.yaml` - Style transfer prompts and parameters

## API Usage

### Generate Stylized Portrait

**Endpoint**: `POST /api/characters/project/{project_id}/portrait-stylized`

**Request Body** (JSON):
```json
{
  "user_description": "wearing glasses, big smile",  // Optional
  "style_id": "animated_3d",  // Optional, default: "animated_3d"
  "style_strength": 0.8    // Optional, default: 0.8, range: 0.0-1.0
}
```

**Response**:
```json
{
  "_id": "asset_123",
  "project_id": "proj_456",
  "asset_type": "portrait",
  "image_id": "img_789",
  "is_approved": false,
  "version": 1,
  "prompt": "A cheerful young child... (style: animated_3d, strength: 0.8)"
}
```

### Available Style IDs

Current styles (defined in `src/config/style_references.py`):
- `animated_3d` - High-quality 3D animated 3D animated character (default)
- `storybook` - Classic storybook illustration
- `watercolor` - Soft watercolor painting style
- `comic` - Comic book/graphic novel style

### Style Strength Parameter

- **0.0-0.3**: Very subtle stylization, mostly preserves original photo
- **0.4-0.6**: Moderate stylization with good likeness preservation
- **0.7-0.9**: Strong stylization (Recommended for high-quality animation style effects)
- **0.9-1.0**: Maximum stylization, may drift from likeness

**Recommended**: 0.8 (configured in `config/config.yaml`)

## Setup Instructions

### 1. Add Style Reference Images

Place style reference images in: `storybook/backend/assets/styles/`

Required files:
- `animated_3d_reference.png` - High-quality 3D animated character example
- `storybook_reference.png` - Storybook illustration example
- `watercolor_reference.png` - Watercolor style example
- `comic_reference.png` - Comic art style example

**Requirements**:
- Format: PNG (preferred) or JPEG
- Size: Minimum 512x512, recommended 1024x1024
- Content: Should clearly demonstrate the desired artistic style

**How to get style references**:
1. Generate using Stability AI text-to-image with your desired style
2. Use existing artwork (internal use only - don't redistribute copyrighted material)
3. Create custom styled portraits
4. Commission artists

See `assets/styles/README.md` for detailed guidance.

### 2. Configure Prompts

Edit `config/config.yaml` to customize:

```yaml
character:
  # Style transfer prompt (appended with user description)
  style_transfer_prompt: "A cheerful young child character portrait..."

  # What to avoid
  style_transfer_negative: "photorealistic, adult, scary, dark..."

  # Default strength (0.0-1.0)
  style_strength: 0.8

  # Default style_id
  default_style_id: "animated_3d"
```

## Frontend Integration

### Update Character Controller API

Add new API function in `src/apis/characterController.tsx`:

```typescript
export const generateStylizedPortrait = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  userDescription?: string,
  styleId?: string,
  styleStrength?: number
): Promise<CharacterAsset> => {
  const response = await axiosInstance.post(
    `/api/characters/project/${projectId}/portrait-stylized`,
    {
      user_description: userDescription,
      style_id: styleId,
      style_strength: styleStrength
    }
  );
  return response.data;
};
```

### Update Character Creation Component

In `characterCreationStep.tsx`, you can either:

**Option A**: Replace the existing generate call with style transfer
```typescript
const result = await generateStylizedPortrait(
  axiosInstance,
  projectId,
  userDescription || undefined,
  "animated_3d",  // or let user select
  undefined  // use default strength
);
```

**Option B**: Add a toggle to let users choose between methods

## Comparison: Style Transfer vs Image-to-Image

### Style Transfer (NEW - Recommended)
✅ Better likeness preservation
✅ More consistent results
✅ Easier to control artistic style
✅ Uses dedicated Stability AI endpoint
❌ Requires backend style reference images

### Image-to-Image (Legacy)
✅ No additional assets needed
✅ Supports style presets directly
❌ Less predictable likeness preservation
❌ Harder to achieve consistent 3D animation studio look

## Configuration Reference

### Prompts Config Methods

```python
# Style transfer
prompts_config.get_style_transfer_prompt()  # Base prompt
prompts_config.get_style_transfer_negative()  # Negative prompt
prompts_config.get_style_strength()  # Default strength (0.8)
prompts_config.get_default_style_id()  # Default style ("animated_3d")
prompts_config.build_style_transfer_prompt(user_desc)  # Build full prompt
```

### Style References Methods

```python
# Style management
style_references.get_available_styles()  # List available style IDs
style_references.is_valid_style(style_id)  # Validate style_id
style_references.get_style_image(style_id)  # Load style reference image
style_references.get_default_style()  # Get default ("animated_3d")
```

## Testing

### Test the Endpoint

```bash
# Generate stylized portrait
curl -X POST http://localhost:5001/api/characters/project/{project_id}/portrait-stylized \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "user_description": "wearing glasses, big smile",
    "style_id": "animated_3d",
    "style_strength": 0.8
  }'
```

### Error Cases to Test

1. Missing kid photos → 400 error
2. Invalid style_id → 400 error with available styles list
3. style_strength out of range → 400 error
4. Missing style reference file → 500 error with helpful message

## Migration Path

### Phase 1: Parallel Implementation (Current)
- Both endpoints available
- Old: `/project/{id}/portrait` (image-to-image)
- New: `/project/{id}/portrait-stylized` (style transfer)
- Frontend can use either

### Phase 2: Switch Default (After testing)
- Update frontend to use style transfer by default
- Keep old endpoint for fallback

### Phase 3: Deprecation (Optional)
- Remove old image-to-image endpoint if style transfer proves superior
- Or keep both for different use cases

## Troubleshooting

### Style reference images not found
- Check `assets/styles/` directory exists
- Verify image filenames match `style_map` in `style_references.py`
- Check file permissions

### Poor likeness preservation
- Try lowering `style_strength` (e.g., 0.6 instead of 0.8)
- Ensure kid photos are good quality (well-lit, clear face)
- Try different kid photo (first photo is used as init_image)

### Results too realistic
- Increase `style_strength` (e.g., 0.9)
- Check that style reference image is clearly stylized
- Verify prompt includes artistic style keywords

## Next Steps

1. ✅ Add style reference images to `assets/styles/`
2. ✅ Test endpoint with real kid photos
3. ✅ Integrate into frontend
4. ✅ Gather user feedback
5. ✅ Iterate on prompts and style_strength defaults
6. ✅ Consider adding more style options

## Reference

- **Stability AI Docs**: https://platform.stability.ai/docs/api-reference#tag/Control/paths/~1v2beta~1stable-image~1control~1style-transfer/post
- **Implementation**: `src/services/stability_service.py:332` (style_transfer method)
- **Endpoint**: `src/controllers/character_controller.py:97` (portrait-stylized)
