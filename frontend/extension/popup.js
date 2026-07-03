import { VITE_API_URL, WEBSITE_URL } from './config.js';

document.addEventListener("DOMContentLoaded", async () => {
  const loggedOutState = document.getElementById("auth-state-logged-out");
  const loggedInState = document.getElementById("auth-state-logged-in");
  const btnLogin = document.getElementById("btn-login");
  const btnSave = document.getElementById("btn-save");
  const tabTitleEl = document.getElementById("tab-title");
  const tabUrlEl = document.getElementById("tab-url");
  const quoteCardContainer = document.getElementById("quote-card-container");
  const quoteTextEl = document.getElementById("quote-text");
  const btnClearQuote = document.getElementById("btn-clear-quote");
  const contextNoteInput = document.getElementById("context-note");
  const statusEl = document.getElementById("status-message");
  const tagsContainer = document.getElementById("tags-container");
  const suggestedTagsList = document.getElementById("suggested-tags-list");

  let currentTab = null;
  let jwtToken = null;
  let selectedText = "";
  let selectedTags = [];

  if (btnLogin) {
    btnLogin.addEventListener("click", () => {
      chrome.tabs.create({ url: `${WEBSITE_URL}/auth/telegram` });
    });
  }

  if (btnClearQuote) {
    btnClearQuote.addEventListener("click", () => {
      if (quoteCardContainer) {
        quoteCardContainer.classList.add("slingshot-out");
        setTimeout(() => {
          quoteCardContainer.classList.add("hidden");
          quoteCardContainer.classList.remove("slingshot-out");
          selectedText = "";
        }, 350);
      }
    });
  }

  if (btnSave) {
    btnSave.addEventListener("click", async () => {
      if (!jwtToken || !currentTab) return;
      
      btnSave.disabled = true;
      btnSave.innerHTML = '<span class="spinner"></span>Saving...';
      hideStatus();

      const payload = {
        type: "SAVE_CURRENT_TAB"
      };
      if (contextNoteInput && contextNoteInput.value.trim()) {
        payload.context_note = contextNoteInput.value.trim();
      }
      if (selectedText) {
        payload.quote = selectedText;
      }
      if (selectedTags && selectedTags.length > 0) {
        payload.tags = selectedTags;
      }

      chrome.runtime.sendMessage(payload, (response) => {
      if (chrome.runtime.lastError) {
        showError("Communication failed.");
        btnSave.disabled = false;
        btnSave.textContent = "Save to Recall";
        return;
      }

      if (response && response.success) {
        showSuccess("Saved ✓");
        btnSave.textContent = "Saved ✓";
        btnSave.classList.add("saved");
        btnSave.disabled = true;
        if (contextNoteInput) contextNoteInput.value = "";
        if (quoteCardContainer) quoteCardContainer.classList.add("hidden");
        setTimeout(() => {
          window.close();
        }, 1500);
      } else {
        const errMsg = (response && response.error) || "Failed to save.";
        showError(errMsg);
        btnSave.disabled = false;
        btnSave.textContent = "Save to Recall";
      }
    });
  });
}

  function xorCipher(text, key) {
    let result = "";
    for (let i = 0; i < text.length; i++) {
      const textChar = text.charCodeAt(i);
      const keyChar = key.charCodeAt(i % key.length);
      result += String.fromCharCode(textChar ^ keyChar);
    }
    return result;
  }

  function encryptToken(token, extensionId) {
    const encrypted = xorCipher(token, extensionId);
    return btoa(encrypted);
  }

  function decryptToken(encryptedBase64, extensionId) {
    try {
      const encrypted = atob(encryptedBase64);
      return xorCipher(encrypted, extensionId);
    } catch (e) {
      return null;
    }
  }

  async function checkAuthentication() {
    const extensionId = chrome.runtime.id;
    try {
      const data = await chrome.storage.local.get("jwt");
      if (data.jwt) {
        const decrypted = decryptToken(data.jwt, extensionId);
        if (decrypted) return decrypted;
      }
    } catch (err) {
      console.error("Local storage read failed:", err);
    }

    try {
      const cookie = await chrome.cookies.get({
        url: WEBSITE_URL,
        name: "jwt"
      });
      if (cookie && cookie.value) {
        const encrypted = encryptToken(cookie.value, extensionId);
        await chrome.storage.local.set({ jwt: encrypted });
        return cookie.value;
      }
    } catch (err) {
      console.error("Cookie detection failed:", err);
    }

    return null;
  }

  async function checkSelectedText(tabId) {
    if (!chrome.scripting) return;
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tabId, allFrames: true },
        func: () => window.getSelection().toString()
      });
      if (results && results.length > 0) {
        for (const res of results) {
          if (res && res.result && res.result.trim()) {
            selectedText = res.result.trim();
            break;
          }
        }
        if (selectedText && quoteTextEl && quoteCardContainer) {
          quoteTextEl.textContent = selectedText;
          quoteCardContainer.classList.remove("hidden");
        }
      }
    } catch (err) {
      console.warn("Could not retrieve selected text:", err);
    }
  }

  async function loadActiveTab() {
    try {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tabs && tabs.length > 0) {
        currentTab = tabs[0];
        tabTitleEl.textContent = currentTab.title || "Untitled Link";
        tabUrlEl.textContent = currentTab.url || "";
        
        // Check if page is already saved in Recall
        chrome.runtime.sendMessage({ type: "CHECK_CURRENT_TAB" }, (response) => {
          if (response && response.exists) {
            btnSave.textContent = "Saved ✓";
            btnSave.classList.add("saved");
            btnSave.disabled = true;
          }
        });

        await checkSelectedText(currentTab.id);
        await fetchSuggestedTags();
      } else {
        tabTitleEl.textContent = "No active tab";
        tabUrlEl.textContent = "";
        btnSave.disabled = true;
      }
    } catch (err) {
      console.error("Query active tab failed:", err);
      tabTitleEl.textContent = "Tab error";
      tabUrlEl.textContent = "";
      btnSave.disabled = true;
    }
  }

  async function fetchSuggestedTags() {
    if (!jwtToken || !currentTab) return;
    try {
      let url = `${VITE_API_URL}/api/extension/suggest_tags?url=${encodeURIComponent(currentTab.url)}&title=${encodeURIComponent(currentTab.title)}`;
      if (selectedText) {
        url += `&text=${encodeURIComponent(selectedText)}`;
      }
      const response = await fetch(url, {
        headers: {
          "Authorization": `Bearer ${jwtToken}`
        }
      });
      if (response.ok) {
        const tags = await response.json();
        renderSuggestedTags(tags);
      }
    } catch (err) {
      console.error("Failed to fetch suggested tags:", err);
    }
  }

  function renderSuggestedTags(tags) {
    if (!tags || tags.length === 0) {
      tagsContainer.classList.add("hidden");
      return;
    }
    suggestedTagsList.innerHTML = "";
    selectedTags = [];
    tags.forEach(tag => {
      const pill = document.createElement("span");
      pill.className = "tag-pill active";
      pill.textContent = `#${tag}`;
      selectedTags.push(tag);

      pill.addEventListener("click", () => {
        pill.classList.toggle("active");
        if (pill.classList.contains("active")) {
          if (!selectedTags.includes(tag)) {
            selectedTags.push(tag);
          }
        } else {
          selectedTags = selectedTags.filter(t => t !== tag);
        }
      });
      suggestedTagsList.appendChild(pill);
    });
    tagsContainer.classList.remove("hidden");
  }

  function showSuccess(msg) {
    statusEl.textContent = msg;
    statusEl.className = "status-message success";
  }

  function showError(msg) {
    statusEl.textContent = msg;
    statusEl.className = "status-message error";
  }

  function hideStatus() {
    statusEl.textContent = "";
    statusEl.className = "status-message hidden";
  }

  jwtToken = await checkAuthentication();
  if (jwtToken) {
    loggedOutState.classList.add("hidden");
    loggedInState.classList.remove("hidden");
    await loadActiveTab();
  } else {
    loggedInState.classList.add("hidden");
    loggedOutState.classList.remove("hidden");
  }
});
