from typing import Any, Literal, TYPE_CHECKING
from ii_agent.engine.v1.tools.mcp.base import MCPTool
from ii_agent.engine.v1.tools.slide_system.hook_utils import (
    persist_slide_tool_result,
    process_slide_content,
)
from ii_agent.engine.v1.tools.base import ToolResult

if TYPE_CHECKING:
    from ii_agent.engine.v1.agents.agent import IIAgent
    from ii_agent.engine.v1.tools.function import FunctionCall

NAME = "SlideWrite"
DISPLAY_NAME = "Write slide"
DESCRIPTION = """Creates or overwrites a slide with complete HTML content.

Usage:
- Use this tool instead of FileWriteTool for slide content
- Creates a new slide or overwrites an existing one in a presentation
- The slide will be saved as slide_XXX.html (e.g., slide_001.html for slide 1)
- Automatically creates the presentation directory if it doesn't exist
- Updates the metadata.json with slide information
- Local file paths in the HTML must be absolute paths accessible by the agent
- The HTML content should follow the system prompt guidelines for dimensions

IMPORTANT - Design Mode Support:
- Add `data-design-id` attributes to ALL editable elements for visual editing after creation.
- Design IDs must be LITERAL strings in the HTML, NOT dynamic values.
- Use descriptive, unique IDs following the pattern: "slide-{N}-{element-type}" or "slide-{N}-{section}-{element-type}".

REQUIRED elements that MUST have `data-design-id`:
1. **Structural/Container Elements** (for background, layout, border changes):
   - Main slide container: <div class="slide" data-design-id="slide-1-container">
   - Section containers: <section data-design-id="slide-1-hero-section">
   - Grid/flex containers: <div class="cards-grid" data-design-id="slide-1-cards-container">
   - Background/decorative elements: <div class="glow-circle" data-design-id="slide-1-glow-1">

2. **Content Elements** (for text, color changes):
   - Headings: <h1 data-design-id="slide-1-title">My Title</h1>
   - Paragraphs: <p data-design-id="slide-1-intro-text">Introduction paragraph</p>
   - Labels/badges: <span class="badge" data-design-id="slide-1-badge">Label</span>
   - Stats/numbers: <div data-design-id="slide-1-stat-1-number">85M</div>

3. **Card/Component Elements**:
   - Card wrapper: <div class="card" data-design-id="slide-1-card-1">
   - Card heading: <h3 data-design-id="slide-1-card-1-heading">Card Title</h3>
   - Card description: <p data-design-id="slide-1-card-1-description">Card text</p>

4. **Icons** (MUST be separately selectable):
   - Prefer inline `<svg>` icons with ID directly on the SVG element.
   - Example: <svg data-design-id="slide-1-icon-brain" ...>
   - Avoid icon-font `<i>` / Material Icons for primary iconography.
   - Do NOT combine icon + label in the same element; use separate DOM nodes with their own IDs.

5. **Images and Media**:
   - Image wrappers: <div class="image-container" data-design-id="slide-1-image-1-wrapper">
   - Images: <img data-design-id="slide-1-image-1" src="..." />

Example complete structure:
<div class="slide" data-design-id="slide-1-container">
  <div class="glow-circle glow-1" data-design-id="slide-1-glow-1"></div>
  <div class="content" data-design-id="slide-1-content">
    <h1 data-design-id="slide-1-title">Title</h1>
    <p data-design-id="slide-1-subtitle">Subtitle text</p>
  </div>
</div>

Examples of slide structure:
- Please refer to the examples below for the structure of the slide.
- Do not use the examples below as a template / theme / color ... ONLY learn the structure to make sure the slide is fit with full screen size.
- YOU MUST MAKE SURE THE SLIDE IS FIT WITH FULL SCREEN SIZE DO NOT SCROLL X,Y AXIS.
<example_1>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Deep Learning All Around Us!</title>
    <link href="https://fonts.googleapis.com/css2?family=Fredoka:wght@400;600;700&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Fredoka', sans-serif;
            background-color: #f5f5f5;
            overflow: hidden;
        }
        .slide {
            width: 1280px;
            min-height: 720px;
            position: relative;
            overflow: hidden;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            display: flex;
            flex-direction: column;
        }
        .slide-content {
            display: flex;
            flex-direction: column;
            flex-grow: 1;
            padding: 40px 70px;
            position: relative;
            z-index: 2;
        }
        .title {
            font-size: 40px;
            font-weight: 700;
            color: #ffffff;
            text-align: center;
            margin-bottom: 40px;
            text-shadow: 0px 2px 4px rgba(0, 0, 0, 0.1);
        }
        .examples-container {
            display: flex;
            justify-content: space-between;
            align-items: stretch;
            flex-grow: 1;
            gap: 20px;
        }
        .example-card {
            flex: 1;
            background-color: rgba(255, 255, 255, 0.2);
            backdrop-filter: blur(5px);
            border-radius: 20px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s ease;
        }
        .example-card:hover {
            transform: translateY(-5px);
        }
        .example-icon {
            font-size: 48px;
            color: #FFD54F;
            margin-bottom: 15px;
        }
        .example-title {
            font-size: 24px;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 15px;
            text-align: center;
        }
        .example-image {
            width: 180px;
            height: 180px;
            object-fit: contain;
            border-radius: 10px;
            margin-bottom: 15px;
        }
        .example-desc {
            font-size: 20px;
            color: #ffffff;
            text-align: center;
            line-height: 1.4;
        }
        .decoration {
            position: absolute;
            border-radius: 50%;
            background-color: rgba(255, 255, 255, 0.15);
            z-index: 1;
        }
        .decoration-1 {
            width: 150px;
            height: 150px;
            top: -40px;
            left: -40px;
        }
        .decoration-2 {
            width: 120px;
            height: 120px;
            bottom: -30px;
            right: 80px;
        }
        .material-icons {
            vertical-align: middle;
        }
    </style>
</head>
<body>
    <div class="slide">
        <div class="decoration decoration-1"></div>
        <div class="decoration decoration-2"></div>
        <div class="slide-content">
            <h1 class="title">Deep Learning All Around Us!</h1>
            
            <div class="examples-container">
                <!-- Voice Assistants -->
                <div class="example-card">
                    <i class="material-icons example-icon">mic</i>
                    <h2 class="example-title">Voice Assistants</h2>
                    <img src="https://sfile.chatglm.cn/images-ppt/8039cd4f1d97.jpg" alt="Voice Assistants" class="example-image">
                    <p class="example-desc">Siri, Alexa and Google understand your voice and answer questions!</p>
                </div>
                
                <!-- Self-Driving Cars -->
                <div class="example-card">
                    <i class="material-icons example-icon">directions_car</i>
                    <h2 class="example-title">Self-Driving Cars</h2>
                    <img src="https://sfile.chatglm.cn/images-ppt/d7630e18f659.jpg" alt="Self-Driving Cars" class="example-image">
                    <p class="example-desc">Cars that can see the road and drive all by themselves!</p>
                </div>
                
                <!-- Image Recognition -->
                <div class="example-card">
                    <i class="material-icons example-icon">photo_camera</i>
                    <h2 class="example-title">Image Recognition</h2>
                    <img src="https://sfile.chatglm.cn/images-ppt/df5764ce1424.jpg" alt="Image Recognition" class="example-image">
                    <p class="example-desc">Phones and apps that can identify animals and objects!</p>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
</example_1>

<example_2>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Big Bang Theory: Nerdiest Moments</title>
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Roboto', sans-serif;
            overflow: hidden;
        }
        .slide {
            width: 1280px;
            min-height: 720px;
            position: relative;
            overflow: hidden;
            background-color: #1a237e;
            display: flex;
            flex-direction: column;
        }
        .background {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, rgba(25, 118, 210, 0.9) 0%, rgba(156, 39, 176, 0.9) 100%);
        }
        .content {
            position: relative;
            width: 100%;
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            padding: 40px 70px;
            color: #ffffff;
            z-index: 1;
        }
        .title {
            font-family: 'Oswald', sans-serif;
            font-size: 40px;
            font-weight: 700;
            margin-bottom: 30px;
            text-transform: uppercase;
            letter-spacing: 1px;
            text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);
        }
        .moments-container {
            display: flex;
            flex-direction: column;
            gap: 20px;
            flex-grow: 1;
        }
        .moment-card {
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            padding: 20px;
            display: flex;
            transition: transform 0.3s ease;
            position: relative;
        }
        .moment-card:hover {
            transform: translateY(-3px);
            background-color: rgba(255, 255, 255, 0.15);
        }
        .moment-icon {
            flex-shrink: 0;
            width: 60px;
            height: 60px;
            background-color: rgba(255, 235, 59, 0.2);
            border-radius: 50%;
            display: flex;
            justify-content: center;
            align-items: center;
            margin-right: 20px;
        }
        .moment-icon i {
            font-size: 36px;
            color: #ffeb3b;
        }
        .moment-content {
            flex-grow: 1;
        }
        .moment-title {
            font-family: 'Oswald', sans-serif;
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 10px;
            color: #ffeb3b;
        }
        .moment-details {
            display: flex;
            gap: 20px;
        }
        .moment-description {
            flex: 1;
            font-size: 20px;
            line-height: 1.4;
        }
        .moment-examples {
            flex: 1;
            font-size: 20px;
            line-height: 1.4;
        }
        .highlight {
            color: #ffeb3b;
            font-weight: 700;
        }
        .rules-list {
            list-style-type: none;
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
        }
        .rules-list li {
            display: flex;
            align-items: center;
        }
        .rules-list li i {
            color: #ffeb3b;
            margin-right: 8px;
            font-size: 18px;
        }
        .decoration {
            position: absolute;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 0;
        }
        .atom {
            position: absolute;
            width: 120px;
            height: 120px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 50%;
            top: 50px;
            right: 50px;
            animation: rotate 20s linear infinite;
        }
        .atom::before {
            content: '';
            position: absolute;
            width: 120px;
            height: 120px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 50%;
            transform: rotate(60deg);
        }
        .atom::after {
            content: '';
            position: absolute;
            width: 120px;
            height: 120px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 50%;
            transform: rotate(-60deg);
        }
        .nucleus {
            position: absolute;
            width: 15px;
            height: 15px;
            background-color: #ffeb3b;
            border-radius: 50%;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
        }
        .electron {
            position: absolute;
            width: 8px;
            height: 8px;
            background-color: #ffeb3b;
            border-radius: 50%;
            top: -4px;
            left: 50%;
            transform: translateX(-50%);
            animation: orbit 3s linear infinite;
        }
        .equation {
            position: absolute;
            font-family: 'Roboto', sans-serif;
            font-size: 16px;
            color: rgba(255, 255, 255, 0.2);
            transform: rotate(-15deg);
        }
        .equation:nth-child(1) {
            top: 120px;
            left: 100px;
        }
        .equation:nth-child(2) {
            bottom: 150px;
            right: 120px;
            transform: rotate(10deg);
        }
        @keyframes rotate {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        @keyframes orbit {
            from { transform: rotate(0deg) translateX(60px) rotate(0deg); }
            to { transform: rotate(360deg) translateX(60px) rotate(-360deg); }
        }
    </style>
</head>
<body>
    <div class="slide">
        <div class="background"></div>
        <div class="decoration">
            <div class="atom">
                <div class="nucleus"></div>
                <div class="electron"></div>
            </div>
            <div class="equation">E = mc²</div>
            <div class="equation">Schrödinger's Cat</div>
        </div>
        <div class="content">
            <h1 class="title">Nerdiest Moments</h1>
            
            <div class="moments-container">
                <div class="moment-card">
                    <div class="moment-icon">
                        <i class="material-icons">casino</i>
                    </div>
                    <div class="moment-content">
                        <h2 class="moment-title">Rock-Paper-Scissors-Lizard-Spock</h2>
                        <div class="moment-details">
                            <div class="moment-description">
                                Because regular Rock-Paper-Scissors wasn't complicated enough. Created by Sam Kass, popularized when Sheldon used it to settle a TV dispute with Raj.
                            </div>
                            <div class="moment-examples">
                                <ul class="rules-list">
                                    <li><i class="material-icons">content_cut</i>Scissors cuts Paper</li>
                                    <li><i class="material-icons">description</i>Paper covers Rock</li>
                                    <li><i class="material-icons">landscape</i>Rock crushes Lizard</li>
                                    <li><i class="material-icons">pets</i>Lizard poisons Spock</li>
                                    <li><i class="material-icons">front_hand</i>Spock smashes Scissors</li>
                                    <li><i class="material-icons">content_cut</i>Scissors decapitates Lizard</li>
                                    <li><i class="material-icons">pets</i>Lizard eats Paper</li>
                                    <li><i class="material-icons">description</i>Paper disproves Spock</li>
                                    <li><i class="material-icons">front_hand</i>Spock vaporizes Rock</li>
                                    <li><i class="material-icons">landscape</i>Rock crushes Scissors</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="moment-card">
                    <div class="moment-icon">
                        <i class="material-icons">lightbulb</i>
                    </div>
                    <div class="moment-content">
                        <h2 class="moment-title">Bazinga</h2>
                        <div class="moment-details">
                            <div class="moment-description">
                                Sheldon's way of saying "Just kidding" but with more condescension. First used in Season 2 finale, became his signature catchphrase. Originated from a comic book store novelty item.
                            </div>
                            <div class="moment-examples">
                                <span class="highlight">Iconic moments:</span>
                                <ul>
                                    <li>Sheldon popping up from ball pit: "Bazinga!"</li>
                                    <li>Sheldon scaring Leonard from under couch cushions</li>
                                    <li>Trademarked by Warner Bros in 2012</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="moment-card">
                    <div class="moment-icon">
                        <i class="material-icons">music_note</i>
                    </div>
                    <div class="moment-content">
                        <h2 class="moment-title">Soft Kitty</h2>
                        <div class="moment-details">
                            <div class="moment-description">
                                The lullaby that makes grown physicists act like babies. Sung by Sheldon's mother when he was sick, now demanded whenever he feels ill. Based on a 1937 children's song.
                            </div>
                            <div class="moment-examples">
                                <span class="highlight">Lyrics:</span><br>
                                "Soft kitty, warm kitty, little ball of fur.<br>
                                Happy kitty, sleepy kitty, purr purr purr."
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
</example_2>


<example_3>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Big Bang Theory: Why You Should Watch</title>
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Roboto', sans-serif;
            overflow: hidden;
        }
        .slide {
            width: 1280px;
            min-height: 720px;
            position: relative;
            overflow: hidden;
            background-color: #1a237e;
            display: flex;
            flex-direction: column;
        }
        .background {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, rgba(25, 118, 210, 0.9) 0%, rgba(156, 39, 176, 0.9) 100%);
        }
        .content {
            position: relative;
            width: 100%;
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            padding: 40px 70px;
            color: #ffffff;
            z-index: 1;
        }
        .title {
            font-family: 'Oswald', sans-serif;
            font-size: 40px;
            font-weight: 700;
            margin-bottom: 30px;
            text-transform: uppercase;
            letter-spacing: 1px;
            text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);
        }
        .sales-container {
            display: flex;
            flex-grow: 1;
        }
        .sales-pitch {
            flex: 3;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .sales-points {
            list-style-type: none;
        }
        .sales-points li {
            display: flex;
            align-items: flex-start;
            margin-bottom: 20px;
            font-size: 20px;
            line-height: 1.4;
        }
        .sales-points li i {
            color: #ffeb3b;
            margin-right: 15px;
            font-size: 24px;
            flex-shrink: 0;
        }
        .highlight {
            color: #ffeb3b;
            font-weight: 700;
        }
        .sales-image {
            flex: 2;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding-left: 40px;
        }
        .sales-sticker {
            background-color: #ff5722;
            color: white;
            font-family: 'Oswald', sans-serif;
            font-size: 28px;
            font-weight: 700;
            padding: 15px 25px;
            transform: rotate(10deg);
            border-radius: 10px;
            box-shadow: 3px 3px 0 rgba(0, 0, 0, 0.2);
            margin-bottom: 30px;
            text-align: center;
        }
        .sales-disclaimer {
            font-size: 16px;
            font-style: italic;
            color: rgba(255, 255, 255, 0.7);
            text-align: center;
            margin-top: 20px;
        }
        .decoration {
            position: absolute;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 0;
        }
        .atom {
            position: absolute;
            width: 120px;
            height: 120px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 50%;
            top: 50px;
            right: 50px;
            animation: rotate 20s linear infinite;
        }
        .atom::before {
            content: '';
            position: absolute;
            width: 120px;
            height: 120px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 50%;
            transform: rotate(60deg);
        }
        .atom::after {
            content: '';
            position: absolute;
            width: 120px;
            height: 120px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 50%;
            transform: rotate(-60deg);
        }
        .nucleus {
            position: absolute;
            width: 15px;
            height: 15px;
            background-color: #ffeb3b;
            border-radius: 50%;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
        }
        .electron {
            position: absolute;
            width: 8px;
            height: 8px;
            background-color: #ffeb3b;
            border-radius: 50%;
            top: -4px;
            left: 50%;
            transform: translateX(-50%);
            animation: orbit 3s linear infinite;
        }
        .equation {
            position: absolute;
            font-family: 'Roboto', sans-serif;
            font-size: 16px;
            color: rgba(255, 255, 255, 0.2);
            transform: rotate(-15deg);
        }
        .equation:nth-child(1) {
            top: 120px;
            left: 100px;
        }
        .equation:nth-child(2) {
            bottom: 150px;
            right: 120px;
            transform: rotate(10deg);
        }
        @keyframes rotate {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        @keyframes orbit {
            from { transform: rotate(0deg) translateX(60px) rotate(0deg); }
            to { transform: rotate(360deg) translateX(60px) rotate(-360deg); }
        }
    </style>
</head>
<body>
    <div class="slide">
        <div class="background"></div>
        <div class="decoration">
            <div class="atom">
                <div class="nucleus"></div>
                <div class="electron"></div>
            </div>
            <div class="equation">E = mc²</div>
            <div class="equation">Schrödinger's Cat</div>
        </div>
        <div class="content">
            <h1 class="title">Why You Should Watch</h1>
            
            <div class="sales-container">
                <div class="sales-pitch">
                    <ul class="sales-points">
                        <li><i class="material-icons">trending_up</i> <span>Guaranteed to make you <span class="highlight">73.6% smarter</span> (results may vary)</span></li>
                        <li><i class="material-icons">science</i> <span>Features <span class="highlight">actual science jokes</span> you'll feel smart for understanding</span></li>
                        <li><i class="material-icons">record_voice_over</i> <span>Includes a <span class="highlight">laugh track</span> so you know when to laugh</span></li>
                        <li><i class="material-icons">favorite</i> <span>Comes with <span class="highlight">12 seasons</span> of character development and relationship drama</span></li>
                        <li><i class="material-icons">people</i> <span>Bonus: You'll finally understand what your <span class="highlight">nerdy friends</span> are talking about</span></li>
                        <li><i class="material-icons">warning</i> <span>Warning: May cause <span class="highlight">spontaneous use</span> of the word "Bazinga" in everyday conversation</span></li>
                    </ul>
                </div>
                
                <div class="sales-image">
                    <div class="sales-sticker">LIMITED TIME OFFER!</div>
                    <div class="sales-sticker">WATCH NOW!</div>
                    <p class="sales-disclaimer">*Offer void where prohibited. Side effects may include increased intelligence and social awkwardness.</p>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
</example_3>
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "presentation_name": {
            "type": "string",
            "description": "Name of the presentation",
        },
        "slide_number": {
            "type": "integer",
            "description": "Slide number (1-based)",
            "minimum": 1,
        },
        "content": {
            "type": "string",
            "description": "Complete HTML content for the slide",
        },
        "title": {"type": "string", "description": "Slide title for metadata"},
        "description": {
            "type": "string",
            "description": "Purpose/description of the slide",
        },
        "type": {
            "type": "string",
            "description": "Slide type (cover, content, chart, conclusion, etc.)",
            "default": "content",
        },
    },
    "required": [
        "presentation_name",
        "slide_number",
        "content",
        "title",
        "description",
    ],
}


class SlideWriteTool(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(
        self,
        name: str,
        display_name: str,
        description: str,
        input_schema: dict[str, Any],
        read_only: bool,
        requires_confirmation: bool,
        type: Literal["function", "openai_custom"] = "function",
    ) -> None:
        super().__init__(
            name=name,
            display_name=display_name,
            description=description,
            input_schema=input_schema,
            read_only=read_only,
            requires_confirmation=requires_confirmation,
            type=type,
        )
        self.url_cache = None

    async def on_tool_end(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        if fc.error:
            return

        tool_result = fc.result
        if not isinstance(tool_result, ToolResult):
            return
        if tool_result.is_error:
            return

        user_display = tool_result.user_display_content
        if user_display is None:
            return

        if self.url_cache is None:
            self.url_cache = {}

        processed_display = await process_slide_content(
            agent=agent,
            tool_name=self.name,
            user_display_content=user_display,
            url_cache=self.url_cache,
        )
        tool_result.user_display_content = processed_display

        await persist_slide_tool_result(
            agent=agent,
            tool_name=self.name,
            tool_input=fc.arguments or {},
            user_display_content=processed_display,
        )
