import { describe, it, expect } from 'vitest';
import { add, subtract } from '../src/index.js';

describe('add', () => {
  it('adds two positive numbers', () => {
    expect(add(1, 2)).toBe(3);
  });

  it('handles negative numbers', () => {
    expect(add(-5, 3)).toBe(-2);
  });
});

describe('subtract', () => {
  it('subtracts', () => {
    expect(subtract(10, 4)).toBe(6);
  });
});
