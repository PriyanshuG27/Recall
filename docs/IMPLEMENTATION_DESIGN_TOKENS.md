# Recall — Frontend Implementation Design Tokens

This document provides copy-pasteable CSS, Tailwind config, and JavaScript Canvas code snippets to implement the **Cosmic Noir (Cinema Mobile)** design system exactly as specified.

---

## 1. Tailwind CSS Configuration (`tailwind.config.js`)

Add these custom extend tokens to lock in the color system and easing curves:

```javascript
module.exports = {
  theme: {
    extend: {
      colors: {
        space: {
          deep: '#030307',
          base: '#07070F',
        },
        nebula: {
          surface: 'rgba(10, 10, 20, 0.65)',
          border: 'rgba(255, 255, 255, 0.08)',
        },
        galaxy: {
          violet: '#6C63FF',
          violetGlow: 'rgba(108, 99, 255, 0.15)',
          mint: '#00D4AA',
          mintGlow: 'rgba(0, 212, 170, 0.2)',
        },
        starlight: '#F1F1F6',
        stardust: '#8E8E9F',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        heading: ['Outfit', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      transitionTimingFunction: {
        'cinema-out': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
      animation: {
        'float-nebula-slow': 'floatNebula 25s ease-in-out infinite',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
      },
      keyframes: {
        floatNebula: {
          '0%, 100%': { transform: 'translate(0px, 0px) scale(1)' },
          '50%': { transform: 'translate(40px, -60px) scale(1.1)' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: 0.15 },
          '50%': { opacity: 0.35 },
        },
      },
    },
  },
}
```

---

## 2. Global CSS Custom Styles (`theme.css`)

Include these classes in your global styles to support animated background blobs and glassmorphic cards:

```css
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

body {
  background-color: #030307;
  color: #F1F1F6;
  font-family: 'Inter', sans-serif;
  overflow-x: hidden;
}

/* Floating Ambient Nebulae */
.nebula-blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  z-index: 0;
  pointer-events: none;
  mix-blend-mode: screen;
}

.nebula-violet {
  width: 450px;
  height: 450px;
  background: radial-gradient(circle, rgba(108, 99, 255, 0.08) 0%, rgba(0,0,0,0) 70%);
  top: 15%;
  left: 10%;
  animation: floatNebula 30s ease-in-out infinite;
}

.nebula-mint {
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(0, 212, 170, 0.06) 0%, rgba(0,0,0,0) 70%);
  bottom: 20%;
  right: 15%;
  animation: floatNebula 25s ease-in-out infinite alternate;
}

/* Glassmorphism Card Style */
.glass-card {
  background: rgba(10, 10, 20, 0.65);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
  transition: border-color 0.3s cubic-bezier(0.16, 1, 0.3, 1), transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.glass-card:hover {
  border-color: rgba(108, 99, 255, 0.25);
  transform: translateY(-2px);
}

/* Top-Edge Lightning Border (Linear highlight) */
.glass-glow-top {
  position: relative;
}
.glass-glow-top::before {
  content: "";
  position: absolute;
  top: 0;
  left: 16px;
  right: 16px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(108, 99, 255, 0.3), transparent);
}
```

---

## 3. Canvas Constellation Drawing Engine (`canvas.js`)

Draw frosted-glass nodes and glowing Bezier connections on the 2D canvas context:

```javascript
/**
 * Draws a glowing curved connection line between two nodes
 */
function drawConstellationEdge(ctx, x1, y1, x2, y2, isActive = false) {
  ctx.beginPath();
  
  // Calculate quadratic control point for a subtle curve
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;
  const controlX = midX + (y2 - y1) * 0.05; // Offset multiplier controls curve amount
  const controlY = midY - (x2 - x1) * 0.05;

  ctx.moveTo(x1, y1);
  ctx.quadraticCurveTo(controlX, controlY, x2, y2);
  
  if (isActive) {
    ctx.strokeStyle = 'rgba(0, 212, 170, 0.65)';
    ctx.lineWidth = 2;
    ctx.shadowBlur = 8;
    ctx.shadowColor = '#00D4AA';
  } else {
    ctx.strokeStyle = 'rgba(0, 212, 170, 0.15)';
    ctx.lineWidth = 1;
    ctx.shadowBlur = 0; // Clear shadow
  }
  ctx.stroke();
  ctx.shadowBlur = 0; // Reset
}

/**
 * Draws a frosted glass star node with connection-based star glow
 */
function drawFrostedNode(ctx, x, y, radius, label, degree = 1, isHovered = false) {
  // 1. Draw Star Glow (radial gradient behind node)
  const glowRadius = radius * (1.5 + (degree * 0.3));
  const radialGlow = ctx.createRadialGradient(x, y, radius * 0.2, x, y, glowRadius);
  radialGlow.addColorStop(0, isHovered ? 'rgba(108, 99, 255, 0.3)' : 'rgba(108, 99, 255, 0.15)');
  radialGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
  
  ctx.fillStyle = radialGlow;
  ctx.beginPath();
  ctx.arc(x, y, glowRadius, 0, Math.PI * 2);
  ctx.fill();

  // 2. Draw Frosted Glass Surface
  ctx.fillStyle = 'rgba(10, 10, 20, 0.8)';
  ctx.strokeStyle = isHovered ? 'rgba(108, 99, 255, 0.6)' : 'rgba(255, 255, 255, 0.12)';
  ctx.lineWidth = 1.5;
  ctx.shadowBlur = isHovered ? 12 : 0;
  ctx.shadowColor = '#6C63FF';

  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  
  // Reset shadow effects
  ctx.shadowBlur = 0;

  // 3. Draw Label
  ctx.font = '500 11px Inter';
  ctx.fillStyle = isHovered ? '#F1F1F6' : '#8E8E9F';
  ctx.textAlign = 'center';
  ctx.fillText(label, x, y + radius + 16);
}
```

---

## 4. React Native Haptic Scale Button (`HapticButton.js`)

A reusable button implementing scale press animation and haptic integration for the Telegram Mini App:

```jsx
import React from 'react';
import { Pressable, Animated } from 'react-native';
import * as Haptics from 'expo-haptics';

export const HapticButton = ({ children, onPress, style }) => {
  const scaleAnim = React.useRef(new Animated.Value(1)).current;

  const handlePressIn = () => {
    // 1. Play scale down animation (0.97)
    Animated.spring(scaleAnim, {
      toValue: 0.97,
      useNativeDriver: true,
      speed: 15,
      bounciness: 0,
    }).start();

    // 2. Trigger micro haptic click
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  };

  const handlePressOut = () => {
    // Return button back to full scale
    Animated.spring(scaleAnim, {
      toValue: 1,
      useNativeDriver: true,
      speed: 15,
      bounciness: 4,
    }).start();
  };

  return (
    <Pressable
      onPress={onPress}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
    >
      <Animated.View style={[{ transform: [{ scale: scaleAnim }] }, style]}>
        {children}
      </Animated.View>
    </Pressable>
  );
};
```
