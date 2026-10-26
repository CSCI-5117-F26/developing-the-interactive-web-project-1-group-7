// Mixtape editor (create, edit and remix): search Spotify without reloading the page, add songs to the mixtape, reorder them by dragging, and submit them with the form.
// Each selected song row holds hidden inputs (track_ids, annotations), so the order of rows on the page is the order the server saves.

const searchForm = document.getElementById("song-search");
const searchInput = document.getElementById("q");
const searchStatus = document.getElementById("search-status");
const searchResults = document.getElementById("search-results");
const selectedSongs = document.getElementById("selected-songs");
const noSongs = document.getElementById("no-songs");
const resultTemplate = document.getElementById("search-result-template");
const selectedTemplate = document.getElementById("selected-song-template");
const removeSongDialog = document.getElementById("remove-song");
const removeSongTitle = document.getElementById("remove-song-title");
const confirmRemoveSong = document.getElementById("confirm-remove-song");
let songToRemove = null;

const MAX_TRACKS = 50;

function formatDuration(ms) {
    if (!ms) return "";
    const totalSeconds = Math.floor(ms / 1000); 
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = String(totalSeconds % 60).padStart(2, "0");
    return `${minutes}:${seconds}`;
}

// Fill the shared song fields. textContent (not innerHTML) keeps song names from Spotify from being treated as HTML.
function fillSong(row, track) {
    const img = row.querySelector(".song-img");
    if (track.album_image_url) {
        img.src = track.album_image_url;
        img.alt = `${track.album || track.title} cover`;
    }
    row.querySelector(".song-title").textContent = track.title;
    row.querySelector(".song-artist").textContent = track.artist;
    row.querySelector(".song-album").textContent = track.album || "";
}

function selectedIds() {
    return Array.from(
        selectedSongs.querySelectorAll('input[name="track_ids"]'),
        (input) => input.value
    );
}

function refreshSelectedState() {
    const ids = selectedIds();
    noSongs.hidden = ids.length > 0;

    // Disable Add on results that are already in the mixtape
    searchResults.querySelectorAll(".add-song").forEach((button) => {
        const added = ids.includes(button.dataset.spotifyId);
        button.disabled = added || ids.length >= MAX_TRACKS;
        button.textContent = added ? "Added" : "Add";
    });
}

function addSong(track) {
    if (selectedIds().includes(track.spotify_id)) return;

    const row = selectedTemplate.content.firstElementChild.cloneNode(true);
    fillSong(row, track);
    row.querySelector('input[name="track_ids"]').value = track.spotify_id;
    row.querySelector(".song-duration").textContent = formatDuration(track.duration_ms);
    row.querySelector(".song-note-input").value = track.annotation || "";
    // row.querySelector(".remove-song").addEventListener("click", () => {
    //     row.remove();
    //     refreshSelectedState();
    // });

    // adding confirm modal
    row.querySelector(".remove-song").addEventListener("click", () => {
        songToRemove = row;
        removeSongTitle.textContent = track.title;
        removeSongDialog.showModal();
    });

    selectedSongs.appendChild(row);
    refreshSelectedState();
}

// if confirm
confirmRemoveSong.addEventListener("click", () => {
    songToRemove.remove();
    refreshSelectedState();
    removeSongDialog.close();
});

function showResults(tracks) {
    searchResults.replaceChildren();

    for (const track of tracks) {
        const row = resultTemplate.content.firstElementChild.cloneNode(true);
        fillSong(row, track);

        const button = row.querySelector(".add-song");
        button.dataset.spotifyId = track.spotify_id;
        button.addEventListener("click", () => addSong(track));

        searchResults.appendChild(row);
    }

    refreshSelectedState();
}

searchForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const query = searchInput.value.trim();
    if (!query) return;

    searchStatus.textContent = "Searching...";

    try {
        const response = await fetch(
            `${searchForm.action}?${new URLSearchParams({ q: query })}`
        );
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Search failed.");
        }

        showResults(data.tracks);
        searchStatus.textContent = data.tracks.length
            ? `Showing results for "${query}"`
            : `No songs found for "${query}"`;
    } catch (error) {
        searchResults.replaceChildren();
        searchStatus.textContent = error.message || "Search failed. Please try again.";
    }
});

// Enter in a note field shouldn't save the whole mixtape
selectedSongs.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.matches(".song-note-input")) {
        event.preventDefault();
    }
});

// Show the description and tags on the page as soon as they're chosen in the dialogs, before the mixtape is saved
const descriptionInput = document.querySelector('textarea[name="description"]');
const descriptionPreview = document.getElementById("description-preview");
const descriptionButtonLabel = document.getElementById("description-button-label");
const tagCheckboxes = document.querySelectorAll('input[name="tags"]');
const tagPreview = document.getElementById("tag-preview");
const tagButtonLabel = document.getElementById("tag-button-label");

const titleInput = document.querySelector('input[name="title"]');
const titlePreview = document.getElementById("title-preview");

function refreshTitlePreview() {
    const title = titleInput.value.trim();
    if (title) {
        titlePreview.textContent = title;
    } else {
        titlePreview.textContent = "Mixtape Title";
    }
}

function refreshDescriptionPreview() {
    const description = descriptionInput.value.trim();

    if (description) {
        descriptionPreview.textContent = description;
        descriptionPreview.style.color = "";
    } else {
        descriptionPreview.textContent = "No description yet";
        descriptionPreview.style.color = "#cccccc";
    }

    // changed the edit/add btn to just pencil icon
    // descriptionPreview.textContent = description;
    // descriptionPreview.hidden = !description;
    // descriptionButtonLabel.textContent = description ? "Edit Description" : "Add Description";
}

function refreshTagPreview() {
    tagPreview.replaceChildren();

    const checked = Array.from(tagCheckboxes).filter((box) => box.checked);
    for (const box of checked) {
        const chip = document.createElement("span");
        chip.className = `pure-button tag-${box.value}`;
        chip.textContent = box.value;

        const item = document.createElement("li");
        item.appendChild(chip);
        tagPreview.appendChild(item);
    }

    if (checked.length === 0) {
        tagPreview.textContent = "No tags yet";
        tagPreview.style.color = "#cccccc";
    } else {
        tagPreview.style.color = "";
    }

    // tagButtonLabel.textContent = checked.length ? "Edit tags" : "Add tag";
}

descriptionInput.addEventListener("input", refreshDescriptionPreview);
tagCheckboxes.forEach((box) => box.addEventListener("change", refreshTagPreview));
refreshDescriptionPreview();
refreshTagPreview();

titleInput.addEventListener("input", refreshTitlePreview);
refreshTitlePreview();

// When editing or remixing, start with the mixtape's existing songs and notes.
// Done before Sortable so the songs still show (and aren't lost on save) if the Sortable CDN fails to load.
JSON.parse(document.getElementById("initial-songs").textContent).forEach(addSong);
refreshSelectedState();

// Using Sortable's mouse/touch dragging instead of native HTML5 drag-and-drop, which behaves differently across browsers and doesn't work on phones
new Sortable(selectedSongs, {
    animation: 150,
    handle: ".drag-handle",
    forceFallback: true,
});
