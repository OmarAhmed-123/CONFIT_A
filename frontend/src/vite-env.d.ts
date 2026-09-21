/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly DEV: boolean;
  readonly PROD: boolean;
  readonly MODE: string;
  /**
   * Data-protection contact published on the legal pages. Optional by design:
   * an unset value makes the UI state that no mailbox is configured rather
   * than print an address nobody monitors.
   */
  readonly VITE_LEGAL_CONTACT_EMAIL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
