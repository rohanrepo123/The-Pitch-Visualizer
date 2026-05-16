const form = document.getElementById("story-form");
const storyInput = document.getElementById("story-input");
const storyboardGrid = document.getElementById("storyboard-grid");
const statusText = document.getElementById("status-text");
const progressPill = document.getElementById("progress-pill");
const generateButton = document.getElementById("generate-button");

let activeController = null;
// Each placeholder slot is kept in panel order so streamed updates can replace
// the right card even though generation takes time.
let placeholderCards = [];

function setBusy(isBusy) {
    generateButton.disabled = isBusy;
    generateButton.textContent = isBusy ? "Generating..." : "Generate Storyboard";
}

function setEmptyState() {
    storyboardGrid.innerHTML = `
        <div class="empty-state">
            Your storyboard panels will appear here one by one as the images finish rendering.
        </div>
    `;
    placeholderCards = [];
}

function clearBoard() {
    storyboardGrid.innerHTML = "";
    placeholderCards = [];
}

function createPanelCard(index, caption) {
    const card = document.createElement("article");
    card.className = "panel-card is-loading is-visible";
    card.innerHTML = `
        <div class="panel-media"></div>
        <div class="panel-content">
            <div class="panel-meta">
                <span class="panel-index">${index}</span>
                <span class="panel-status">Queued</span>
            </div>
            <p class="panel-caption"></p>
        </div>
    `;

    card.querySelector(".panel-caption").textContent = caption;
    return card;
}

function createOutline(captions) {
    clearBoard();
    placeholderCards = captions.map((caption, index) => {
        const card = createPanelCard(index + 1, caption);
        storyboardGrid.appendChild(card);
        return card;
    });
}

function updatePlaceholderStatus(index, text) {
    const card = placeholderCards[index - 1];
    if (!card) {
        return;
    }

    const status = card.querySelector(".panel-status");
    if (status) {
        status.textContent = text;
    }
}

function revealPanel(event) {
    const card = placeholderCards[event.index - 1] || createPanelCard(event.index, event.caption);

    if (!card.isConnected) {
        storyboardGrid.appendChild(card);
        placeholderCards[event.index - 1] = card;
    }

    const media = card.querySelector(".panel-media");
    const caption = card.querySelector(".panel-caption");
    const status = card.querySelector(".panel-status");

    caption.textContent = event.caption;
    status.textContent = "Ready";
    card.classList.remove("is-loading");

    const image = document.createElement("img");
    // Cache-bust each panel image because the file is written during the same
    // browser session that requests it.
    image.src = `${event.image_url}?t=${Date.now()}`;
    image.alt = event.caption;
    image.loading = "lazy";

    media.replaceChildren(image);
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function handleStreamEvent(event) {
    switch (event.type) {
        case "start":
            statusText.textContent = `Planning your storyboard in ${event.style_label}...`;
            progressPill.textContent = "Starting";
            break;
        case "outline":
            createOutline(event.captions);
            statusText.textContent = `Mapped ${event.count} storyboard panels. Rendering begins now.`;
            progressPill.textContent = `${event.count} panels`;
            break;
        case "status":
            statusText.textContent = event.message;
            progressPill.textContent = `${event.index}/${event.count}`;
            updatePlaceholderStatus(event.index, "Rendering...");
            break;
        case "panel":
            revealPanel(event);
            progressPill.textContent = `${event.index}/${event.count} ready`;
            break;
        case "complete":
            statusText.textContent = `Storyboard ready in ${event.style_label}.`;
            progressPill.textContent = "Done";
            break;
        case "error":
            throw new Error(event.message || "Something went wrong while generating the storyboard.");
        default:
            break;
    }
}

async function streamStoryboard(payload, signal) {
    const response = await fetch("/generate", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
        signal,
    });

    if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload.error || "Storyboard generation failed.");
    }

    if (!response.body) {
        throw new Error("Streaming is not available in this browser.");
    }

    // The backend streams newline-delimited JSON, so we decode chunks and only
    // parse complete lines.
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { value, done } = await reader.read();
        if (done) {
            break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
            if (!line.trim()) {
                continue;
            }
            handleStreamEvent(JSON.parse(line));
        }
    }

    if (buffer.trim()) {
        handleStreamEvent(JSON.parse(buffer));
    }
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const story = storyInput.value.trim();
    const style = form.elements.style.value;

    if (!story) {
        statusText.textContent = "Please paste a story before generating the storyboard.";
        progressPill.textContent = "Waiting";
        storyInput.focus();
        return;
    }

    if (activeController) {
        // Starting a new run should stop the previous fetch so the UI never
        // mixes panels from two different stories.
        activeController.abort();
    }

    activeController = new AbortController();
    clearBoard();
    setBusy(true);
    statusText.textContent = "Sending your story to the generator...";
    progressPill.textContent = "Working";

    try {
        await streamStoryboard({ story, style }, activeController.signal);
    } catch (error) {
        if (error.name === "AbortError") {
            statusText.textContent = "The previous generation was cancelled.";
            progressPill.textContent = "Stopped";
        } else {
            statusText.textContent = error.message;
            progressPill.textContent = "Error";
            if (!storyboardGrid.children.length) {
                setEmptyState();
            }
        }
    } finally {
        setBusy(false);
        activeController = null;
    }
});

setEmptyState();
