import { describe, it, expect } from 'vitest';
import { getInterpretiveText } from '../pages/Bridges';

describe('Bridges Observatory - getInterpretiveText helper', () => {
  it('should return correct message for low overlap scores (< 15)', () => {
    expect(getInterpretiveText(0)).toBe('Parallel thinkers. Rare overlap, distinct lenses.');
    expect(getInterpretiveText(5)).toBe('Parallel thinkers. Rare overlap, distinct lenses.');
    expect(getInterpretiveText(14.9)).toBe('Parallel thinkers. Rare overlap, distinct lenses.');
  });

  it('should return correct message for intersecting pathway scores (15 to 35)', () => {
    expect(getInterpretiveText(15)).toBe('Intersecting pathways. Emerging alignment, diverse backgrounds.');
    expect(getInterpretiveText(25)).toBe('Intersecting pathways. Emerging alignment, diverse backgrounds.');
    expect(getInterpretiveText(34.9)).toBe('Intersecting pathways. Emerging alignment, diverse backgrounds.');
  });

  it('should return correct message for resonant minds scores (35 to 55)', () => {
    expect(getInterpretiveText(35)).toBe('Resonant minds. Shared frequencies, complementary insights.');
    expect(getInterpretiveText(45)).toBe('Resonant minds. Shared frequencies, complementary insights.');
    expect(getInterpretiveText(54.9)).toBe('Resonant minds. Shared frequencies, complementary insights.');
  });

  it('should return correct message for deep cognitive synergy scores (55 to 75)', () => {
    expect(getInterpretiveText(55)).toBe('Deep cognitive synergy. High coherence, shared intellectual foundation.');
    expect(getInterpretiveText(65)).toBe('Deep cognitive synergy. High coherence, shared intellectual foundation.');
    expect(getInterpretiveText(74.9)).toBe('Deep cognitive synergy. High coherence, shared intellectual foundation.');
  });

  it('should return correct message for consonant consciousness scores (>= 75)', () => {
    expect(getInterpretiveText(75)).toBe('Consonant consciousness. Identical wavelengths, unified conceptual map.');
    expect(getInterpretiveText(99.9)).toBe('Consonant consciousness. Identical wavelengths, unified conceptual map.');
  });

  it('should default to low score message if score is null or undefined', () => {
    expect(getInterpretiveText(null)).toBe('Parallel thinkers. Rare overlap, distinct lenses.');
    expect(getInterpretiveText(undefined)).toBe('Parallel thinkers. Rare overlap, distinct lenses.');
  });
});
