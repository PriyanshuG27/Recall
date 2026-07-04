/**
 * PerformanceMonitor.js
 * =====================
 * Custom lightweight client-side Core Web Vitals monitor.
 * Measures FCP, LCP, CLS, and INP locally using native PerformanceObservers.
 * Prints values to the developer console to track p75 metrics during local runs.
 */

export function initPerformanceMonitor() {
  if (typeof window === 'undefined') return;

  console.log('⚡ Recall Performance Monitor Initialized.');

  // 1. First Contentful Paint (FCP)
  try {
    const fcpObserver = new PerformanceObserver((entryList) => {
      for (const entry of entryList.getEntries()) {
        if (entry.name === 'first-contentful-paint') {
          const value = entry.startTime;
          // Target: FCP <= 1800ms for green/good
          const status = value <= 1800 ? '🟢 GOOD' : value <= 3000 ? '🟡 NEEDS IMPROVEMENT' : '🔴 POOR';
          console.info(`%c[Perf] FCP (First Contentful Paint): ${value.toFixed(1)}ms [${status}]`, 'color: #CFA365');
        }
      }
    });
    fcpObserver.observe({ type: 'paint', buffered: true });
  } catch (e) {
    console.debug('[Perf] FCP Observer not supported.', e);
  }

  // 2. Largest Contentful Paint (LCP)
  try {
    let lcpValue = 0;
    const lcpObserver = new PerformanceObserver((entryList) => {
      const entries = entryList.getEntries();
      const lastEntry = entries[entries.length - 1];
      lcpValue = lastEntry.startTime;
      // Target: LCP <= 2500ms for green/good
      const status = lcpValue <= 2500 ? '🟢 GOOD' : lcpValue <= 4000 ? '🟡 NEEDS IMPROVEMENT' : '🔴 POOR';
      console.info(`%c[Perf] LCP (Largest Contentful Paint): ${lcpValue.toFixed(1)}ms [${status}]`, 'color: #CFA365');
    });
    lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });
  } catch (e) {
    console.debug('[Perf] LCP Observer not supported.', e);
  }

  // 3. Cumulative Layout Shift (CLS)
  try {
    let clsValue = 0;
    const clsObserver = new PerformanceObserver((entryList) => {
      for (const entry of entryList.getEntries()) {
        if (!entry.hadRecentInput) {
          clsValue += entry.value;
          // Target: CLS <= 0.1 for green/good
          const status = clsValue <= 0.1 ? '🟢 GOOD' : clsValue <= 0.25 ? '🟡 NEEDS IMPROVEMENT' : '🔴 POOR';
          console.info(`%c[Perf] CLS (Cumulative Layout Shift) Current: ${clsValue.toFixed(4)} [${status}]`, 'color: #CFA365');
        }
      }
    });
    clsObserver.observe({ type: 'layout-shift', buffered: true });
  } catch (e) {
    console.debug('[Perf] CLS Observer not supported.', e);
  }

  // 4. Interaction to Next Paint (INP) / First Input Delay (FID)
  try {
    const inpObserver = new PerformanceObserver((entryList) => {
      for (const entry of entryList.getEntries()) {
        const value = entry.duration;
        // Target: INP <= 200ms for green/good
        const status = value <= 200 ? '🟢 GOOD' : value <= 500 ? '🟡 NEEDS IMPROVEMENT' : '🔴 POOR';
        console.info(`%c[Perf] INP (Interaction delay for ${entry.name}): ${value.toFixed(1)}ms [${status}]`, 'color: #CFA365');
      }
    });
    // Monitor both first input and subsequent keyboard/click event durations
    inpObserver.observe({ type: 'first-input', buffered: true });
    inpObserver.observe({ type: 'event', buffered: true });
  } catch (e) {
    console.debug('[Perf] INP Observer not supported.', e);
  }
}
