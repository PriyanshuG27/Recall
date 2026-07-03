import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import fs from 'fs';
import path from 'path';

function encryptToken(token, extensionId) {
  let result = "";
  for (let i = 0; i < token.length; i++) {
    const textChar = token.charCodeAt(i);
    const keyChar = extensionId.charCodeAt(i % extensionId.length);
    result += String.fromCharCode(textChar ^ keyChar);
  }
  return btoa(result);
}

// Setup Mock DOM structure
const htmlContent = `
  <div class="popup-container">
    <div id="auth-state-logged-out" class="state-container hidden">
      <p class="description">Save pages directly.</p>
      <button id="btn-login">Login with Telegram</button>
    </div>
    <div id="auth-state-logged-in" class="state-container hidden">
      <div class="page-info">
        <h4 id="tab-title">Loading...</h4>
        <p id="tab-url">Loading...</p>
      </div>
      <!-- Quote Card (Highlight Clip) -->
      <div id="quote-card-container" class="quote-card-container hidden">
        <div class="quote-header">
          <span class="label">Captured Quote</span>
          <button id="btn-clear-quote" class="clear-quote-btn" title="Clear Quote">×</button>
        </div>
        <p id="quote-text" class="quote-body"></p>
      </div>
      <!-- Custom Context Note Area -->
      <div class="context-container">
        <textarea id="context-note" placeholder="Write a context note..." rows="3"></textarea>
      </div>
      <button id="btn-save">Save to Recall</button>
      <div id="status-message" class="status-message hidden"></div>
    </div>
  </div>
`;

// Helper to run popup.js in tests
function executePopupScript() {
  const scriptPath = path.resolve(__dirname, '../../extension/popup.js');
  const rawCode = fs.readFileSync(scriptPath, 'utf-8');
  
  const executableCode = rawCode.replace(
    "import { VITE_API_URL, WEBSITE_URL } from './config.js';",
    "const VITE_API_URL = 'http://localhost:8000'; const WEBSITE_URL = 'http://localhost:5173';"
  );
  
  const run = new Function(executableCode);
  run();
}

describe('Chrome Extension Popup', () => {
  beforeEach(() => {
    document.body.innerHTML = htmlContent;

    global.chrome = {
      runtime: {
        id: "mock-extension-id",
        sendMessage: vi.fn((msg, cb) => { if (cb) cb({ success: true }); })
      },
      storage: {
        local: {
          get: vi.fn(),
          set: vi.fn()
        }
      },
      cookies: {
        get: vi.fn()
      },
      tabs: {
        query: vi.fn(),
        create: vi.fn()
      }
    };

    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders unauthenticated state when no token exists in storage or cookies', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    chrome.cookies.get.mockResolvedValue(null);

    executePopupScript();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    
    await new Promise(resolve => setTimeout(resolve, 10));

    const loggedOutEl = document.getElementById("auth-state-logged-out");
    const loggedInEl = document.getElementById("auth-state-logged-in");

    expect(loggedOutEl.classList.contains("hidden")).toBe(false);
    expect(loggedInEl.classList.contains("hidden")).toBe(true);

    const btnLogin = document.getElementById("btn-login");
    btnLogin.click();
    expect(chrome.tabs.create).toHaveBeenCalledWith({
      url: 'http://localhost:5173/auth/telegram'
    });
  });

  it('renders authenticated state using token from storage and loads active tab info', async () => {
    const encryptedToken = encryptToken('mock-local-token', 'mock-extension-id');
    chrome.storage.local.get.mockResolvedValue({ jwt: encryptedToken });
    chrome.tabs.query.mockResolvedValue([
      { url: 'https://example.com/page', title: 'Example Page' }
    ]);

    executePopupScript();
    document.dispatchEvent(new Event("DOMContentLoaded"));

    await new Promise(resolve => setTimeout(resolve, 10));

    const loggedOutEl = document.getElementById("auth-state-logged-out");
    const loggedInEl = document.getElementById("auth-state-logged-in");
    const tabTitleEl = document.getElementById("tab-title");
    const tabUrlEl = document.getElementById("tab-url");

    expect(loggedOutEl.classList.contains("hidden")).toBe(true);
    expect(loggedInEl.classList.contains("hidden")).toBe(false);
    expect(tabTitleEl.textContent).toBe('Example Page');
    expect(tabUrlEl.textContent).toBe('https://example.com/page');
  });

  it('syncs JWT from cookies if storage is empty, then renders authenticated state', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    chrome.cookies.get.mockResolvedValue({ value: 'mock-cookie-token' });
    chrome.tabs.query.mockResolvedValue([
      { url: 'https://example.com', title: 'Example' }
    ]);

    executePopupScript();
    document.dispatchEvent(new Event("DOMContentLoaded"));

    await new Promise(resolve => setTimeout(resolve, 10));

    const expectedEncrypted = encryptToken('mock-cookie-token', 'mock-extension-id');
    expect(chrome.storage.local.set).toHaveBeenCalledWith({ jwt: expectedEncrypted });
    expect(document.getElementById("auth-state-logged-in").classList.contains("hidden")).toBe(false);
  });

  it('handles successful save to Recall on Save button click via background message passing', async () => {
    const encryptedToken = encryptToken('mock-jwt-token', 'mock-extension-id');
    chrome.storage.local.get.mockResolvedValue({ jwt: encryptedToken });
    chrome.tabs.query.mockResolvedValue([
      { url: 'https://mysite.com', title: 'My Site' }
    ]);

    chrome.runtime.sendMessage.mockImplementation((message, callback) => {
      if (callback) callback({ success: true });
    });

    executePopupScript();
    document.dispatchEvent(new Event("DOMContentLoaded"));

    await new Promise(resolve => setTimeout(resolve, 10));

    const btnSave = document.getElementById("btn-save");
    btnSave.click();

    await new Promise(resolve => setTimeout(resolve, 10));

    expect(chrome.runtime.sendMessage).toHaveBeenCalledWith(
      { type: 'SAVE_CURRENT_TAB' },
      expect.any(Function)
    );

    const statusEl = document.getElementById("status-message");
    expect(statusEl.classList.contains("success")).toBe(true);
    expect(statusEl.textContent).toBe('Saved ✓');
  });

  it('displays error message on save API failure via background message passing', async () => {
    const encryptedToken = encryptToken('mock-jwt-token', 'mock-extension-id');
    chrome.storage.local.get.mockResolvedValue({ jwt: encryptedToken });
    chrome.tabs.query.mockResolvedValue([
      { url: 'https://mysite.com', title: 'My Site' }
    ]);

    chrome.runtime.sendMessage.mockImplementation((message, callback) => {
      if (callback) callback({ success: false, error: 'Invalid URL format' });
    });

    executePopupScript();
    document.dispatchEvent(new Event("DOMContentLoaded"));

    await new Promise(resolve => setTimeout(resolve, 10));

    const btnSave = document.getElementById("btn-save");
    btnSave.click();

    await new Promise(resolve => setTimeout(resolve, 10));

    expect(chrome.runtime.sendMessage).toHaveBeenCalledWith(
      { type: 'SAVE_CURRENT_TAB' },
      expect.any(Function)
    );

    const statusEl = document.getElementById("status-message");
    expect(statusEl.classList.contains("error")).toBe(true);
    expect(statusEl.textContent).toBe('Invalid URL format');
  });
});
