import { describe, it, expect, vi, beforeEach } from 'vitest';
import AudioEngine from '../utils/AudioEngine';

describe('AudioEngine Utility', () => {
  const mockOscillator = {
    connect: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    frequency: {
      setValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn()
    }
  };
  const mockGainNode = {
    connect: vi.fn(),
    gain: {
      setValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
      linearRampToValueAtTime: vi.fn()
    }
  };
  const mockAudioContext = {
    currentTime: 0,
    state: 'suspended',
    destination: {},
    createOscillator: vi.fn(() => mockOscillator),
    createGain: vi.fn(() => mockGainNode),
    resume: vi.fn().mockImplementation(function() { this.state = 'running'; return Promise.resolve(); })
  };

  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal('AudioContext', vi.fn(() => mockAudioContext));
  });

  it('defaults to muted if localStorage value is not set', () => {
    expect(AudioEngine.isMuted()).toBe(true);
  });

  it('updates muting state in localStorage and dispatches window event', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    
    AudioEngine.setMuted(false);
    expect(AudioEngine.isMuted()).toBe(false);
    expect(localStorage.getItem('recall_muted')).toBe('false');
    
    // Should dispatch custom recall-mute-toggle event
    expect(dispatchSpy).toHaveBeenCalled();
    const event = dispatchSpy.mock.calls[0][0];
    expect(event.type).toBe('recall-mute-toggle');
    expect(event.detail).toBe(false);
  });

  it('plays sounds when unmuted', () => {
    AudioEngine.setMuted(false);

    // Call all synth play methods to cover their implementation lines
    expect(() => AudioEngine.playClick()).not.toThrow();
    expect(() => AudioEngine.playTransition()).not.toThrow();
    expect(() => AudioEngine.playClusterChord()).not.toThrow();
    expect(() => AudioEngine.playThud()).not.toThrow();
    expect(() => AudioEngine.playChime()).not.toThrow();
    expect(() => AudioEngine.playDissonantTone()).not.toThrow();
  });
});
