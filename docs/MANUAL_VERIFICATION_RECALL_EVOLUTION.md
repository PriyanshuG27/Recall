# Manual Verification Guide — Recall Evolution & 2D Map Features

This document provides step-by-step manual verification instructions specifically for the 4 newly delivered features:

---

## 🧪 Feature 1: 2D Map Canvas Visual Upgrades

### Objective:
Verify 60 FPS flowing light particles along active edge connections and orbiting micro-particles around hot/warning nodes directly on the 2D Map Canvas.

### Steps to Test:
1. Open the Web Dashboard in your browser and click on the **Map** tab (`/map`).
2. **Observe Connection Lines**:
   - Check the lines connecting memory nodes. You will see small glowing light particles flowing along active edge paths.
   - Nodes with stronger connection weights will have faster particle flow.
3. **Observe Hot / Hovered / Warning Nodes**:
   - Hover your mouse over any node, select a node, or find a node with an upcoming SM-2 review state.
   - You will see 2 to 3 micro-particles orbiting around the node circle at radius $1.7\times - 2.2\times$, with orbital speed and glowing opacity reflecting the node's review urgency.

---

## 🧪 Feature 2: Interactive RAG Citations (Chat Drawer $\rightarrow$ 2D Map)

### Objective:
Verify that clicking a numbered citation badge (`[1]`, `[2]`) in the AI Assistant automatically navigates to the Map, centers the cited node, highlights its connection lines, and triggers a pulsing gold flare ring.

### Steps to Test:
1. Click the **Assistant** icon in the top header or press `Cmd+K` / click Assistant to open `ChatDrawer.jsx`.
2. Ask any question about your saved knowledge (e.g., *"What did I save about Stoicism?"* or *"Summarize my AI notes"*).
3. Once the assistant responds with numbered citation badges (e.g. `[1]`, `[2]`), click directly on badge **`[1]`**.
4. **Expected Behavior**:
   - The dashboard automatically switches to the **Map** room (`/map`).
   - The camera transform smoothly pans and zooms to center the cited node at scale $k = 1.35$.
   - The cited node is selected, its connecting edge lines brighten, and a pulsing gold flare ring animates around it for 3 seconds.

---

## 🧪 Feature 3: Telegram Friend Fast-Track (`/match`)

### Objective:
Verify the `/match` command referral link generator and the 5-question thought-compatibility game in Telegram.

### Steps to Test:
1. Open Telegram and open your chat with `@RecallBot`.
2. Send the `/match` command.
   - **Expected Result**: The bot replies with a message containing your unique referral link: `https://t.me/RecallBot?start=match_{your_user_id}`.
3. Click the referral link (or open it from another Telegram account).
   - **Expected Result**: The bot opens and delivers Question 1/5 of the **Friend Fast-Track** game with 4 inline keyboard buttons:
     - *Deep technical docs 📖*
     - *Hands-on projects 🛠️*
     - *Video tutorials 🎬*
     - *Conversational AI 💬*
4. Tap options sequentially for Questions 1 through 5.
   - **Expected Result**: The message updates in-place for each question. After Question 5, the bot calculates your tag synergy score, creates a bridge in the `bridges` table, and sends:
     > 🎉 **Friend Fast-Track Completed!**  
     > 🧠 **Thought-Compatibility Match: 88%**  
     > *Your memory graphs are now connected! View your shared hubs on the Web Dashboard Bridges page.*

---

## 🧪 Feature 4: Mobile Share Sheet Specs & PWA Install Banner

### Objective:
Verify the floating PWA Install Banner card on desktop and the mobile share configuration.

### Steps to Test (PWA Install Banner):
1. Open Recall in a standard desktop browser tab (not standalone mode).
2. Look at the bottom-center of the screen.
   - **Expected Result**: A floating dark glassmorphic banner appears with:
     - Square icon container with gold `R` logo.
     - Header `"Install Recall"` and subtitle `recall.onrender.com`.
     - Glowing neon green **Install** text button and soft gray **Close** text button.
3. Click **Close**:
   - The banner smoothly animates down and dismisses for your session.

### Specs & iOS/Android Configurations:
* View the full mobile configuration guide in [docs/MOBILE_SHARE_SHEET.md](file:///d:/Recall/docs/MOBILE_SHARE_SHEET.md).
