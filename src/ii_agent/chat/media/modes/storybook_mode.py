"""Storybook mode strategy for narrative generation."""

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.schemas import MediaPreferences
from ii_agent.content.media.service import MediaTemplateService
from ii_agent.content.media.repository import MediaTemplateRepository
from ii_agent.core.storage.client import media_storage
from ii_agent.core.config.settings import get_settings
from .base import BaseModeStrategy


class StorybookModeStrategy(BaseModeStrategy):
    """
    Storybook mode strategy for multi-scene narrative generation.

    - Keeps conversation context for narrative continuity
    - Provides story structure and character consistency guidance
    - Supports iterative refinement of story scenes
    """

    def should_clear_context(self) -> bool:
        """Storybook mode keeps conversation context for narrative continuity."""
        return False

    async def build_prompt_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: str,
        media_preferences: MediaPreferences,
    ) -> str:
        """Build narrative generation guidance for storybook mode."""
        # Build page count instruction if provided
        page_count_instruction = ""
        page_count = getattr(media_preferences, 'page_count', None)
        if page_count:
            page_count_instruction = f"\n**IMPORTANT: The user has requested EXACTLY {page_count} pages/scenes. You MUST generate {page_count} scenes in the scenes array.**\n"

        # Build text position default if provided (skip 'none')
        text_position_note = ""
        text_position = getattr(media_preferences, 'text_position', None)
        if text_position and text_position != "none":
            text_position_note = f"\n**DEFAULT TEXT POSITION: Use '{text_position}' as the default text_position unless the user specifies otherwise.**\n"

        # Build language instruction if provided
        language_instruction = ""
        language = getattr(media_preferences, 'language', None)
        if language:
            language_instruction = (
                f"\n\n*** CRITICAL LANGUAGE INSTRUCTION ***\n"
                f"You MUST write ALL 'text_content' (narrative, dialogue) in {language}.\n"
                f"Even if the user's prompt is in another language, translate/adapt the story to {language}.\n"
                f"***************************************\n"
            )

        # Build genre instruction if provided
        genre_instruction = ""
        genre = getattr(media_preferences, 'genre', None)
        if genre:
            try:
                template = await MediaTemplateService(config=get_settings(), repo=MediaTemplateRepository(), media_storage=media_storage).get_media_template_by_name(db_session, genre)
                if template and template.prompt:
                    genre_instruction = f"\n**GENRE STYLE GUIDE ({genre}):**\n{template.prompt}\n"
            except Exception:
                pass

        return f"""

[STORYBOOK GENERATION MODE]

You are creating an illustrated storybook with multiple pages. Each page combines:
- An AI-generated image (visual scene)
- Brief narrative text (1-3 sentences per scene)
{page_count_instruction}{text_position_note}{language_instruction}{genre_instruction}
COVER PAGE (FIRST SCENE - REQUIRED):
- The FIRST scene MUST ALWAYS be a cover page
- The cover page should include the storybook title integrated into the image itself
- Use text_position: "none" for the cover page (the title should be part of the generated image, not overlaid text)
- The image_prompt should describe a visually appealing cover that includes the title text within the artwork
- Example cover image_prompt: "Full-bleed storybook cover illustration (no borders) with the title 'The Adventures of Rosie Rabbit' in decorative lettering integrated into the sky, showing a small brown rabbit with floppy ears in a sunny meadow extending to all edges, watercolor style, cheerful and inviting"
- The text_content for the cover should be empty or contain minimal text (it won't be displayed since text_position is "none")

STORY STRUCTURE GUIDELINES (starting from scene 2):
- Beginning: Introduce characters, setting, and initial situation
- Middle: Build tension, conflict, adventure, or journey
- End: Resolution, lesson learned, or satisfying conclusion
- Aim for 3-8 scenes for a complete story arc (plus the cover page)

CHARACTER CONSISTENCY:
- If a character appears in multiple scenes, describe them with identical details each time
- Use the style.character_description field to establish and maintain appearance
- Reference visual details from previous scenes when a character reappears
- Example: "the small brown rabbit with floppy ears" should be described the same way throughout

SCENE DESCRIPTIONS (image_prompt):
- Be highly detailed and specific for consistent visual style
- Include: subject, action, setting, lighting, mood, artistic style
- Maintain consistent art style across all scenes (watercolor, cartoon, realistic, etc.)
    - **CRITICAL IMAGE GENERATION REQUIREMENT**: EVERY image prompt MUST explicitly specify that the image should fill the ENTIRE canvas (full bleed) with NO borders, NO letterboxing, NO white/gray bars on sides, NO empty space around edges, and NO centered content with surrounding emptiness. ALSO: Do NOT ask for "framed" or "book page style" designs that might trigger decorative borders. The generated artwork must extend completely to all edges.
    - Example: "A small brown rabbit with floppy ears standing in a sunny meadow, wearing a red vest, surrounded by wildflowers, soft watercolor illustration style, warm lighting, cheerful mood"

TEXT CONTENT (text_content):
- Keep narrative text brief (1-3 sentences per scene)
- Text should complement the image, not repeat it
- Provide story context, dialogue, or character thoughts
- Example: "Rosie the rabbit loved exploring the meadow. One day, she discovered a mysterious path she had never seen before."

TEXT LAYOUT (text_position & text_percentage):
- **COVER PAGE (Scene 1)**: MUST use text_position: "none" because the title is part of the generated image
- **Story Pages (Scene 2+)**: Use the user-selected setting ("left", "right", "top", "bottom") or "none" to omit text entirely
- text_percentage: Follow the user's prompt; if not specified, default to ~30% text / 70% image
- For horizontal layouts (left/right): Better for landscape images
- For vertical layouts (top/bottom): Better for portrait images or dramatic scenes
- Keep position consistent within a story for visual flow, or vary deliberately for emphasis

IMAGE-TEXT COORDINATION:
- Image shows the ACTION or SCENE visually
- Text provides NARRATIVE CONTEXT, dialogue, or progression
- Together they tell a cohesive, flowing story
- **ABSOLUTELY CRITICAL - NO BORDERS ALLOWED**: Images MUST be full-bleed edge-to-edge illustrations that completely fill the entire canvas area. NEVER generate images with borders, frames, vignettes, letterboxing, white/gray bars on sides, or any empty space around the edges. The artwork must extend 100% to all four edges of the canvas with no exceptions. Do NOT create centered artwork with surrounding empty space - fill the complete frame.
- Each scene should advance the plot meaningfully

STYLE CONSISTENCY (use style parameter):
- character_description: Physical appearance of main character(s) - use identical wording across all scenes
- art_style: "watercolor", "cartoon", "storybook illustration", "realistic", "comic book", etc.
- color_palette: "warm and bright", "cool and mysterious", "monochrome", "pastel", etc.
- These help maintain visual consistency across all generated scenes

SCENE PACING:
- Vary scene complexity and energy level
- Simple → detailed → climax → resolution
- Use calm scenes between action scenes for pacing
- Final scene should feel conclusive and satisfying

Remember: You MUST call the generate_storybook tool with a "scenes" array containing all scenes at once. The FIRST scene MUST be the cover page with text_position: "none". Each scene object should have: image_prompt, text_content, text_position, and text_percentage.

**CRITICAL - RESPONSE FORMAT RULES:**
After calling the generate_storybook tool, you MUST follow these rules STRICTLY:

1. DO NOT include any image URLs in your response
2. DO NOT use markdown image syntax like ![...](...)
3. DO NOT mention or reference specific image links
4. DO NOT list the generated image URLs
5. ONLY provide a brief, friendly acknowledgment without any links

✓ CORRECT Response Examples:
- "I've created your storybook! Check out the interactive viewer below to flip through the pages."
- "Your 5-page adventure is ready! Click the storybook to read it."
- "Done! Your illustrated story is displayed below with page-flip functionality."

✗ WRONG - Never do this:
- Including URLs like "Here are your images: https://storage.googleapis.com/..."
- Using markdown like "![Page 1](https://...)"
- Listing image links in any format

The UI automatically displays the storybook in an interactive page-flip viewer. You only need to acknowledge completion.
"""

    def get_mode_name(self) -> str:
        """Return mode name for logging."""
        return "storybook"
