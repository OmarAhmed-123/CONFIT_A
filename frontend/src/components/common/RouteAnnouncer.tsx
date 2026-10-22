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
  const prevPathnameRef = useRef<string | null>(null);
  const formatRouteChanged = (heading: string) => t("a11y.route_changed", { title: heading });
  const formatAnnouncementRef = useRef(formatRouteChanged);
  formatAnnouncementRef.current = formatRouteChanged;
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    if (prevPathnameRef.current === null) {
      prevPathnameRef.current = location.pathname;
      return;
    }
    if (prevPathnameRef.current === location.pathname) {
      return;
    }
    prevPathnameRef.current = location.pathname;
    // Clear first so consecutive announcements with similar fallback titles
    // always trigger a single polite DOM text mutation in AT live regions.
    setAnnouncement("");

    const timer = window.setTimeout(() => {
      const heading =
        document.querySelector("main h1")?.textContent?.trim() ||
        document.title ||
        location.pathname;
      setAnnouncement(formatAnnouncementRef.current(heading));
    }, 80);

    return () => window.clearTimeout(timer);
  }, [location.pathname]);

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
