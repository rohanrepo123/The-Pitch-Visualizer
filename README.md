# The Pitch Visualizer: From Words to Storyboard

## Overview
This project turns a short story or pitch into a visual storyboard using a Flask web app and OpenAI models.

The user pastes story text into the browser, selects a visual style, and clicks **Generate Storyboard**. The app then:

- breaks the story into 3 to 5 visual panels
- creates an image prompt for each panel
- generates the images one by one
- streams the storyboard to the UI as each panel finishes
- saves the generated images under `static/generated/<storyboard_id>/`

## Capabilities
- Flask-based web interface for story input and storyboard generation
- User-selectable visual styles
- Progressive panel-by-panel rendering in the browser
- Story segmentation into a coherent storyboard sequence
- Image continuity support across panels using visual memory
- Style locking so the chosen art direction is reused across all panels

## Project Structure
```text
Darwix Project/
|-- app.py
|-- project.py
|-- storyboard_service.py
|-- functions.py
|-- modules.py
|-- pydantic_obj.py
|-- requirement.txt
|-- templates/
|   `-- index.html
`-- static/
    |-- app.js
    |-- styles.css
    `-- generated/
```

## Requirements
- Python 3.11 recommended
- An OpenAI API key
- Internet access for model and image generation requests

## Setup

### 1. Open the project folder
```powershell
cd "D:\Study_IIITN\CampusX\GenAI\Darwix Project"
```

### 2. Create and activate a virtual environment
If you already have `venv311`, you can reuse it.

```powershell
python -m venv venv311
.\venv311\Scripts\activate
```

### 3. Install dependencies
The project currently includes a dependency file named `requirement.txt`.

```powershell
pip install -r requirement.txt
```

If you want only the main runtime packages, these are the important ones used directly by the app:

```powershell
pip install Flask openai python-dotenv nltk langchain langchain-openai langchain-core pydantic
```

### 4. Add your OpenAI API key
This project loads environment variables automatically using `python-dotenv`.

Create a file named `.env` in the project root:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

Important notes:

- do not commit `.env` to version control
- keep the API key private
- the application will fail to generate text or images if `OPENAI_API_KEY` is missing

Alternative PowerShell-only setup for the current terminal session:

```powershell
$env:OPENAI_API_KEY="your_openai_api_key_here"
```

## Running the App
For seeing image of outputs refer to -> "https://drive.google.com/drive/folders/1lfH6NvCW-N2ElTW8Z2QJ1jBef4LDsrC8?usp=sharing"
Start the Flask server with:

```powershell
python project.py
```

Then open:

[http://127.0.0.1:5000](http://127.0.0.1:5000)

## How to Use
1. Paste your story or pitch into the text area.
2. Select a visual style.
3. Click **Generate Storyboard**.
4. Watch the panels appear one by one.
5. Review the generated images saved under `static/generated/`.

## Execution Flow
At a high level, the application works like this:

1. The browser sends the story and selected style to the `/generate` route in `app.py`.
2. `storyboard_service.py` converts the story into structured storyboard descriptions.
3. Each panel prompt is enhanced with the chosen style and continuity instructions.
4. The image is generated and saved locally.
5. The backend streams newline-delimited JSON to the frontend so each completed panel appears immediately.

## Design Choices

### Flask for a simple interactive workflow
Flask was chosen because the project only needs a lightweight backend:

- render one HTML page
- accept story-generation requests
- stream results back to the browser

This keeps the app simple and easy to run for a demo or assignment.

### Streaming UI instead of waiting for the full storyboard
Image generation can take time, so the frontend does not wait for every panel to finish.

Instead, the backend streams NDJSON events and the browser updates the page incrementally. This improves perceived responsiveness and makes the storyboard feel dynamic.

### Structured parsing for reliability
The project uses Pydantic-based parsers for two places:

- turning the story into 3 to 5 storyboard panels
- extracting memory fields from previously generated images

This was done to make downstream logic more predictable than relying on loose plain-text responses.

### Fallback parsing when models return prose
Model outputs are not always perfectly structured. Because of that, the code includes fallback logic that attempts to recover usable panel descriptions or memory even if a model returns prose instead of the requested JSON.

This improves robustness and avoids hard failures in the middle of generation.

## Prompt Engineering Methodology

### 1. Story-to-panel decomposition
The first prompt does not generate images directly. It first converts the full story into a small storyboard outline.

Goal:

- cover the beginning, middle, and end
- keep the number of panels manageable
- preserve recurring characters and locations

This creates more coherent visual sequencing than sending the full story directly to the image model.

### 2. Scene prompt enhancement
For each panel, the app builds a richer prompt containing:

- the panel scene description
- the selected visual style
- continuity instructions
- memory from previous panels

This helps the image model produce a scene that is not only visually rich, but also consistent with the rest of the storyboard.

### 3. Prompt compression
The app uses a separate model pass to compress verbose scene instructions into a tighter image-generation prompt.

Reason:

- image prompts work better when they are focused
- smaller prompts are easier to control
- it helps keep the strongest visual details while reducing noise

### 4. Visual memory for continuity
After a panel is generated, the app sends that image back through a vision model to extract:

- environment details
- subject appearance
- style and rendering clues
- miscellaneous continuity hints

Those details are then reused for later panels so the storyboard feels like one connected sequence instead of unrelated images.

### 5. Style locking
One important design choice is the **style lock** added in the current version.

Problem solved:

- earlier generations could drift into a more realistic look even when the selected style was more illustrative

Current approach:

- the chosen style is injected into every panel prompt
- the compressor is told to preserve that style exactly
- previous panel memory is used for continuity, but not allowed to override the selected art direction

This keeps the visual style more stable from panel 1 through the final panel.

## Output
Generated images are stored inside:

```text
static/generated/<storyboard_id>/
```

Each run receives a unique folder, for example:

```text
static/generated/162cad60e5b645d98f628d332ebed2d8/scene_1.png
```

## Notes
- `project.py` is the main entrypoint and starts the Flask app.
- `storyboard_service.py` contains the current storyboard generation pipeline.
- `functions.py` is a legacy helper module from the older script-based flow and is kept mainly for reference/backward compatibility.
- If NLTK sentence resources are unavailable, the app falls back to regex-based sentence splitting.

## Troubleshooting

### Missing API key
If generation fails immediately, check that `.env` exists and contains:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

### Flask not found
Install dependencies again:

```powershell
pip install -r requirement.txt
```

### Style drift between panels
The current pipeline includes a style-lock mechanism, but if style drift still appears:

- regenerate the storyboard
- choose a style preset with a stronger visual identity
- inspect the final prompt logged in the backend pipeline if you are debugging prompt behavior

## Future Improvements
- export the full storyboard as PDF or presentation slides
- allow users to edit panel captions before generation
- add downloadable prompt/debug metadata in the UI
- support custom user-entered style descriptions in addition to presets
