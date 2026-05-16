from pydantic_obj import *
from openai import OpenAI
from nltk.tokenize import sent_tokenize
import re
from langchain_core.exceptions import OutputParserException

# Legacy helper module retained for the older script-driven flow.

# This prompt is used only when we inspect a previously generated panel and ask
# the vision model to summarize the visual details we should preserve next time.
prompt_memory = PromptTemplate(
    template="""Analyze this image and extract the visual details needed to keep future story images consistent.

Return only valid JSON that matches this schema:
{instruction}""",
    input_variables=[],
    partial_variables={"instruction": memory_parser.get_format_instructions()},
)
# The old pipeline stores continuity hints in plain lists and keeps appending
# what it learns from each generated image.
memory = {'environment':[],'look':[],'picture_style':[],'miscellaneous':[]}

# Model roles in the legacy pipeline:
# - llm_compressed trims prompts to a size that works well for image generation
# - llm1 reads rendered images back as vision input
# - llm is the text model originally used for story-to-scene expansion
llm_compressed = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7, max_tokens=600)
llm1 = ChatOpenAI(model="gpt-4o", temperature=0.7, max_tokens=1500)
llm = ChatOpenAI(model="gpt-4", temperature=0)


from modules import *

def sent_tokenizer(text):
    # Keep the original helper name so older callers do not need to change.
    return sent_tokenize(text)

def get_tokens(sent):
    # Group sentences in pairs so a long story becomes a smaller number of
    # broader visual beats before image generation starts.
    new_sent = []
    j =2
    sent_nn = ""
    for i in sent: 
        if j>0:
            sent_nn += i +" "
            j-=1
        if j==0:
            new_sent.append(sent_nn)
            sent_nn =""
            j=2
    if sent_nn:
        new_sent.append(sent_nn.strip())
    new_sent
    return new_sent

character_memory = ""
style_memory = " highly detailed"

# These globals mirror the older script design where one run mutates shared
# module state while generating a sequence of images.
generated_images = []
image_url = []
def enhance_prompt(scene):
    # Combine the current scene, any fixed character/style hints, and memory
    # captured from prior images into one prompt for the image model.
    return f"""
    {scene},
    character: {character_memory},
    style: {style_memory},
    memory details of previous image: {memory if memory else 'None'}
    same person, same face, same clothes, consistent identity,
    sharp focus, high quality
    """

def compress_prompt(prompt,memory,idx):
    # The first panel only needs the current scene. Later panels also receive
    # summarized memory so the model can keep visual continuity across images.
    if idx ==1:
        response = llm_compressed.invoke([
        {"role": "system", "content": "Shorten this to under 900 characters while keeping strong visual details."},
        {"role": "user", "content": prompt}
    ])
    else:
        response = llm_compressed.invoke([
        {"role": "system", "content": "Shorten this to under 900 characters , you are image descriptor for generating images from story."},
        {"role": "user", "content": f"These are the previous informations of images which you have to use to maintaining consistency of the current image from the previoss image knowledge create a new propmt by using {prompt} and {memory} to create the current image description so that it looks like story telling"}
    ])
    return response.content

def generate_image(prompt, filename):
    # The image API returns base64, so this helper is responsible for decoding
    # the bytes, writing the local file, and remembering where it was saved.
    result = OpenAI().images.generate(
        model="gpt-image-1.5",   # NEW model for image generation
        prompt=prompt,
        size="1024x1024"
    )
    image_base64 = result.data[0].b64_json
    image_bytes = base64.b64decode(image_base64)

    # Save locally
    with open(filename, "wb") as f:
        f.write(image_bytes)
    image_url.append(filename)
    return filename

# ── 5. Helper: encode image ────────────────────────────────────────────────────
def encode_image(image_path: str) -> str:
    # Vision requests need the previous panel in base64 form, not as a file path.
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# # ── 6. Run ─────────────────────────────────────────────────────────────────────
# if __name__ == "__main__":
#     b64_image = encode_image("scene_1.png")
#     memory_obj = image_understanding(b64_image)

#     print("🌍 Environment :", memory_obj.environment)
#     print("👤 Look        :", memory_obj.look)
#     print("🎨 Style       :", memory_obj.picture_style)
#     print("📝 Misc        :", memory_obj.miscellaneous)


#############################
def _memory_from_fallback_text(text: str) -> Memory:
    """Best-effort recovery when the model replies with prose instead of JSON."""
    # If parsing fails, map section-like prose back into the strict Memory
    # schema so downstream code can continue using the same interface.
    sections = {
        "environment": "",
        "look": "",
        "picture_style": "",
        "miscellaneous": "",
    }

    content = text.strip()
    # The fallback expects markdown-style headings such as **Environment**.
    heading_matches = list(re.finditer(r"\*\*(.+?)\*\*:?","" if not content else content))

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

    for key in sections:
        if not sections[key]:
            sections[key] = "Not clearly identified."

    return Memory(**sections)


def image_understanding(base64_image: str) -> Memory:
    """
    Accepts a base64-encoded image string.
    Returns a Memory pydantic object.
    """
    # Render the parser instructions into the prompt before sending the request.
    formatted_prompt = prompt_memory.format()             # ✅ fills {instruction}

    # Build the message manually because the vision call needs mixed text/image content.
    message = {
        "role": "user",
        "content": [
            {"type": "text", "text": formatted_prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64_image}"
                }
            }
        ]
    }
    # Vision input is sent directly to the model rather than through the older
    # text-only LangChain chain pattern.
    raw_response = llm1.invoke([message])                 # returns AIMessage

    # Try strict parsing first and recover gracefully if the model answers in prose.
    raw_content = raw_response.content
    if not isinstance(raw_content, str):
        raw_content = str(raw_content)

    try:
        return memory_parser.parse(raw_content)           # returns Memory object
    except OutputParserException:
        return _memory_from_fallback_text(raw_content)

#######################
def image_producer(scene, idx):
    # End-to-end legacy flow for one panel:
    # 1. Build a prompt for the current scene
    # 2. If this is not the first panel, inspect the previous image and update memory
    # 3. Generate the new image
    # 4. Save panel metadata for later inspection

    # Step 1: Create prompt
    raw_prompt = enhance_prompt(scene)
    if idx == 1:
        # The first panel has no previous image, so it can be compressed using
        # only the current scene description.
        final_prompt = compress_prompt(raw_prompt,None,idx)
    else:
        # Later panels reuse the most recently generated image as the source of
        # continuity memory. That lets the next prompt inherit setting, look,
        # and style from what was actually rendered, not only from the text.
        b64_image = encode_image(image_url[-1])
        memory_update = image_understanding(b64_image)
        memory['environment'].append(memory_update.environment)
        memory['look'].append(memory_update.look)
        memory['picture_style'].append(memory_update.picture_style)
        memory['miscellaneous'].append(memory_update.miscellaneous)
        final_prompt = compress_prompt(raw_prompt, memory, idx)


    # Step 3: Generate image
    filename = f"scene_{idx}.png"
    image_path = generate_image(final_prompt, filename)

    # Step 4: Store both the scene caption and the final prompt so the caller
    # can inspect what text actually produced the image.
    generated_images.append({
        "scene": scene,
        "prompt": final_prompt,
        "image": image_path
    })

    return image_path, generated_images
