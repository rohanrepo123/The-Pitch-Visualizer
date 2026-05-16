import json
from pathlib import Path
from uuid import uuid4

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from storyboard_service import DEFAULT_STYLE_KEY, STYLE_PRESETS, generate_storyboard_stream


BASE_DIR = Path(__file__).resolve().parent
STATIC_GENERATED_DIR = BASE_DIR / "static" / "generated"


def _json_line(payload):
    # The frontend reads one JSON object per line while the request is still open.
    return json.dumps(payload) + "\n"


def create_app():
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            styles=STYLE_PRESETS,
            default_style=DEFAULT_STYLE_KEY,
        )

    @app.post("/generate")
    def generate():
        payload = request.get_json(silent=True) or {}
        story = (payload.get("story") or "").strip()
        style_key = payload.get("style") or DEFAULT_STYLE_KEY

        if not story:
            return jsonify({"error": "Please paste a story before generating the storyboard."}), 400

        if style_key not in STYLE_PRESETS:
            return jsonify({"error": "The selected visual style is not available."}), 400

        storyboard_id = uuid4().hex
        output_dir = STATIC_GENERATED_DIR / storyboard_id

        def event_stream():
            # Send an immediate event so the browser can swap into "working" state
            # before the first panel is finished.
            yield _json_line(
                {
                    "type": "start",
                    "storyboard_id": storyboard_id,
                    "style_label": STYLE_PRESETS[style_key]["label"],
                }
            )

            try:
                for event in generate_storyboard_stream(
                    story=story,
                    style_key=style_key,
                    output_dir=output_dir,
                    storyboard_id=storyboard_id,
                ):
                    yield _json_line(event)
            except Exception as exc:
                yield _json_line({"type": "error", "message": str(exc)})

        return Response(
            stream_with_context(event_stream()),
            # NDJSON keeps the transport simple while still letting the UI update
            # panel-by-panel as each image arrives.
            mimetype="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
