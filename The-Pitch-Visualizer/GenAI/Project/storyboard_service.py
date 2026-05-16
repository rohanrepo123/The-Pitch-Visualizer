from dataclasses import dataclass, field
from pathlib import Path
import re

from langchain_core.exceptions import OutputParserException
from nltk.tokenize import sent_tokenize
from openai import OpenAI

from modules import *
from pydantic_obj import *


STYLE_PRESETS = {
    "storybook": {
        "label": "Storybook Watercolor",
        "description": "Soft watercolor washes with warm paper texture and gentle lighting.",
        "prompt": "storybook watercolor illustration, soft painted textures, warm paper grain, expressive characters, inviting color palette",
    },
    "cinematic-3d": {
        "label": "Cinematic 3D",
        "description": "Stylized 3D frames with polished lighting and animated-film depth.",
        "prompt": "stylized 3D animated film frame, cinematic lighting, rich depth, polished materials, expressive character acting",
    },
    "anime": {
        "label": "Anime Adventure",
        "description": "Vibrant anime-inspired visuals with dynamic lighting and emotion.",
        "prompt": "anime feature film illustration, vibrant color design, dynamic lighting, expressive faces, dramatic composition",
    },
    "graphic-novel": {
        "label": "Graphic Novel",
        "description": "Bold inked outlines, dramatic contrast, and panel-ready composition.",
        "prompt": "graphic novel illustration, bold inked linework, dramatic shading, textured color blocks, striking panel composition",
    },
    "paper-cut": {
        "label": "Paper Cut Collage",
        "description": "Layered handcrafted shapes with tactile paper textures and whimsy.",
        "prompt": "layered paper cut collage illustration, handcrafted textures, tactile shadows, playful shapes, dimensional depth",
    },
}

DEFAULT_STYLE_KEY = "storybook"
IMAGE_MODEL = "gpt-image-1.5"

storyboard_prompt = PromptTemplate(
    template="""You turn short stories into storyboard captions for image generation.

Create between 3 and 5 storyboard panels that cover the full story from beginning to end.
Each panel should describe one visual beat in 1 or 2 vivid sentences.
Keep recurring characters, props, and locations consistent across panels.

Return only valid JSON that matches this schema:
{instruction}

Story:
{story}""",
    input_variables=["story"],
    partial_variables={"instruction": parser2.get_format_instructions()},
)

prompt_memory = PromptTemplate(
    template="""Analyze this image and extract the visual details needed to keep future storyboard panels consistent.

Return only valid JSON that matches this schema:
{instruction}""",
    input_variables=[],
    partial_variables={"instruction": memory_parser.get_format_instructions()},
)

llm_compressed = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.4, max_tokens=600)
llm_visual = ChatOpenAI(model="gpt-4o", temperature=0.7, max_tokens=1500)
llm_story = ChatOpenAI(model="gpt-4", temperature=0, max_tokens=1200)
openai_client = OpenAI()


@dataclass
class StoryboardState:
    style_key: str
    # Memory is accumulated from previously rendered panels so later prompts can
    # keep characters, setting, and look-and-feel consistent.
    memory: dict = field(
        default_factory=lambda: {
            "environment": [],
            "look": [],
            "picture_style": [],
            "miscellaneous": [],
        }
    )
    image_paths: list = field(default_factory=list)
    generated_panels: list = field(default_factory=list)

    @property
    def style(self):
        return STYLE_PRESETS.get(self.style_key, STYLE_PRESETS[DEFAULT_STYLE_KEY])


def sent_tokenizer(text):
    try:
        sentences = sent_tokenize(text)
    except LookupError:
        # Fall back to regex splitting if the NLTK punkt resource is unavailable.
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def get_tokens(sentences, group_size=2):
    grouped_sentences = []
    bucket = []

    for sentence in sentences:
        bucket.append(sentence.strip())
        if len(bucket) == group_size:
            grouped_sentences.append(" ".join(bucket))
            bucket = []

    if bucket:
        grouped_sentences.append(" ".join(bucket))

    return grouped_sentences


def _raw_content(response):
    content = response.content
    return content if isinstance(content, str) else str(content)


def _collect_story_descriptions(parsed_story):
    descriptions = []
    for field_name in ("c1", "c2", "c3", "c4", "c5"):
        value = getattr(parsed_story, field_name, None)
        if value:
            descriptions.append(value.strip())
    return descriptions


def _fallback_story_descriptions(text):
    # Models sometimes return bullets or loose prose instead of the requested
    # schema. This keeps the pipeline moving instead of failing hard.
    lines = []
    for line in text.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if cleaned:
            lines.append(cleaned)

    candidate_lines = [line for line in lines if len(line.split()) >= 4]
    if 3 <= len(candidate_lines) <= 5:
        return candidate_lines

    source_text = " ".join(candidate_lines) if candidate_lines else text
    sentences = sent_tokenizer(source_text)
    if len(sentences) > 5:
        sentences = get_tokens(sentences)[:5]
    return sentences


def create_storyboard_descriptions(story):
    formatted_prompt = storyboard_prompt.format(story=story)
    raw_response = llm_story.invoke(formatted_prompt)
    raw_text = _raw_content(raw_response)

    try:
        parsed_story = parser2.parse(raw_text)
        descriptions = _collect_story_descriptions(parsed_story)
    except OutputParserException:
        # If the JSON parser fails, salvage usable panel captions from the text.
        descriptions = _fallback_story_descriptions(raw_text)

    if not descriptions:
        descriptions = sent_tokenizer(story)

    return descriptions[:5]


def _has_memory(memory):
    return any(values for values in memory.values())


def _style_lock_text(style):
    return (
        f"Use this exact visual style in every panel: {style['prompt']}. "
        "Keep the same artistic medium, rendering approach, shading, and overall art direction throughout the storyboard. "
        "Do not switch to photorealistic, live-action, or any unrelated style."
    )


def _continuity_memory_for_prompt(state):
    if not _has_memory(state.memory):
        return None

    # Keep continuity cues from prior images, but do not feed back picture_style.
    # The user-selected style should stay fixed even if a previous render drifted.
    return {
        "environment": state.memory["environment"],
        "look": state.memory["look"],
        "miscellaneous": state.memory["miscellaneous"],
    }


def enhance_prompt(scene, state):
    style_lock = _style_lock_text(state.style)
    previous_memory = _continuity_memory_for_prompt(state) or "None yet"
    return f"""
Scene to illustrate:
{scene}

Style lock:
{style_lock}

Continuity guidance:
- Preserve the same main characters, wardrobe, props, and setting details across panels unless the story changes them.
- Compose this like a polished storyboard panel with a clear focal point and emotional storytelling.
- Use previous visual memory only for character, prop, and background continuity.
- Do not let previous renders change the selected art style.
- Previous visual memory: {previous_memory}
"""


def compress_prompt(prompt, style_lock, memory_context=None):
    if memory_context:
        user_message = (
            "Write a single concise image-generation prompt under 900 characters.\n\n"
            f"Style lock:\n{style_lock}\n\n"
            f"Scene brief:\n{prompt}\n\n"
            f"Previous panel memory:\n{memory_context}"
        )
    else:
        user_message = (
            "Write a single concise image-generation prompt under 900 characters.\n\n"
            f"Style lock:\n{style_lock}\n\n"
            f"Scene brief:\n{prompt}"
        )

    response = llm_compressed.invoke(
        [
            {
                "role": "system",
                "content": (
                    "You write rich, concise prompts for visual storyboard panels. "
                    "Preserve the supplied style lock exactly in the final prompt. "
                    "Never switch to photorealistic imagery unless the style lock explicitly says so. "
                    "Return only the final prompt text."
                ),
            },
            {"role": "user", "content": user_message},
        ]
    )
    return _raw_content(response)


def generate_image(prompt, filename):
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)

    result = openai_client.images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        size="1024x1024",
    )
    image_base64 = result.data[0].b64_json
    image_bytes = base64.b64decode(image_base64)

    with filename.open("wb") as file_obj:
        file_obj.write(image_bytes)

    return str(filename)


def encode_image(image_path):
    with open(image_path, "rb") as file_obj:
        return base64.b64encode(file_obj.read()).decode("utf-8")


def _memory_from_fallback_text(text):
    # Vision models often answer with bold markdown headings; map those sections
    # back into the strict Memory schema expected by the rest of the pipeline.
    sections = {
        "environment": "",
        "look": "",
        "picture_style": "",
        "miscellaneous": "",
    }

    content = text.strip()
    heading_matches = list(re.finditer(r"\*\*(.+?)\*\*[:]?", content))

    if heading_matches:
        for idx, match in enumerate(heading_matches):
            heading = match.group(1).strip().lower()
            start = match.end()
            end = heading_matches[idx + 1].start() if idx + 1 < len(heading_matches) else len(content)
            section_text = content[start:end].strip(" :\n-")

            if not section_text:
                continue

            if "environment" in heading or "setting" in heading:
                sections["environment"] = section_text
            elif "look" in heading or "person" in heading or "subject" in heading:
                sections["look"] = section_text
            elif "style" in heading or "palette" in heading:
                sections["picture_style"] = section_text
            elif "additional" in heading or "misc" in heading or "other" in heading:
                sections["miscellaneous"] = section_text
    else:
        sections["miscellaneous"] = content

    for key, value in sections.items():
        if not value:
            sections[key] = "Not clearly identified."

    return Memory(**sections)


def image_understanding(base64_image):
    formatted_prompt = prompt_memory.format()
    message = {
        "role": "user",
        "content": [
            {"type": "text", "text": formatted_prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{base64_image}"},
            },
        ],
    }

    raw_response = llm_visual.invoke([message])
    raw_text = _raw_content(raw_response)

    try:
        return memory_parser.parse(raw_text)
    except OutputParserException:
        return _memory_from_fallback_text(raw_text)


def _update_visual_memory(state):
    if not state.image_paths:
        return

    # Read the most recent panel back through the vision model so later panels
    # can inherit the same visual identity.
    memory_update = image_understanding(encode_image(state.image_paths[-1]))
    state.memory["environment"].append(memory_update.environment)
    state.memory["look"].append(memory_update.look)
    state.memory["picture_style"].append(memory_update.picture_style)
    state.memory["miscellaneous"].append(memory_update.miscellaneous)


def image_producer(scene, idx, state, output_dir):
    if idx > 1:
        _update_visual_memory(state)

    raw_prompt = enhance_prompt(scene, state)
    style_lock = _style_lock_text(state.style)
    memory_context = _continuity_memory_for_prompt(state)
    compressed_prompt = compress_prompt(raw_prompt, style_lock, memory_context)
    final_prompt = f"{style_lock}\n\n{compressed_prompt}"

    filename = Path(output_dir) / f"scene_{idx}.png"
    image_path = generate_image(final_prompt, filename)
    state.image_paths.append(image_path)

    panel = {
        "scene": scene,
        "prompt": final_prompt,
        "image": image_path,
    }
    state.generated_panels.append(panel)
    return panel


def generate_storyboard_stream(story, style_key, output_dir, storyboard_id):
    state = StoryboardState(style_key=style_key)
    descriptions = create_storyboard_descriptions(story)

    if not descriptions:
        raise ValueError("The storyboard could not be broken into visual panels.")

    # The frontend first receives the outline so it can render placeholders in
    # the final order before actual images begin streaming in.
    yield {
        "type": "outline",
        "count": len(descriptions),
        "captions": descriptions,
        "style_label": state.style["label"],
    }

    total = len(descriptions)
    for idx, scene in enumerate(descriptions, start=1):
        yield {
            "type": "status",
            "message": f"Rendering panel {idx} of {total}...",
            "index": idx,
            "count": total,
        }

        panel = image_producer(scene, idx, state, output_dir)
        yield {
            "type": "panel",
            "index": idx,
            "count": total,
            "caption": scene,
            "prompt": panel["prompt"],
            "image_url": f"/static/generated/{storyboard_id}/scene_{idx}.png",
            "style_label": state.style["label"],
        }

    yield {"type": "complete", "count": total, "style_label": state.style["label"]}
