import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import React, { useState } from 'react';
import { useModalFocus } from '../useModalFocus';

const Harness: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const ref = useModalFocus<HTMLDivElement>(onClose);
  return (
    <div ref={ref} role="dialog" aria-modal="true" tabIndex={-1}>
      <button>first</button>
      <input aria-label="middle" />
      <button>last</button>
    </div>
  );
};

describe('P1-05: useModalFocus — modal keyboard/focus contract', () => {
  it('focuses the first focusable element on open', () => {
    const { getByText } = render(<Harness onClose={() => {}} />);
    expect(document.activeElement).toBe(getByText('first'));
  });

  it('wraps Tab from last to first and shift+Tab from first to last (trap)', () => {
    const { getByText } = render(<Harness onClose={() => {}} />);
    // jsdom does not move focus on Tab; place focus on last, then Tab -> wraps to first
    (getByText('last') as HTMLElement).focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(getByText('first'));
    // shift+Tab from first -> wraps to last
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(getByText('last'));
  });

  it('closes on Escape when this modal owns focus', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('ignores Escape when a stacked modal owns focus', () => {
    const onClose = vi.fn();
    const { getByLabelText } = render(
      <div>
        <button>outside</button>
        <Harness onClose={onClose} />
      </div>
    );
    // focus the outer button — as if another layer is on top
    const outside = document.querySelector('button');
    (outside as HTMLElement).focus();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('unmounts on close and restores focus to the opener', () => {
    function Wrapper() {
      const [open, setOpen] = useState(false);
      return (
        <div>
          <button onClick={() => setOpen(true)}>opener</button>
          {open && <Harness onClose={() => setOpen(false)} />}
        </div>
      );
    }
    const { getByText } = render(<Wrapper />);
    getByText('opener').focus(); // opener focused before open
    fireEvent.click(getByText('opener')); // open modal -> focus moves to 'first'
    expect(document.activeElement).toBe(getByText('first'));
    fireEvent.keyDown(document, { key: 'Escape' }); // close
    expect(document.querySelector('[role=dialog]')).toBeNull();
    expect(document.activeElement?.textContent).toBe('opener');
  });
});
