// Username page: check the format and whether the name is free while typing, show a live preview, and only enable the button when both checks pass. The server checks again when the form is sent.

const usernameInput = document.getElementById("username");
const formatCheck = document.getElementById("check-format");
const availableCheck = document.getElementById("check-available");
const preview = document.getElementById("username-preview");
const submitButton = document.getElementById("username-submit");

const USERNAME_PATTERN = /^[A-Za-z0-9_]{3,20}$/;
let checkTimer = null;
let latestCheck = 0;

// state is "pass", "fail" or "pending"
function setCheck(item, state) {
    item.className = state;
    const icon = item.querySelector("i");
    icon.className = {
        pass: "fa-solid fa-circle-check",
        fail: "fa-solid fa-circle-xmark",
        pending: "fa-solid fa-circle",
    }[state];
}

async function checkAvailability(username) {
    const checkId = ++latestCheck;
    try {
        const url = `${usernameInput.dataset.checkUrl}?${new URLSearchParams({ username })}`;
        const response = await fetch(url);
        const data = await response.json();
        // Ignore answers that arrive after the user has typed something newer
        if (checkId !== latestCheck) return;
        setCheck(availableCheck, data.available ? "pass" : "fail");
        submitButton.disabled = !data.available;
    } catch {
        // If the check can't run, let the server decide on submit
        if (checkId === latestCheck) {
            setCheck(availableCheck, "pending");
            submitButton.disabled = false;
        }
    }
}

function refresh() {
    const username = usernameInput.value.trim();
    preview.textContent = username || "username";

    const validFormat = USERNAME_PATTERN.test(username);
    setCheck(formatCheck, username ? (validFormat ? "pass" : "fail") : "pending");

    clearTimeout(checkTimer);
    if (!validFormat) {
        latestCheck++;
        setCheck(availableCheck, "pending");
        submitButton.disabled = true;
        return;
    }

    // Your own current name (edit profile) is always fine
    if (username.toLowerCase() === usernameInput.dataset.current.toLowerCase()) {
        latestCheck++;
        setCheck(availableCheck, "pass");
        submitButton.disabled = false;
        return;
    }

    setCheck(availableCheck, "pending");
    submitButton.disabled = true;
    checkTimer = setTimeout(() => checkAvailability(username), 300);
}

usernameInput.addEventListener("input", refresh);
refresh();
