import { describe, it, expect, vi, beforeEach } from 'vitest';
import client, { setUnauthorizedHandler, setToastHandler } from '../api/client';

describe('API Client Interceptors', () => {
  beforeEach(() => {
    setUnauthorizedHandler(null);
    setToastHandler(null);
  });

  it('passes through successful responses', async () => {
    const res = { status: 200, data: { ok: true } };
    const interceptor = client.interceptors.response.handlers[0].fulfilled;
    expect(interceptor(res)).toEqual(res);
  });

  it('handles network error (no response)', async () => {
    const toastSpy = vi.fn();
    setToastHandler(toastSpy);
    const interceptor = client.interceptors.response.handlers[0].rejected;

    const err = {};
    await expect(interceptor(err)).rejects.toEqual({
      userMessage: 'Connection lost — check your internet'
    });
    expect(toastSpy).toHaveBeenCalledWith('Connection lost — check your internet', 'error');
  });

  it('handles 401 unauthorized response', async () => {
    const unauthSpy = vi.fn();
    setUnauthorizedHandler(unauthSpy);

    const interceptor = client.interceptors.response.handlers[0].rejected;
    const err = { response: { status: 401, data: {} }, config: { url: '/api/items' } };

    await expect(interceptor(err)).rejects.toEqual({
      ...err,
      userMessage: 'Session expired — please log in again'
    });
    expect(unauthSpy).toHaveBeenCalled();
  });

  it('handles status code errors 400, 403, 404, 429 with/without retry, 503, default', async () => {
    const toastSpy = vi.fn();
    setToastHandler(toastSpy);
    const interceptor = client.interceptors.response.handlers[0].rejected;

    const err429 = { response: { status: 429, data: { retry_after: 5 } }, config: { url: '/api/items' } };
    await expect(interceptor(err429)).rejects.toBeDefined();
    expect(toastSpy).toHaveBeenCalledWith('Too many requests — please retry in 5s.', 'warning');

    toastSpy.mockClear();
    const err429NoRetry = { response: { status: 429, data: {} }, config: { url: '/api/items' } };
    await expect(interceptor(err429NoRetry)).rejects.toBeDefined();
    expect(toastSpy).toHaveBeenCalledWith('Too many requests — please wait', 'warning');

    toastSpy.mockClear();
    const err503 = { response: { status: 503, data: {} }, config: { url: '/api/items' } };
    await expect(interceptor(err503)).rejects.toBeDefined();
    expect(toastSpy).toHaveBeenCalledWith('Server unavailable — retrying in 30 s', 'error');

    // 400, 403, 404, 500
    const otherStatuses = [400, 403, 404, 500];
    for (const st of otherStatuses) {
      const errOther = { response: { status: st, data: {} }, config: { url: '/api/items' } };
      await expect(interceptor(errOther)).rejects.toBeDefined();
    }
  });
});
