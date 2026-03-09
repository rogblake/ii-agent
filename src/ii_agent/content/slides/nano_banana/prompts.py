"""AI prompts for Nano Banana design mode.

Contains prompts for:
- Vision-based component detection (Gemini 3 Flash)
- Image regeneration with modifications
- Background removal
"""

from typing import Dict, List, Optional

from .schemas import DetectedComponent, Instruction, SelectionType


# ============ Component Detection Prompt ============


COMPONENT_DETECTION_PROMPT = """Analyze this presentation slide image and detect all visual components.

IMAGE DIMENSIONS: {width}px × {height}px

You MUST call the submit_detected_components tool with every component you detect.

COMPONENT TYPES (detect all that apply):
- "title": Main heading/title text
- "subtitle": Secondary heading text
- "text_block": Paragraph or body text
- "bullet_list": Bulleted or numbered list
- "header": Top header area
- "footer": Bottom footer area
- "image": Photo, illustration, or embedded image
- "icon": Small icon or symbol
- "logo": Brand logo
- "chart": Graph, chart, or data visualization
- "shape": Decorative shape (rectangle, circle, line, etc.)
- "character": Person, avatar, or character illustration
- "background_element": Decorative background element

DETECTION RULES:
1. Detect EVERY visible element, including small ones
2. Bounding boxes must be TIGHT around content (minimal padding, ~2px max)
3. For text: capture the EXACT text content if readable
4. Group related items (e.g., bullet list items as one component)
5. For overlapping elements, assign appropriate z_index
6. Include decorative elements and shapes
7. Detect characters/people as "character" type
8. All bounding_box values are in PIXELS

If no components are detected, call the tool with an empty components array."""


# ============ Slide Regeneration Prompt ============


REGENERATION_PROMPT_TEMPLATE = """You are regenerating a presentation slide image based on specific modifications.

REFERENCE IMAGE: The attached image is the ORIGINAL slide that needs to be modified.

MODIFICATIONS TO APPLY:
{modifications}

CRITICAL RULES:
1. Keep EVERYTHING else IDENTICAL to the original slide
2. Same layout, same colors, same fonts, same decorative elements, same background
3. ONLY change the specific elements/regions described above
4. Maintain the exact same visual style and professional quality
5. Output dimensions: 1920×1080 pixels (16:9 landscape)
6. The result must look like a professional presentation slide
7. Preserve all spacing, alignment, and visual hierarchy from the original

{context_section}

Generate the modified slide image now."""


# ============ Remove Background Prompt ============


REMOVE_BACKGROUND_PROMPT = """Remove the background from this presentation slide image.

INSTRUCTIONS:
1. Keep ALL foreground elements (text, icons, characters, shapes, logos, etc.)
2. Replace the background with a solid white (#FFFFFF) color
3. Maintain crisp edges around foreground elements
4. Do not modify any foreground content - keep them exactly as they are
5. Output: 1920×1080 pixels

Generate the slide with the background removed (replaced with white)."""


# ============ Helper Functions ============


def build_modifications_text(
    instructions: List[Instruction],
    components: Optional[List[DetectedComponent]] = None,
) -> str:
    """Convert instructions to human-readable modification text for the AI prompt."""
    if not instructions:
        return "No modifications specified."

    components_map: Dict[str, DetectedComponent] = {}
    if components:
        components_map = {c.design_id: c for c in components}

    lines = []

    for inst in instructions:
        sel = inst.selection
        location = _describe_selection_location(sel, components_map)

        if inst.instruction_type.value == "text_edit" and inst.new_text:
            lines.append(f'- Change the text at {location} to: "{inst.new_text}"')
        elif inst.instruction_type.value == "ai_modify" and inst.ai_prompt:
            lines.append(f"- At {location}: {inst.ai_prompt}")
        elif inst.instruction_type.value == "remove_background":
            lines.append(f"- Remove/clear the background at {location}")

    return "\n".join(lines) if lines else "No modifications specified."


def _describe_selection_location(sel, components_map: Dict[str, DetectedComponent]) -> str:
    """Generate a human-readable description of a selection location."""

    if sel.type == SelectionType.COMPONENT and sel.component_id:
        comp = components_map.get(sel.component_id)
        if comp:
            location = f"the {comp.component_type} '{comp.label}'"
            if comp.text_content:
                text_preview = (
                    f"{comp.text_content[:50]}..."
                    if len(comp.text_content) > 50
                    else comp.text_content
                )
                location += f' (text: "{text_preview}")'
            location += f" at position ({comp.bounding_box.x:.1f}%, {comp.bounding_box.y:.1f}%)"
            return location
        return f"component {sel.component_id}"

    elif sel.type == SelectionType.SPOT:
        return f"the spot at ({sel.spot_x:.1f}%, {sel.spot_y:.1f}%) from top-left"

    elif sel.type == SelectionType.BOX and sel.box:
        box = sel.box
        return (
            f"the rectangular region from ({box.x:.1f}%, {box.y:.1f}%) "
            f"to ({box.x + box.width:.1f}%, {box.y + box.height:.1f}%)"
        )

    return "the selected area"


def build_context_section(
    components: Optional[List[DetectedComponent]] = None,
) -> str:
    """Build context section describing all detected components for the AI prompt."""
    if not components:
        return ""

    lines = ["DETECTED COMPONENTS IN ORIGINAL (for reference):"]
    for comp in components:
        line = (
            f"- {comp.component_type} at ({comp.bounding_box.x:.1f}%, {comp.bounding_box.y:.1f}%)"
        )
        if comp.text_content:
            text_preview = (
                f"{comp.text_content[:30]}..." if len(comp.text_content) > 30 else comp.text_content
            )
            line += f': "{text_preview}"'
        lines.append(line)

    return "\n".join(lines)


def build_regeneration_prompt(
    instructions: List[Instruction],
    components: Optional[List[DetectedComponent]] = None,
) -> str:
    """Build the complete regeneration prompt."""
    modifications = build_modifications_text(instructions, components)
    context = build_context_section(components)

    return REGENERATION_PROMPT_TEMPLATE.format(
        modifications=modifications,
        context_section=context,
    )
