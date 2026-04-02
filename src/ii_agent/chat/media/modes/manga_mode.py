"""Manga mode strategy for manga-style panel layout generation."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.types import MediaPreferences
from ii_agent.core.container import get_app_container
from .base import BaseModeStrategy


class MangaModeStrategy(BaseModeStrategy):
    """
    Manga mode strategy for multi-panel manga page generation.

    - Keeps conversation context for narrative continuity
    - Provides manga panel composition, speech bubble, and color consistency guidance
    - Forces text_position to "none" (text rendered inside image as speech bubbles)
    """

    def should_clear_context(self) -> bool:
        """Manga mode keeps conversation context for narrative continuity."""
        return False

    async def build_prompt_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
        media_preferences: MediaPreferences,
    ) -> str:
        """Build narrative generation guidance for manga mode."""
        # Build page count instruction if provided
        page_count_instruction = ""
        page_count = getattr(media_preferences, 'page_count', None)
        if page_count and page_count != 'unlimited':
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

        manga_language_label = language or "the selected language"

        # Build rich dialogue + manga combined instruction if rich_dialogue is enabled
        combined_mode_instruction = ""
        rich_dialogue = getattr(media_preferences, 'rich_dialogue', None)
        if rich_dialogue:
            combined_mode_instruction = """

MANGA + RICH DIALOGUE COMBINED MODE
Both manga_layout and rich_dialogue are enabled. Follow these priority rules:

RULES THAT STILL APPLY ABSOLUTELY:
- PAGE COUNT RULE: One scene = one page (even if multi-panel manga)
- COVER PAGE RULE: Cover may be manga-style but must still be Scene 1
- CHARACTER CONSISTENCY: Remains ABSOLUTE
- FULL-BLEED RULE: Remains ABSOLUTE
- LANGUAGE LOCK: Remains ABSOLUTE

COMBINED MODE PRIORITIES:
- Prioritize visual storytelling first
- Dialogue must support panel rhythm, not overwhelm it
- Let the manga panels carry the action; use dialogue to enhance emotional beats
- Balance extended dialogue with visual pacing — avoid text-heavy pages that break manga flow
"""

        manga_layout_instruction = f"""

MANGA LAYOUT MODE — ENABLED
You are no longer generating single-page illustrations. You are now directing a REAL manga comic page.

MANGA PANEL RULES (MANDATORY)
- Each scene may contain multiple panels within ONE page
- Panels must follow authentic manga composition, including:
  - Panel gutters (spacing between panels)
  - Asymmetrical panel sizes
  - Vertical reading flow (top → bottom, right → left unless specified otherwise)
- Do NOT generate western comic layouts unless explicitly requested

PANEL COMPOSITION GUIDELINES
Each manga page should include a deliberate mix of:
- Wide establishing panels (setting, mood)
- Medium action panels (movement, interaction)
- Close-up panels (eyes, hands, emotional beats)
- Avoid repetitive framing.

VISUAL STORY FLOW
- Action should visually flow from panel to panel
- Character motion should guide the reader's eye
- Use overlapping motion lines, background streaks, or environment continuity

MANGA-SPECIFIC VISUAL ELEMENTS (ENCOURAGED)
- Speed lines
- Impact bursts
- Stylized shadows
- Emotional background effects (flowers, darkness, patterns, noise texture)
- Panel breaks that emphasize shock, silence, or climax

TEXT-IN-IMAGE REQUIREMENTS (MANDATORY)
- All dialogue and captions must be rendered inside the image (speech bubbles or caption boxes)
- The dialogue text MUST be written in {manga_language_label}
- Use the scene's text_content as the exact speech bubble/caption text
- Aim for 3-6 speech bubbles or caption boxes per page for richer dialogue
- Keep bubble text short and legible; avoid long paragraphs
- Set text_position to "none" for all non-cover pages (no external text blocks)

CONSISTENCY ACROSS PAGES (MANDATORY)
- Maintain consistent character design, line weight, screentone, panel gutter thickness, and lettering style across all pages
- Keep reading direction consistent across the entire storybook

MANGA COLOR CONSISTENCY (MANDATORY)
- The ENTIRE storybook MUST use a SINGLE, CONSISTENT color treatment on EVERY page — either fully black-and-white OR fully colored. NEVER mix B&W and color pages.
- If no color palette is specified or if the style is traditional manga: use STRICTLY black-and-white ink art with screentone shading on ALL pages. No color whatsoever — no colored backgrounds, no colored effects, no colored highlights, no colored speech bubbles, no tinted panels.
- If a color palette IS specified: apply that EXACT palette uniformly to EVERY page. Do not let any page fall back to grayscale or use different colors.
- EVERY image_prompt MUST explicitly state the color treatment (e.g., "black-and-white ink art, no color" or the specified color palette) to prevent the image generator from introducing inconsistent coloring.

MANGA LAYOUT IMAGE PROMPT REQUIREMENT
When manga_layout is enabled, the image_prompt MUST explicitly include:
- "multi-panel manga page"
- "comic panel layout"
- "visible panel gutters"
- "dynamic manga composition"
- "speech bubbles with readable {manga_language_label} text"
- The color treatment: "black-and-white ink art with screentone shading, no color" (or the user's specified color palette applied consistently)

⚠️ STILL FULL-BLEED: The entire manga page must fill the canvas edge-to-edge. Panels exist INSIDE the page — NOT framed by borders around the page.
"""

        return f"""

[STORYBOOK GENERATION MODE — MANGA]

You are creating a manga-style illustrated storybook with multiple pages. Each page combines:
- An AI-generated manga panel layout (visual scene with speech bubbles)
- Dialogue-heavy text rendered inside the image as speech bubbles
{page_count_instruction}{language_instruction}{genre_instruction}{template_instruction}{manga_layout_instruction}{combined_mode_instruction}
COVER PAGE (FIRST SCENE - REQUIRED):
- The FIRST scene MUST ALWAYS be a cover page
- The cover page should include the storybook title integrated into the image itself
- Use text_position: "none" for the cover page (the title should be part of the generated image, not overlaid text)
- The image_prompt should describe a visually appealing cover that includes the title text within the artwork
- Example cover image_prompt: "Full-bleed manga cover illustration (no borders) with the title 'The Adventures of Luna the Brave Cat' in decorative lettering integrated into the sky, showing a small brown rabbit with floppy ears in a sunny meadow extending to all edges, manga art style, dynamic composition"
- The text_content for the cover should at least include the storybook title for voice narration (it won't be displayed since text_position is "none")

STORY STRUCTURE GUIDELINES (starting from scene 2):
- Beginning: Introduce characters, setting, and initial situation
- Middle: Build tension, conflict, adventure, or journey
- End: Resolution, lesson learned, or satisfying conclusion
- The number of content pages is determined by the user's page count selection
- Remember: Cover page (Scene 1) is SEPARATE from content pages - it doesn't count toward the page limit
- **NON-COVER PAGES (Scene 2+)**: Include speech bubbles only — no titles or book-cover-style lettering in the image_prompt.
- **MAXIMUM SCENE LIMIT: Never exceed 50 content scenes in the scenes array (51 total including cover).**

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

SCENE DESCRIPTIONS (image_prompt):
- Be highly detailed and specific for consistent visual style
- Include: subject, action, setting, lighting, mood, artistic style
- Maintain consistent art style across all scenes
    - **CRITICAL IMAGE GENERATION REQUIREMENT**: EVERY image prompt MUST explicitly specify that the image should fill the ENTIRE canvas (full bleed) with NO borders, NO letterboxing, NO white/gray bars on sides, NO empty space around edges, and NO centered content with surrounding emptiness.

TEXT CONTENT (text_content):
- Use MORE dialogue. Target 3-6 short dialogue lines per scene (split with line breaks or " / " to indicate separate bubbles), ~45-120 words total, keep each line under ~12 words so text fits in speech bubbles
- Text should complement the image, not repeat it
- Provide story context, dialogue, or character thoughts

TEXT LAYOUT (text_position & text_percentage):
- **COVER PAGE (Scene 1)**: MUST use text_position: "none" because the title is part of the generated image
- **Story Pages (Scene 2+)**: MUST use text_position: "none" (text is rendered inside the image as speech bubbles)
- text_percentage: 0 for all manga pages

IMAGE-TEXT COORDINATION:
- Image shows the ACTION or SCENE visually with speech bubbles containing dialogue
- Together the panels and bubbles tell a cohesive, flowing story
- **ABSOLUTELY CRITICAL - NO BORDERS ALLOWED**: Images MUST be full-bleed edge-to-edge illustrations that completely fill the entire canvas area.
- Each scene should advance the plot meaningfully

STYLE CONSISTENCY (use style parameter):
- character_description: FULL physical appearance of main character(s) — include face, body, hair, clothing, accessories, and all distinguishing features. Use IDENTICAL wording across ALL scenes.
- art_style: "manga", "comic book", "anime", etc.
- color_palette: "monochrome", "black and white", or a specific color palette applied uniformly
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
- "I've created your manga! Check out the interactive viewer below to flip through the pages."
- "Your manga adventure is ready! Click to read it."
- "Done! Your manga is displayed below with page-flip functionality."

✗ WRONG - Never do this:
- Including URLs like "Here are your images: https://storage.googleapis.com/..."
- Using markdown like "![Page 1](https://...)"
- Listing image links in any format

The UI automatically displays the storybook in an interactive page-flip viewer. You only need to acknowledge completion.
"""

    def get_mode_name(self) -> str:
        """Return mode name for logging."""
        return "manga"
