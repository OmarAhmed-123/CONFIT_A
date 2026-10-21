import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HonestProductImage } from '../HonestProductImage';

/**
 * A product card must never show a silently broken image.
 *
 * Context (measured on the live store, 2026-10-20): every card's registry hero
 * URL answered 404, so all 14 image slots on the home page were empty boxes.
 * The component's job is to make that state *visible and honest* rather than an
 * `alt` fragment the shopper has to interpret — it must never substitute a
 * different product's photograph to look complete.
 */
describe('HonestProductImage', () => {
  it('renders the image when a source is present', () => {
    render(<HonestProductImage src="/api/v1/media/products/1/1-4x5.jpg" alt="Navy blazer" />);
    const img = screen.getByRole('img', { name: 'Navy blazer' });
    expect(img.tagName).toBe('IMG');
    expect(img).toHaveAttribute('src', '/api/v1/media/products/1/1-4x5.jpg');
  });

  it('shows an explicit, labelled fallback when the image fails to load', () => {
    render(<HonestProductImage src="/api/v1/media/products/1/1-4x5.jpg" alt="Navy blazer" />);
    fireEvent.error(screen.getByRole('img', { name: 'Navy blazer' }));

    const fallback = screen.getByRole('img', { name: /Navy blazer — Image unavailable/ });
    expect(fallback.tagName).not.toBe('IMG');
    expect(fallback).toHaveTextContent('Image unavailable');
    // not a silent empty box: the state is announced to assistive tech too
    expect(fallback).toHaveAttribute('aria-label');
  });

  it('shows the fallback when there is no source at all', () => {
    render(<HonestProductImage src={null} alt="Silk dress" />);
    expect(screen.getByText('Image unavailable')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'Silk dress' })).toBeNull();
  });

  it('never invents a substitute photograph on failure', () => {
    const onErrorSpy = vi.fn();
    render(<HonestProductImage src="/api/v1/media/products/1/1-4x5.jpg" alt="Wool coat" />);
    fireEvent.error(screen.getByRole('img', { name: 'Wool coat' }));
    // The fallback is a <div>, so no <img> remains to carry a fake src.
    expect(document.querySelectorAll('img').length).toBe(0);
    expect(onErrorSpy).not.toHaveBeenCalled();
  });

  it('recovers when a new source arrives after a failure', () => {
    const { rerender } = render(<HonestProductImage src="/broken.jpg" alt="Cardigan" />);
    fireEvent.error(screen.getByRole('img', { name: 'Cardigan' }));
    expect(screen.getByText('Image unavailable')).toBeInTheDocument();

    rerender(<HonestProductImage src="/api/v1/media/products/2/2-4x5.jpg" alt="Cardigan" />);
    const img = screen.getByRole('img', { name: 'Cardigan' });
    expect(img.tagName).toBe('IMG');
    expect(img).toHaveAttribute('src', '/api/v1/media/products/2/2-4x5.jpg');
  });
});
