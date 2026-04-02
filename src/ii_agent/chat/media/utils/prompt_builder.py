"""Utility for building media generation prompts."""

from typing import Dict, List, Tuple

from ii_agent.chat.types import MediaReference


class PromptBuilder:
    """Handles construction of prompts for media generation."""

    @staticmethod
    def build_reference_guidance(
        references: list[MediaReference],
        starting_index: int = 1,
    ) -> Tuple[str, Dict[str, List[int]], int]:
        """
        Build reference type guidance (subject/scene/style) with image indices.

        Args:
            references: List of MediaReference objects
            starting_index: Starting index for image numbering

        Returns:
            Tuple of (guidance_text, image_index_map, next_index)
            - guidance_text: Formatted guidance string
            - image_index_map: Maps reference type to list of image indices
            - next_index: Next available image index
        """
        if not references:
            return "", {}, starting_index

        ref_descriptions = []
        image_index_map = {}
        current_image_index = starting_index

        # Group references by type and track indices
        subject_refs = [r for r in references if r.type == "subject"]
        scene_refs = [r for r in references if r.type == "scene"]
        style_refs = [r for r in references if r.type == "style"]

        # Calculate image indices for each type
        if subject_refs:
            subject_indices = list(
                range(current_image_index, current_image_index + len(subject_refs))
            )
            image_index_map["subject"] = subject_indices
            current_image_index += len(subject_refs)

            indices_str = ", ".join([f"Image #{i}" for i in subject_indices])
            ref_descriptions.append(
                f"MANDATORY SUBJECT - {indices_str}:\n"
                f"   REQUIRED: The subject/character/person/object from these images MUST appear in the generated image\n"
                f"   EXTRACT: Identity, appearance, distinctive features, characteristics, form\n"
                f"   INTEGRATION: If modifying an existing image, integrate this subject INTO the existing scene/composition (don't replace the entire image, feature this subject within the existing context)\n"
                f"   IGNORE: Background, scene composition, artistic style, lighting from these images\n"
                f"   FAILURE: If the subject is not recognizably present, the generation is INVALID"
            )

        if scene_refs:
            scene_indices = list(range(current_image_index, current_image_index + len(scene_refs)))
            image_index_map["scene"] = scene_indices
            current_image_index += len(scene_refs)

            indices_str = ", ".join([f"Image #{i}" for i in scene_indices])
            ref_descriptions.append(
                f"MANDATORY SCENE/BACKGROUND - {indices_str}:\n"
                f"   REQUIRED: The environment/setting from these images MUST be used as the background\n"
                f"   EXTRACT: Location, environment type, spatial layout, key background elements, atmosphere\n"
                f"   IGNORE: Any people/characters in these images, artistic style\n"
                f"   FAILURE: If the background doesn't match this scene, the generation is INVALID"
            )

        if style_refs:
            style_indices = list(range(current_image_index, current_image_index + len(style_refs)))
            image_index_map["style"] = style_indices
            current_image_index += len(style_refs)

            indices_str = ", ".join([f"Image #{i}" for i in style_indices])
            ref_descriptions.append(
                f"MANDATORY STYLE - {indices_str}:\n"
                f"   REQUIRED: The artistic style from these images MUST be applied to the generated image\n"
                f"   EXTRACT ONLY: Art style name, color palette/scheme, rendering technique, brush stroke style, lighting mood, visual treatment method\n"
                f"   CRITICAL - STYLE = VISUAL TREATMENT ONLY: Think of this as applying a filter or artistic technique on top of existing content. The style should NOT change WHAT is shown (subjects, objects, scene composition), only HOW it's visually rendered (artistic technique, colors, mood)\n"
                f"   ABSOLUTELY IGNORE: ALL subjects/people/objects/scene elements/spatial composition - extract ZERO content from style images\n"
                f"   FAILURE: If the style doesn't match OR if style changes the scene composition/content OR if any subject from style image appears, the generation is INVALID"
            )

        if ref_descriptions:
            guidance_text = "=== REFERENCE IMAGES (Attached below in order) ===\n\n" + "\n\n".join(
                ref_descriptions
            )
        else:
            guidance_text = ""

        return guidance_text, image_index_map, current_image_index

    @staticmethod
    def build_previous_images_guidance(
        starting_index: int,
    ) -> str:
        """
        Build guidance for previously generated images.

        Args:
            starting_index: Index where previously generated images start

        Returns:
            Formatted guidance string
        """
        return (
            "=== PREVIOUSLY GENERATED IMAGES ===\n"
            f"Images starting from #{starting_index} onwards are previously generated images from this conversation.\n\n"
            "When user asks to modify/remake/change previous images:\n"
            "1. Use the MOST RECENT generated image as the base composition\n"
            "2. If SUBJECT references are provided: Integrate the subject INTO the existing scene (don't replace the entire scene, add/feature the subject within it)\n"
            "3. If SCENE references are provided: Replace the background/environment while keeping other elements intact\n"
            "4. If STYLE references are provided: Re-render the existing content with the new artistic style (preserve all content, only change visual treatment)\n"
            "5. Preserve all other aspects of the previous image that aren't covered by references or explicit user requests"
        )

    @staticmethod
    def build_checklist(
        references: list[MediaReference],
    ) -> str:
        """
        Build dynamic checklist based on what references exist.

        Args:
            references: List of MediaReference objects

        Returns:
            Formatted checklist string
        """
        if not references:
            return ""

        # Group references by type
        subject_refs = [r for r in references if r.type == "subject"]
        scene_refs = [r for r in references if r.type == "scene"]
        style_refs = [r for r in references if r.type == "style"]

        checklist_items = []
        if subject_refs:
            checklist_items.append(
                "□ Subject from SUBJECT reference is clearly visible and recognizable"
            )
        if scene_refs:
            checklist_items.append("□ Background matches the SCENE reference environment")
        if style_refs:
            checklist_items.append(
                "□ Artistic style matches STYLE reference (colors, technique, mood)"
            )
            checklist_items.append("□ NO content/subjects from STYLE reference appear in output")

        checklist_str = "\n".join(checklist_items) if checklist_items else ""

        return (
            "=== MANDATORY GENERATION RULES ===\n"
            "BEFORE generating, you MUST ensure ALL conditions are met:\n\n"
            f"{checklist_str}\n\n"
            "PROMPT CONSTRUCTION RULE:\n"
            "Your prompt to the image generator MUST explicitly describe ALL of these (when provided):\n"
            "1. The EXACT subject from subject references (describe their appearance, features, and characteristics in detail)\n"
            "2. The EXACT environment from scene references (describe the setting, location, and spatial layout)\n"
            "3. The EXACT style from style references (describe ONLY artistic treatment: art style, color palette, rendering technique, brush strokes, lighting style, visual mood - DO NOT describe any content/objects/people from style images)\n\n"
            "COMBINATION RULES when modifying existing images WITH references:\n"
            "- When SUBJECT reference is provided: The subject MUST be integrated into the existing scene composition. Preserve the scene/environment from previous image, but ensure the referenced subject is prominently featured.\n"
            "- When SCENE reference is provided: Replace the background/environment while preserving other elements (subjects, composition) from previous image unless explicitly asked to change.\n"
            "- When STYLE reference is provided: Apply ONLY the artistic style (colors, rendering, technique, mood) to the existing content. DO NOT change the scene composition, subjects, or any content - only change how it's visually rendered. Think of style as a filter or artistic treatment applied on top.\n"
            "- PRESERVE: All elements from previous image that are NOT covered by the references or user's explicit change request\n"
            "- CHANGE: Only aspects covered by references or explicitly mentioned by user\n\n"
            "STYLE ISOLATION (CRITICAL):\n"
            "- Style references provide ZERO content (no subjects, no objects, no scenes)\n"
            "- Style references provide ONLY visual treatment (how things look, not what is shown)\n"
            "- When applying style, the scene composition and subjects must remain unchanged from previous image or other references\n"
            "- Style = artistic rendering method applied to existing content, NOT a source of content\n\n"
            "INVALID GENERATION if:\n"
            "- Subject reference provided but subject not visible in output\n"
            "- Scene reference provided but background doesn't match\n"
            "- Style reference provided but artistic style doesn't match\n"
            "- Style reference causes changes to scene composition or content (subjects/objects)\n"
            "- Any person/object from STYLE reference appears in output\n"
            "CRITICAL EXTRACTION INSTRUCTION:\n"
            "Don't skip anything in subject/scene/style references.\n"
            "It is absolutely necessary to extract the information from it.\n\n"
            "=== GLOBAL IDENTITY PRIORITY ===\n"
            "Identity accuracy is mandatory; aesthetic quality is secondary.\n\n"
            "This rule OVERRIDES all style, artistic, or aesthetic considerations.\n"
            "If any conflict exists between identity fidelity and visual quality,\n"
            "identity fidelity MUST ALWAYS win.\n\n"
            "=== SUBJECT IDENTITY LOCKING ===\n\n"
            "MANDATORY IDENTITY LOCK — HUMAN SUBJECT:\n"
            "REQUIRED:\n"
            "- The human subject MUST be recognizably the SAME PERSON as in subject references\n"
            "- Facial identity consistency is TOP PRIORITY across all generations\n\n"
            "EXTRACT & LOCK (IMMUTABLE):\n"
            "- Facial structure & geometry\n"
            "- Face shape & proportions\n"
            "- Eye shape, spacing, size, color\n"
            "- Nose shape & size\n"
            "- Lip shape & proportions\n"
            "- Jawline & cheekbone structure\n"
            "- Skin tone & undertone\n"
            "- Age appearance\n"
            "- Ethnicity-defining features\n"
            "- Unique asymmetries\n"
            "- Distinctive marks (moles, scars, freckles)\n\n"
            "STRICTLY PRESERVE:\n"
            "- Identity-defining facial ratios\n"
            "- Head-to-body proportions\n"
            "- Hairline & hair density\n"
            "- Facial hair pattern (if present)\n"
            "- Baseline facial expression (unless explicitly changed)\n\n"
            "ALLOWED TO CHANGE (ONLY IF USER EXPLICITLY REQUESTS):\n"
            "- Pose\n"
            "- Clothing\n"
            "- Environment\n"
            "- Camera angle\n"
            "- Lighting\n"
            "- Artistic style (visual treatment ONLY)\n\n"
            "ABSOLUTELY FORBIDDEN:\n"
            "- Facial beautification\n"
            "- Symmetry correction\n"
            "- Face enhancement or idealization\n"
            "- Facial feature averaging\n"
            "- Identity stylization\n"
            "- Changing perceived age or gender expression\n\n"
            "FAILURE:\n"
            "- If the face appears as a different person\n"
            "- If facial features drift or are altered\n"
            "→ GENERATION IS INVALID\n\n"
            "MANDATORY IDENTITY LOCK — OBJECT / BRAND / LOGO:\n"
            "REQUIRED:\n"
            "- The object or brand asset MUST match the reference EXACTLY\n\n"
            "EXTRACT & LOCK (IMMUTABLE):\n"
            "- Overall geometry\n"
            "- Shape proportions\n"
            "- Aspect ratio\n"
            "- Structural layout\n"
            "- Icon construction\n\n"
            "TEXT & BRANDING RULE (CRITICAL):\n"
            "- Text MUST be reproduced EXACTLY character-for-character\n"
            "- No spelling changes\n"
            "- No paraphrasing\n"
            "- No substitutions\n"
            "- No auto-correction\n"
            "- No decorative distortion\n\n"
            "STRICTLY PRESERVE:\n"
            "- Letterforms\n"
            "- Kerning & spacing\n"
            "- Typography style\n"
            "- Logo alignment\n"
            "- Brand mark proportions\n\n"
            "ABSOLUTELY FORBIDDEN:\n"
            "- 'Inspired by' interpretations\n"
            "- Redesigns\n"
            "- Stylized logo variants\n"
            "- Brand simplification\n"
            "- Readability-altering effects\n\n"
            "FAILURE:\n"
            "- Any text mismatch\n"
            "- Any logo deformation\n"
            "→ GENERATION IS INVALID\n\n"
            "=== SUBJECT FINGERPRINT PERSISTENCE ===\n"
            "SUBJECT FINGERPRINT RULE:\n"
            "You MUST internally extract a persistent subject fingerprint that includes:\n"
            "- Facial ratios\n"
            "- Unique asymmetries\n"
            "- Identity-defining details\n\n"
            "This fingerprint MUST persist across:\n"
            "- Style changes\n"
            "- Lighting changes\n"
            "- Scene changes\n"
            "- Camera changes\n\n"
            "FAILURE:\n"
            "- If fingerprint consistency is broken\n"
            "→ GENERATION IS INVALID\n\n"
            "=== MULTI-SUBJECT IDENTITY ISOLATION ===\n"
            "MULTI-SUBJECT IDENTITY RULE:\n"
            "If multiple subject references are provided:\n"
            "- Each subject MUST retain its OWN identity\n"
            "- No facial blending\n"
            "- No feature averaging\n"
            "- No identity cross-contamination\n\n"
            "FAILURE:\n"
            "- Any identity mixing\n"
            "→ GENERATION IS INVALID\n\n"
            "=== PRIORITY RESOLUTION ORDER ===\n"
            "PRIORITY ORDER (HIGHEST → LOWEST):\n"
            "1. Subject Identity Accuracy\n"
            "2. Text / Logo Accuracy\n"
            "3. Scene / Environment Fidelity\n"
            "4. Style (Visual Treatment ONLY)\n\n"
            "Style MUST yield if it threatens identity fidelity.\n\n"
            "=== IDENTITY DRIFT PREVENTION ===\n"
            "IDENTITY DRIFT PREVENTION:\n"
            "If a requested style, rendering method, or aesthetic risks:\n"
            "- Facial distortion\n"
            "- Feature drift\n"
            "- Logo deformation\n"
            "- Text alteration\n\n"
            "Then:\n"
            "- Reduce stylization\n"
            "- Increase realism\n"
            "- Preserve geometry\n\n"
            "Identity fidelity OVERRIDES style strength.\n\n"
            "=== MANDATORY IDENTITY VALIDATION CHECKLIST ===\n"
            "IDENTITY VALIDATION CHECKLIST:\n"
            "□ Subject identity matches reference\n"
            "□ Facial features unchanged\n"
            "□ No beautification or enhancement\n"
            "□ No facial averaging\n"
            "□ Text is exact\n"
            "□ Logo geometry intact\n\n"
            "FAILURE:\n"
            "- If ANY item fails → DO NOT GENERATE\n\n"
            "=== IDENTITY FAILURE HANDLING ===\n"
            "FAILURE HANDLING DIRECTIVE:\n"
            "If perfect identity preservation cannot be guaranteed:\n"
            "- DO NOT approximate\n"
            "- DO NOT generate 'close enough' results\n"
            "- DO NOT prioritize aesthetics\n\n"
            "Non-generation is preferable to identity corruption"
        )

    @staticmethod
    def build_settings_constraint(
        aspect_ratio: str | None,
        resolution: str | None,
    ) -> str:
        """
        Build settings constraint notice for aspect ratio and resolution.

        Args:
            aspect_ratio: Aspect ratio setting (e.g., "16:9")
            resolution: Resolution setting (e.g., "1024x1024")

        Returns:
            Formatted settings constraint string
        """
        if not aspect_ratio and not resolution:
            return ""

        ar = aspect_ratio or "default"
        res = resolution or "default"
        return (
            f"\n\nIMPORTANT - UI Settings Override: The user has configured image settings via the UI toggle: "
            f"aspect_ratio={ar}, resolution={res}. "
            f"These settings will be used REGARDLESS of any ratio/resolution mentioned in the prompt. "
            f"Do NOT try to match the prompt's ratio/resolution - the UI settings take priority. "
            f"Generate ONE image only, using the UI settings. Do NOT retry with different ratios."
        )

    @staticmethod
    def build_mini_tool_hint(
        mini_tool_id: str,
        mini_tool_name: str,
    ) -> str:
        """
        Build hint text for mini tools mode.

        Args:
            mini_tool_id: ID of the mini tool
            mini_tool_name: Name of the mini tool

        Returns:
            Formatted mini tool hint string
        """
        return f' mini_tool_id={mini_tool_id}, mini_tool_name="{mini_tool_name}". '
