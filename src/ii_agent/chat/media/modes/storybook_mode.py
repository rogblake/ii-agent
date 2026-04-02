"""Storybook mode strategy for narrative generation."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.types import MediaPreferences
from ii_agent.core.container import get_app_container
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
        session_id: uuid.UUID,
        media_preferences: MediaPreferences,
    ) -> str:
        """Build narrative generation guidance for storybook mode."""
        # Build page count instruction if provided
        page_count_instruction = ""
        page_count = getattr(media_preferences, 'page_count', None)
        if page_count and page_count != 'unlimited':
            # page_count represents content pages only (cover page is NOT counted)
            # Total scenes = 1 cover + page_count content pages
            total_scenes = int(page_count) + 1  # +1 for cover page
            page_count_instruction = f"""
**CRITICAL PAGE COUNT REQUIREMENT:**
- The user has requested EXACTLY {page_count} content pages (PLUS 1 cover page)
- You MUST generate EXACTLY {total_scenes} scenes total in the scenes array:
  - Scene 1: Cover page (title/artwork)
  - Scenes 2-{total_scenes}: {page_count} content pages with story
- DO NOT generate more or fewer scenes than {total_scenes}
- The cover page does NOT count toward the {page_count} content pages
"""
        elif page_count == 'unlimited':
            page_count_instruction = """
**UNLIMITED PAGES MODE:**
- You have freedom to generate as many pages as needed for the story
- Still include a cover page as Scene 1
- Generate a complete, well-paced story without artificial constraints
- **HARD CAP (NON-NEGOTIABLE): Never exceed 50 content scenes. If the user asks for more, compress/condense the story to fit 50 content scenes.**
- **HARD CAP (SCENES ARRAY): Total scenes array must never exceed 51 (1 cover + 50 content scenes), regardless of any user request.**
- **If the user requests "unlimited" or any number > 50, treat it as 50 content scenes max and proceed without exceeding the cap.**
- **DRAFT → CONFIRM WORKFLOW (MANDATORY):**
  1) First respond with the FULL scene list (cover + all content scenes) in plain text and invite edits.
  2) Do NOT call the generate_storybook tool in this draft response.
  3) Only after the user explicitly confirms in a later message (e.g., "confirm", "approved", "looks good—generate") should you call generate_storybook.
  4) If the latest user message is not an explicit confirmation, keep refining the draft instead of generating.
"""

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
                template = await get_app_container().media_template_service.get_media_template_by_name(db_session, genre)
                if template and template.prompt:
                    genre_instruction = f"\n**GENRE STYLE GUIDE ({genre}):**\n{template.prompt}\n"
            except Exception:
                pass

        # Build template instruction if provided (via template_id)
        template_instruction = ""
        template_id = getattr(media_preferences, 'template_id', None)
        if template_id:
            try:
                template = await get_app_container().media_template_service.get_media_template_by_id(db_session, template_id)
                if template and template.prompt:
                    template_instruction = (
                        f"\n\n**TEMPLATE INSTRUCTIONS ({template.name}):**\n"
                        f"{template.prompt}\n"
                        f"IMPORTANT: Use these template instructions as the primary guide for visual style and narrative tone.\n"
                    )
            except Exception:
                pass

        # Build rich dialogue instruction if enabled
        rich_dialogue_instruction = ""
        rich_dialogue = getattr(media_preferences, 'rich_dialogue', None)
        if rich_dialogue:
            rich_dialogue_instruction = """

**RICH DIALOGUE MODE ENABLED:**
- Text content should be LONGER (4-5 sentences per scene, not just 1-3)
- HARD LIMIT: Maximum 490 characters per scene (including spaces and punctuation)
- Include extended dialogue exchanges between characters
- Add emotional inner thoughts and character monologue
- Use sound effects (BAM, WHOOSH, tap tap) for dramatic effect
- Show tension through pauses, ellipses, and silence
- Every line must reveal character, increase tension, or advance the story
- Keep dialogue purposeful and cinematic—avoid filler
"""

        return f"""

[STORYBOOK GENERATION MODE]

You are creating an illustrated storybook with multiple pages. Each page combines:
- An AI-generated image (visual scene)
- Brief narrative text (1-3 sentences per scene)
{page_count_instruction}{text_position_note}{language_instruction}{genre_instruction}{template_instruction}{rich_dialogue_instruction}
COVER PAGE (FIRST SCENE - REQUIRED):
- The FIRST scene MUST ALWAYS be a cover page
- The cover page should include the storybook title integrated into the image itself
- Use text_position: "none" for the cover page (the title should be part of the generated image, not overlaid text)
- The image_prompt should describe a visually appealing cover that includes the title text within the artwork
- Example cover image_prompt: "Full-bleed storybook cover illustration (no borders) with the title 'The Adventures of Rosie Rabbit' in decorative lettering integrated into the sky, showing a small brown rabbit with floppy ears in a sunny meadow extending to all edges, watercolor style, cheerful and inviting"
- The text_content for the cover should at least include the storybook title for voice narration (it won't be displayed since text_position is "none")

STORY STRUCTURE GUIDELINES (starting from scene 2):
- Beginning: Introduce characters, setting, and initial situation
- Middle: Build tension, conflict, adventure, or journey
- End: Resolution, lesson learned, or satisfying conclusion
- The number of content pages is determined by the user's page count selection
- Remember: Cover page (Scene 1) is SEPARATE from content pages - it doesn't count toward the page limit
- **NON-COVER PAGES (Scene 2+)**: Do NOT include any titles, text, or book-cover-style lettering in the image_prompt.
- **MAXIMUM SCENE LIMIT: Never exceed 50 content scenes in the scenes array (51 total including cover). Each scene = 1 image generation. In separate_page mode, each scene produces 2 pages (image + text), so 50 scenes = 100 content pages.**

CHARACTER CONSISTENCY (ABSOLUTE LOCK — CRITICAL):
- Every character MUST remain visually identical across ALL scenes unless the user explicitly instructs a change.
- This applies to the ENTIRE character — not just the face, but also:
  - Body proportions, build, height, and posture
  - Hairstyle, hair color, and hair length
  - Skin tone and facial features
  - Clothing, accessories, shoes, and any worn items
  - Distinctive markings, scars, tattoos, or unique traits
  - Color palette associated with the character
- Use the style.character_description field to establish the full appearance and repeat it VERBATIM in every scene's image_prompt where the character appears.
- The reference image from the previous page is provided to the image generator — your image_prompt MUST align with what was depicted in that reference. Do NOT introduce visual changes to characters between pages.
- If a character's outfit or appearance should change (e.g., a costume change in the story), the user must explicitly request it or the story context must clearly justify it.
- Example: If Scene 2 shows "a small brown rabbit with floppy ears wearing a red vest and blue scarf," then Scene 3, 4, 5, etc. must describe that rabbit with the EXACT same details: "a small brown rabbit with floppy ears wearing a red vest and blue scarf."

SCENE DESCRIPTIONS (image_prompt):
- Be highly detailed and specific for consistent visual style
- Include: subject, action, setting, lighting, mood, artistic style
- Maintain consistent art style across all scenes (watercolor, cartoon, realistic, etc.)
    - **CRITICAL IMAGE GENERATION REQUIREMENT**: EVERY image prompt MUST explicitly specify that the image should fill the ENTIRE canvas (full bleed) with NO borders, NO letterboxing, NO white/gray bars on sides, NO empty space around edges, and NO centered content with surrounding emptiness. ALSO: Do NOT ask for "framed" or "book page style" designs that might trigger decorative borders. The generated artwork must extend completely to all edges.
    - Example: "A small brown rabbit with floppy ears standing in a sunny meadow, wearing a red vest, surrounded by wildflowers, soft watercolor illustration style, warm lighting, cheerful mood"

TEXT CONTENT (text_content):
- Default (rich dialogue disabled): Keep text SHORT - less than 3 sentences per scene (ideally 1-2 sentences), max 190 characters per scene
- With rich dialogue enabled: Use longer text (4-5 sentences with dialogue and inner thoughts), max 490 characters per scene
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
- character_description: FULL physical appearance of main character(s) — include face, body, hair, clothing, accessories, and all distinguishing features. Use IDENTICAL wording across ALL scenes.
- art_style: "watercolor", "cartoon", "storybook illustration", "realistic", "comic book", etc.
- color_palette: "warm and bright", "cool and mysterious", "monochrome", "pastel", etc.
- These help maintain visual consistency across all generated scenes
- The previous page's generated image is used as a visual reference for each new page — your prompts must stay consistent with what was already rendered.

SCENE PACING:
- Vary scene complexity and energy level
- Simple → detailed → climax → resolution
- Use calm scenes between action scenes for pacing
- Final scene should feel conclusive and satisfying

Remember: When you're ready to generate (and in unlimited mode, only after explicit user confirmation), you MUST call the generate_storybook tool with a "scenes" array containing all scenes at once. The FIRST scene MUST be the cover page with text_position: "none". Each scene object should have: image_prompt, text_content, text_position, and text_percentage.

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
