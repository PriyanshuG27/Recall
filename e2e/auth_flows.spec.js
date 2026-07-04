import { test, expect } from '@playwright/test';

test.describe('Authentication & Session Persistence', () => {
  test.beforeEach(async ({ context }) => {
    // Clear all cookies and storage before each test
    await context.clearCookies();
  });

  test('TWA automatic auth transitions to 3D Observatory', async ({ page }) => {
    // Navigate with simulated initData hash
    await page.goto('/#tgWebAppStartParam=test_session');
    
    // Expect the navigation structure to be visible depending on viewport
    const isMobile = page.viewportSize().width <= 768;
    if (isMobile) {
      await expect(page.locator('.mobile-bottom-nav')).toBeVisible();
    } else {
      await expect(page.locator('.sidebar-rail')).toBeVisible();
    }
    await expect(page).toHaveURL(/.*archive/);
  });

  test('Telegram Widget Login (Desktop Web via Dev Bypass)', async ({ page }) => {
    // Navigate to login page
    await page.goto('/login');
    
    // Fill the dev bypass input field
    await page.locator('.bypass-input').fill('987654');
    
    // Click the bypass go button
    await page.locator('.bypass-btn').click();
    
    // Expect redirection to archive
    const isMobile = page.viewportSize().width <= 768;
    if (isMobile) {
      await expect(page.locator('.mobile-bottom-nav')).toBeVisible();
    } else {
      await expect(page.locator('.sidebar-rail')).toBeVisible();
    }
    await expect(page).toHaveURL(/.*archive/);
  });

  test('Expired JWT redirects to login and clears cookie', async ({ page, context }) => {
    // Seed an expired cookie
    await context.addCookies([
      {
        name: 'recall_session',
        value: 'expired_token',
        domain: 'localhost',
        path: '/',
        expires: Date.now() / 1000 - 3600
      },
      {
        name: 'jwt',
        value: 'expired_token',
        domain: 'localhost',
        path: '/',
        expires: Date.now() / 1000 - 3600
      }
    ]);

    // Attempt to navigate to a protected route
    await page.goto('/map');
    
    // Should be redirected to the login page due to expired cookie
    await expect(page).toHaveURL(/.*login/);
    
    // Verify cookie was cleared by checking context cookies
    const cookies = await context.cookies();
    const sessionCookie = cookies.find(c => c.name === 'recall_session' || c.name === 'jwt');
    expect(sessionCookie).toBeUndefined();
  });

  test('User Logout clears session and local state', async ({ page, context }) => {
    // Log in using the bypass
    await page.goto('/login');
    await page.locator('.bypass-input').fill('123456');
    await page.locator('.bypass-btn').click();
    
    const isMobile = page.viewportSize().width <= 768;
    if (isMobile) {
      await expect(page.locator('.mobile-bottom-nav')).toBeVisible();
    } else {
      await expect(page.locator('.sidebar-rail')).toBeVisible();
    }

    // Verify session storage or local storage can be written to
    await page.evaluate(() => {
      localStorage.setItem('test_persistence_key', 'should_be_cleared');
      sessionStorage.setItem('test_session_key', 'should_be_cleared');
    });

    if (isMobile) {
      // On mobile viewports, settings and logout are triggered via bottom nav settings tab
      await page.locator('.mobile-nav-item:has-text("Settings")').click();
      await page.locator('button:has-text("Sign Out Session")').click();
    } else {
      // Open profile dropdown avatar
      await page.locator('#sidebar-avatar').click();
      // Click sign out button
      await page.locator('.sidebar-dropdown-item.logout').click();
    }

    // Expect redirect back to login
    await expect(page).toHaveURL(/.*login/);

    // Verify localStorage & sessionStorage custom keys are completely cleared
    const testPersistenceCleared = await page.evaluate(() => localStorage.getItem('test_persistence_key') === null);
    const testSessionCleared = await page.evaluate(() => sessionStorage.getItem('test_session_key') === null);
    expect(testPersistenceCleared).toBe(true);
    expect(testSessionCleared).toBe(true);

    // Verify session cookies are deleted
    const cookies = await context.cookies();
    const hasRecallSession = cookies.some(c => c.name === 'recall_session' || c.name === 'jwt');
    expect(hasRecallSession).toBe(false);
  });
});
