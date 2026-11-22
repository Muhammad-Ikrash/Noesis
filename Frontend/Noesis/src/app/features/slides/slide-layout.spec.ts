import { DEFAULT_DESIGN, designVars, effectiveAccent, slideDensity } from './slide-design';
import { fitSlide } from './slides-viewer-page';

const words = (n: number) => 'word '.repeat(n).trim();

describe('slideDensity', () => {
  it('uses large type for a few short bullets', () => {
    expect(slideDensity({ title: 'Glycolysis', bullets: ['Splits glucose', 'Makes 2 ATP'] })).toBe('sparse');
  });

  it('is normal for a typical slide', () => {
    expect(slideDensity({ title: 'Krebs cycle', bullets: Array(4).fill(words(12)) })).toBe('normal');
  });

  it('gets smaller as text grows', () => {
    expect(slideDensity({ title: 'Long', bullets: Array(6).fill(words(15)) })).toBe('dense');
    expect(slideDensity({ title: 'Longer', bullets: Array(9).fill(words(15)) })).toBe('tight');
  });

  it('ignores blank bullets and counts very long titles', () => {
    expect(slideDensity({ title: 'T', bullets: ['a', ' ', '', 'b'] })).toBe('sparse');
    const longTitle = 'x'.repeat(300);
    expect(slideDensity({ title: longTitle, bullets: ['short'] })).not.toBe('sparse');
  });
});

describe('designVars', () => {
  it('leaves colours to the app theme in auto mode', () => {
    const vars = designVars(DEFAULT_DESIGN);
    expect(vars['--s-bg']).toBeUndefined();
    expect(vars['--s-head']).toBe('var(--font-read)');
  });

  it('applies a theme and a custom accent', () => {
    const vars = designVars({ ...DEFAULT_DESIGN, theme: 'midnight', accent: '#ff0000', body_font: 'mono' });
    expect(vars['--s-bg']).toBe('#0f172a');
    expect(vars['--s-accent']).toBe('#ff0000');
    expect(vars['--s-body']).toBe('var(--font-mono)');
    expect(effectiveAccent({ ...DEFAULT_DESIGN, theme: 'slate' })).toBe('#2563eb');
  });
});

describe('fitSlide', () => {
  /** jsdom has no layout, so fake one: content height shrinks with the --fit scale. */
  function fakeSlide(contentAtFullSize: number, boxHeight = 100): HTMLElement {
    const slide = document.createElement('section');
    Object.defineProperty(slide, 'clientHeight', { get: () => boxHeight });
    Object.defineProperty(slide, 'scrollHeight', {
      get: () => Math.max(boxHeight, contentAtFullSize * Number(slide.style.getPropertyValue('--fit') || 1)),
    });
    return slide;
  }

  it('keeps full size when the content fits', () => {
    const slide = fakeSlide(90);
    expect(fitSlide(slide)).toBe(1);
    expect(slide.style.getPropertyValue('--fit')).toBe('1');
  });

  it('shrinks in steps until the content fits', () => {
    expect(fitSlide(fakeSlide(120))).toBe(0.8); // 120 × 0.8 = 96 ≤ 100
  });

  it('stops at the minimum scale', () => {
    expect(fitSlide(fakeSlide(500))).toBe(0.6);
  });

  it('starts again from full size each time', () => {
    const slide = fakeSlide(120);
    slide.style.setProperty('--fit', '0.6');
    expect(fitSlide(slide)).toBe(0.8);
  });
});
