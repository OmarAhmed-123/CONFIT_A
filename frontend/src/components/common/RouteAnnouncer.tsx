import React, { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

/**
 * Single non-spammy SPA route announcer for assistive technologies
 * (`Orca`, `NVDA`, `JAWS`, `VoiceOver`, `TalkBack`).
 *
 * Silent on initial load so screen readers announce the document title
 * naturally without double speech, then announces genuine client-side route
 * changes after `document.title` updates.
 */
export const RouteAnnouncer: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const prevPathRef = useRef<string | null>(null);
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    if (prevPathRef.current === null) {
      prevPathRef.current = location.pathname;
      return;
    }
    if (prevPathRef.current === location.pathname) {
      return;
    }
    prevPathRef.current = location.pathname;

    const timer = window.setTimeout(() => {
      const heading =
        document.querySelector("main h1")?.textContent?.trim() ||
        document.title ||
        location.pathname;
      setAnnouncement(t("a11y.route_changed", { title: heading }));
    }, 80);

    return () => window.clearTimeout(timer);
  }, [location.pathname, t]);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-testid="spa-route-announcer"
      className="sr-only"
    >
      {announcement}
    </div>
  );
};
