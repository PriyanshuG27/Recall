# Manual Verification Test Suite — Recall New Features

This document provides step-by-step manual verification procedures to validate all newly implemented features via the UI, Telegram, and Mobile OS interfaces without using scripts.

---

## 🧪 Test Case 1: 2D Map Canvas Visual Upgrades

### Objective:
Verify flowing light particles along connection edges and active orbiting micro-particles around hot/warning nodes on the 2D Map.

### Steps:
1. Open the Web Dashboard in your browser and click on the **Map** tab (`/map`).
2. Observe the connection lines connecting memory nodes:
   - **Expected**: Glowing light particles flow continuously along active edges at 60 FPS. The movement speed scales with the connection weight.
3. Click or hover over any node (or find a node with an urgent/decaying SM-2 review interval):
   - **Expected**: 2 to 3 micro-particles circle smoothly around the node in an active orbit, with orbital speed and opacity reflecting the temperature of the node.

---

## 🧪 Test Case 2: Interactive RAG Citations & Map Focus

### Objective:
Verify that clicking a citation badge in the AI Assistant automatically navigates to the Map, centers the target node, lights up its edges, and triggers a pulsing gold flare ring.

### Steps:
1. Click the **Assistant** icon in the top header or press `Cmd+K` / click Assistant to open `ChatDrawer.jsx`.
2. Ask any question about your saved knowledge (e.g., *"What did I save about Stoicism?"*) and press Enter.
3. Once the assistant responds with cited source badges (e.g., `[1]`, `[2]`), click on **`[1]`**.
4. **Expected**:
   - The application automatically switches to the **Map** view.
   - The camera transform centers on the cited node at zoom $k = 1.35$.
   - The cited node is selected, its connecting edge lines brighten, and a pulsing gold flare ring animates around it for 3 seconds.

---

## 🧪 Test Case 3: Telegram Friend Fast-Track (`/match`)

### Objective:
Verify the 5-question thought-compatibility flow natively inside Telegram.

### Steps:
1. Open Telegram and navigate to your chat with `@RecallBot`.
2. Send the `/match` command.
   - **Expected**: The bot replies with an invite message containing your unique referral link: `https://t.me/RecallBot?start=match_{your_user_id}`.
3. Tap the link (or forward it to a friend / test account to tap).
   - **Expected**: The bot opens and sends Question 1/5 of the **Friend Fast-Track** game with 4 inline keyboard buttons.
4. Answer Questions 1 through 5 by tapping an inline button for each step.
   - **Expected**: The message updates sequentially in-place with the next question.
5. After answering Question 5:
   - **Expected**: The bot displays the final result:
     > 🎉 **Friend Fast-Track Completed!**  
     > 🧠 **Thought-Compatibility Match: 88%**  
     > *Your memory graphs are now connected! View your shared hubs on the Web Dashboard Bridges page.*

---

## 🧪 Test Case 4: Native PWA Web Share Target

### Objective:
Verify that sharing a link from an external app natively to the installed PWA ingests the item into Recall.

### Steps:
1. Open Recall in Chrome / Safari on your mobile phone or desktop.
2. Click the browser address bar icon or menu $\rightarrow$ **Install app** / **Add to Home screen** to install Recall as a PWA.
3. Open any external browser tab or mobile app (e.g. YouTube, Wikipedia, Twitter).
4. Tap **Share** $\rightarrow$ select **Recall** from your phone/OS native Share Sheet.
5. **Expected**:
   - Recall opens and displays a green toast banner:  
     `"Shared content ingested into your memory graph! 🧠"`
   - The shared link appears instantly as a new item in your **Archive** and node on your **Map**.

---

## 🧪 Test Case 5: Floating PWA Install Banner

### Objective:
Verify the dark-mode PWA install banner floating card at the bottom of the dashboard.

### Steps:
1. Open Recall in a standard browser window (not in standalone PWA mode).
2. Look at the bottom-center of the viewport.
   - **Expected**: A dark glassmorphic banner appears with:
     - App icon box with gold `R` logo.
     - Title `"Install Recall"` and domain caption (`recall.onrender.com`).
     - Neon lime green **Install** text link and soft gray **Close** text link.
3. Click **Close**:
   - **Expected**: The banner smoothly animates down and dismisses for the active session (`sessionStorage`).
4. Re-open in a fresh tab and click **Install**:
   - **Expected**: The native browser installation dialog opens.
