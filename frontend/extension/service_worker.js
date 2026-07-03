import { VITE_API_URL } from './config.js';

function xorCipher(text, key) {
  let result = "";
  for (let i = 0; i < text.length; i++) {
    const textChar = text.charCodeAt(i);
    const keyChar = key.charCodeAt(i % key.length);
    result += String.fromCharCode(textChar ^ keyChar);
  }
  return result;
}

function decryptToken(encryptedBase64, extensionId) {
  try {
    const encrypted = atob(encryptedBase64);
    return xorCipher(encrypted, extensionId);
  } catch (e) {
    return null;
  }
}

function isTokenExpired(token) {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return true;
    const payloadJson = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(payloadJson);
    if (!payload.exp) return false;
    const now = Math.floor(Date.now() / 1000);
    return payload.exp < now;
  } catch (e) {
    return true;
  }
}

// Unified Save Execution Flow
async function executeSave(info, tab, contextNote = null, quote = null, tags = null) {
  const extensionId = chrome.runtime.id;
  const storageData = await chrome.storage.local.get(["jwt", "api_url", "notifications_enabled"]);
  
  if (!storageData.jwt) {
    showNotification("Error", "Please log in via the Recall extension first.", storageData.notifications_enabled);
    return { success: false, error: "Unauthenticated" };
  }

  const token = decryptToken(storageData.jwt, extensionId);
  if (!token || isTokenExpired(token)) {
    await chrome.storage.local.remove("jwt");
    showNotification("Session Expired", "Please log in again.", storageData.notifications_enabled);
    return { success: false, error: "Session Expired" };
  }

  let url = "";
  let text = "";
  let title = "";

  if (quote) {
    text = quote;
    title = tab ? tab.title : "Saved Webpage Clip";
    url = info.pageUrl || (tab ? tab.url : "");
  } else if (info.selectionText) {
    text = info.selectionText;
    title = tab ? `Selection from ${tab.title || "Webpage"}` : "Selected Text";
    url = tab ? tab.url : "";
  } else if (info.linkUrl) {
    url = info.linkUrl;
    title = "Saved Link";
  } else {
    url = info.pageUrl || (tab ? tab.url : "");
    title = tab ? tab.title : "Saved Webpage";
  }

  const currentApiUrl = storageData.api_url || VITE_API_URL;

  try {
    const response = await fetch(`${currentApiUrl}/api/extension/save`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: (() => {
        const payload = { url, text, title };
        if (contextNote !== null && contextNote !== undefined) {
          payload.context_note = contextNote;
        }
        if (tags !== null && tags !== undefined) {
          payload.tags = tags;
        }
        return JSON.stringify(payload);
      })()
    });

    if (response.ok) {
      chrome.action.setBadgeText({ text: "✓" });
      setTimeout(() => {
        chrome.action.setBadgeText({ text: "" });
      }, 3000);

      const notifTitle = response.status === 200 ? "Already saved" : "Saved to Recall";
      showNotification(notifTitle, title, storageData.notifications_enabled);
      return { success: true };
    } else {
      const errorData = await response.json().catch(() => ({}));
      const errMsg = errorData.detail || "Failed to save to Recall.";
      showNotification("Error Saving", errMsg, storageData.notifications_enabled);
      return { success: false, error: errMsg };
    }
  } catch (err) {
    showNotification("Error", "Recall server unreachable.", storageData.notifications_enabled);
    return { success: false, error: "Network Error" };
  }
}

// 1. Context Menu Registration
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "recall-save-link",
    title: "Save to Recall",
    contexts: ["link", "page", "selection"]
  });
});

// 2. Click Handler
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "recall-save-link") return;
  await executeSave(info, tab);
});

// 3. Keyboard Shortcut Command Listener
chrome.commands.onCommand.addListener(async (command) => {
  if (command === "save-current-page") {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs && tabs.length > 0) {
      await executeSave({ pageUrl: tabs[0].url }, tabs[0]);
    }
  }
});

async function executeCheck(url) {
  const extensionId = chrome.runtime.id;
  const storageData = await chrome.storage.local.get(["jwt", "api_url"]);
  
  if (!storageData.jwt) {
    return { exists: false };
  }

  const token = decryptToken(storageData.jwt, extensionId);
  if (!token || isTokenExpired(token)) {
    return { exists: false };
  }

  const currentApiUrl = storageData.api_url || VITE_API_URL;

  try {
    const response = await fetch(`${currentApiUrl}/api/extension/check?url=${encodeURIComponent(url)}`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });

    if (response.ok) {
      const data = await response.json();
      return { success: true, exists: data.exists };
    }
  } catch (err) {
    console.error("Check URL failed:", err);
  }
  return { exists: false };
}

// 4. Runtime Message Listener (Popup shared logic)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "SAVE_CURRENT_TAB") {
    chrome.tabs.query({ active: true, currentWindow: true }).then(async (tabs) => {
      if (tabs && tabs.length > 0) {
        const result = await executeSave(
          { pageUrl: tabs[0].url },
          tabs[0],
          message.context_note,
          message.quote,
          message.tags
        );
        sendResponse(result);
      } else {
        sendResponse({ success: false, error: "No active tab" });
      }
    });
    return true;
  }

  if (message.type === "CHECK_CURRENT_TAB") {
    chrome.tabs.query({ active: true, currentWindow: true }).then(async (tabs) => {
      if (tabs && tabs.length > 0) {
        const result = await executeCheck(tabs[0].url);
        sendResponse(result);
      } else {
        sendResponse({ exists: false });
      }
    });
    return true;
  }
});

function showNotification(title, message, enabledSetting) {
  if (enabledSetting === false) return;
  
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon48.png",
    title: title,
    message: message,
    priority: 2
  }, () => {
    if (chrome.runtime.lastError) {
      console.warn("Notification warning:", chrome.runtime.lastError.message);
    }
  });
}
